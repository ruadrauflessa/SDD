#requires -Version 7.0
<#
.SYNOPSIS
    Scan a workspace for repos whose integration branch has work not yet merged into the
    matching release branch, and dry-run each merge before any pull request is opened.

.DESCRIPTION
    Pure git. Touches no ref, no index and no working tree - `git merge-tree --write-tree`
    merges entirely in the object database.

    Per repo it fetches, resolves the EXACT remote casing of both branches, measures
    divergence, dry-runs the merge, flags database-migration files, extracts work-item
    candidates from the commit subjects, and parses the Azure DevOps org/project/repo out of
    the origin URL.

.PARAMETER Version
    The version both branches share, e.g. 1.1.0.

.PARAMETER Root
    Workspace root. Defaults to the nearest ancestor of the current directory holding the
    repos directory (see -ReposDir) or a `.gitmodules`, else the current directory.

.PARAMETER ReposDir
    Name of the shared directory holding the sibling repos. Default 'projects'. Pass '' to
    treat Root itself as the repo, or as the parent of the repos.

.PARAMETER Repos
    Explicit repo paths (absolute, or relative to Root). Overrides discovery.

.PARAMETER SourcePattern
    Source branch pattern, {0} = version. Default 'team/{0}'.

.PARAMETER TargetPattern
    Target branch pattern, {0} = version. Default 'release/{0}'.

.PARAMETER JsonPath
    Write the full result set here as JSON.

.PARAMETER NoFetch
    Skip `git fetch`. Only for a repeat run seconds after a fetched one.

.OUTPUTS
    Exit 0 = nothing blocking. 1 = at least one repo conflicts. 2 = at least one repo errored.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Version,
    [string]$Root,
    [string]$ReposDir = 'projects',
    [string[]]$Repos,
    [string]$SourcePattern = 'team/{0}',
    [string]$TargetPattern = 'release/{0}',
    [string]$JsonPath,
    [switch]$NoFetch
)

$ErrorActionPreference = 'Continue'

$sourceWanted = $SourcePattern -f $Version
$targetWanted = $TargetPattern -f $Version
$unitSep = [char]0x1F

