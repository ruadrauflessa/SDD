#Requires -Version 7.0
<#
.SYNOPSIS
    Classify every repo in a multi-repo workspace for a branch forward-sync.

.DESCRIPTION
    Phase 1 of the sync-team-branches skill. For each git repo under the repos directory:
      1. git fetch --prune origin
      2. verify BOTH origin/<source> and origin/<destination> exist
      3. check whether either branch is LOCKED in Azure DevOps — if so, stop here (status `Locked`)
      4. record working-tree cleanliness (a dirty tree blocks the local-merge path)
      5. measure divergence
      6. dry-run the merge with `git merge-tree --write-tree` (destination first = "ours",
         mirroring what most forges compute for a PR's merge preview)

    The lock check (step 3) needs `az` (with the `azure-devops` extension) authenticated against
    the repo's own organization, read from its `origin` URL — never assumed to be one fixed
    org/project for the whole workspace. It fails open: if `az` is missing, unauthenticated, or the
    repo isn't Azure DevOps-hosted, every branch is treated as unlocked (a warning is shown once)
    rather than the scan refusing to run. -SkipLockCheck disables it outright.

    Read-only with respect to refs, index and working tree. `git fetch` updates
    remote-tracking refs; `merge-tree` writes loose objects that git GCs on its own. The lock check
    itself is a read (`az repos ref list`), never a write. Nothing is checked out, merged,
    committed or pushed.

    Nothing here is tied to any particular project's branch names or org — "team/x.y.z" is one
    workspace's naming convention, not a requirement. Pass whatever two branches need syncing.

.PARAMETER Source
    Lower/older branch being synced forward. Pass a full branch name (e.g. "release/1.1.0",
    "team/1.1.0", "develop"), or a bare value that gets -BranchPrefix prepended (e.g. "1.1.0" with
    the default prefix becomes "team/1.1.0" — a convenience for workspaces that version their
    integration branches).

.PARAMETER Destination
    Higher/newer branch receiving the changes. Same rules as -Source.

.PARAMETER BranchPrefix
    Prefix applied to -Source/-Destination when they don't already look like a full branch name
    (i.e. contain no "/"). Defaults to "team/". Pass "" to disable prefixing and always require
    full branch names, or another value (e.g. "release/") to match a different convention.

.PARAMETER Root
    Workspace root. Defaults to the nearest ancestor of the current directory containing a
    -ReposDir directory. This skill lives in the user's GLOBAL skills directory, so the root
    cannot be derived from the script's own location.

.PARAMETER ReposDir
    Name of the directory (directly under -Root) that holds the sibling repos, e.g. "projects",
    "repos", "packages". Defaults to "projects". Not required to be a git-submodule parent — plain
    sibling clones work the same way.

.PARAMETER Repos
    Optional repo-name filter (matches the directory name under -ReposDir).

.PARAMETER SkipFetch
    Skip `git fetch --prune`. Only for re-running the scan within the same minute;
    results are otherwise stale.

.PARAMETER SkipLockCheck
    Skip the Azure DevOps branch-lock check and scan a repo even if -Source or -Destination is
    locked there. The check is silently skipped anyway for a repo whose origin isn't Azure
    DevOps-hosted, or if `az` isn't installed/authenticated (a warning is shown once, then every
    branch is treated as unlocked) — this switch is for suppressing that warning, or for
    deliberately scanning a locked branch anyway (e.g. to inspect it, not to actually PR into it).

