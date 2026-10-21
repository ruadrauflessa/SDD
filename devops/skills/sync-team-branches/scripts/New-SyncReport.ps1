#Requires -Version 7.0
<#
.SYNOPSIS
    Build a shareable markdown report for a completed team-branch sync.

.DESCRIPTION
    Phase 6 of the sync-team-branches skill. Merges the Phase 1 scan JSON with the PR results
    gathered during Phases 3-4 and writes a single markdown file that can be pasted straight into
    Teams, an ADO wiki page, a PR description, or an email.

    Formatting lives here rather than in the model's head so the report does not drift between
    runs — same columns, same wording, same ordering every time.

    Every scanned repo appears somewhere in the output. A repo silently dropping out of a sync
    report is the exact failure this skill exists to prevent, so `Skipped` and `Needs attention`
    rows are rendered as their own tables rather than omitted.

.PARAMETER ScanJson
    Path to the JSON written by Scan-TeamBranchSync.ps1 -JsonPath.

.PARAMETER PrResultsJson
    Optional path to a JSON array describing what happened per repo. Any subset of repos may
    appear; anything absent is reported as "not raised". Shape:

      [
        { "repo": "SomeRepo",
          "prId": 12345,
          "prUrl": "https://dev.azure.com/...",
          "syncBranch": null,
          "note": "",
          "techStoryId": 85397,
          "techStoryUrl": "https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/85397" },
        { "repo": "OtherRepo",
          "prId": 12346,
          "prUrl": "https://dev.azure.com/...",
          "syncBranch": "sync/alex/1.1.0_to_1.2.0",
          "note": "2 migration files resolved by Alex",
          "techStoryId": 85397,
          "techStoryUrl": "https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/85397" }
      ]

    `techStoryId`/`techStoryUrl` name the team-sync work item that repo's PR was linked to instead
    of the work items on the branches being merged. Optional per entry; distinct values across
    entries are all listed in the report header (a chain run can span more than one ADO project).

.PARAMETER OutputPath
    Where to write. Defaults to <root>/documents/sync-reports/sync-<src>-to-<dst>-<yyyyMMdd>.md,
    falling back to <root>/temp/ when documents/ does not exist.

.PARAMETER Author
    Name shown in the header. Defaults to `git config user.name`.

.PARAMETER PassThru
    Also emit the markdown to stdout.

.EXAMPLE
    ./New-SyncReport.ps1 -ScanJson temp/sync-scan.json -PrResultsJson temp/sync-prs.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ScanJson,
    [string]$PrResultsJson,
    [string]$OutputPath,
    [string]$Author,
    [switch]$PassThru
)

Set-StrictMode -Version Latest

if (-not (Test-Path $ScanJson)) { throw "No scan JSON at '$ScanJson'. Run Scan-TeamBranchSync.ps1 -JsonPath first." }

$scan = Get-Content $ScanJson -Raw | ConvertFrom-Json
$root = $scan.root
$src = $scan.source
$dst = $scan.destination

# ConvertFrom-Json yields PSCustomObjects; under StrictMode a missing property throws.
function Get-Prop {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p -or $null -eq $p.Value) { return $Default }
    return $p.Value
}

$prByRepo = @{}
if ($PrResultsJson) {
    if (-not (Test-Path $PrResultsJson)) { throw "No PR results JSON at '$PrResultsJson'." }
    foreach ($r in @(Get-Content $PrResultsJson -Raw | ConvertFrom-Json)) {
        $name = Get-Prop $r 'repo'
        if ($name) { $prByRepo[$name] = $r }
    }
}

if (-not $Author) {
    $Author = (& git -C $root config user.name 2>$null)
    if (-not $Author) { $Author = $env:USERNAME }
}

$now = Get-Date
$stamp = $now.ToString('yyyy-MM-dd')

if (-not $OutputPath) {
    $dir = Join-Path $root 'documents' 'sync-reports'
    if (-not (Test-Path (Join-Path $root 'documents'))) { $dir = Join-Path $root 'temp' }
    $safe = "$src-to-$dst" -replace '[^\w.\-]', '_'
    $OutputPath = Join-Path $dir "sync-$safe-$($now.ToString('yyyyMMdd')).md"
}

# Escape markdown table cell content — a stray pipe in a branch or path would break the row.
function Esc([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return '' }
    return ($s -replace '\|', '\|')
}

function Format-Pr {
    param($pr)
    if ($null -eq $pr) { return '_not raised_' }
    $id = Get-Prop $pr 'prId'
    $url = Get-Prop $pr 'prUrl'
    if ($id -and $url) { return "[PR $id]($url)" }
    if ($url) { return "[link]($url)" }
    if ($id) { return "PR $id" }
    return '_not raised_'
}

function Format-TechStory {
    param($pr)
    if ($null -eq $pr) { return '—' }
    $id = Get-Prop $pr 'techStoryId'
    $url = Get-Prop $pr 'techStoryUrl'
    if ($id -and $url) { return "[$id]($url)" }
    if ($id) { return "$id" }
    return '—'
}

