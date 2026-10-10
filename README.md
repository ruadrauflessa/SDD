# sdd — spec-driven development for Claude Code

One Claude Code plugin for working Azure DevOps work items end to end: the spec flow (stories, tech
stories, change requests, features, epics) and the bug flow (bugs, issues), each with approval gates,
a git worktree per work item, an ADO spec mirror, impact analysis and visual pages. A side pane, the
**sdd view**, shows where the work item stands and what was decided at each stage, and why.

## Install

```
/plugin marketplace add ruadrauflessa/SDD
/plugin install sdd@sdd
```

Then, in each workspace (the folder above your repos), run `/sdd init` once. It checks Python 3, Node,
git, the Azure CLI login and the rest, and writes `.claude/sdd.json`.

The plugin also installs the **ELI5** output style (plain, short replies in ASD-STE100 Simplified
Technical English) as your global style: `~/.claude/output-styles/ELI5.md`, and `"outputStyle": "ELI5"`
in `~/.claude/settings.json`. It does this at the first session after the plugin is installed or
updated, and on `/sdd init`. Restart Claude Code to see it. It sets the style once: pick another in
`/config` and the plugin leaves your choice alone (`/sdd init` sets it again). A style file you edit
is kept; an unedited one is updated with the plugin.

Needs: Python 3.9+, Node 18+, git, the Azure CLI (`az login`). Optional: graphify (code graphs),
pandoc, Ollama (meaning search).

**Moving from the loose skills** (`~/.claude/skills/sdd*`): remove those folders and the two
`question_guard.py` entries from `~/.claude/settings.json`, or every question is checked twice.
`/sdd init` warns while the old entries are there.

## Use

| You type | What happens |
| --- | --- |
| `/sdd <id>` | Starts or resumes the work item, in the bug or spec flow by its type |
| `/sdd help` | A short tour |
| `/sdd status <id>` | Where the item stands |
| `/sdd <id> feedback <stage>: <text>` | Back to a done or waiting stage with your feedback |
| `/sdd-view [id]` | Opens the sdd view for this chat's work item (or the one given) |

The sdd view opens by itself the first time a chat takes up a work item. In it:

- each stage opens to its **Stage log**, its **gates** (what you were asked, what you answered, what
  was revoked), its documents and a **Give feedback** box;
- the review stage (spec: Review, bug: Phase 15) has **Approved**, **Merged** and **Rejected**;
- a worktree opens in File Explorer or VS Code from its box.

## Configure (`.claude/sdd.json`)

```json
"view": {
  "autoOpen": true,
  "colors": { "done": "#3f9a63", "now": "#c98a12", "hoverText": "#ffffff" }
}
```

```json
"agents": { "models": { "investigator": "sonnet", "skeptic": "opus" } }
```

`agents.models` picks the model of each sub-agent (`sonnet`, `opus` or `haiku`). A workspace without
it gets these defaults written into its `sdd.json` at the first session after the plugin updates;
values already set are kept. `skills/workspace/SKILL.md` lists every key.

## Layout

| Path | What |
| --- | --- |
| `skills/` | `sdd` (entry; `references/flow-rules.md` holds the rules both flows share), `spec` (outline + `modes/`), `bug` (outline + `phases/`), `sync`, `impact`, `harness`, `visual`, `workspace` |
| `agents/` | `investigator` (read-only code search) and `skeptic` (independent review of a root cause, a test or a design), used by the bug and spec flows; models from `agents.models` |
| `scripts/` | `env.py` (work item folders, state guards, progress, config upgrades), `spec.py` (ADO mirror, impact, rev-tested writes: claim, handover, sprint, comment), `adowrite.py` (those writes), `proof.py` (recorded test runs that gates need), `flows.json` (the stages of each flow) |
| `hooks/` | `hooks.json`, `question_guard.py` (links before every question), `agent_guard.py` (keeps the sdd agents read-only: no git writes, no `env.py` / `spec.py` runs), `edit_guard.py` (no edits in the main checkout during a flow), `register.tsx` + `view/` (the sdd view) |
| `assets/output-styles/` | `ELI5.md`, the output style the plugin installs globally |
| `types/` | The view's state contract |

## Develop

```
python scripts/test_sdd.py
python hooks/test_question_guard.py
python hooks/test_agent_guard.py
python hooks/test_edit_guard.py
python scripts/test_proof.py
claude plugin validate .
claude plugin test .
```

`skills/visual` is a fork of visual-explainer 0.11.0 (MIT, see `skills/visual/LICENSE`).