.PARAMETER PriorSource
    Chain mode only: the source branch of the hop immediately BEFORE this one (e.g. if this scan
    is 1.1.0 -> 1.2.0, pass 1.1.0's own source, 1.0.0). When set together with -PriorDestination,
    a repo is only scanned for THIS hop once `git merge-base --is-ancestor` confirms the prior
    hop's source is already merged into the prior hop's destination — i.e. that hop actually
    landed, not merely that a PR was opened for it. A repo that fails this check gets status
    `PendingPriorHop` instead of being scanned, so an unfinished earlier hop can never be silently
    skipped past. Omit both for the first hop in a chain, or for a one-off pair sync.

.PARAMETER PriorDestination
    See -PriorSource. Same normalization rules (bare value + -BranchPrefix, or a full branch
    name).

.PARAMETER JsonPath
    Optional path to write the full result set as JSON for downstream phases.

.EXAMPLE
    ./Scan-TeamBranchSync.ps1 -Source 1.1.0 -Destination 1.2.0

.EXAMPLE
    ./Scan-TeamBranchSync.ps1 -Source release/2.3 -Destination release/2.4 -ReposDir repos -BranchPrefix ''

.EXAMPLE
    # Chain mode: don't scan 1.2.0 -> 1.3.0 for a repo until 1.1.0 -> 1.2.0 has actually landed there.
    ./Scan-TeamBranchSync.ps1 -Source 1.2.0 -Destination 1.3.0 -PriorSource 1.1.0 -PriorDestination 1.2.0
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$Destination,
    [string]$BranchPrefix = 'team/',
    [string]$Root,
    [string]$ReposDir = 'projects',
    [string[]]$Repos,
    [switch]$SkipFetch,
    [switch]$SkipLockCheck,
    [string]$PriorSource,
    [string]$PriorDestination,
    [string]$JsonPath
)

Set-StrictMode -Version Latest

# This skill ships in a plugin, so $PSScriptRoot says nothing about which workspace is being
# operated on. Discover the root by walking up from the caller's directory instead. A workspace
# is recognized purely by having a -ReposDir directory somewhere above the cwd — no assumption
# about git submodules, repo count, or naming.
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

function Normalize-Branch([string]$name) {
    if ($name -like 'refs/*') { return ($name -replace '^refs/heads/', '') }
    if ($name.Contains('/')) { return $name }
    return "$BranchPrefix$name"
}

$srcBranch = Normalize-Branch $Source
$dstBranch = Normalize-Branch $Destination
$srcRef = "origin/$srcBranch"
$dstRef = "origin/$dstBranch"

if ($srcBranch -eq $dstBranch) {
    throw "Source and destination are the same branch ($srcBranch)."
}

$gateOnPriorHop = [bool]$PriorSource -and [bool]$PriorDestination
if ([bool]$PriorSource -ne [bool]$PriorDestination) {
    throw "-PriorSource and -PriorDestination must be passed together."
}
if ($gateOnPriorHop) {
    $priorSrcBranch = Normalize-Branch $PriorSource
    $priorDstBranch = Normalize-Branch $PriorDestination
    $priorSrcRef = "origin/$priorSrcBranch"
    $priorDstRef = "origin/$priorDstBranch"
}

$reposPath = Join-Path $Root $ReposDir
if (-not (Test-Path $reposPath)) {
    throw "No '$ReposDir' directory under '$Root'. Pass -Root and/or -ReposDir explicitly."
}

# Invoke git, returning stdout lines plus the exit code. stderr is discarded —
# callers branch on the exit code, and merge-tree reports conflicts on stdout.
function Invoke-Git {
    param([string]$RepoPath, [string[]]$GitArgs)
    $out = & git -C $RepoPath @GitArgs 2>$null
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Lines  = @($out)
    }
}

function Test-Ref {
    param([string]$RepoPath, [string]$Ref)
    (Invoke-Git $RepoPath @('rev-parse', '--verify', '--quiet', "$Ref^{commit}")).Code -eq 0
}

# Azure DevOps only knows "locked" at the ref level, never in plain git — this always needs a
# server round trip. The org/project/repo triple is read from each repo's OWN origin URL rather
# than assumed to be one fixed org/project for the whole workspace.
function Get-AzureDevOpsCoordinates([string]$OriginUrl) {
    if ($OriginUrl -match 'dev\.azure\.com/(?<org>[^/]+)/(?<project>[^/]+)/_git/(?<repo>[^/]+)') {
        return [pscustomobject]@{ Organization = "https://dev.azure.com/$($Matches.org)"; Project = $Matches.project; Repository = $Matches.repo }
    }
    if ($OriginUrl -match '(?<org>[A-Za-z0-9\-]+)\.visualstudio\.com/(?<project>[^/]+)/_git/(?<repo>[^/]+)') {
        return [pscustomobject]@{ Organization = "https://dev.azure.com/$($Matches.org)"; Project = $Matches.project; Repository = $Matches.repo }
    }
    return $null
}

