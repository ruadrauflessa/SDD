#Requires -Version 7.0
<#
.SYNOPSIS
    Snapshot and restore per-repo working state around a team-branch sync.

.DESCRIPTION
    Phase 2 / Phase 5 of the sync-team-branches skill.

    Save    — for each named repo: record the current branch and HEAD, and if the working tree is
              dirty, stash it (including untracked files) and record the stash's COMMIT SHA.
              Writes a manifest so the snapshot survives a crashed or abandoned session.
    Restore — for each manifest entry: return to the recorded branch/HEAD, re-apply the stash by
              SHA, and drop it only after the apply succeeds.
    Status  — report what the manifest holds and whether each stash still exists.

    Design decisions that matter:

    * Stashes are restored by **commit SHA**, never by `stash@{0}`. The index shifts whenever
      anything else stashes in between, and restoring the wrong stash is unrecoverable.
    * `--include-untracked`, never `--all`. `-u` picks up new files (the __tests__ directories that
      show up mid-feature); `-a` would also sweep in gitignored build output.
    * `stash apply` + explicit `drop`, never `stash pop`. If the apply conflicts, the stash stays
      on the stack and the manifest still points at it.
    * A repo with a merge in progress is never restored — the user must finish or abort first.

.PARAMETER Action
    Save, Restore, or Status.

.PARAMETER Repos
    Repo directory names under -ReposDir. Required for Save.

.PARAMETER ManifestPath
    Manifest location. Defaults to temp/sync-repo-state.json under the workspace root.

.PARAMETER Root
    Workspace root. Defaults to the nearest ancestor of the current directory containing a
    -ReposDir directory. This skill lives in the user's GLOBAL skills directory, so the root
    cannot be derived from the script's own location.

.PARAMETER ReposDir
    Name of the directory (directly under -Root) that holds the sibling repos, e.g. "projects",
    "repos", "packages". Defaults to "projects".

.PARAMETER Force
    Restore only: attempt the stash apply even if the working tree is currently dirty.

.EXAMPLE
    ./Invoke-RepoStateSnapshot.ps1 -Action Save -Repos SomeRepo
    ./Invoke-RepoStateSnapshot.ps1 -Action Restore
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Save', 'Restore', 'Status')][string]$Action,
    [string[]]$Repos,
    [string]$ManifestPath,
    [string]$Root,
    [string]$ReposDir = 'projects',
    [switch]$Force
)

Set-StrictMode -Version Latest

