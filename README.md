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
- the review stage (spec: Review, bug: Phase 13) has **Approved**, **Merged** and **Rejected**;
- a worktree opens in File Explorer or VS Code from its box.

## Configure (`.claude/sdd.json`)

```json
"view": {
  "autoOpen": true,
  "colors": { "done": "#3f9a63", "now": "#c98a12", "hoverText": "#ffffff" }
}
```

`skills/workspace/SKILL.md` lists every key.

## Layout

| Path | What |
| --- | --- |
| `skills/` | `sdd` (entry), `spec`, `bug`, `sync`, `impact`, `harness`, `visual`, `workspace` |
| `agents/` | `investigator` (read-only code search) and `skeptic` (independent review of a root cause, a test or a design), used by the bug and spec flows |
| `scripts/` | `env.py` (work item folders, state guards, progress), `spec.py` (ADO mirror, impact), `flows.json` (the stages of each flow) |
| `hooks/` | `hooks.json`, `question_guard.py` (links before every question), `agent_guard.py` (keeps the sdd agents' git use read-only), `register.tsx` + `view/` (the sdd view) |
| `types/` | The view's state contract |

## Develop

```
python scripts/test_sdd.py
python hooks/test_question_guard.py
python hooks/test_agent_guard.py
claude plugin validate .
claude plugin test .
```

`skills/visual` is a fork of visual-explainer 0.11.0 (MIT, see `skills/visual/LICENSE`).