$script:azChecked = $false
$script:azAvailable = $false
function Test-AzCliReady {
    if (-not $script:azChecked) {
        $script:azChecked = $true
        $script:azAvailable = $null -ne (Get-Command az -ErrorAction SilentlyContinue)
        if (-not $script:azAvailable) {
            Write-Warning "az CLI not found — branch-lock check skipped everywhere; every branch is treated as unlocked. Pass -SkipLockCheck to silence this."
        }
    }
    return $script:azAvailable
}

# Returns the set of SHORT branch names (e.g. "team/1.0.0") Azure DevOps reports as locked for
# this repo. Deliberately NOT filtered by -BranchPrefix: -Source/-Destination may be arbitrary
# full branch names unrelated to it (e.g. -BranchPrefix left at its default while syncing
# "release/2.3" -> "release/2.4"), so a prefix-scoped query could silently miss the very branches
# being scanned. Lists every head once per repo instead and lets the caller match by exact name.
#
# Empty (never $null) when the check can't be done, so the caller fails open — a false
# "not locked" just means a hop gets scanned and, at worst, a PR completion fails obviously later;
# a false "locked" would silently refuse a repo that was actually fine to sync.
function Get-LockedBranchNames {
    param([string]$RepoPath)
    if ($SkipLockCheck -or -not (Test-AzCliReady)) { return @() }

    $originUrl = ((Invoke-Git $RepoPath @('config', '--get', 'remote.origin.url')).Lines -join '').Trim()
    $coords = Get-AzureDevOpsCoordinates $originUrl
    if (-not $coords) { return @() }

    $json = az repos ref list --organization $coords.Organization --project $coords.Project --repository $coords.Repository --filter heads -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) {
        Write-Warning "$($coords.Repository): could not check branch locks (az call failed) — treating its branches as unlocked."
        return @()
    }
    try {
        $refs = @($json | ConvertFrom-Json)
    }
    catch {
        Write-Warning "$($coords.Repository): could not parse branch-lock response — treating its branches as unlocked."
        return @()
    }
    return @($refs | Where-Object { $_.isLocked } | ForEach-Object { $_.name -replace '^refs/heads/', '' })
}

