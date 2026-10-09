---
name: harness
description: 'Create, audit, and maintain a Claude Code harness — CLAUDE.md files, .claude/settings.json permission allowlists, hooks, skill placement, and MCP scope — for a single repo or a multi-repo workspace. Invoked by the sdd skill for `/sdd harness <create|onboard|audit|maintain>`; also use whenever the user wants to set up Claude Code for a repo or workspace, write or review a CLAUDE.md, onboard a new repo, audit harness coverage or drift, cut down permission prompts with an allowlist, or decide where something belongs (global vs project skill, settings.json vs settings.local.json, root vs repo CLAUDE.md, user vs project MCP scope). Also covers the sdd workflow''s own footprint (the spec folder, `.claude/sdd.json`, the CLAUDE.md sdd block, ADO read-only allowlist entries) — but not running that workflow, which is the other sdd skills'' job.'
---

# sdd:harness — Claude Code harness

Run it as `/sdd harness <operation>`: `create`, `onboard`, `audit` or `maintain`. No operation →
ask with `AskUserQuestion` which one, recommending the one that fits the workspace's state.
Scripts are in `${CLAUDE_PLUGIN_ROOT}/skills/harness/scripts/`.

A **harness** is everything that shapes how Claude Code behaves in a codebase before the first
prompt is typed. It has three layers:

| Layer | Lives at | Carries |
| --- | --- | --- |
| User | `~/.claude/` | global skills, user settings, MCP servers (user scope), auto-memory |
| Workspace / repo root | `<root>/CLAUDE.md` + `<root>/.claude/` | project context, permission allowlist, hooks, project skills |
| Sub-repo (multi-repo workspaces) | `<repo>/CLAUDE.md` + `<repo>/.claude/` | per-repo build/test/run commands and conventions |
| Spec workflow (where sdd is in use) | `{specRoot}` from `.claude/sdd.json` | per-work-item requirements mirror, design, tasks — owned by the `sdd:spec` and `sdd:sync` skills |

The root `CLAUDE.md` (plus anything it `@imports`) is loaded into **every session** — it is a
per-session context tax, so every line must earn its place. Sub-directory `CLAUDE.md` files are
pulled in when Claude works on files in that subtree, so repo-specific detail belongs there, not
at the root.

## Pick your operation

| Situation | `/sdd harness …` |
| --- | --- |
| Repo/workspace has no harness yet | **Create** (`create`) |
| Workspace has a harness; a new repo joined it | **Onboard** (`onboard`) |
| "Is the harness healthy / complete / current?" | **Audit** (`audit`) |
| Something changed (skill added, commands changed, prompts annoying) | **Maintain** (`maintain`) |

## Principles (read before any mode)

1. **Only verified facts.** Never write a build/test/run command into a CLAUDE.md without
   running it first. A wrong command in CLAUDE.md is worse than none — every future session
   trusts it.
2. **Only what Claude can't infer.** Claude can read code, list folders, and find configs.
   CLAUDE.md is for what that *won't* reveal: commands, ports, environment quirks, deploy rules,
   conventions that deviate from defaults. If `ls` or a 30-second read answers it, leave it out.
3. **Lean beats complete.** A 400-line CLAUDE.md gets skimmed; an 80-line one gets followed.
   Push depth into imported/linked files (loaded on demand) rather than the root file.
4. **The harness is code.** It drifts like code. Update it in the same commit as the change
   that invalidated it, and audit it when repos, skills, or pipelines change.

## Mode: Create

**For a single repo:**

1. **Gather facts by doing, not guessing.** Detect the stack (solution/package files), then
   actually run the build, the tests, and — if cheap — the app. Note ports, env-config
   locations, anything that failed the first time and why.
2. **Write `CLAUDE.md`** from `assets/repo-CLAUDE.md.template`, following
   `references/claude-md-guide.md`. Target 60–120 lines; readable in under a minute.
3. **Write `.claude/settings.json`** from `assets/settings.json.template`, following
   `references/settings-guide.md`. Allowlist only commands you observed being needed
   (build/test/lint, read-only git). On Windows, mirror every `Bash(...)` entry with a
   `PowerShell(...)` entry — sessions use both shells.
4. **Don't scaffold empty skills.** Note repeated multi-step patterns as *candidates* and where
   each would live (see Placement below); create them later with a skill-authoring skill when
   the pattern has proven itself.
5. **Verify with fresh eyes.** Ask: would a session with zero prior context succeed at a routine
   task using only these files? Then run `scripts/audit-coverage.ps1` to confirm coverage.

**For a multi-repo workspace**, do root first, then repos:

1. Root `CLAUDE.md` from `assets/root-CLAUDE.md.template`: the repo map table ("read this
   first" — is the root itself a git repo? are commits per-repo?), cross-cutting rules
   (branching, environments), a one-line-per-skill catalogue, environment notes, and — where
   spec-driven development is in use — the spec workflow section (the `{specRoot}` convention, branch
   naming, the `ado_id` join key; for an sdd workspace that is the `<!-- sdd:begin -->` block from
   `/sdd init` — never write a second one). `@import`
   shared architecture docs (e.g. an existing `copilot-instructions.md`) instead of duplicating
   them — one source of truth serves every AI tool.
2. Root `.claude/settings.json`: the allowlist shared by all repos, plus any hooks.
3. Then a per-repo harness (steps above) for **every** repo — including test suites, scaffolds,
   and "empty" repos. A one-paragraph CLAUDE.md saying "early scaffold, no features, build with
   X" is cheap; a repo with nothing is where drift and wrong assumptions start.

## Mode: Onboard (new repo into an existing workspace)

1. Find the most similar sibling repo (same stack/shape) and mirror its `CLAUDE.md` structure
   and `settings.json` — consistency across repos is itself a feature.
2. Replace the facts: verify build/test/run in the *new* repo, don't inherit the sibling's.
3. Update the root `CLAUDE.md`: add the repo to the map table; add any new skills to the
   catalogue.
4. Run `scripts/audit-coverage.ps1` — it should come back clean.

## Mode: Audit

1. **Coverage scan (mechanical):**
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File ${CLAUDE_PLUGIN_ROOT}/skills/harness/scripts/audit-coverage.ps1 -Root <workspace-root>
   ```
   Reports per-repo CLAUDE.md / settings.json presence, skill counts, repos missing from the
   root repo map, and skills missing from the root catalogue.
2. **Drift check (judgment):** work through `references/audit-checklist.md` — stale repo tables,
   dead commands, broken `@import` targets, hook scripts that no longer exist, allowlist
   entries for removed tools, ports/domains that moved. Where sdd is in use, the checklist's
   spec-harness section covers the spec folder; staleness against live ADO is `/sdd sync`'s job,
   not this audit.
3. **Report, don't fix.** Deliver the findings in the checklist's report format, ranked by
   impact. Only apply fixes when the user asks (or asked up front).

## Mode: Maintain

React to events; don't wait for an annual cleanup:

| Event | Action |
| --- | --- |
| New repo added to workspace | Run **Onboard** |
| Skill added/removed in `.claude/skills` | Update the root CLAUDE.md catalogue (same sitting) |
| Build/test/run commands changed | Update that repo's CLAUDE.md in the same commit |
| Same safe command prompts for permission repeatedly | Add allowlist entry (both shells on Windows) |
| User corrects the same mistake twice | Encode it: CLAUDE.md if project-wide truth, auto-memory if personal/contextual |
| Pipeline/environment/ports changed | Update root CLAUDE.md environment notes + any port tables |
| Spec workflow adopted in a repo | Run `/sdd init` (it owns `.claude/sdd.json` and the CLAUDE.md sdd block), then add the ADO read-only allowlist entries |
| Branch convention or ADO project changed | Update `.claude/sdd.json` and the root CLAUDE.md sdd block in the same commit |
| Suspicion of rot, or quarterly | Run **Audit** |

**Standing drift check (optional):** wire the audit script into a `SessionStart` hook with
`-Quiet` — it prints nothing when healthy and a short gap list when not, so every session
self-reports drift. Setup in `references/settings-guide.md` § Hooks. Keep hooks fast (< a few
seconds) and silent-when-healthy; a noisy hook gets deleted.

## Placement: where does this thing go?

| Thing | Home |
| --- | --- |
| Workflow useful across projects (git, diagrams, ADO) | Global skill — `~/.claude/skills/` |
| Codebase-specific pattern (scaffolding, house conventions) | Project skill — `<root>/.claude/skills/` |
| Team-shared permissions & hooks | `.claude/settings.json` (committed) |
| Personal-only permissions/overrides | `.claude/settings.local.json` (gitignored) |
| Fact every session needs | `CLAUDE.md` |
| Long reference detail | Separate file, `@import`ed or linked from CLAUDE.md |
| Requirements and acceptance criteria | ADO work item (canonical) + mirrored `{specRoot}/**/<ado-id>-<slug>/requirements.md` — never authored in the repo |
| Technical design and task breakdown | Repo only — `design.md` / `tasks.md`, never pushed to ADO |
| Personal cross-session facts, in-flight work state | Auto-memory — never duplicate into CLAUDE.md |
| MCP server you want everywhere | User scope (`claude mcp add -s user`) |
| MCP server the whole team needs for one project | Project scope (`.mcp.json`, committed) |

## Bundled resources

| File | Read when |
| --- | --- |
| `references/claude-md-guide.md` | Writing or reviewing any CLAUDE.md |
| `references/settings-guide.md` | Writing allowlists, hooks, choosing settings vs settings.local, MCP scope |
| `references/audit-checklist.md` | Running an audit (step 2) or producing the report |
| `assets/repo-CLAUDE.md.template` | Creating a repo-level CLAUDE.md |
| `assets/root-CLAUDE.md.template` | Creating a workspace-root CLAUDE.md |
| `assets/settings.json.template` | Creating a settings.json |
| `scripts/audit-coverage.ps1` | Coverage scan (manual or as a SessionStart hook with `-Quiet`) |

## Questions

Ask with `AskUserQuestion`, never as plain text. The links-before-every-question rule of the `sdd`
skill applies only while a work item flow runs; harness work is workspace tooling, so no links
block is needed.