$outcomeMap = @{
    FastForward      = 'Fast-forward'
    Clean            = 'Clean merge'
    Conflicts        = 'Conflicts resolved'
    UpToDate         = 'Already up to date'
    Skipped          = 'Skipped'
    PendingPriorHop  = 'Waiting on a prior hop'
    Locked           = 'Locked (excluded)'
    FetchFailed      = 'Needs attention'
    MergeError       = 'Needs attention'
}

# Sort-Object on strings is culture-aware and ignores '.' and '_', which scrambles repo names that
# differ only in punctuation/case (e.g. Foo.Bar / Foo_Bar.Baz / foo_bar_UI) into an order that looks
# arbitrary to a reader. Force an ordinal sort so the table is predictable.
#
# The two-array [Array]::Sort(keys, items, comparer) overload does NOT work here: PowerShell
# marshals a copy of the items array, so the keys come back sorted and the items don't move.
# Sorting the keys alone and mapping back is reliable. Repo names are unique, so a lookup is safe.
function Sort-Repos {
    param([object[]]$Items)
    if (-not $Items -or $Items.Count -eq 0) { return @() }
    $byName = @{}
    foreach ($i in $Items) { $byName[$i.Repo] = $i }
    $keys = [string[]]@($byName.Keys)
    [Array]::Sort($keys, [StringComparer]::OrdinalIgnoreCase)
    return @($keys | ForEach-Object { $byName[$_] })
}

# The @() around each call matters: a function returning an empty array has it unrolled to $null
# by the pipeline, and under StrictMode the later .Count access would then throw.
$all = @($scan.repos)
$synced = @(Sort-Repos @($all | Where-Object { $_.Status -in @('Clean', 'FastForward', 'Conflicts') }))
$upToDate = @(Sort-Repos @($all | Where-Object { $_.Status -eq 'UpToDate' }))
$skipped = @(Sort-Repos @($all | Where-Object { $_.Status -eq 'Skipped' }))
$pending = @(Sort-Repos @($all | Where-Object { $_.Status -eq 'PendingPriorHop' }))
$locked = @(Sort-Repos @($all | Where-Object { $_.Status -eq 'Locked' }))
$attention = @(Sort-Repos @($all | Where-Object { $_.Status -in @('FetchFailed', 'MergeError') }))

$prCount = @($synced | Where-Object { $prByRepo.ContainsKey($_.Repo) }).Count
$conflicted = @($synced | Where-Object { $_.Status -eq 'Conflicts' })
# Piping an empty array into Measure-Object emits nothing at all, so under Set-StrictMode the
# assignment's RHS never resolves and $totalCommits would be undefined rather than $null -- the
# very next line's read of it would then itself throw. Guard on Count first instead of relying on
# "-not $totalCommits" to catch a value that, in the all-excluded case, was never even set.
$totalCommits = 0
if ($synced.Count -gt 0) {
    $totalCommits = ($synced | Measure-Object -Property Ahead -Sum).Sum
    if (-not $totalCommits) { $totalCommits = 0 }
}

$md = [System.Collections.Generic.List[string]]::new()

$md.Add("# Team branch sync — ``$src`` → ``$dst``")
$md.Add('')
$md.Add("**Run:** $stamp by $Author  ")
$md.Add("**Repos scanned:** $($all.Count) · **Synced:** $($synced.Count) · **PRs raised:** $prCount · **Commits carried forward:** $totalCommits")

$techStories = [System.Collections.Generic.List[string]]::new()
$seenTechStories = @{}
foreach ($pr in $prByRepo.Values) {
    $id = Get-Prop $pr 'techStoryId'
    if (-not $id -or $seenTechStories.ContainsKey($id)) { continue }
    $seenTechStories[$id] = $true
    $techStories.Add((Format-TechStory $pr))
}
if ($techStories.Count -gt 0) {
    $label = if ($techStories.Count -gt 1) { 'Team-sync work items' } else { 'Team-sync work item' }
    $md.Add("**${label}:** $($techStories -join ', ')  ")
    $md.Add('_The old work items on the branches being merged are deliberately not linked to these PRs — see the sync-team-branches skill._')
}
$md.Add('')

if ($synced.Count -gt 0) {
    $md.Add('## Synced')
    $md.Add('')
    $md.Add('| Repo | Outcome | Commits | Conflicts | Pull request | Tech story |')
    $md.Add('| --- | --- | --- | --- | --- | --- |')
    foreach ($r in $synced) {
        $pr = if ($prByRepo.ContainsKey($r.Repo)) { $prByRepo[$r.Repo] } else { $null }
        $conf = if ($r.Status -eq 'Conflicts') { "$($r.ConflictCount) file(s)" } else { '—' }
        $md.Add("| $(Esc $r.Repo) | $($outcomeMap[$r.Status]) | $($r.Ahead) | $conf | $(Format-Pr $pr) | $(Format-TechStory $pr) |")
    }
    $md.Add('')
}