$candidates = Get-ChildItem -Path $reposPath -Directory | Sort-Object Name
if ($Repos) {
    # `pwsh -File` passes every argument as a string, so `-Repos a,b,c` arrives as the single
    # string "a,b,c" rather than an array. Re-split so both invocation styles behave the same.
    $repoNames = @($Repos -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $unknown = @($repoNames | Where-Object { $_ -notin $candidates.Name })
    if ($unknown.Count -gt 0) {
        throw "Unknown repo name(s): $($unknown -join ', '). Check the directory names under $ReposDir/."
    }
    $candidates = $candidates | Where-Object { $repoNames -contains $_.Name }
}

$results = [System.Collections.Generic.List[object]]::new()

foreach ($dir in $candidates) {
    $path = $dir.FullName

    if ((Invoke-Git $path @('rev-parse', '--git-dir')).Code -ne 0) {
        Write-Verbose "$($dir.Name): not a git repo, skipping"
        continue
    }

    $row = [ordered]@{
        Repo          = $dir.Name
        Path          = $path
        Status        = $null
        Ahead         = 0      # commits on source not yet on destination
        Behind        = 0      # commits on destination not on source
        Dirty         = $false
        DirtyFiles    = @()
        ConflictCount = 0
        Conflicts     = @()
        Detail        = ''
    }

    if (-not $SkipFetch) {
        $fetch = Invoke-Git $path @('fetch', '--prune', '--quiet', 'origin')
        if ($fetch.Code -ne 0) {
            $row.Status = 'FetchFailed'
            $row.Detail = 'git fetch --prune origin failed (auth or network)'
            $results.Add([pscustomobject]$row); continue
        }
    }

    if ($gateOnPriorHop -and (Test-Ref $path $priorSrcRef) -and (Test-Ref $path $priorDstRef)) {
        $landed = (Invoke-Git $path @('merge-base', '--is-ancestor', $priorSrcRef, $priorDstRef)).Code -eq 0
        if (-not $landed) {
            $row.Status = 'PendingPriorHop'
            $row.Detail = "$priorSrcBranch is not yet merged into $priorDstBranch — finish that hop first, then re-run this scan"
            $results.Add([pscustomobject]$row); continue
        }
    }
    # If the prior hop's branches don't both exist in this repo, there is nothing to gate on here
    # (this repo either wasn't part of that hop, or has already moved past it) — fall through to
    # the normal checks for THIS hop.

    $hasSrc = Test-Ref $path $srcRef
    $hasDst = Test-Ref $path $dstRef
    if (-not ($hasSrc -and $hasDst)) {
        $missing = @()
        if (-not $hasSrc) { $missing += $srcBranch }
        if (-not $hasDst) { $missing += $dstBranch }
        $row.Status = 'Skipped'
        $row.Detail = "missing branch: $($missing -join ', ')"
        $results.Add([pscustomobject]$row); continue
    }

    $lockedHere = Get-LockedBranchNames -RepoPath $path
    $lockedInvolved = @($lockedHere | Where-Object { $_ -in @($srcBranch, $dstBranch) })
    if ($lockedInvolved.Count -gt 0) {
        # A locked branch cannot receive a push, including a PR completion — nothing can be
        # scanned into or out of it in a way that could ever actually be merged.
        $row.Status = 'Locked'
        $row.Detail = "locked in Azure DevOps: $($lockedInvolved -join ', ') — nothing can be merged into or out of a locked branch"
        $results.Add([pscustomobject]$row); continue
    }

    $porcelain = @((Invoke-Git $path @('status', '--porcelain')).Lines | Where-Object { $_ })
    if ($porcelain.Count -gt 0) {
        $row.Dirty = $true
        $row.DirtyFiles = $porcelain
    }

    $counts = @((Invoke-Git $path @('rev-list', '--left-right', '--count', "$dstRef...$srcRef")).Lines | Where-Object { $_ })
    if ($counts.Count -gt 0) {
        $parts = ($counts[0] -split '\s+') | Where-Object { $_ }
        $row.Behind = [int]$parts[0]
        $row.Ahead = [int]$parts[1]
    }

    if ($row.Ahead -eq 0) {
        $row.Status = 'UpToDate'
        $row.Detail = "$dstRef already contains everything on $srcRef"
        $results.Add([pscustomobject]$row); continue
    }

    # Destination is an ancestor of source => merge is a pure fast-forward.
    $isFF = (Invoke-Git $path @('merge-base', '--is-ancestor', $dstRef, $srcRef)).Code -eq 0

    # Dry-run merge. Destination first: it is "ours", matching the PR's target branch.
    $mt = Invoke-Git $path @('merge-tree', '--write-tree', '--name-only', $dstRef, $srcRef)

    switch ($mt.Code) {
        0 {
            $row.Status = if ($isFF) { 'FastForward' } else { 'Clean' }
            $row.Detail = "$($row.Ahead) commit(s) to bring forward"
        }
        1 {
            # merge-tree stdout: <tree-oid> / conflicted paths / blank line / messages
            $lines = @($mt.Lines)
            $paths = [System.Collections.Generic.List[string]]::new()
            for ($i = 1; $i -lt $lines.Count; $i++) {
                if ([string]::IsNullOrWhiteSpace($lines[$i])) { break }
                $paths.Add($lines[$i])
            }
            $row.Status = 'Conflicts'
            $row.Conflicts = @($paths)
            $row.ConflictCount = $paths.Count
            $row.Detail = "$($row.Ahead) commit(s), $($paths.Count) conflicted path(s)"
        }
        default {
            $row.Status = 'MergeError'
            $row.Detail = "git merge-tree exited $($mt.Code) (unrelated histories?)"
        }
    }

    $results.Add([pscustomobject]$row)
}

Write-Host ''
Write-Host "Sync scan: $srcBranch -> $dstBranch" -ForegroundColor Cyan
Write-Host ("Root: {0}" -f $Root)
Write-Host ''

# Render to the host, not the output stream, so `return $results` stays clean for callers.
$results |
    Select-Object Repo, Status, Ahead, @{n = 'Dirty'; e = { if ($_.Dirty) { 'yes' } else { '' } } }, @{n = 'Conflicts'; e = { if ($_.Status -eq 'Conflicts') { $_.ConflictCount } else { '' } } }, Detail |
    Format-Table -AutoSize | Out-String | Write-Host

foreach ($r in $results | Where-Object { $_.Status -eq 'Conflicts' }) {
    Write-Host "$($r.Repo) — conflicted paths:" -ForegroundColor Yellow
    $r.Conflicts | ForEach-Object { Write-Host "    $_" }
    Write-Host ''
}

$actionable = @($results | Where-Object { $_.Status -in @('Clean', 'FastForward', 'Conflicts') })
$needSnapshot = @($actionable | Where-Object { $_.Status -eq 'Conflicts' -and $_.Dirty })
$pending = @($results | Where-Object { $_.Status -eq 'PendingPriorHop' })
$locked = @($results | Where-Object { $_.Status -eq 'Locked' })

Write-Host ("Summary: {0} need syncing ({1} clean/ff, {2} conflicted), {3} up to date, {4} skipped, {5} waiting on a prior hop, {6} locked." -f
    $actionable.Count,
    @($actionable | Where-Object { $_.Status -in @('Clean', 'FastForward') }).Count,
    @($actionable | Where-Object { $_.Status -eq 'Conflicts' }).Count,
    @($results | Where-Object { $_.Status -eq 'UpToDate' }).Count,
    @($results | Where-Object { $_.Status -eq 'Skipped' }).Count,
    $pending.Count,
    $locked.Count) -ForegroundColor Cyan

if ($pending.Count -gt 0) {
    Write-Host ''
    Write-Host "These are waiting on an earlier hop to land — not scanned this round:" -ForegroundColor Yellow
    $pending | ForEach-Object { Write-Host "    $($_.Repo): $($_.Detail)" }
}

if ($locked.Count -gt 0) {
    Write-Host ''
    Write-Host "These have a locked branch — nothing can be merged there, so they were not scanned further:" -ForegroundColor Yellow
    $locked | ForEach-Object { Write-Host "    $($_.Repo): $($_.Detail)" }
}

if ($needSnapshot.Count -gt 0) {
    Write-Host ''
    Write-Host "These need a local merge and have uncommitted work —" -ForegroundColor Yellow
    $needSnapshot | ForEach-Object { Write-Host "    $($_.Repo) ($($_.DirtyFiles.Count) file(s))" }
    Write-Host "Phase 2 (Invoke-RepoStateSnapshot.ps1 -Action Save) will stash and later restore them." -ForegroundColor Yellow
}

if ($JsonPath) {
    $payload = [ordered]@{
        source      = $srcBranch
        destination = $dstBranch
        root        = $Root
        reposDir    = $ReposDir
        repos       = $results
    }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $JsonPath -Encoding utf8
    Write-Host ''
    Write-Host "Wrote $JsonPath"
}

# The table above and -JsonPath are the interface. Emitting $results here as well would make
# `pwsh -File` render the whole object graph as a Format-List after the table.
#
# Conflicts are a normal outcome of a scan, not a failure. Without the explicit exit the script
# would inherit $LASTEXITCODE from the last `git merge-tree` (1 = conflicts) and look like it errored.
exit 0
