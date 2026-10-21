# devops

Release and branch work on Azure DevOps repos: prepare a release, sync team branches, write release notes.
Standalone (same marketplace as sdd and repowatch; it needs neither).

```
/plugin install devops --marketplace ruadrauflessa/SDD
```

Needs Python 3.9+, git, PowerShell 7 (`pwsh`) for the scans, and `az login` (or a PAT in
`AZURE_DEVOPS_EXT_PAT`) for the ADO reads and writes. Without `az`, the skills fall back to the Azure DevOps
MCP tools (`references/mcp-fallback.md`), and the guards still hold. For a public project,
`DEVOPS_ADO_ANONYMOUS=1` reads without signing in (writes always need a sign-in).

## The skills

| Skill | Say | What happens |
| --- | --- | --- |
| `release-prep` | "prep the release", "prepare release 1.1.0" | one scan, one plan, your Yes, one PR per repo, hand-off to the notes |
| `sync-team-branches` | "sync team branches", "merge team/1.1.0 into team/1.2.0" | the version chain, a dry-run per hop, PRs for clean repos, a `sync/*` branch you resolve for conflicts, a report |
| `release-notes` | "generate release notes" | five questions at once, then a file in `documents/release-notes/` and a wiki page after your Yes |

## Why it is cheap on tokens

The mechanics live in `scripts/devops.py`; the skills keep only the judgement. The agent reads a short
summary, not raw git and ADO output:

- The three skills went from 128k to 13.5k characters, and their descriptions, which load into every session,
  from 5.9k to 1.4k.
- `release scan` replaces the git scan, three rounds of MCP calls and the plan the agent used to write; `release
  open` makes the PRs, links the work items and reads the links back.
- `notes render` writes the file and the wiki page from the template (badges, links, priority groups, the
  file counter), so the agent writes only one sentence per bug fix.
- `sync start | verify | finish | plan | open` do the conflict branch (`--no-track`), the four checks after
  a resolution, the push, the sanitized PR text and the single work-item link.

## What it never lets through

Two hook sets, on in every session (turn off with `"guard": {"enabled": false}` in `.claude/devops.json`):

- **Branches**: no push to `main`, `master`, `develop`, `release/*` or `team/*` (named, or through the branch's
  upstream); no force push; no `--mirror`/`--prune`; no remote branch deleted but a `sync/*` one; no new
  branch from `origin/<protected>` without `--no-track`; no branch locked, unlocked or cut with a protected
  name; no PR completed, auto-completed or voted on by Claude.
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
- **Your name on a PR**: review comments and votes go out only from your own press in the pane's Reviews tab,
  after a confirm. Claude may read a PR (`reviews list|show|pack`) but the guard refuses `reviews post|vote|save`.
- **Devops' own files**: plans, approvals and scans under `.claude/devops/` are written by the script only;
  a published release-notes file is not edited.

Each refusal is logged to `.claude/devops/guard.jsonl` and shown in the pane.

## The pane

`/devops` (or `/devops release 1.1.0`, `sync`, `notes`, `reviews`, `guard`) opens it beside the chat, on the terminal and
in the Desktop app. The status line says what needs you (`devops · 1 to approve · release 1.1.0: 2 ready`).

- **Overview**: what needs you, most urgent first (a sync conflict to resolve, a plan to approve, a release
  branch to cut, a snapshot to restore), and buttons that fill the prompt for each skill.
- **Release**: pick a version, Scan, each repo's facts on a press (branches, counts, work items,
  migrations, commits with no work item), the PRs still headed into the team branch, the plan with
  **Review & approve…**, and once approved, **Open the PRs now**. The PR links after.
- **Sync**: syncs waiting for you (with "I resolved it: ask Claude to verify"), the snapshot with
  **Restore…**, the chain's waves, each scan's repos, the sync plan, the team-sync work items, the reports.
- **Notes**: each run (rendered, approved, published), **Review & approve…**, **Publish now**, the wiki link.
- **Reviews**: the active PRs of the workspace's ADO projects, **Waiting on me** by default (you are a reviewer,
  directly or through a group, with no vote yet, and it is not yours or a draft), **All active** on a press. Press a
  PR for its policies, votes, linked work items, files and comment threads, then:
  - **Quick review**: one model call (`reviews.model`, Sonnet by default) reads the diff, the description and the
    work items' acceptance criteria, and drafts comments. Only a finding on a line the diff shows is kept; it is
    saved for that push, so reopening the PR shows it again.
  - The drafts are yours: rewrite, keep or drop each, add your own. **Post N comments…** shows them, then **Post**
    sends them under your name, on the right file and line (a code suggestion as ADO's suggestion block). Posting is
    refused if the PR got a new push since the review read it.
  - **Approve**, **Approve with suggestions**, **Wait for author**, **Reject**, **Reset vote**, each with a confirm,
    under your name. On your own PR, when its reviewer policy does not count the author's vote, only Reset shows.
- **Guard**: what it protects and what it refused lately.

It reads `devops.py status --json` (files only: no git, no ADO) when it opens, once a minute while open, and
after each press. The Reviews tab reads ADO when it opens and on **Refresh list**. Approve runs nothing; a write runs only on its own press or by the agent.

## Config: `.claude/devops.json`

```json
{
  "reposDir": "projects",
  "sourcePattern": "team/{0}", "targetPattern": "release/{0}", "branchPrefix": "team/",
  "notesDir": "documents/release-notes",
  "clusterGapHours": 2,
  "syncFeatureTitle": "Branch Synchronizations", "syncWorkItemType": "Tech Story",
  "reviews": { "model": "sonnet", "maxTokens": 4000, "maxDiffChars": 60000, "maxFindings": 12 },
  "guard": {
    "enabled": true,
    "protectedBranches": ["main", "master", "develop", "release/*", "team/*"],
    "forcePush": false, "protectWorkingTree": true, "requireApproval": true, "approvalHours": 24
  }
}
```

Every key is optional. By hand: `python scripts/devops.py --help`.