if ($conflicted.Count -gt 0) {
    $md.Add('## Conflicts resolved')
    $md.Add('')
    $md.Add('Resolved by hand before the sync branch was pushed.')
    $md.Add('')
    foreach ($r in $conflicted) {
        $pr = if ($prByRepo.ContainsKey($r.Repo)) { $prByRepo[$r.Repo] } else { $null }
        $branch = Get-Prop $pr 'syncBranch'
        $note = Get-Prop $pr 'note'
        $head = "- **$(Esc $r.Repo)**"
        if ($branch) { $head += " — via ``$(Esc $branch)``" }
        $md.Add($head)
        foreach ($f in @($r.Conflicts)) { $md.Add("  - ``$(Esc $f)``") }
        if ($note) { $md.Add("  - $(Esc $note)") }
    }
    $md.Add('')
}

if ($upToDate.Count -gt 0) {
    $md.Add('## Already up to date')
    $md.Add('')
    $md.Add("No action needed — ``$dst`` already contained everything on ``$src``.")
    $md.Add('')
    $md.Add(($upToDate | ForEach-Object { Esc $_.Repo }) -join ', ')
    $md.Add('')
}

if ($skipped.Count -gt 0) {
    $md.Add('## Not applicable')
    $md.Add('')
    $md.Add('| Repo | Reason |')
    $md.Add('| --- | --- |')
    foreach ($r in $skipped) {
        # "missing branch: team/1.2.0" -> "no `team/1.2.0` branch in this repo"
        $reason = Esc $r.Detail
        if ($reason -match '^missing branch:\s*(.+)$') {
            $branches = ($Matches[1] -split ',\s*' | ForEach-Object { "``$_``" }) -join ' and '
            $reason = "no $branches branch in this repo"
        }
        $md.Add("| $(Esc $r.Repo) | $reason |")
    }
    $md.Add('')
}

if ($pending.Count -gt 0) {
    $md.Add('## Waiting on a prior hop')
    $md.Add('')
    $md.Add('This chain run does not go past an earlier hop until that hop has actually landed ' +
        '(checked with `git merge-base --is-ancestor`, not assumed from a PR merely being open). ' +
        'Re-scan this hop once the PR named below is merged.')
    $md.Add('')
    $md.Add('| Repo | Waiting on |')
    $md.Add('| --- | --- |')
    foreach ($r in $pending) {
        $md.Add("| $(Esc $r.Repo) | $(Esc $r.Detail) |")
    }
    $md.Add('')
}

if ($locked.Count -gt 0) {
    $md.Add('## Locked (excluded)')
    $md.Add('')
    $md.Add('One of the two branches is locked in Azure DevOps. A locked branch cannot receive a ' +
        'push — including a PR completion — so nothing was scanned any further here.')
    $md.Add('')
    $md.Add('| Repo | Detail |')
    $md.Add('| --- | --- |')
    foreach ($r in $locked) {
        $md.Add("| $(Esc $r.Repo) | $(Esc $r.Detail) |")
    }
    $md.Add('')
}

if ($attention.Count -gt 0) {
    $md.Add('## Needs attention')
    $md.Add('')
    $md.Add('| Repo | Problem |')
    $md.Add('| --- | --- |')
    foreach ($r in $attention) {
        $md.Add("| $(Esc $r.Repo) | $(Esc $r.Detail) |")
    }
    $md.Add('')
}

$missingPr = @($synced | Where-Object { -not $prByRepo.ContainsKey($_.Repo) })
if ($missingPr.Count -gt 0) {
    $md.Add('> **Incomplete:** no pull request recorded for ' +
        (($missingPr | ForEach-Object { Esc $_.Repo }) -join ', ') +
        '. These repos still need a PR before the sync is done.')
    $md.Add('')
}

$md.Add('---')
$md.Add('')
$md.Add("<sub>Conflicts were detected up front with ``git merge-tree`` before any branch was pushed. " +
    "Each repo is versioned independently, so every row is a separate pull request.</sub>")

$outDir = Split-Path -Parent $OutputPath
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

$text = ($md -join "`n")
Set-Content -Path $OutputPath -Value $text -Encoding utf8

Write-Host ''
Write-Host "Sync report written to:" -ForegroundColor Cyan
Write-Host "  $OutputPath"
Write-Host ''
Write-Host ("{0} synced · {1} PR(s) · {2} up to date · {3} not applicable · {4} waiting on a prior hop · {5} locked · {6} needing attention" -f
    $synced.Count, $prCount, $upToDate.Count, $skipped.Count, $pending.Count, $locked.Count, $attention.Count)
if ($missingPr.Count -gt 0) {
    Write-Host "WARNING: $($missingPr.Count) synced repo(s) have no PR recorded." -ForegroundColor Yellow
}

if ($PassThru) {
    Write-Host ''
    Write-Host $text
}

exit 0
