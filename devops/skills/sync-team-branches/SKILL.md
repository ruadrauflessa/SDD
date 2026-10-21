---
name: sync-team-branches
description: >-
  Forward-sync version branches (team/{version}) across the workspace repos: one pair, or the whole
  chain lowest version first, each repo on its own chain, a hop only after its prior hop landed. Dry-runs
  each merge, opens PRs for clean repos, and for conflicts makes a sync/* branch the USER resolves. Links
  only a team-sync work item, skips locked branches, writes a report. Use for "sync team branches",
  "merge team/1.1.0 into team/1.2.0", "sync every version up the chain", "which repos will conflict".
---

# Sync team branches (older version → newer version)

`devops.py` does the mechanics; you relay, ask, and hand over. Below, `devops.py` means
`python "${CLAUDE_PLUGIN_ROOT}/scripts/devops.py"` and `snapshot` means
`pwsh -File "${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Invoke-RepoStateSnapshot.ps1"`.

## Two modes

- **Single pair**: the user names two versions or branches. Steps 2 to 7 once.
- **Full chain** (the user names no pair, or says "sync everything", "make sure nothing was missed"):
  step 1, then steps 2 to 7 for each group, wave by wave, lowest destination first.
- "sync team branches" with no version: ask which they mean. A chain is a much bigger job.

## Rules (the guard enforces the ones marked *)

1. *Never resolve a conflict.* Show the paths and what each side did; the user resolves every hunk.
   You do not edit, stage, `checkout --ours/--theirs` or abort it.
2. *Never push to a team branch* and *never force-push*. Only a `sync/*` branch is pushed.
3. *Never throw away uncommitted work.* Snapshot first; restore by SHA with the script, never `stash pop`.
4. Confirm before opening PRs (the plan's question), and in chain mode confirm the wave plan first.
5. Chain mode: a group runs only after its own prior hop landed. Pass the group's `--prior-*` flags; a
   `PendingPriorHop` repo waits for a later run. Never take the user's word that a PR merged.
6. A repo whose chain skips a version is normal. A locked branch is treated as absent. Never lock or
   unlock one.
7. *A sync PR links only the run's team-sync work item.* `sync plan` strips `AB#`/`#` from the old commit
   subjects; `sync open` unlinks anything ADO auto-links.
8. Plain English in chat; branch names and commands exact.

## Steps

1. **Chain** (chain mode): `devops.py sync chain [--from <v>] [--to <v>]`. Show the wave plan and ask the
   user to confirm it. It prints the scan command for each group.
2. **Scan** the pair or group: `devops.py sync scan --source <s> --destination <d> [--repos a,b]
   [--prior-source <p> --prior-destination <q>]`. Relay every repo line, Skipped and Locked too.
   Nothing to sync in this group: report and move on (no work item question).
3. **Team-sync work item**, once per ADO project per run, only when a repo needs a PR. Ask: "Do you want
   me to auto-create the sync tech story for <project>, or do you already have one to use?"
   Then `devops.py sync techstory --project <P> --create` or `--id <N>`. It checks the id is in that
   project. No valid id: raise no PR for that project.
4. **Conflicted repos**, one at a time, in this session (sub-agents cannot ask the user):
   - `snapshot -Action Save -Repos <repo>` (always through the script).
   - Ask the user for their branch segment if the workspace has no convention (`development/<user>/...`).
   - `devops.py sync start --repo <r> --source <s> --destination <d> --user <u>`: makes
     `sync/<u>/<s>_to_<d>` from `origin/<d>` with `--no-track` and merges. It lists the conflicts and
     what each side changed. Hand them over and wait. An existing branch: ask reuse or `--recreate`.
   - When the user says done: `devops.py sync verify --repo <r>` (unmerged entries, `diff --check`, a
     CRLF-safe marker scan, status). A FAIL goes back to the user as is.
   - `devops.py sync finish --repo <r> --note "<how the user resolved it, in their words>"`: commits,
     checks the merge landed, pushes the sync branch.
5. **Plan the PRs**: `devops.py sync plan --source <s> --destination <d>` (clean repos straight across,
   conflicted repos from their pushed sync branch). Ask with AskUserQuestion using its question word for
   word, options "Yes, go ahead" / "No".
6. **Open**: `devops.py sync open --source <s> --destination <d>`. Report every PR link.
7. **Restore and report**, once the whole hop is done: `snapshot -Action Restore` (relay Blocked,
   Conflict and Failed rows as they are: they are the user's to settle), then
   `devops.py sync report --source <s> --destination <d>`. Give the user the path; do not post it.
   In chain mode, re-fetch happens in the next scan; finish each hop's restore before the next wave.

**No ADO access**: read `${CLAUDE_PLUGIN_ROOT}/references/mcp-fallback.md`, section *sync-team-branches*.

## Worth knowing

- A plain clone and a submodule sync the same way. Other people's stashes may sit at `stash@{0}`: that
  is why the snapshot restores by SHA.
- Version folders (`Migrations/<version>/`) conflict often, including modify/delete: `ls-files -u` in
  `verify` catches what a marker scan cannot.
- A chain can be 20+ versions long. Resume with `sync chain --from <v>` past the waves that landed.
- After the PRs complete, a root repo with no remote may take the submodule pointers as a local
  commit. Never push it.
