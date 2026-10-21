#Requires -Version 7.0
<#
.SYNOPSIS
    Discover every version-bearing integration branch across a multi-repo workspace and build the
    ordered chain of adjacent version hops.

.DESCRIPTION
    Phase 0 of the sync-team-branches skill's chain mode. Enumerates remote branches matching
    -BranchPrefix across every repo under -ReposDir, extracts the version segment, and sorts all
    distinct versions found ANYWHERE in the workspace numerically — "1.2.0" sorts before "1.10.0",
    unlike a plain string sort. This is what lets the skill "start with the lowest available
    version... to make sure we do not miss anything" instead of assuming which pair the user meant.

    Builds EACH REPO'S OWN hop chain from its own present versions, not one chain forced onto
    every repo alike. A version bump is project-wide, but a branch for it only exists in a repo
    that actually had changes for that release — a repo with nothing to ship in 1.1.0 never gets a
    team/1.1.0 branch, and its next hop legitimately runs 1.0.0 -> 1.2.0 directly. That is normal,
    not a defect, so it is not flagged as one; the per-repo chain model means the orchestrator
    never has to force a repo through a version it never had.

    Those per-repo hops are then grouped into "waves" by destination version (lowest destination
    first), and within a wave, repos whose hop has an identical (Source, PriorSource,
    PriorDestination) are grouped together — exactly the set that can be scanned in one
    Scan-TeamBranchSync.ps1 call, since its -PriorSource/-PriorDestination gate applies uniformly
    to whichever -Repos are named in that call.

    A branch LOCKED in Azure DevOps is excluded from discovery entirely — for that repo it is
    treated exactly as if the branch didn't exist. A lock means the team has frozen that branch
    (typically: everything on it already shipped and landed forward, and nobody is meant to push to
    it again); a PR can never be completed into a locked branch anyway, so there is nothing to gain
    by planning a hop into or out of one. This falls out of the existing "repo doesn't have this
    version" handling with no extra logic — a repo whose only branch for a version is locked simply
    has one less entry in its own present-version list, and its chain skips straight over it like
    any other gap. Requires `az` (with the `azure-devops` extension) authenticated against the
    repo's own organization, detected per repo from its `origin` URL — never assumed to be one
    fixed org/project for the whole workspace. Falls back to "include everything, can't tell" with
    a warning if `az` is missing, unauthenticated, or the repo isn't Azure DevOps-hosted; use
    -SkipLockCheck to silence that and always include everything.

    Read-only with respect to git: only `git fetch --prune` and `git for-each-ref`. Nothing is
    checked out, merged, or pushed. The lock check itself is a read (`az repos ref list`), never a
    write — this script never locks or unlocks a branch.

.PARAMETER BranchPrefix
    Prefix identifying an integration branch as version-bearing. Defaults to "team/" — a branch
    "origin/team/1.2.0" contributes the version "1.2.0". Must be non-empty; there is no
    version-chain concept for a workspace that doesn't name branches this way.

.PARAMETER Root
    Workspace root. Defaults to the nearest ancestor of the current directory containing a
    -ReposDir directory. This skill lives in the user's GLOBAL skills directory, so the root
    cannot be derived from the script's own location.

.PARAMETER ReposDir
    Name of the directory (directly under -Root) that holds the sibling repos. Defaults to
    "projects".

.PARAMETER Repos
    Optional repo-name filter (matches the directory name under -ReposDir).

.PARAMETER FromVersion
    Optional lower bound (inclusive). Versions below this are still discovered (they still count
    for gap detection) but excluded from the hop list. Omit to start from the lowest version found
    — the safe default.

.PARAMETER ToVersion
    Optional upper bound (inclusive). Versions above this are excluded from the hop list.

.PARAMETER SkipFetch
    Skip `git fetch --prune`. Only for re-running within the same minute; results are otherwise
    stale, and a stale view here is exactly how a hop's landed-check gives a false answer.

