# devops

Release and branch work on Azure DevOps repos: prepare a release, sync team branches, write release notes,
start the stack for manual testing. Standalone (same marketplace as sdd and repowatch; it needs neither).

```
/plugin install devops --marketplace ruadrauflessa/SDD
```

Needs Python 3.9+, git, PowerShell 7 (`pwsh`) for the scans, and `az login` (or a PAT in
`AZURE_DEVOPS_EXT_PAT`) for the ADO reads and writes. Without `az`, the skills fall back to the Azure DevOps
MCP tools (`references/mcp-fallback.md`), and the guards still hold.

## The skills

| Skill | Say | What happens |
| --- | --- | --- |
| `release-prep` | "prep the release", "prepare release 1.1.0" | one scan, one plan, your Yes, one PR per repo, hand-off to the notes |
| `sync-team-branches` | "sync team branches", "merge team/1.1.0 into team/1.2.0" | the version chain, a dry-run per hop, PRs for clean repos, a `sync/*` branch you resolve for conflicts, a report |
| `release-notes` | "generate release notes" | five questions at once, then a file in `documents/release-notes/` and a wiki page after your Yes |
| `pre-pr-verify` | "start the environment" | the stack from the bug's worktrees, proven to answer from them, and a short test brief |

## Why it is cheap on tokens

The mechanics live in `scripts/devops.py`; the skills keep only the judgement. The agent reads a short
summary, not raw git and ADO output:

- The four skills went from 143k to 18k characters, and their descriptions, which load into every session,
  from 7.3k to 1.8k.
- `release scan` replaces the git scan, three rounds of MCP calls and the plan the agent used to write; `release
  open` makes the PRs, links the work items and reads the links back.
- `notes render` writes the file and the wiki page from the template (badges, links, priority groups, the
  file counter), so the agent writes only one sentence per bug fix.
- `sync start | verify | finish | plan | open` do the conflict branch (`--no-track`), the four checks after
  a resolution, the push, the sanitized PR text and the single work-item link.
- `env find` and `env gate` find the worktrees, the run script and its flags, and prove Gate D.

## What it never lets through

Two hook sets, on in every session (turn off with `"guard": {"enabled": false}` in `.claude/devops.json`):

- **Branches**: no push to `main`, `master`, `develop`, `release/*` or `team/*` (named, or through the branch's
  upstream); no force push; no `--mirror`/`--prune`; no remote branch deleted but a `sync/*` one; no new
  branch from `origin/<protected>` without `--no-track`; no branch locked, unlocked or cut with a protected
  name; no PR completed, auto-completed or voted on.
- **Your work**: no `reset --hard`, file checkout or restore, `clean -f`, `switch --discard-changes` while
  there is uncommitted work; no `stash drop|clear`; no `stash pop` in a repo the sync snapshot holds; no
  edit, stage, `--ours/--theirs` or abort of a sync merge you have not resolved.
- **What goes out**: a release or sync PR (and a `/Release Notes` wiki page) needs a plan **you approved**:
  the script prints a question ending `(plan <token>)`; your Yes in the question dialog, or **Approve** in the
  pane, is recorded; the agent cannot approve (the guard refuses `devops.py approve` and writes to the
  approvals file). The approval holds only for exactly what was shown: a changed plan has a new token. Every
  outbound text is checked for secrets, tokens, local paths, template placeholders, `#<id>` mentions (which
  post onto the work item), the 4000-character PR limit, and old `AB#<id>` on a sync PR. A wiki page must be
  the rendered one, unchanged.
- **Devops' own files**: plans, approvals and scans under `.claude/devops/` are written by the script only;
  a generated launcher goes in `.claude/scripts/`, not the shared `scripts/`; a published release-notes
  file is not edited.

Each refusal is logged to `.claude/devops/guard.jsonl` and shown in the pane.

## The pane

`/devops` (or `/devops release 1.1.0`, `sync`, `notes`, `guard`) opens it beside the chat, on the terminal and
in the Desktop app. The status line says what needs you (`devops · 1 to approve · release 1.1.0: 2 ready`).

- **Overview**: what needs you, most urgent first (a sync conflict to resolve, a plan to approve, a release
  branch to cut, a snapshot to restore), and buttons that fill the prompt for each skill.
- **Release**: pick a version, Scan, each repo's facts on a press (branches, counts, work items,
  migrations, commits with no work item), the PRs still headed into the team branch, the plan with
  **Review & approve…**, and once approved, **Open the PRs now**. The PR links after.
- **Sync**: syncs waiting for you (with "I resolved it: ask Claude to verify"), the snapshot with
  **Restore…**, the chain's waves, each scan's repos, the sync plan, the team-sync work items, the reports.
- **Notes**: each run (rendered, approved, published), **Review & approve…**, **Publish now**, the wiki link.
- **Guard**: what it protects and what it refused lately.

It reads `devops.py status --json` (files only: no git, no ADO) when it opens, once a minute while open, and
after each press. Approve runs nothing; a write runs only on its own press or by the agent.

## Config: `.claude/devops.json`

```json
{
  "reposDir": "projects",
  "sourcePattern": "team/{0}", "targetPattern": "release/{0}", "branchPrefix": "team/",
  "notesDir": "documents/release-notes",
  "clusterGapHours": 2,
  "syncFeatureTitle": "Branch Synchronizations", "syncWorkItemType": "Tech Story",
  "guard": {
    "enabled": true,
    "protectedBranches": ["main", "master", "develop", "release/*", "team/*"],
    "forcePush": false, "protectWorkingTree": true, "requireApproval": true, "approvalHours": 24
  }
}
```

Every key is optional. By hand: `python scripts/devops.py --help`.
