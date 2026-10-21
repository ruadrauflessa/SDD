# sdd plugin — working on this repo

A Claude Code plugin: spec-driven development on Azure DevOps work items. The skills are read by
an agent at run time, the scripts do the mechanics, the hooks enforce the rules. `README.md` has
the user's view; this file is for working on the plugin itself.

## Versioning

- Bump the plugin version in `.claude-plugin/plugin.json` only when raising a PR, as part of that PR.
  Never bump it with an ordinary change or commit.

## Where things live

| Path | What |
| --- | --- |
| `skills/sdd/` | The `/sdd` router, `help/help.html` (the one help page: first-time walk-through and every command; `env.py help` copies it, and `help/hooks-picasso.jpg` the hooks picture it shows, into the workspace, because Desktop cannot open files in the plugin cache; the prompt that regenerates the picture is in the page's "The hooks in a picture" section), and `references/flow-rules.md` — the rules both flows share (Abandon, Decision briefs, bugs this work did not cause, checkpoints, stage guards, proof runs, resuming, sub-agents). Change a shared rule there, once |
| `skills/bug/`, `skills/spec/` | Each flow: `SKILL.md` is the outline (rules, gates, stage index); each stage's steps are in `phases/NN-*.md` / `modes/*.md` |
| `skills/request/` | Ai Agent Request triage: report on a hand-over, ask spec or bug, route the work (`spec.py request` / `route`), then hand over to that flow. No stages of its own: `route.json` in the request's spec folder is its record |
| `skills/help/` | `/sdd:help`: a thin skill that sends the same page as `/sdd:sdd` with no arguments; the steps live once, in `skills/sdd/SKILL.md` |
| `skills/pre-pr-verify/` | The bug flow's Phase 11 helper ("start the environment"): brings the stack up from a work item's worktrees and proves the worktree build answers. `env.py stack` finds the worktrees, the run script and its flags and the workspace facts; `env.py stack-gate` is Gate D. `hooks/edit_guard.py` refuses a new launcher in the workspace's shared `scripts/` (it goes in `.claude/scripts/`) |
| `skills/next/`, `sync/`, `impact/`, `harness/`, `visual/`, `workspace/` | The other skills. `visual/` is a fork of visual-explainer (MIT) |
| `scripts/flows.json` | **The source of truth for the flows**: stages, gates each stage needs and passes, stops, `doc` (the stage file `env.py can` prints), `proofs`, `paths`. Scripts, hooks and the view all read it |
| `scripts/env.py` | Work item folders, worktrees, progress, gates, stage guards, proofs, PRs |
| `scripts/graphfocus.py` | `env.py graph-focus`: which nodes of graphify's graph the design (`design.md`, `tasks.md`) or the changed lines touch, and the script injected into graphify's `graph.html` that lights them. Pure functions; `lens` in `flows.json` says what each stage lights |
| `scripts/spec.py` | The ADO mirror and index, impact, rev-tested ADO writes, `next`, metrics.json, Ai Agent Request `request` / `route` |
| `scripts/sddlib.py` | Shared helpers, `DEFAULTS` for `.claude/sdd.json`, config upgrade, the output style install |
| `scripts/adowrite.py`, `proof.py`, `nextpick.py`, `metrics.py`, `anchors.py` | ADO writes; recorded test runs; next-item rules; metrics.json; design.md's Affected components checked against the code graph (`env.py anchors`, the proof "Design agreed" needs) — logic as plain functions, tested without ADO |
| `scripts/bugs/` | The bug manager's mechanics (`/sdd-bugs`), in PowerShell: `Sync-Bugs`, `Get-BugDetail`, `Save-BugChanges` (rev-tested batch writes), `Find-BugEvidence` (git, no tokens); `BugsCommon.ps1` is what they share, `defaults.json` the one source of the `bugs` settings (sddlib, the scripts and the view all read it) |
| `scripts/fakeado.py` | Offline ADO for tests and evals: on when `SDD_FAKE_ADO` names a JSON world file |
| `hooks/` | `run.cmd` (every hook in `hooks.json` runs through it: one file that sh (Git Bash on Windows) and cmd.exe both read, which finds a real Python 3.9+ and skips Windows' Microsoft Store stand-in; keep it LF, executable, and without `goto`), `question_guard.py`, `agent_guard.py`, `edit_guard.py`, `graph_use.py` (the graph first: rebuilds a stale graph before any read of it, refuses a search of a work item's code until that caller asked the graph in the stage, and counts both in `graph-use.jsonl`), `spec_use.py` (meaning first: while Ollama is on, refuses a grep of the spec folder until that caller ran `spec.py query search` or `similar` in the turn; the runs go in `.claude/sdd/spec-use.jsonl`), and `register.tsx` + `view/model.ts` (the sdd view, a mod), `view/worktrees.ts` (pure helpers of the `/sdd-worktrees` page, whose hooks live in `register.tsx`), `view/bugs.ts` (pure helpers of the `/sdd-bugs` bug manager: categories, filters, staged changes, the probable-cause prompt), `view/settings.ts` (pure helpers of its ⚙ Config panel: the draft, the fields, the category rules, and `applyToSdd` / `applyToDevelopers`, which write only changed keys) |
| `agents/` | `investigator` and `skeptic`, the read-only sub-agents |
| `evals/` | `claude plugin eval` cases; `_fixtures/workspace.py` builds each case's workspace |
| `repowatch/` | A second, standalone plugin (sdd depends on it, same marketplace): tracks many git repos and worktrees. `scripts/repowatch.py` does the git mechanics and writes `.claude/repowatch/state.json`; `hooks/register.tsx` draws the pane and status line from it, and runs a clean-up only after `plan`, a confirm and `apply` (which re-checks). Has its own `plugin.json` and version |
| `devops/` | A third, standalone plugin (same marketplace; needs neither sdd nor repowatch): `release-prep`, `sync-team-branches`, `release-notes`. The skills are outlines; `scripts/devops.py` does the mechanics (it wraps the skills' PowerShell scans, `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/...`, and reads and writes ADO over REST with an `az` token): `devopslib.py` (config `.claude/devops.json`, git, the ADO client, plans and approvals, the outbound lint), `notes.py` (the release-notes file and wiki page), `prs.py` (PR texts), `reviews.py` (the Reviews tab: who waits, may you vote, the diff bundle, comment threads), `pipelines.py` (the newest build per pipeline and its failed step, what each environment runs now, `doctor`'s checks), `fakeado.py` (offline ADO: `DEVOPS_FAKE_ADO`). `hooks/` holds the guards (`git_guard.py` branches, working tree, az; `edit_guard.py`; `outbound_guard.py` the ADO MCP writes; `approval_hook.py` records the user's Yes to a `(plan <token>)` question) and the `/devops` pane (`register.tsx`, pure helpers in `view/model.ts`, `view/reviews.ts` and `view/pipelines.ts`). State lives in `<workspace>/.claude/devops/`. Has its own `plugin.json` and version. `devops/references/writing-style.md` is its own copy of the house writing style (`skills/bug/references/writing-style.md` is sdd's), so devops works without sdd; keep the ten rules and the word swaps in step |
| `assets/output-styles/ELI5.md` | The output style installed globally (kept outside `output-styles/` on purpose) |

## Checks to run

```
python scripts/test_sdd.py
python scripts/test_proof.py         # needs git; real worktrees in temp folders
python scripts/test_fakeado.py       # the real commands against the offline ADO
python scripts/test_bugs.py          # needs pwsh or powershell; the bug scripts against the offline ADO over HTTP,
                                     # and a PowerShell 5.1 compatibility check when PSScriptAnalyzer is installed
python scripts/check_evals.py        # needs PyYAML; checks the eval cases, runs nothing
python hooks/test_question_guard.py
python hooks/test_agent_guard.py
python hooks/test_edit_guard.py
python hooks/test_graph_use.py
python hooks/test_spec_use.py
python repowatch/scripts/test_repowatch.py   # needs git; real repos in temp folders
python devops/scripts/test_devops.py # needs git; the scan commands need pwsh (skipped without it); offline ADO
python devops/hooks/test_guards.py   # needs git; every guard rule through the hook's stdin/exit code
python devops/scripts/check_ado_routes.py   # needs the network (no sign-in): each ADO call devops makes is a route ADO serves
claude plugin test repowatch         # also mounts and presses the pane (hooks/pane.test.ts)
claude plugin validate repowatch
claude plugin test devops            # the /devops pane (hooks/pane.test.ts mounts and presses it) and view/model.ts
claude plugin validate devops
claude plugin test .                 # the view (model tests and hooks/pane.test.ts, which mounts the pane) and the Worktrees page; it also finds repowatch's tests, whose pane tests stand down (the plugin under test is sdd)
claude plugin validate .             # the author warning is expected
uv run --no-project --python 3.9 python scripts/test_sdd.py   # and the other python tests: the oldest Python the users run
```

All of them should pass before a commit. Never run `claude plugin eval` yourself: it needs the user
to trust the plugin directory, and each case is a paid agent run. A full TypeScript check of
`register.tsx` fails here (the mod types in `.claude-plugin/types` are generated on a dev machine);
`model.ts` and `types/` check on their own.

## Rules for changes

- **Scripts are standard library only and must run on Python 3.9 and on Windows.** A third-party module may only
  speed a path up (`spec.top_similar` uses numpy when it is there), never be needed. The users run
  PowerShell on Windows: no shell-only paths, no 3.10+ syntax (`match`, `X | Y` types, a quote in an
  f-string's `{}` that matches its own quotes).
- **A test removes everything it creates.** Temp files go in a `TemporaryDirectory` (or `scratch()` in `test_sdd.py`, which also
  moves the working folder back out, closes open SQLite handles and waits out a Windows lock); a `delete=False` file is
  unlinked in a `finally`. Never `ignore_cleanup_errors`: it is 3.10+, and it hides the leak instead of fixing it.
- **Mechanics go in a script, judgement in a skill.** If a rule can be checked, the script enforces
  it (`env.py can`, `progress --passed`, `env.py pr`) rather than the skill text asking for it.
- **ADO writes only through `adowrite.py`** (`spec.py claim | handover | sprint | comment | route`): every
  patch is rev-tested. Never a `#<id>` in text ADO stores — it posts a mention; write `ADO <id>`. The one
  other writer is the bug manager's `scripts/bugs/Save-BugChanges.ps1` (the person asked for PowerShell
  there): it keeps the same rules (a `test /rev` op, re-read and decide again on 412, no `#<id>`).
  **A tag list is changed with `replace`, never `add`**: ADO merges an `add` on `System.Tags` into the tags the item has, so only a
  `replace` takes a tag off (`fakeado` does the same, and `test_fakeado.py` pins it).
- **The bug scripts run on Windows PowerShell 5.1 too**: no `??`, `?:`, `-AsHashtable` or `&&`; ASCII only
  (5.1 reads a file without a BOM as ANSI; `test_bugs.py` checks); JSON written without a BOM.
- **Renaming or renumbering a stage** touches `flows.json` (key, `doc`, `reworkTo`), the stage file,
  the skills, `view.test.ts`, the tests, and old `workitem.json` records (see
  `sddlib.renumber_bug_phases` for how the bug phases were migrated on read).
- **New `sdd.json` keys** go in `sddlib.DEFAULTS` and the `load_config` merge; add them to
  `UPGRADE_KEYS` when a person should find them in the file to tune.
- **Skill text is for a tired reader**: short sentences, active voice, exact paths and commands.
  A skill's `SKILL.md` stays an outline; stage detail goes in the stage's own file.
- **The code graph is a hard dependency.** `env.py new` fails without one, stages that read code need the derived `Graph`
  gate (and a current graph to start), and `hooks/graph_use.py` refuses code searches until the graph was asked and
  rebuilds it before every read. The build record lives in `graph/built.json`, never in `workitem.json`: the hooks
  rebuild in the background and must not race a progress write. `--no-graph` is for the tests' fixtures only.
- **repowatch deletes nothing on a remote except a stale `sync/<x>-<y>` branch.** `remote_delete_refusal` in
  `repowatch/scripts/repowatch.py` refuses every other deleting `git push` (and `--mirror`, `--prune`), and
  `test_remote_deletes` pins it. A new action must not route around `git()` for pushes.
- **devops writes nothing outward without the user's approved plan.** A release or sync PR and a `/Release Notes` wiki page
  go out only from a plan (`devopslib.save_plan`, token = hash of its items) that the user approved: their Yes to the printed
  `(plan <token>)` question (`hooks/approval_hook.py`) or Approve in the pane. The agent cannot approve (`git_guard.py`), and
  `outbound_guard.py` holds the ADO MCP tools to the same plans. A developer's own PR is not devops': only the secrets check
  applies there. A new outward write goes through a plan too, and its text through `lint_outbound`.
  Review comments and votes are the one exception, because they go out under the person's own name: only the pane's
  Reviews tab sends them, on the person's press after a confirm, and `git_guard.py` refuses `devops.py reviews post|vote|save`
  to the agent. The quick review is the pane's one model call (`reviews.model`), on a press.
- **The view must load on the engine the Desktop app ships, not only the newest.** The Desktop app runs its own, older
  Claude Code (2.1.295 when this was written). On it, a mod that passes `$` or `on` into a function from another file, or
  calls a mods API method the engine lacks (`$.ui.view` is 2.1.300+), is refused whole, and nothing of it shows. Keep `$`
  and `on` in `register.tsx`; put pure code in `view/`. Before a PR, run `claude plugin validate .` and `claude plugin test .`
  on that engine too: `npm i @anthropic-ai/claude-code@<version>` in a temp folder and run its `claude`.
- **The view is for the Claude Desktop app only.** A mod cannot refuse to load, so it stays out of the way: `setupDesktop`
  (commands, first read, cost baseline, timers) runs from `session.start` and `session.attach` when a Desktop app is
  attached, every draw hook returns `next(e)` unless `e.surface === 'desktop'`, and every other hook passes through until
  setup ran. Never set up from a draw hook: the engine refuses state writes while a draw is dispatched.
  The view opens itself at a Desktop session's start (`openAtSessionStart`, from `setupDesktop`; once per session, `sdd.startOpened`) unless the `openAtStart`
  option (`userConfig` in `plugin.json`, a row in `/config`) is off or the workspace's `view.autoOpen` is false.
- **The view writes one thing**: what each turn cost, in dollars and tokens, through `env.py cost` (one appended
  line in the item's `cost.jsonl`; `view` reports the totals). Otherwise `register.tsx` reads `env.py view` and posts the user's
  messages. It never passes a gate or runs another state-changing command; the one exception is `env.py graph-focus` (the **Open code graph** button), which writes only files under the item's `graph/`. The bug manager (`/sdd-bugs`) is
  apart: it writes the staged changes to `<bugs folder>/pending.json` and a probable cause to `items/<id>.analysis.json`,
  and runs the bug scripts on the person's press; its one model call is the probable cause, on a press. Its ⚙ Config
  panel is the one place the view writes config: on Save it rewrites `.claude/sdd.json` (only the `bugs` keys that
  changed) and the dev team file, each read fresh first and refused if it is not valid JSON. A new `bugs` key needs a
  `FIELDS` entry in `view/settings.ts` (or a place in the category rules) to show in the panel.
