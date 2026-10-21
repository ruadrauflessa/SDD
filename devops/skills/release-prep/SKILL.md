---
name: release-prep
description: >-
  Prepare a release across the workspace repos: find which repos have team-branch work not yet on the
  release branch, dry-run each merge, check pending and open PRs and the work items, get the user's
  approval, then open one release PR per repo (or refresh an open one after late commits) and hand off
  to release-notes. Use for "prep the release", "prepare release 1.1.0", "what is not in release yet",
  "raise the release PRs", "cut the release", "update the release PR, more commits came in".
---

# Release prep (team branch → release branch)

`devops.py` does the mechanics: the git scan, the ADO reads, the PR text, the PRs. You run it, relay
what it prints, ask the one question, and stop where it says stop.

Below, `devops.py` means `python "${CLAUDE_PLUGIN_ROOT}/scripts/devops.py"`, run from the workspace.

## Rules

1. **Confirm the version first.** If the request names none, run `devops.py versions` and ask with
   AskUserQuestion, the versions as options (the four newest; the user can type another). Never reuse
   a version from an earlier run or a file.
2. **Nothing outward before the user's Yes.** The scan writes a plan. Opening or refreshing a PR needs
   that plan approved. The guard refuses a release PR that no approved plan holds.
3. **Never type a branch name to ADO.** The scan resolves the server's casing (`Team/1.1.0` is not
   `team/1.1.0`). Use what it prints.
4. **Never resolve a conflict, push to a release branch, create a branch, or merge or approve someone
   else's PR.** The guard refuses these. A conflict goes to the user (sync-team-branches covers a local
   merge). A missing release branch is cut by the user: give them the link the scan prints.
5. **Say every repo out loud**: Skipped, Conflicts and missing release branches too. A repo quietly
   missing from a release is the failure this skill exists to stop.
6. **Plain English** in chat: short sentences, active voice. Branch names, ids and commands stay exact.

## Steps

1. **Scan** (fetches, dry-runs each merge, reads PRs into the source, open release PRs, work items):
   `devops.py release scan --version <v>`. Exit 1 means a repo conflicts or errored.
2. **Relay** the output: every repo line, the missing-release-branch links, the PRs still headed into
   the source branch (and what each means), dropped ids, migration files (each needs a deployment
   decision), commits with no work item. Do not shorten the repo list.
3. **Ask** with AskUserQuestion, using the question the scan printed word for word (it ends with
   `(plan <token>)`), options "Yes, go ahead" and "No". Repeat the missing-release-branch links in the
   message above it. The devops hook records a Yes; the user can also press Approve in `/devops`.
4. **Open**: `devops.py release open --version <v>`. It refuses a branch that moved since the scan (scan
   again and ask again), skips a PR that already exists, links the work items and reads them back.
   Report every PR link and every failure.
5. **Hand off** to the `release-notes` skill with the hand-off line `open` printed (PR ids, projects,
   work items, migration finding). Do not pre-answer its questions.

**Refresh after late commits**: run the scan again. It plans a description refresh and the new links
for each open release PR that changed. Say whether the PR grew (commit and file counts): an approved PR
that doubled needs review again. Then steps 3 to 4. Update the release notes too if they exist.

**No ADO access** (the scan says "ADO not read", or `az` is missing): read
`${CLAUDE_PLUGIN_ROOT}/references/mcp-fallback.md`, section *release-prep*. `devops.py doctor` names what is
missing (tools, sign-in, rights on a repo) and the fix: relay its FAIL lines.

## Traps

- `Behind` is normal: hotfixes land on release first. Report it; do not act on it.
- A repo with no team branch for this version has no work in it: say so, without alarm. A repo with a
  team branch but no release branch needs the user to cut one (the link).
- `UpToDate` where you expected work: someone may have completed the PR already.
- `[AB#123]` in a commit does not link in an ADO repo: `open` links every work item explicitly.
- The workspace root repo (no remote) is never pushed.