.PARAMETER SkipLockCheck
    Skip the Azure DevOps branch-lock check entirely and include every branch regardless of lock
    state. Use this for a non-Azure-DevOps workspace (the check is silently skipped per repo
    anyway once the origin URL doesn't match Azure DevOps, so this is rarely needed), or if `az`
    isn't installed/authenticated and you'd rather not see the per-repo warnings about it.

.PARAMETER JsonPath
    Optional path to write the full result set (versions, hops, per-repo membership, gaps) as
    JSON, for the orchestrating loop and as the source of -Source/-Destination for each call to
    Scan-TeamBranchSync.ps1.

.EXAMPLE
    ./Get-TeamVersionChain.ps1 -JsonPath temp/sync-chain.json

.EXAMPLE
    ./Get-TeamVersionChain.ps1 -FromVersion 1.1.0 -JsonPath temp/sync-chain.json
#>
[CmdletBinding()]
param(
    [string]$BranchPrefix = 'team/',
    [string]$Root,
    [string]$ReposDir = 'projects',
    [string[]]$Repos,
    [string]$FromVersion,
    [string]$ToVersion,
    [switch]$SkipFetch,
    [switch]$SkipLockCheck,
    [string]$JsonPath
)

Set-StrictMode -Version Latest

if (-not $BranchPrefix) {
    throw "Chain discovery needs a non-empty -BranchPrefix (e.g. 'team/') to know which branches carry a version. Use Scan-TeamBranchSync.ps1 directly for a workspace with no such convention."
}

# This skill ships in a plugin, so $PSScriptRoot says nothing about which workspace is being
# operated on. Discover the root by walking up from the caller's directory instead.
function Find-WorkspaceRoot {
    param([string]$ReposDirName)
    $dir = (Get-Location).Path
    while ($dir) {
        if (Test-Path (Join-Path $dir $ReposDirName) -PathType Container) { return $dir }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return (Get-Location).Path
}

if (-not $Root) { $Root = Find-WorkspaceRoot $ReposDir }

$reposPath = Join-Path $Root $ReposDir
if (-not (Test-Path $reposPath)) {
    throw "No '$ReposDir' directory under '$Root'. Pass -Root and/or -ReposDir explicitly."
}

function Invoke-Git {
    param([string]$RepoPath, [string[]]$GitArgs)
    $out = & git -C $RepoPath @GitArgs 2>$null
    return [pscustomobject]@{ Code = $LASTEXITCODE; Lines = @($out) }
}

# Azure DevOps only knows "locked" at the ref level, never in plain git — this always needs a
# server round trip. The org/project/repo triple is read from each repo's OWN origin URL rather
# than assumed to be one fixed org/project for the whole workspace, since a workspace can mix
# projects (this one does: HealthCodeIndex_V2 has its own).
function Get-AzureDevOpsCoordinates([string]$OriginUrl) {
    if ($OriginUrl -match 'dev\.azure\.com/(?<org>[^/]+)/(?<project>[^/]+)/_git/(?<repo>[^/]+)') {
        return [pscustomobject]@{ Organization = "https://dev.azure.com/$($Matches.org)"; Project = $Matches.project; Repository = $Matches.repo }
    }
    # Legacy host form; the REST API/CLI still accept the unified dev.azure.com organization URL.
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

# Returns the set of SHORT branch names (e.g. "team/1.0.0") that Azure DevOps reports as locked
# for this repo. Empty (never $null) when the check can't be done — the caller then includes
# everything, which is the safe direction to fail in: a false "not locked" just means a hop gets
# scanned and, at worst, a PR completion fails obviously later; a false "locked" would silently
# drop real branches from the whole chain.
function Get-LockedBranchNames {
    param([string]$RepoPath, [string]$BranchPrefix)
    if ($SkipLockCheck -or -not (Test-AzCliReady)) { return @() }

    $originUrl = ((Invoke-Git $RepoPath @('config', '--get', 'remote.origin.url')).Lines -join '').Trim()
    $coords = Get-AzureDevOpsCoordinates $originUrl
    if (-not $coords) { return @() }  # not Azure DevOps-hosted (or an unrecognized URL shape) — no lock concept here

    $filterPath = "heads/$BranchPrefix".TrimEnd('/')
    $json = az repos ref list --organization $coords.Organization --project $coords.Project --repository $coords.Repository --filter $filterPath -o json 2>$null
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

# Numeric, not lexical: "1.2.0" must sort before "1.10.0". [version] handles the common case
# (2-4 numeric dot-separated segments). Anything it rejects — a 1-segment version, or a
# non-numeric suffix like "1.1.0-rc1" — falls back to a manual per-segment numeric parse, which
# still orders correctly against its numeric peers.
function Get-VersionSortKey([string]$v) {
    try { return [version]$v } catch { }
    $parts = @(($v -split '[.\-]') | ForEach-Object {
            $n = 0; if ([int]::TryParse($_, [ref]$n)) { $n } else { 0 }
        })
    while ($parts.Count -lt 4) { $parts += 0 }
    return [version]::new($parts[0], $parts[1], $parts[2], $parts[3])
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

$repoVersions = [ordered]@{}
$repoLockedVersions = [ordered]@{}
$allVersionsSet = [System.Collections.Generic.HashSet[string]]::new()

foreach ($dir in $candidates) {
    $path = $dir.FullName
    if ((Invoke-Git $path @('rev-parse', '--git-dir')).Code -ne 0) {
        Write-Verbose "$($dir.Name): not a git repo, skipping"
        continue
    }

    if (-not $SkipFetch) {
        Invoke-Git $path @('fetch', '--prune', '--quiet', 'origin') | Out-Null
    }

    $locked = @(Get-LockedBranchNames -RepoPath $path -BranchPrefix $BranchPrefix)

    $refs = (Invoke-Git $path @('for-each-ref', '--format=%(refname:short)', "refs/remotes/origin/$BranchPrefix*")).Lines
    $versions = [System.Collections.Generic.List[string]]::new()
    $lockedHere = [System.Collections.Generic.List[string]]::new()
    foreach ($r in $refs) {
        if ([string]::IsNullOrWhiteSpace($r)) { continue }
        $prefix = "origin/$BranchPrefix"
        if (-not $r.StartsWith($prefix)) { continue }
        $v = $r.Substring($prefix.Length)
        if (-not $v) { continue }
        if ($locked -contains "$BranchPrefix$v") {
            # Locked in Azure DevOps -- treated exactly as if this repo never had the branch.
            # Nothing more will land here, and a PR can never complete into a locked branch, so
            # there is no hop worth planning into or out of it.
            $lockedHere.Add($v)
            continue
        }
        $versions.Add($v); [void]$allVersionsSet.Add($v)
    }
    if ($lockedHere.Count -gt 0) { $repoLockedVersions[$dir.Name] = @($lockedHere | Sort-Object -Property @{ Expression = { Get-VersionSortKey $_ } }) }

    $sorted = @($versions | Sort-Object -Unique -Property @{ Expression = { Get-VersionSortKey $_ } })
    $repoVersions[$dir.Name] = $sorted
}

$allVersions = @($allVersionsSet) | Sort-Object -Property @{ Expression = { Get-VersionSortKey $_ } }

if ($FromVersion) {
    $fromKey = Get-VersionSortKey $FromVersion
    $allVersions = @($allVersions | Where-Object { (Get-VersionSortKey $_) -ge $fromKey })
}
if ($ToVersion) {
    $toKey = Get-VersionSortKey $ToVersion
    $allVersions = @($allVersions | Where-Object { (Get-VersionSortKey $_) -le $toKey })
}

# Each repo's OWN chain, not one global chain applied to everyone. A version bump is
# project-wide, but a branch for it is only cut in a repo that actually has changes for that
# release — a repo with nothing to ship in 1.1.0 simply never gets a team/1.1.0 branch, and its
# next hop legitimately runs 1.0.0 -> 1.2.0 directly. That is normal, not a gap to flag; forcing
# every repo through every global version would invent hops that never needed to exist.
#
# Bound to the (possibly -FromVersion/-ToVersion-restricted) $allVersions, so a repo's chain for
# THIS run only ever touches versions actually in scope.
$repoChains = [ordered]@{}
foreach ($repo in $repoVersions.Keys) {
    $present = @($repoVersions[$repo] | Where-Object { $allVersions -contains $_ })
    $chain = [System.Collections.Generic.List[object]]::new()
    for ($i = 0; $i -lt $present.Count - 1; $i++) {
        $prior = if ($i -eq 0) { $null } else { $present[$i - 1] }
        $chain.Add([pscustomobject]@{
                Source           = $present[$i]
                Destination      = $present[$i + 1]
                PriorSource      = $prior
                PriorDestination = if ($prior) { $present[$i] } else { $null }
            })
    }
    $repoChains[$repo] = $chain
}

# Group every repo's next hop by destination version, so the orchestrator can walk destinations
# lowest-to-highest ("waves") instead of forcing one uniform Source across the whole workspace.
# Within a wave, repos that happen to share an identical (Source, PriorSource, PriorDestination)
# are grouped together — that's the set Scan-TeamBranchSync.ps1 can be called for in one pass,
# since -PriorSource/-PriorDestination apply uniformly to whichever -Repos are named in that call.
$entriesByDestination = [ordered]@{}
foreach ($repo in $repoChains.Keys) {
    foreach ($hop in $repoChains[$repo]) {
        if (-not $entriesByDestination.Contains($hop.Destination)) {
            $entriesByDestination[$hop.Destination] = [System.Collections.Generic.List[object]]::new()
        }
        $entriesByDestination[$hop.Destination].Add([pscustomobject]@{
                Repo             = $repo
                Source           = $hop.Source
                PriorSource      = $hop.PriorSource
                PriorDestination = $hop.PriorDestination
            })
    }
}

$waves = [System.Collections.Generic.List[object]]::new()
foreach ($destVersion in $allVersions) {
    if (-not $entriesByDestination.Contains($destVersion)) { continue }
    $groups = $entriesByDestination[$destVersion] | Group-Object -Property {
        "$($_.Source)|$($_.PriorSource)|$($_.PriorDestination)"
    }
    $groupObjs = foreach ($g in $groups) {
        [pscustomobject]@{
            Source           = $g.Group[0].Source
            PriorSource      = $g.Group[0].PriorSource
            PriorDestination = $g.Group[0].PriorDestination
            Repos            = @($g.Group.Repo | Sort-Object)
        }
    }
    $waves.Add([pscustomobject]@{ Destination = $destVersion; Groups = @($groupObjs) })
}

# Purely informational, and every repo lands in exactly one bucket so none silently vanish from
# the summary: on the convention with 2+ versions in scope (has a wave entry above), exactly one
# version in scope (nothing to sync yet), some branches but none inside -FromVersion/-ToVersion,
# or never on the convention at all.
$inScopeCount = @{}
foreach ($repo in $repoVersions.Keys) {
    $inScopeCount[$repo] = @($repoVersions[$repo] | Where-Object { $allVersions -contains $_ }).Count
}
$singleVersionRepos = @($repoVersions.Keys | Where-Object { $inScopeCount[$_] -eq 1 })
$outOfRangeRepos = @($repoVersions.Keys | Where-Object { $inScopeCount[$_] -eq 0 -and $repoVersions[$_].Count -gt 0 })
$noVersionRepos = @($repoVersions.Keys | Where-Object { $repoVersions[$_].Count -eq 0 })

Write-Host ''
Write-Host "Team version chain — prefix '$BranchPrefix'" -ForegroundColor Cyan
Write-Host ("Root: {0}" -f $Root)
Write-Host ''

if ($allVersions.Count -eq 0) {
    Write-Host "No branches matching '$BranchPrefix*' found in any repo under $ReposDir/." -ForegroundColor Yellow
}
else {
    Write-Host ("Versions found, lowest to highest: {0}" -f ($allVersions -join ' -> ')) -ForegroundColor Cyan
    Write-Host ''

    if ($waves.Count -eq 0) {
        Write-Host 'No repo has more than one version in scope — nothing to chain-sync.' -ForegroundColor Yellow
    }
    else {
        Write-Host 'Wave plan (run in this order — each destination is one wave; a repo whose own' -ForegroundColor Cyan
        Write-Host 'chain skips a version jumps straight to its next one, which is expected):' -ForegroundColor Cyan
        foreach ($w in $waves) {
            Write-Host ("  -> {0}" -f $w.Destination)
            foreach ($g in $w.Groups) {
                $note = if ($g.PriorSource) { "after $($g.PriorSource) -> $($g.PriorDestination)" } else { 'first hop for these repos' }
                Write-Host ("      {0} -> {1}   [{2}]   {3}" -f $g.Source, $w.Destination, ($g.Repos -join ', '), $note)
            }
        }
    }
    Write-Host ''

    Write-Host 'Per-repo coverage (- = branch absent in that repo):'
    foreach ($repo in $repoVersions.Keys) {
        $present = $repoVersions[$repo]
        $marked = $allVersions | ForEach-Object { if ($present -contains $_) { $_ } else { '-' } }
        Write-Host ("  {0,-40} {1}" -f $repo, ($marked -join '  '))
    }

    if ($singleVersionRepos.Count -gt 0) {
        Write-Host ''
        Write-Host ("Only one version in scope, nothing to sync yet: {0}" -f ($singleVersionRepos -join ', '))
    }
    if ($outOfRangeRepos.Count -gt 0) {
        Write-Host ("Has '$BranchPrefix' branches, but none inside this run's range: {0}" -f ($outOfRangeRepos -join ', '))
    }
    if ($noVersionRepos.Count -gt 0) {
        Write-Host ("Not on the '$BranchPrefix' convention at all: {0}" -f ($noVersionRepos -join ', '))
    }

    if ($repoLockedVersions.Count -gt 0) {
        Write-Host ''
        Write-Host 'Excluded — locked in Azure DevOps (frozen; treated as if the branch did not exist):' -ForegroundColor Yellow
        foreach ($repo in $repoLockedVersions.Keys) {
            Write-Host ("  {0}: {1}" -f $repo, ($repoLockedVersions[$repo] -join ', '))
        }
    }
}

if ($JsonPath) {
    $payload = [ordered]@{
        root                = $Root
        reposDir            = $ReposDir
        branchPrefix        = $BranchPrefix
        versions            = $allVersions
        waves               = $waves
        repoChains          = $repoChains
        repoVersions        = $repoVersions
        repoLockedVersions  = $repoLockedVersions
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $JsonPath -Encoding utf8
    Write-Host ''
    Write-Host "Wrote $JsonPath"
}

exit 0