function Resolve-WorkspaceRoot {
    param([string]$Explicit, [string]$ReposDirName)
    if ($Explicit) { return (Resolve-Path -LiteralPath $Explicit).Path }
    $dir = (Get-Location).Path
    while ($dir) {
        $hasReposDir = $ReposDirName -and (Test-Path (Join-Path $dir $ReposDirName))
        if ($hasReposDir -or (Test-Path (Join-Path $dir '.gitmodules'))) { return $dir }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return (Get-Location).Path
}

function Test-GitRepo {
    param([string]$Path)
    # A submodule has .git as a FILE, a normal clone as a directory. Both count.
    return (Test-Path (Join-Path $Path '.git'))
}

function Get-CandidateRepos {
    param([string]$RootPath, [string]$ReposDirName, [string[]]$Explicit)
    if ($Explicit) {
        return $Explicit | ForEach-Object {
            $p = if ([System.IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $RootPath $_ }
            if (Test-Path -LiteralPath $p) { (Resolve-Path -LiteralPath $p).Path }
            else { Write-Warning "Repo path not found: $p" }
        }
    }
    if ($ReposDirName) {
        $reposRoot = Join-Path $RootPath $ReposDirName
        if (Test-Path $reposRoot) {
            $found = Get-ChildItem -LiteralPath $reposRoot -Directory |
                Where-Object { Test-GitRepo $_.FullName } | ForEach-Object { $_.FullName }
            if ($found) { return $found }
        }
    }
    if (Test-GitRepo $RootPath) { return @($RootPath) }
    return Get-ChildItem -LiteralPath $RootPath -Directory |
        Where-Object { Test-GitRepo $_.FullName } | ForEach-Object { $_.FullName }
}

function Invoke-Git {
    param([string]$RepoPath, [string[]]$GitArgs)
    $out = & git -C $RepoPath @GitArgs 2>&1
    $lines = @($out | ForEach-Object { "$_" })
    [pscustomobject]@{
        Code  = $LASTEXITCODE
        Text  = ($lines -join "`n")
        Lines = $lines
    }
}

function ConvertTo-AdoCoordinates {
    param([string]$RemoteUrl)
    $r = [pscustomobject]@{ Org = $null; Project = $null; Repo = $null }
    if (-not $RemoteUrl) { return $r }
    # https://user@dev.azure.com/{org}/{project}/_git/{repo}
    if ($RemoteUrl -match 'dev\.azure\.com/(?<org>[^/]+)/(?<proj>[^/]+)/_git/(?<repo>[^/]+?)(?:\.git)?$') {
        $r.Org = $Matches.org
        $r.Project = [uri]::UnescapeDataString($Matches.proj)
        $r.Repo = $Matches.repo
        return $r
    }
    # git@ssh.dev.azure.com:v3/{org}/{project}/{repo}
    if ($RemoteUrl -match 'ssh\.dev\.azure\.com:v3/(?<org>[^/]+)/(?<proj>[^/]+)/(?<repo>[^/]+?)(?:\.git)?$') {
        $r.Org = $Matches.org; $r.Project = $Matches.proj; $r.Repo = $Matches.repo
        return $r
    }
    # https://{org}.visualstudio.com/{project}/_git/{repo}
    if ($RemoteUrl -match '(?<org>[^/.]+)\.visualstudio\.com/(?<proj>[^/]+)/_git/(?<repo>[^/]+?)(?:\.git)?$') {
        $r.Org = $Matches.org
        $r.Project = [uri]::UnescapeDataString($Matches.proj)
        $r.Repo = $Matches.repo
        return $r
    }
    return $r
}

function Get-WorkItemCandidates {
    param([string[]]$Subjects)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    $patterns = @(
        'AB#(\d{3,7})',
        'ADO[\s:#-]*(\d{3,7})',
        '#(\d{3,7})',
        '(?:fix|fixes|fixed|bug|issue|resolve|resolves|resolved)[\s:#-]+(\d{3,7})'
    )
    foreach ($s in $Subjects) {
        foreach ($p in $patterns) {
            foreach ($m in [regex]::Matches($s, $p, 'IgnoreCase')) {
                [void]$ids.Add([int]$m.Groups[1].Value)
            }
        }
    }
    return @($ids | Sort-Object)
}

function Get-AdoBranchesUrl {
    param([string]$Org, [string]$Project, [string]$Repo)
    if (-not $Org -or -not $Project -or -not $Repo) { return $null }
    $orgEnc = [uri]::EscapeDataString($Org)
    $projEnc = [uri]::EscapeDataString($Project)
    $repoEnc = [uri]::EscapeDataString($Repo)
    return "https://dev.azure.com/$orgEnc/$projEnc/_git/$repoEnc/branches"
}

function Get-MigrationKind {
    param([string]$Path)
    if ($Path -match '\.sql$') { return 'SQL Script' }
    if ($Path -match '(^|/)Migrations/.*\.cs$') { return 'EF Core Migration' }
    if ($Path -match '(^|/)\d{14}_.*\.cs$') { return 'EF Core Migration' }
    return $null
}

$rootPath  = Resolve-WorkspaceRoot -Explicit $Root -ReposDirName $ReposDir
$repoPaths = @(Get-CandidateRepos -RootPath $rootPath -ReposDirName $ReposDir -Explicit $Repos)

if (-not $repoPaths) {
    Write-Error "No git repositories found under '$rootPath' (repos dir '$ReposDir'). Pass -Root, -ReposDir or -Repos."
    exit 2
}

Write-Host "Workspace : $rootPath"
Write-Host "Source    : $sourceWanted"
Write-Host "Target    : $targetWanted"
Write-Host "Repos     : $($repoPaths.Count)"
Write-Host ''

$results = foreach ($repoPath in $repoPaths) {
    $name = Split-Path -Leaf $repoPath
    $row = [ordered]@{
        Repo = $name; Path = $repoPath; Status = 'Unknown'; Detail = ''
        SourceBranch = $null; TargetBranch = $null
        Ahead = 0; Behind = 0
        FilesChanged = 0; Insertions = 0; Deletions = 0
        Conflicts = @(); Commits = @(); WorkItemCandidates = @(); MigrationFiles = @()
        RemoteUrl = $null; AdoOrg = $null; AdoProject = $null; AdoRepo = $null
        BranchesUrl = $null; MissingSourceBranch = $false; MissingTargetBranch = $false
    }

    $remote = Invoke-Git $repoPath @('remote', 'get-url', 'origin')
    if ($remote.Code -eq 0) {
        $row.RemoteUrl = $remote.Text.Trim()
        $ado = ConvertTo-AdoCoordinates $row.RemoteUrl
        $row.AdoOrg = $ado.Org; $row.AdoProject = $ado.Project; $row.AdoRepo = $ado.Repo
        $row.BranchesUrl = Get-AdoBranchesUrl -Org $ado.Org -Project $ado.Project -Repo $ado.Repo
    }

    if (-not $NoFetch) {
        $fetch = Invoke-Git $repoPath @('fetch', '--prune', '--quiet', 'origin')
        if ($fetch.Code -ne 0) {
            $row.Status = 'FetchFailed'; $row.Detail = $fetch.Text.Trim()
            [pscustomobject]$row; continue
        }
    }

    # Authoritative branch casing comes from the SERVER, not from local refs. On Windows the
    # filesystem is case-insensitive, so `origin/team/1.1.0` happily resolves a ref that is
    # really `origin/Team/1.1.0` - and Azure DevOps then rejects the lower-cased ref name.
    $ls = Invoke-Git $repoPath @('ls-remote', '--heads', 'origin')
    if ($ls.Code -ne 0) {
        $row.Status = 'FetchFailed'; $row.Detail = "ls-remote failed: $($ls.Text.Trim())"
        [pscustomobject]$row; continue
    }
    $remoteHeads = foreach ($line in $ls.Lines) {
        if ($line -match '^\S+\s+refs/heads/(?<n>.+)$') { $Matches.n.Trim() }
    }
    $srcExact = $remoteHeads | Where-Object { $_ -ieq $sourceWanted } | Select-Object -First 1
    $tgtExact = $remoteHeads | Where-Object { $_ -ieq $targetWanted } | Select-Object -First 1
    $row.SourceBranch = $srcExact
    $row.TargetBranch = $tgtExact

    if (-not $srcExact -or -not $tgtExact) {
        $missing = @()
        if (-not $srcExact) { $row.MissingSourceBranch = $true; $missing += $sourceWanted }
        if (-not $tgtExact) { $row.MissingTargetBranch = $true; $missing += $targetWanted }
        $row.Status = 'Skipped'
        $row.Detail = "Branch not on origin: $($missing -join ', ')"
        if ($row.MissingTargetBranch -and -not $row.MissingSourceBranch) {
            # Source (team) branch exists and has commits waiting, but nobody cut the release
            # branch yet - this needs a human to create it, not something git can do for them.
            $row.Detail = "Release branch '$targetWanted' does not exist yet - create it from '$sourceWanted' at: $($row.BranchesUrl)"
        }
        [pscustomobject]$row; continue
    }

    $srcRef = "refs/remotes/origin/$srcExact"
    $tgtRef = "refs/remotes/origin/$tgtExact"

    $counts = Invoke-Git $repoPath @('rev-list', '--left-right', '--count', "$tgtRef...$srcRef")
    if ($counts.Code -ne 0) {
        $row.Status = 'MergeError'; $row.Detail = "rev-list failed: $($counts.Text.Trim())"
        [pscustomobject]$row; continue
    }
    $parts = -split $counts.Text.Trim()
    $row.Behind = [int]$parts[0]   # on target, absent from source
    $row.Ahead = [int]$parts[1]    # on source, absent from target - what a PR would merge

    if ($row.Ahead -eq 0) {
        $row.Status = 'UpToDate'
        $row.Detail = "Target already has every source commit ($($row.Behind) the other way)."
        [pscustomobject]$row; continue
    }

    $fmt = "%H$unitSep%h$unitSep%an$unitSep%ad$unitSep%s"
    $log = Invoke-Git $repoPath @('log', '--no-merges', "--format=$fmt", '--date=short', "$tgtRef..$srcRef")
    $subjects = [System.Collections.Generic.List[string]]::new()
    $row.Commits = @(foreach ($line in $log.Lines) {
        if (-not $line) { continue }
        $f = $line -split $unitSep
        if ($f.Count -lt 5) { continue }
        $subjects.Add($f[4])
        [pscustomobject]@{ Sha = $f[0]; Short = $f[1]; Author = $f[2]; Date = $f[3]; Subject = $f[4] }
    })
    $row.WorkItemCandidates = Get-WorkItemCandidates -Subjects $subjects

    $stat = Invoke-Git $repoPath @('diff', '--shortstat', "$tgtRef...$srcRef")
    if ($stat.Text -match '(\d+) files? changed') { $row.FilesChanged = [int]$Matches[1] }
    if ($stat.Text -match '(\d+) insertions?\(\+\)') { $row.Insertions = [int]$Matches[1] }
    if ($stat.Text -match '(\d+) deletions?\(-\)') { $row.Deletions = [int]$Matches[1] }

    $files = Invoke-Git $repoPath @('diff', '--name-only', "$tgtRef...$srcRef")
    $row.MigrationFiles = @(foreach ($f in $files.Lines) {
        if (-not $f) { continue }
        $kind = Get-MigrationKind $f
        if ($kind) { [pscustomobject]@{ Path = $f; Kind = $kind } }
    })

    # Target first = "ours", mirroring how Azure DevOps computes the PR merge preview.
    $mt = Invoke-Git $repoPath @('merge-tree', '--write-tree', '--name-only', $tgtRef, $srcRef)
    if ($mt.Code -eq 0) {
        $row.Status = 'Ready'
    }
    elseif ($mt.Code -eq 1) {
        $row.Status = 'Conflicts'
        # Output is: <tree oid> NL <conflicted paths...> NL <informational messages>
        $row.Conflicts = @($mt.Lines | Select-Object -Skip 1 |
            Where-Object { $_ -and $_ -notmatch '^(CONFLICT|Auto-merging|warning:)' })
        $row.Detail = "$($row.Conflicts.Count) conflicted path(s)."
    }
    else {
        $row.Status = 'MergeError'; $row.Detail = $mt.Text.Trim()
    }

    [pscustomobject]$row
}

$results = @($results)

$order = @{ 'Ready' = 0; 'Conflicts' = 1; 'UpToDate' = 2; 'Skipped' = 3; 'FetchFailed' = 4; 'MergeError' = 5; 'Unknown' = 6 }
$sorted = $results | Sort-Object @{ E = { $order[$_.Status] } }, Repo

$sorted | Format-Table -AutoSize @(
    @{ L = 'Repo'; E = { $_.Repo } }
    @{ L = 'Status'; E = { $_.Status } }
    @{ L = 'Source'; E = { $_.SourceBranch } }
    @{ L = 'Ahead'; E = { if ($_.Status -in 'Ready', 'Conflicts', 'UpToDate') { $_.Ahead } else { '' } } }
    @{ L = 'Behind'; E = { if ($_.Status -in 'Ready', 'Conflicts', 'UpToDate') { $_.Behind } else { '' } } }
    @{ L = 'Files'; E = { if ($_.FilesChanged) { $_.FilesChanged } else { '' } } }
    @{ L = 'Mig'; E = { if ($_.MigrationFiles.Count) { $_.MigrationFiles.Count } else { '' } } }
    @{ L = 'WorkItems'; E = { ($_.WorkItemCandidates -join ',') } }
    @{ L = 'Detail'; E = { $_.Detail } }
) | Out-String -Width 240 | Write-Host

$needsReleaseBranch = @($sorted | Where-Object { $_.MissingTargetBranch -and -not $_.MissingSourceBranch })
if ($needsReleaseBranch) {
    Write-Host ''
    Write-Host "MISSING RELEASE BRANCH - create these by hand before this repo can be prepped:"
    foreach ($r in $needsReleaseBranch) {
        Write-Host "  $($r.Repo): create '$targetWanted' from '$sourceWanted' -> $($r.BranchesUrl)"
    }
}

if ($JsonPath) {
    $dir = Split-Path -Parent $JsonPath
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $payload = [ordered]@{
        Version = $Version; Source = $sourceWanted; Target = $targetWanted
        Root = $rootPath; Repos = $sorted
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $JsonPath -Encoding utf8
    Write-Host "JSON: $JsonPath"
}

$ready = @($results | Where-Object Status -eq 'Ready').Count
$conflicts = @($results | Where-Object Status -eq 'Conflicts').Count
$errors = @($results | Where-Object { $_.Status -in 'FetchFailed', 'MergeError', 'Unknown' }).Count
Write-Host ''
Write-Host "Ready: $ready   Conflicts: $conflicts   Errors: $errors"

if ($errors) { exit 2 }
if ($conflicts) { exit 1 }
exit 0
