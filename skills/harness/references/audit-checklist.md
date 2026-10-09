# Harness audit checklist

Run the coverage script first (mechanical), then work through the drift checks (judgment).
Findings go in the report format at the bottom. Report; fix only when asked.

## 1. Coverage (scripted)

```
powershell -NoProfile -ExecutionPolicy Bypass -File <this-skill-dir>/scripts/audit-coverage.ps1 -Root <root>
```

Flags per repo: missing `CLAUDE.md`, missing `.claude/settings.json`, repos absent from the
root repo map, project skills absent from the root catalogue.

## 2. Drift checks (judgment)

Work top-down; each check names the failure it catches.

**Root CLAUDE.md**
- [ ] Repo map table matches the actual folders — no ghost rows (deleted repos), no missing
      rows (new repos). *Catches: sessions planning work against repos that don't exist.*
- [ ] Every `@import` target exists. *Catches: silently missing shared context.*
- [ ] Skills catalogue matches `.claude/skills/` one-to-one, and each description still matches
      what the skill does. *Catches: sessions reaching for renamed/removed skills, or never
      discovering new ones.*
- [ ] Branching/deploy rules still match the pipelines. *Catches: commits to branches that
      trigger the wrong deployment.*
- [ ] Environment notes (domains, ports, config locations) spot-checked against one real
      config. *Catches: debugging against the wrong environment.*

**Per-repo CLAUDE.md (sample 2–3 repos, or all if asked)**
- [ ] Build and test commands actually run. *The single most valuable check — run them.*
- [ ] No references to projects/folders that no longer exist.
- [ ] Date-stamped facts older than ~6 months: still true? Re-stamp or delete.

**settings.json (root and repos)**
- [ ] Every hook's script file exists and runs cleanly by hand. *Catches: every session
      starting with a hook error.*
- [ ] Allowlist entries reference tools/commands still in use (e.g. MCP tools that still
      exist). Dead entries out.
- [ ] On Windows: `Bash(...)`/`PowerShell(...)` entries are mirrored.
- [ ] Nothing state-changing has crept into `allow` (pushes, installs, migrations, deletes).

**Spec harness (only where `.claude/sdd.json` or a spec tree exists)**
- [ ] Root CLAUDE.md has the spec workflow section and it names the right ADO org/project.
      *Catches: sessions mirroring requirements from the wrong project.*
- [ ] `.claude/sdd.json` exists, `specRoot` points at a real folder, and the CLAUDE.md
      `<!-- sdd:begin -->` block matches it (one block only). *Catches: `/sdd` flows failing at the
      first step.* Anything missing → `/sdd init`.
- [ ] Allowlist has the read-only ADO MCP tools and **no** write tools. *Catches: prompt fatigue
      on reads; unattended writes without a revision guard.*
- [ ] Every spec folder is `<ado-id>-<slug>` and every `requirements.md` has frontmatter — the
      coverage script checks this. *Catches: specs invisible to the sync and impact index.*
- [ ] Spot-check that no `requirements.md` has been hand-edited (compare against the work item).
      *Catches: repo-authored intent that ADO will overwrite and nobody will notice.*
- [ ] Freshness against live ADO is **not** this audit's job — run `/sdd sync`.

**Cross-cutting**
- [ ] No fact is duplicated between root and repo files (they will diverge — pick one home).
- [ ] No secrets anywhere in CLAUDE.md or settings files.
- [ ] If auto-memory is in use: no CLAUDE.md fact contradicts a memory file (stale one loses).

## 3. Report format

```markdown
# Harness audit — <root> — <date>

## Coverage
<script output table>

## Drift findings
| # | Severity | Where | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | high | root CLAUDE.md | repo X missing from map | add row |

Severity: **high** = misleads sessions into wrong actions (dead commands, wrong branch rules);
**medium** = missing context that costs time (uncovered repo, uncatalogued skill);
**low** = hygiene (dead allowlist entry, unstamped fragile fact).

## Recommendations
1. <ranked, most impactful first — usually: cover the uncovered, then fix the lies, then hygiene>
```
