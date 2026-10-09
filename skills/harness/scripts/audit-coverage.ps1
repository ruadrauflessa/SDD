<#
.SYNOPSIS
  Scans a repo or multi-repo workspace for Claude Code harness coverage.

.DESCRIPTION
  Multi-repo mode (default when the root contains child git repos): reports, per repo,
  whether CLAUDE.md and .claude/settings.json exist, how many skills it carries, and
  whether the repo is mentioned in the root CLAUDE.md. Also flags project skills that
  are missing from the root CLAUDE.md catalogue.
  Single-repo mode (root itself is a git repo, no child repos): audits just the root.

.PARAMETER Root
  Workspace or repo root. Defaults to the current directory.

.PARAMETER Quiet
  Print nothing when healthy; print only the gap list when drift is found.
  Intended for use as a SessionStart hook.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File audit-coverage.ps1 -Root C:\src\MyWorkspace
#>
param(
    [string]$Root = (Get-Location).Path,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$gaps = New-Object System.Collections.Generic.List[string]
$rows = New-Object System.Collections.Generic.List[object]

function Count-Skills([string]$dir) {
    if (-not (Test-Path $dir)) { return 0 }
    return @(Get-ChildItem -Path $dir -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') }).Count
}

# Child repos may sit directly under the root, or one level deeper in a container
# folder (e.g. projects/<repo>) — scan both so nested workspace layouts aren't missed.
$skipDirs = @('node_modules', '.git', 'bin', 'obj', 'dist', 'artifacts', 'temp', '.vs', '.vscode')
$topLevel = @(Get-ChildItem -Path $Root -Directory -Force |
    Where-Object { $skipDirs -notcontains $_.Name })

$found = New-Object System.Collections.Generic.List[object]
foreach ($dir in $topLevel) {
    if (Test-Path (Join-Path $dir.FullName '.git')) {
        $found.Add($dir)
    } else {
        # container folder: look one level deeper for repos
        Get-ChildItem -Path $dir.FullName -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $skipDirs -notcontains $_.Name -and (Test-Path (Join-Path $_.FullName '.git')) } |
            ForEach-Object { $found.Add($_) }
    }
}
$repoDirs = @($found.ToArray())
$isWorkspace = $repoDirs.Count -gt 0

if (-not $isWorkspace) {
    if (Test-Path (Join-Path $Root '.git')) {
        $repoDirs = @(Get-Item $Root)
    } else {
        Write-Output "No git repos found under $Root (neither the folder itself nor its children)."
        exit 0
    }
}

$rootClaudePath = Join-Path $Root 'CLAUDE.md'
$rootClaudeContent = ''
if (Test-Path $rootClaudePath) { $rootClaudeContent = Get-Content $rootClaudePath -Raw }

foreach ($repo in $repoDirs) {
    $hasClaudeMd = Test-Path (Join-Path $repo.FullName 'CLAUDE.md')
    $hasSettings = Test-Path (Join-Path $repo.FullName '.claude\settings.json')
    $skills = Count-Skills (Join-Path $repo.FullName '.claude\skills')

    $claudeCell = 'MISSING'
    if ($hasClaudeMd) { $claudeCell = 'yes' }
    $settingsCell = 'MISSING'
    if ($hasSettings) { $settingsCell = 'yes' }
    $mapCell = '-'
    if ($isWorkspace -and $rootClaudeContent -ne '' -and $repo.FullName -ne $Root) {
        if ($rootClaudeContent.Contains($repo.Name)) { $mapCell = 'yes' } else { $mapCell = 'NOT LISTED' }
    }

    $rows.Add([pscustomobject]@{
        Repo        = $repo.Name
        'CLAUDE.md' = $claudeCell
        'settings'  = $settingsCell
        'skills'    = $skills
        'inRootMap' = $mapCell
    })

    if (-not $hasClaudeMd) { $gaps.Add("$($repo.Name): no CLAUDE.md") }
    if (-not $hasSettings) { $gaps.Add("$($repo.Name): no .claude/settings.json") }
    if ($mapCell -eq 'NOT LISTED') { $gaps.Add("$($repo.Name): not mentioned in root CLAUDE.md") }
}

if ($isWorkspace) {
    if ($rootClaudeContent -eq '') { $gaps.Add('workspace root: no CLAUDE.md') }
    if (-not (Test-Path (Join-Path $Root '.claude\settings.json'))) { $gaps.Add('workspace root: no .claude/settings.json') }

    # Project skills missing from the root catalogue
    $skillsDir = Join-Path $Root '.claude\skills'
    if ($rootClaudeContent -ne '' -and (Test-Path $skillsDir)) {
        Get-ChildItem -Path $skillsDir -Directory | ForEach-Object {
            if ((Test-Path (Join-Path $_.FullName 'SKILL.md')) -and (-not $rootClaudeContent.Contains($_.Name))) {
                $gaps.Add("skill '$($_.Name)' not mentioned in root CLAUDE.md catalogue")
            }
        }
    }
}

# Spec harness (only where a spec tree exists). Structure only — freshness against live ADO is
# `/sdd sync`. The spec folder is `specRoot` from <Root>\.claude\sdd.json, else docs/spec.
$specRel = 'docs/spec'
$sddJson = Join-Path $Root '.claude\sdd.json'
if (Test-Path $sddJson) {
    try {
        $cfg = Get-Content -LiteralPath $sddJson -Raw | ConvertFrom-Json
        if ($cfg.specRoot) { $specRel = [string]$cfg.specRoot }
    } catch { $gaps.Add('.claude/sdd.json is not valid JSON') }
}
$specRoots = @()
foreach ($repo in $repoDirs) {
    $sd = Join-Path $repo.FullName $specRel
    if (Test-Path $sd) { $specRoots += [pscustomobject]@{ Repo = $repo.Name; Dir = $sd } }
}
if ($isWorkspace) {
    $sd = Join-Path $Root $specRel
    if (Test-Path $sd) { $specRoots += [pscustomobject]@{ Repo = '(root)'; Dir = $sd } }
}

$specCount = 0
foreach ($sr in $specRoots) {
    $folders = @(Get-ChildItem -Path $sr.Dir -Directory -Recurse -Force -ErrorAction SilentlyContinue)
    foreach ($f in $folders) {
        $req = Join-Path $f.FullName 'requirements.md'
        $hasReq = Test-Path $req
        $hasChildSpecs = @(Get-ChildItem -Path $f.FullName -Directory -ErrorAction SilentlyContinue).Count -gt 0

        if ($f.Name -notmatch '^(\d+)(-[a-z0-9-]+)?$') {
            $gaps.Add("$($sr.Repo): spec folder '$($f.Name)' is not <ado-id>-<slug>")
            continue
        }
        if (-not $hasReq) {
            if (-not $hasChildSpecs) { $gaps.Add("$($sr.Repo): spec folder '$($f.Name)' has no requirements.md") }
            continue
        }

        $specCount++
        $head = (Get-Content -LiteralPath $req -TotalCount 40) -join "`n"
        if ($head -notmatch '(?m)^\s*primary:\s*(\d+)') {
            $gaps.Add("$($sr.Repo): $($f.Name)/requirements.md has no ADO frontmatter")
        } elseif ([int]$Matches[1] -ne [int]($f.Name -replace '^(\d+).*$', '$1')) {
            $gaps.Add("$($sr.Repo): $($f.Name)/requirements.md primary id does not match its folder")
        }

        foreach ($companion in @('design.md', 'tasks.md')) {
            $p = Join-Path $f.FullName $companion
            if ((Test-Path $p) -and (((Get-Content -LiteralPath $p -TotalCount 5) -join "`n") -notmatch 'ado_id:\s*\d+')) {
                $gaps.Add("$($sr.Repo): $($f.Name)/$companion has no ado_id join key")
            }
        }
    }
}

if ($Quiet) {
    if ($gaps.Count -gt 0) {
        Write-Output "Claude harness drift detected under ${Root}:"
        $gaps | ForEach-Object { Write-Output "  - $_" }
    }
    exit 0
}

Write-Output "Harness coverage for $Root"
if ($isWorkspace) {
    $rootClaudeState = 'MISSING'
    if ($rootClaudeContent -ne '') { $rootClaudeState = 'yes' }
    $rootSettingsState = 'MISSING'
    if (Test-Path (Join-Path $Root '.claude\settings.json')) { $rootSettingsState = 'yes' }
    $rootSkills = Count-Skills (Join-Path $Root '.claude\skills')
    Write-Output "Workspace root: CLAUDE.md=$rootClaudeState  settings.json=$rootSettingsState  skills=$rootSkills"
}
$rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Output

if ($specRoots.Count -gt 0) {
    Write-Output "Spec harness: $specCount spec(s) across $($specRoots.Count) spec tree(s) ($specRel). Freshness against ADO: run /sdd sync."
    Write-Output ''
}

if ($gaps.Count -gt 0) {
    Write-Output 'Gaps:'
    $gaps | ForEach-Object { Write-Output "  - $_" }
} else {
    Write-Output 'No gaps found.'
}