# This skill ships in a plugin, so $PSScriptRoot says nothing about which workspace is being
# operated on. Discover the root by walking up from the caller's directory instead. A workspace
# is recognized purely by having a -ReposDir directory somewhere above the cwd.
function Find-WorkspaceRoot {
    param([string]$ReposDirName)
    $dir = (Get-Location).Path
    while ($dir) {
        if (Test-Path (Join-Path $dir $ReposDirName) -PathType Container) {
            return $dir
        }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return (Get-Location).Path
}

if (-not $Root) { $Root = Find-WorkspaceRoot $ReposDir }
if (-not $ManifestPath) {
    $ManifestPath = Join-Path $Root 'temp' 'sync-repo-state.json'
}

function Invoke-Git {
    param([string]$RepoPath, [string[]]$GitArgs)
    $out = & git -C $RepoPath @GitArgs 2>&1
    return [pscustomobject]@{
        Code  = $LASTEXITCODE
        Lines = @($out | ForEach-Object { "$_" })
        Text  = (@($out | ForEach-Object { "$_" }) -join "`n")
    }
}

function Get-StashIndexBySha {
    param([string]$RepoPath, [string]$Sha)
    $list = Invoke-Git $RepoPath @('stash', 'list', '--format=%H %gd')
    foreach ($line in $list.Lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\s+', 2
        if ($parts[0] -eq $Sha) { return $parts[1].Trim() }
    }
    return $null
}

function Test-MergeInProgress {
    param([string]$RepoPath)
    $gitDir = (Invoke-Git $RepoPath @('rev-parse', '--absolute-git-dir')).Lines[0]
    return (Test-Path (Join-Path $gitDir 'MERGE_HEAD'))
}

# ---------------------------------------------------------------- Save

if ($Action -eq 'Save') {
    if (-not $Repos -or $Repos.Count -eq 0) {
        throw "-Repos is required for Save. Scope the snapshot to the repos that will actually be checked out."
    }

    # `pwsh -File` passes every argument as a string, so `-Repos a,b,c` arrives as the single
    # string "a,b,c" rather than an array. Re-split so both invocation styles behave the same.
    $Repos = @($Repos -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

    $entries = [System.Collections.Generic.List[object]]::new()
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')

    foreach ($name in $Repos) {
        $path = Join-Path $Root $ReposDir $name
        if (-not (Test-Path $path)) { throw "No such repo directory: $path" }
        if ((Invoke-Git $path @('rev-parse', '--git-dir')).Code -ne 0) { throw "Not a git repo: $path" }

        if (Test-MergeInProgress $path) {
            throw "$name has a merge in progress. Finish or abort it before snapshotting."
        }

        $branch = (Invoke-Git $path @('rev-parse', '--abbrev-ref', 'HEAD')).Lines[0]
        $head = (Invoke-Git $path @('rev-parse', 'HEAD')).Lines[0]
        $detached = ($branch -eq 'HEAD')

        $porcelain = @((Invoke-Git $path @('status', '--porcelain')).Lines | Where-Object { $_ })

        $stashSha = $null
        if ($porcelain.Count -gt 0) {
            $msg = "sync-team-branches auto-stash $stamp"
            $push = Invoke-Git $path @('stash', 'push', '--include-untracked', '-m', $msg)
            if ($push.Code -ne 0) {
                throw "$name : git stash push failed — $($push.Text)"
            }
            $stashSha = (Invoke-Git $path @('rev-parse', 'stash@{0}')).Lines[0]

            $after = @((Invoke-Git $path @('status', '--porcelain')).Lines | Where-Object { $_ })
            if ($after.Count -gt 0) {
                Write-Warning "$name : working tree still shows $($after.Count) entr(ies) after stashing (likely ignored files) — these were NOT stashed."
            }
        }

        $entries.Add([pscustomobject]@{
                Repo           = $name
                Path           = $path
                OriginalBranch = if ($detached) { $null } else { $branch }
                OriginalHead   = $head
                Detached       = $detached
                StashSha       = $stashSha
                StashedFiles   = $porcelain.Count
                SavedAt        = $stamp
            })
    }

    $manifestDir = Split-Path -Parent $ManifestPath
    if (-not (Test-Path $manifestDir)) { New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null }

    [ordered]@{ savedAt = $stamp; root = $Root; entries = $entries } |
        ConvertTo-Json -Depth 6 | Set-Content -Path $ManifestPath -Encoding utf8

    Write-Host ''
    Write-Host 'Saved repo state' -ForegroundColor Cyan
    $entries | Select-Object Repo, @{n = 'Branch'; e = { if ($_.Detached) { "(detached $($_.OriginalHead.Substring(0,8)))" } else { $_.OriginalBranch } } },
    @{n = 'Stashed'; e = { if ($_.StashSha) { "$($_.StashedFiles) file(s)" } else { 'clean' } } },
    @{n = 'StashSha'; e = { if ($_.StashSha) { $_.StashSha.Substring(0, 10) } else { '' } } } |
        Format-Table -AutoSize | Out-String | Write-Host

    Write-Host "Manifest: $ManifestPath"
    Write-Host 'Restore with: -Action Restore' -ForegroundColor Yellow
    exit 0
}

# ------------------------------------------------------- Restore / Status

if (-not (Test-Path $ManifestPath)) {
    Write-Host ''
    Write-Host "No snapshot manifest at $ManifestPath — nothing to $($Action.ToLower())." -ForegroundColor Yellow
    Write-Host 'Either Phase 2 was never run, or a previous Restore already completed and removed it.'
    exit 0
}

$manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$results = [System.Collections.Generic.List[object]]::new()

foreach ($e in $manifest.entries) {
    $path = $e.Path
    $row = [ordered]@{ Repo = $e.Repo; Branch = ''; Stash = ''; Outcome = ''; Detail = '' }

    $stashExists = $false
    if ($e.StashSha) {
        $stashExists = $null -ne (Get-StashIndexBySha $path $e.StashSha)
    }

    if ($Action -eq 'Status') {
        $row.Branch = (Invoke-Git $path @('rev-parse', '--abbrev-ref', 'HEAD')).Lines[0]
        $row.Stash = if (-not $e.StashSha) { 'none' } elseif ($stashExists) { 'present' } else { 'MISSING' }
        $row.Outcome = 'n/a'
        $row.Detail = if ($e.Detached) { "was detached at $($e.OriginalHead.Substring(0,8))" } else { "was on $($e.OriginalBranch)" }
        $results.Add([pscustomobject]$row); continue
    }

    # --- Restore
    if (Test-MergeInProgress $path) {
        $row.Outcome = 'Blocked'
        $row.Detail = 'merge in progress — finish or abort it, then re-run Restore'
        $results.Add([pscustomobject]$row); continue
    }

    $target = if ($e.Detached) { $e.OriginalHead } else { $e.OriginalBranch }
    $sw = Invoke-Git $path @('switch', '--quiet', $target)
    if ($sw.Code -ne 0) {
        # detached-HEAD restore needs checkout, not switch
        $sw = Invoke-Git $path @('checkout', '--quiet', $target)
    }
    if ($sw.Code -ne 0) {
        $row.Outcome = 'Blocked'
        $row.Detail = "could not return to '$target' — $($sw.Text)"
        $results.Add([pscustomobject]$row); continue
    }
    $row.Branch = (Invoke-Git $path @('rev-parse', '--abbrev-ref', 'HEAD')).Lines[0]

    if (-not $e.StashSha) {
        $row.Stash = 'none'
        $row.Outcome = 'Restored'
        $row.Detail = 'was clean, branch restored'
        $results.Add([pscustomobject]$row); continue
    }

    if (-not $stashExists) {
        $row.Stash = 'MISSING'
        $row.Outcome = 'Failed'
        $row.Detail = "stash $($e.StashSha.Substring(0,10)) is gone — recover with: git -C $path stash apply $($e.StashSha)"
        $results.Add([pscustomobject]$row); continue
    }

    $dirtyNow = @((Invoke-Git $path @('status', '--porcelain')).Lines | Where-Object { $_ })
    if ($dirtyNow.Count -gt 0 -and -not $Force) {
        $row.Stash = 'held'
        $row.Outcome = 'Blocked'
        $row.Detail = "working tree has $($dirtyNow.Count) uncommitted entr(ies); stash kept. Re-run with -Force to apply anyway."
        $results.Add([pscustomobject]$row); continue
    }

    $apply = Invoke-Git $path @('stash', 'apply', $e.StashSha)
    if ($apply.Code -ne 0) {
        $row.Stash = 'held'
        $row.Outcome = 'Conflict'
        $row.Detail = "stash apply conflicted; stash KEPT at $($e.StashSha.Substring(0,10)). Resolve, then: git -C $path stash drop <ref>"
        $results.Add([pscustomobject]$row); continue
    }

    $idx = Get-StashIndexBySha $path $e.StashSha
    if ($idx) {
        $drop = Invoke-Git $path @('stash', 'drop', $idx)
        $row.Stash = if ($drop.Code -eq 0) { 'applied+dropped' } else { 'applied (drop failed)' }
    }
    else {
        $row.Stash = 'applied'
    }
    $row.Outcome = 'Restored'
    $row.Detail = "$($e.StashedFiles) file(s) returned"
    $results.Add([pscustomobject]$row)
}

Write-Host ''
Write-Host "Repo state — $Action" -ForegroundColor Cyan
$results | Format-Table -AutoSize | Out-String | Write-Host

if ($Action -eq 'Restore') {
    $bad = @($results | Where-Object { $_.Outcome -in @('Blocked', 'Failed', 'Conflict') })
    if ($bad.Count -eq 0) {
        Remove-Item $ManifestPath -Force
        Write-Host "All repos restored. Manifest removed." -ForegroundColor Green
    }
    else {
        Write-Host "$($bad.Count) repo(s) not restored — manifest KEPT at $ManifestPath" -ForegroundColor Red
        Write-Host "Fix the reasons above and re-run -Action Restore." -ForegroundColor Red
    }
}

exit 0
