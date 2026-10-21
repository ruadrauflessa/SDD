---
name: sync-team-branches
description: >-
  Forward-sync version-bearing integration branches (e.g. `team/{version}`) across every repo in a
  multi-repo workspace. Two modes: a single pair (as before), or the full chain — discover every
  `team/{version}` branch that exists ANYWHERE in the workspace, and for EACH REPO build its own
  chain from ITS OWN present versions (a repo with no changes in a given version never gets a
  branch for it, so that repo's chain legitimately jumps straight past it — normal, not a gap to
  flag), grouped into waves by destination version, lowest first. Never scans a repo's next hop
  until that repo's own prior hop has actually landed (verified with `git merge-base
  --is-ancestor`, not assumed from a PR merely being opened). Per hop: fetch and prune, confirm
  both branches exist, dry-run the merge with `git merge-tree` to detect conflicts BEFORE any PR is
  opened, raise PRs directly for the clean repos, and for conflicted ones drive a local merge on a
  `sync/*` branch that the USER resolves by hand before it is pushed and PR'd. Works on any
  workspace with sibling git repos under a shared directory (submodules or plain clones) and any
  branch-naming/version scheme — not tied to a specific project or hosting provider. On Azure
  DevOps, a branch LOCKED there is excluded from consideration entirely (as if it didn't exist,
  both as a source and a destination) since nothing can ever be merged into a locked branch — this
  applies to both modes. USE THIS SKILL when asked to "sync team branches", "merge team/1.1.0 into
  team/1.2.0", "forward-merge the release branch", "sync every version up the chain", "walk all
  the team branches forward", "make sure nothing from an older version got missed", "bring the
  older integration branch up into the new version", "check for merge conflicts before raising a
  PR", "which repos will conflict", "skip locked branches", or "raise the version sync PRs".
  Stashes each repo's uncommitted work before any checkout and restores it when the run finishes,
  then writes a shareable markdown summary report per hop. Triggers - team branch sync, forward
  merge, version sync, version chain, chain sync, wave, hop group, merge-tree, conflict pre-check,
  sync/* branch, cross-repo PR, stash and restore working state, sync summary report, hop landed,
  prior hop, version jump, locked branch, branch lock.
---

# Sync team branches (lower version → higher version)

In a multi-repo workspace, every repo can be independently versioned, carrying its own set of
integration branches (e.g. `team/{version}`, `release/{version}`). When work continues on an
older branch after a newer one is cut, each repo drifts separately and has to be forward-merged
separately — N repos, N PRs, no shared commit. And when there are *three or more* live versions at
once (`1.0.x`, `1.1.x`, `1.2.0`), a fix that only ever reaches `1.1.0` in one repo is invisible to a
sync that jumps that repo straight from `1.0.0` to `1.2.0` while it *does* have a `1.1.0` branch —
the chain mode below exists to stop that. The reverse is equally true and just as important: a repo
that never had a `1.1.0` branch at all (nothing shipped there that release) is *correctly* jumped
straight from `1.0.0` to `1.2.0` — that is not a gap, and forcing it through a version it never had
would be inventing work, not preventing a miss. Each repo's own branches decide its own chain.

This skill answers "will it conflict?" *before* anything is pushed, then takes the two cases down
different paths, one hop at a time.

```
Phase 0 — discover every team/{version} branch; build EACH REPO'S OWN chain from its own
          present versions; group into waves by destination version, lowest first
                 │
                 ▼
   for each wave (destination D), for each group of repos sharing (source, prior) in that wave:
                 │
     has this group's PRIOR hop actually landed? (n/a if it's a repo's first hop) ── no ──→
                 │ yes                                                          PendingPriorHop,
                 ▼                                                              wait, re-run later
                 ┌─ Clean / FastForward ──────→ PR: source ──────────────────────────→ D
   scan repos ───┤                                                                          ─→ restore state
                 └─ Conflicts ─→ snapshot ─→ sync/<user>/<source>_to_<D> ─→ USER resolves ─→ PR ─→ (unstash)
                 │
                 ▼
         report for this group, THEN move to the next group/wave
```

Working state is stashed before any checkout and restored once each group's run finishes, so the
workspace ends where it started. Each hop emits its own shareable markdown report.

## Two modes

- **Single pair** (the original mode): the user names exactly two branches/versions. Run Phases
  1–6 once, for that pair only. No chain, no landed-gate — this is a deliberate one-off sync, e.g.
  "merge team/1.1.0 into team/1.2.0". `-PriorSource`/`-PriorDestination` are simply omitted.
- **Full chain** (the new mode, and the default when the user doesn't name a specific pair, or
  says anything like "sync everything" / "make sure nothing was missed"): run Phase 0 to discover
  every version and build the per-repo/wave plan, then loop Phases 1–6 once per group, lowest
  destination version first, gating each group on that repo's own prior hop having actually
  landed. This is slower and touches more branches — always show the discovered wave plan and get
  confirmation before starting the loop (hard rule 6 extends to this: confirm the *wave plan*, not
  just the PR list for one hop).

If the user's request is ambiguous between the two ("sync team branches" with no version named),
ask which they mean rather than guessing — a chain run is a much bigger, longer operation than a
single pair.

## Where this runs

Installed through the `devops` plugin, so it is offered in every project. It fits any
workspace shaped like: a set of sibling git repos living under one shared directory, each carrying
the two branches being synced. That directory does not need to be named `projects/`, and the repos
inside it do not need to be git submodules — plain clones work identically (this skill's own home
workspace mixes both). All three scripts locate the workspace by walking up from the **current
directory** for an ancestor holding a repos directory (`-ReposDir`, default `projects`); they
cannot infer it from their own path. Pass `-Root` and/or `-ReposDir` explicitly to override. If no
such directory is found the scan reports "No 'projects' directory..." — that means the skill was
triggered outside a workspace it fits, so say so rather than improvising a different layout.

Branch names are also not assumed. `-Source`/`-Destination` accept any full branch name
(`release/2.3`, `develop`, `main`), or a bare value that gets a configurable prefix applied
(`-BranchPrefix`, default `team/`, matching this skill's most common use so far — override or pass
`-BranchPrefix ''` for a workspace that doesn't version its integration branches that way). If a
single repo is the target rather than a whole workspace, point `-Root` at its parent and `-Repos`
at just that one name — the phases below are unchanged.

## Hard rules

These are not preferences. Violating any of them damages a shared repo or the user's working state.

1. **Never resolve a merge conflict.** The user resolves every conflicted hunk by hand. You may
   show the conflicted paths, explain what each side changed, and *verify* that resolution is
   complete — verifying is not resolving. Do not edit a conflicted file, do not `git checkout
   --ours/--theirs`, do not suggest a resolution unless asked.
2. **Never push to the destination branch.** The merge result goes to a `sync/*` branch; the
   destination branch only ever changes by completing a PR.
3. **Never force-push**, and never `git merge --abort` / `git reset --hard` on a repo with
   uncommitted work you did not create.
4. **Snapshot before touching a working tree, restore at the end.** Uncommitted work is stashed in
   Phase 2, recorded in a manifest, and returned in Phase 5. Never stash ad-hoc with a
   bare `git stash` — always go through the script, so the stash SHA and original branch are
   recorded and the snapshot survives a crashed session.
5. **Never restore a stash by `stash@{0}`.** The index shifts if anything else stashes in between.
   The script restores by commit SHA for exactly this reason.
6. **Confirm before opening PRs.** List exactly which repos, which source → target, then ask once.
   A PR is outward-facing and visible to the team. In chain mode, also confirm the discovered hop
   plan itself before starting the loop — it's the bigger commitment.
7. **Fetch immediately before scanning.** A clean result is a snapshot; it goes stale the moment
   anyone pushes to either branch.
8. **Chain mode: never scan a repo's next hop until that repo's own prior hop has actually
   landed.** This is per repo, not a single global gate — a repo whose chain jumps `1.0.0 ->
   1.2.0` has no `1.1.0` hop to wait on at all. "Landed" means `git merge-base --is-ancestor`
   confirms the prior hop's source is now an ancestor of the prior hop's destination — not that a
   PR was opened, not that the user said "go ahead". Pass `-PriorSource`/`-PriorDestination` (from
   the Phase 0 group) to every Phase 1 scan after a repo's first hop and trust its
   `PendingPriorHop` verdict; do not scan ahead "to save time" and do not take the user's word that
   an earlier PR merged — check it. A repo reported `PendingPriorHop` simply waits for a later run;
   it is not an error and not something to force past.
9. **A repo's hop chain skipping a version is normal, not a defect.** Never invent or force a sync
   through a version a repo never had a branch for — use the repo's own chain from Phase 0
   (`repoChains` in the JSON) as-is. A version bump is project-wide; a branch for it exists only in
   a repo that had changes for that release.
10. **Never scan into or out of a branch locked in Azure DevOps.** A lock prevents ANY push to that
    ref, so a PR into a locked destination can never be completed — there is nothing to gain by
    scanning it. Both scripts check this on their own (`Get-LockedBranchNames`, backed by
    `az repos ref list`); trust the resulting `Locked` status (Phase 1) or the branch's absence
    from the coverage table (Phase 0) rather than re-deriving lock state yourself, and never lock
    or unlock a branch as part of this skill — that is the user's call, made in Azure DevOps
    directly, not something this skill does on their behalf.
11. **Never let a sync PR inherit the work items from the branches it merges.** Every sync PR links
    to exactly one work item: this run's team-sync work item, resolved as described in *Work items
    on sync PRs* below. Never pass an old commit's work item ID to a PR-create call, auto-create a
    team-sync work item before there is a confirmed PR to raise, or raise a PR for a project whose
    team-sync work item the user chose to supply but never actually gave.
12. **Write for a tired reader, in plain English.** The PR description, the report and every
    message in chat follow the house style (ASD-STE100 Simplified Technical English): one idea per
    sentence, active voice, small words. Read `${CLAUDE_PLUGIN_ROOT}/references/writing-style.md`
    before Phase 3. Paths, branch names and commands stay exact.

## Work items on sync PRs — never carry the old ones forward

A sync PR moves code that was already reviewed and tracked under its own work item on the branch
where the work actually happened. The sync PR is not that work happening again — carrying its old
work item onto the sync PR misrepresents a merge as new work and reopens tracking on something
already closed elsewhere.

**Where the leak actually comes from:** Phase 3 drafts each PR body by quoting
`git log --pretty='%h %s'` verbatim, and Phase 4 does the same from the conflict range. Old commit
subjects routinely contain `AB#12345` or bare `#12345`, and Azure DevOps auto-links any work item
mentioned that way the moment a PR is created with that text in its title/description. Quoting old
commit messages unmodified is what drags every historical bug into the new PR's "Related work
items" panel — nothing about that is deliberate, it just was never stripped.

**For every PR this skill raises:**

1. **Sanitize commit subjects before they go into a PR description.** Replace every `AB#<digits>`
   and bare `#<digits>` token with a non-linking form (`AB-<digits>` reads fine and does not
   trigger ADO's auto-link). Leave the rest of the subject as-is — the history stays visible, it
   just stops being auto-linkable.
2. **Never pass any of the old commits' work item IDs to the PR-create call.** The only
   `workItems`/`--work-items` entry on a sync PR is this run's team-sync work item (below).
3. **After creating the PR, check its linked work items.** If Azure DevOps auto-linked anything
   besides the team-sync item (it can still happen from a commit message ADO scans independently
   of the description text), unlink it. This is undoing a side effect of a PR *this run just
   created* — not touching shared history — so it needs no confirmation, unlike everything Hard
   Rule 1-3 protects.

### The team-sync work item

Every PR this skill raises links to exactly one work item: a "team sync" Tech Story for this run,
created in that repo's own ADO project (a workspace can span more than one project —
`HealthCodeIndex_V2` is a separate project from the rest of this workspace, for example, so a run
touching it needs its own tech story there). [Work item 85397](https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/85397)
is a real example: titled `sync team branches (yyyy/mm/dd)`, parented under a Feature called
"Branch Synchronizations" ([81443](https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/81443)),
with every PR and commit from that day's run linked to it.

**Only ask about this once there is an actual PR to raise.** After Phase 1, if this hop/group comes
back entirely `UpToDate`/`Skipped`/`PendingPriorHop`, there is nothing to attach a work item to —
don't ask, and don't create anything. Ask only once at least one repo in the hop/group is `Clean`,
`FastForward`, or `Conflicts`.

The first time a run needs one for a given ADO project, ask the user directly:

> Do you want me to auto-create the sync tech story for **\<project\>**, or do you already have one
> to use?

- **User says auto-create:** look for a Feature titled "Branch Synchronizations" (or whatever this
  project already uses for this — search rather than assume the exact title) in that project; if
  none exists, create one. Then create a new Tech Story titled `sync team branches (yyyy/mm/dd)`
  under it. Reuse this same Tech Story for every repo/group processed for that project for the rest
  of this run — never create a second one for the same project on the same day.
- **User says they have one:** ask for the work item ID, fetch it (`wit_work_item` `get`), and
  confirm it exists and sits in the right project. **Refuse to raise any PR for that project's
  repos until a valid ID is given** — do not fall back to auto-create, and do not raise a PR with
  no work item linked either.

Cache whichever ID applies per project for the rest of the run, the same way a scan result is
cached — don't re-ask for a project already resolved earlier in this run.

## Phase 0 — discover the version chain (chain mode only)

Skip this phase entirely for a single-pair sync — go straight to Phase 1 with the two branches the
user named.

For a chain run, one command discovers every version-bearing branch across the whole workspace and
builds the ordered hop list, starting from the lowest version so nothing gets missed:

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Get-TeamVersionChain.ps1 -JsonPath temp/sync-chain.json
```

Add `-ReposDir <name>` / `-BranchPrefix <prefix>` to match the workspace, same as Phase 1.
`-FromVersion`/`-ToVersion` bound a partial run (e.g. resume a chain that already finished its
lowest hops) — omit both to cover everything, which is the safe default.

It builds **each repo's own hop chain from its own present versions**, not one chain forced onto
every repo alike. A version bump is project-wide, but a branch for it only exists in a repo that
actually had changes for that release — a repo with nothing to ship in `1.1.0` never gets a
`team/1.1.0` branch, and its next hop legitimately runs `1.0.0 -> 1.2.0` directly. **That is normal,
not a defect** — don't flag it as one, and don't force that repo through a `1.1.0` it never had.

**A branch LOCKED in Azure DevOps is treated exactly the same way** — excluded from that repo's
present-version list as if the branch didn't exist. This needs no special-casing in the wave/chain
logic; it falls straight out of the rule above. Lock state is read per repo from `az repos ref
list` (org/project/repo parsed from that repo's own `origin` URL, never assumed workspace-wide),
and fails open — missing/unauthenticated `az`, or a non-Azure-DevOps repo, just means "can't tell,
include everything" plus a one-time warning, not a hard stop. Pass `-SkipLockCheck` to disable the
check outright.

Those per-repo hops are grouped into **waves**, one per destination version, lowest first. Within a
wave, repos whose hop has the same `(source, prior source, prior destination)` are grouped together
— that's exactly the set of repos one `Scan-TeamBranchSync.ps1` call can cover at once, since its
`-PriorSource`/`-PriorDestination` gate applies uniformly to whichever `-Repos` are named in a
single call.

It prints, and writes to JSON:

- **Every version found**, lowest to highest, numerically sorted (`1.2.0` before `1.10.0`, not the
  lexical order that would give).
- **The wave plan** — for each destination version, the group(s) of repos sharing an identical
  source/prior, in the order the loop below must run them.
- **Per-repo coverage** — which of those versions each repo actually has a branch for.
- Three informational buckets so no repo goes unaccounted for: repos with only one version in
  scope (nothing to sync yet), repos with branches on the convention but none inside this run's
  `-FromVersion`/`-ToVersion` range, and repos not on the convention at all (every wave will show
  them `Skipped`, which is expected).
- **Excluded — locked**, per repo: which versions were dropped from that repo's own list because
  Azure DevOps reports the branch locked. Purely informational — the wave plan above already has
  these gone, exactly as if the branch never existed.

**Show the wave plan to the user and confirm before starting the loop** (hard rule 6). A chain run
can mean many waves across many repos — make sure that's actually what they want before committing
to it, not just to the first PR.

## Phase 1 — scan (parallel-safe, no agents needed)

One command classifies the whole workspace for a single hop. It fetches with prune, checks that
*both* branches exist per repo, records working-tree cleanliness, measures divergence, and
dry-runs the merge with `git merge-tree --write-tree` — which merges entirely in the object
database, touching no ref, no index and no working tree.

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Scan-TeamBranchSync.ps1 -Source 1.1.0 -Destination 1.2.0 -JsonPath temp/sync-scan.json
```

Add `-ReposDir <name>` if the workspace's shared repo directory isn't called `projects`, and
`-BranchPrefix <prefix>` (or `-BranchPrefix ''`) if the workspace's branches aren't named
`team/{version}`.

**Chain mode: scan one Phase 0 group at a time**, not one call per wave. A wave can contain several
groups with different `-Source` values (a repo jumping `1.0.0 -> 1.2.0` sits in a different group
from one going `1.1.0 -> 1.2.0`, even though both land in the same wave), so pass each group's own
`Source`/`Repos`/`PriorSource`/`PriorDestination` from the Phase 0 JSON:

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Scan-TeamBranchSync.ps1 -Source 1.1.0 -Destination 1.2.0 -Repos RepoA,RepoB -PriorSource 1.0.1 -PriorDestination 1.1.0
```

Omit `-PriorSource`/`-PriorDestination` only for a group whose `PriorSource` is `null` in the JSON
(that repo's first hop) or for a single-pair sync. This is the mechanism behind hard rule 8 — a
repo where the named prior hop hasn't landed comes back `PendingPriorHop` instead of being scanned
for the current hop, so an unfinished earlier hop can never be silently jumped over.

Destination is passed to `merge-tree` **first** so it is treated as "ours", mirroring how most
forges (Azure DevOps, GitHub, GitLab) compute a PR's merge preview. Exit 0 = clean, 1 = conflicts,
anything else = the merge could not be attempted.

Do **not** fan this out to subagents. It is pure shell over the workspace's repos and finishes in
seconds; agents-per-repo would be slower, cost more, and add nothing — there is no reasoning per
repo.

Statuses it returns:

| Status | Meaning | Path |
| --- | --- | --- |
| `UpToDate` | destination already contains everything on source | skip — no PR |
| `FastForward` | destination is an ancestor of source | PR direct |
| `Clean` | real merge, no conflicts | PR direct |
| `Conflicts` | `merge-tree` reported conflicted paths | local merge, user resolves |
| `Skipped` | one or both branches absent in that repo | skip |
| `PendingPriorHop` | chain mode: this repo's own prior hop hasn't landed yet | wait, re-scan this group later |
| `Locked` | source or destination is locked in Azure DevOps for this repo | skip — nothing can ever merge there |
| `FetchFailed` / `MergeError` | auth/network, or unrelated histories | investigate, don't guess |

Present the table to the user before doing anything else. Call out `Skipped` repos explicitly —
a repo silently missing from a sync is the failure mode this skill exists to prevent. In chain
mode, call out `PendingPriorHop` repos too, and say plainly that they'll be picked up on a later
run of this same group once the prior PR actually merges — they are not dropped from the chain.
A single-pair sync can still hit `Locked` even though chain mode's Phase 0 already excludes locked
branches from its own plan — say so plainly and point the user at Azure DevOps if they actually
need that branch unlocked; this skill never locks or unlocks one itself (hard rule 10).

## The chain loop (chain mode only)

Once Phase 0 has produced the wave plan and the user has confirmed it, walk it **wave by wave,
lowest destination first; within a wave, group by group** (groups within the same wave are
independent of each other and may run in any order):

1. Run Phase 1 for that group (`-Source`/`-Repos` from the group, `-Destination` from the wave,
   `-PriorSource`/`-PriorDestination` from the group unless they're `null`).
2. Run Phases 2–6 exactly as below, scoped to that group's repos and `-Source`/`-Destination`.
3. Before moving to the next wave, re-fetch. The next wave's Phase 1 calls will themselves
   re-verify via `-PriorSource`/`-PriorDestination` that the relevant repos' prior hop landed —
   that check, not an assumption, is what decides whether each group proceeds.
4. If any repo comes back `PendingPriorHop`, that's expected when waves run back to back quickly (a
   PR takes time to review and merge) — report it, and either pause the chain there or continue
   with the groups that *are* clear, per the user's preference. Nothing about this is a failure;
   it's the gate in hard rule 8 doing its job.

A chain run naturally spans more than one sitting when PR review takes time — that's fine. Phase 0
can be re-run at any point (it's read-only) to see current status, and a wave already fully landed
everywhere will show as `UpToDate` across the board when re-scanned.

## Phase 2 — snapshot working state (only the repos you will check out)

Run this once the scan tells you which repos take the local-merge path, and **before** creating
any sync branch.

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Invoke-RepoStateSnapshot.ps1 -Action Save -Repos <repo1>,<repo2>
```

Add `-ReposDir <name>` to match whatever you passed the scan script.

Per repo it records the current branch (or detached HEAD), stashes any dirty tree with
`--include-untracked`, and writes `temp/sync-repo-state.json` holding the **stash commit SHA**.
The manifest is the recovery mechanism: if the session dies mid-sync, the stashes are still on the
stack and `-Action Restore` still finds them.

**Scope it to the conflicted repos only.** `Clean` and `FastForward` repos are never checked out —
their PR is raised from remote refs — so stashing them is pure risk for no benefit. `-Repos` is
mandatory to force that choice to be deliberate. If the user explicitly wants every repo
snapshotted anyway, pass them all; it works, it just does nothing useful for the clean ones.

`-Action Status` reports what the manifest holds and whether each stash still exists.

## Phase 3 — clean repos: PR straight across

For `Clean` and `FastForward` repos there is nothing to merge locally. Open a PR from the source
branch into the destination branch on the remote.

Draft the PR body from the commit range:

```bash
git -C <reposDir>/<repo> log --no-merges --pretty='%h %s' origin/<destination>..origin/<source>
```

**Sanitize that log before it goes anywhere near a PR** — replace every `AB#<digits>`/`#<digits>`
token in the quoted subjects with `AB-<digits>`, per *Work items on sync PRs*. Resolve this repo's
project's team-sync work item (ask if this run hasn't resolved one for that project yet) before
drafting the description, and pass only that one ID as the PR's `workItems`.

**This is where subagents earn their keep** — one per repo, summarising its (sanitized) commit
range into a PR description, all in parallel. They are non-interactive and independent, which is
exactly what subagents are good at. Launch them in a single message so they run concurrently.

Then confirm the full list with the user and create the PRs (see *PR backends* below). After each
PR is created, check its linked work items and unlink anything besides the team-sync item.

## Phase 4 — conflicted repos: local merge, user resolves (serial, main session only)

**Subagents cannot do this phase.** They run in the background and cannot prompt the user, so
conflict resolution stays in the main session, one repo at a time.

Per conflicted repo, in order:

1. **Confirm Phase 2 ran for this repo.** The tree must be clean because the snapshot stashed it,
   not because it happened to be clean. If it is still dirty, Phase 2 was skipped or failed — go
   back and run it rather than stashing by hand here.

2. **Create the sync branch from the destination** — not from the user's local branch:

   ```bash
   git -C <reposDir>/<repo> switch -c sync/<user>/<source>_to_<destination> --no-track origin/<destination>
   ```

   **Naming: `sync/{user}/{source}_to_{destination}`** — full version numbers/branch names,
   underscore before `to`, user segment matching whatever this workspace's normal feature-branch
   convention uses for identifying who's driving (e.g. `development/{user}/...`). Ask the user for
   their identifying segment if it isn't already established by convention elsewhere in the
   workspace.

   **`--no-track` is mandatory.** Without it git sets the new branch's upstream to
   `origin/<destination>`, and a later bare `git push` would then target the protected destination
   branch — breaking hard rule 2. Verified: `switch -c` without the flag really does set that
   upstream.

   Branching from `origin/<destination>` also deliberately deviates from "merge into the
   destination branch locally". Merging into the local destination branch would leave it diverged
   from `origin/<destination>` once the sync branch is pushed, quietly breaking the user's next
   `git pull` there. Branching from the remote ref produces an identical tree with no collateral
   damage. Submodules sit on detached HEADs by default, so the explicit `switch -c` is required
   regardless.

   If the branch already exists from an earlier run, ask whether to reuse or recreate it.

3. **Merge and stop:**

   ```bash
   git -C <reposDir>/<repo> merge --no-ff origin/<source>
   ```

4. **Hand over.** Show the conflicted paths and, for each, a one-line description of what each
   side did (`git log --oneline` on both sides of the range is enough). Then wait. Say plainly
   that the user resolves these and confirms when done.

5. **Verify the resolution** once they confirm — all four must pass:

   ```bash
   git -C <reposDir>/<repo> ls-files -u
   git -C <reposDir>/<repo> diff --check
   grep -rnI --exclude-dir={.git,node_modules,bin,obj,dist} -E '^(<{7}|={7}|>{7}|\|{7})( |\r?$)' <reposDir>/<repo>
   git -C <reposDir>/<repo> status --short
   ```

   `ls-files -u` is the authoritative check — it is the only one that catches a **modify/delete**
   conflict, where git leaves one side's file in the tree with no conflict markers in it at all.
   Marker-grep alone will happily pass a merge that is still unresolved. If anything fails, say so
   and hand back — do not clean it up yourself.

   **Use plain `grep` for the marker scan, never `git grep`, if the repo runs
   `core.autocrlf=true`.** With CRLF line endings a conflict separator on disk is `=======\r`.
   `git grep` does not strip the `\r`, so `( |$)` fails on it, while `<<<<<<< HEAD` and
   `>>>>>>> branch` still match on the space that follows them. Git Bash's `grep` does strip CR, so
   it matches all three. Reproduced on an isolated fixture: identical pattern, LF file — `grep`
   3/3, `git grep` 3/3; CRLF file — `grep` 3/3, `git grep` **2/3, missing `=======`**. A marker scan
   that silently skips every separator can pass a file that is still unresolved, defeating the
   point of an independent check. Check `core.autocrlf` per repo rather than assuming either way.

   Three details in that command matter. `\r?` makes the pattern correct regardless of which tool
   or line ending is in play, rather than relying on Git Bash `grep`'s CR-stripping. The `\|{7}`
   branch catches diff3/zdiff3 base markers. And `grep` exits **1 when it finds nothing** — here
   that is the *passing* case, so don't read the non-zero exit as a failure.

6. **Commit and push the sync branch:**

   ```bash
   git -C <reposDir>/<repo> commit --no-edit && git -C <reposDir>/<repo> push -u origin sync/<user>/<source>_to_<destination>
   ```

7. **PR from `sync/<user>/<source>_to_<destination>` into `<destination>`.** Same rule as Phase 3:
   sanitize `AB#<digits>`/`#<digits>` out of anything quoted from the old commit range, resolve
   this repo's project's team-sync work item, pass only that ID as `workItems`, and check the
   created PR's linked work items afterward — unlink anything else that got auto-linked.

## PR backends — probe, never assume

Detect what's available for this hosting provider, in this order, and stop at the first that
works. Don't assume Azure DevOps, GitHub, or any other provider — check what's actually connected
or installed in this environment first.

1. **A connected DevOps MCP server, if one is available** — preferred when connected. For Azure
   DevOps, `repo_pull_request_write` with `action: "create"` takes `repositoryId`, `project`,
   `sourceRefName`, `targetRefName`, `title`, `description`, and optionally `isDraft` / `workItems`
   / `labels`. **`workItems` carries exactly one entry: this run's team-sync work item** — see
   *Work items on sync PRs*, never the old commits' own work items. Note the ref names are **fully
   qualified**: `refs/heads/<branch>`, not `<branch>`. `repo_repository` with `action: "list"`
   resolves repo names per project. GitHub/GitLab MCP servers have their own equivalent PR-create
   tools — use whichever is connected. The server is not always connected — it may attach
   part-way through a session — so check for the tool rather than assuming either way.
2. **The provider's own CLI**, if installed and authenticated — `az repos pr create` (needs the
   `azure-devops` extension), `gh pr create`, `glab mr create`, etc. Ask before installing a
   missing extension or CLI; do not install silently.

   ```bash
   az repos pr create --organization <org-url> --project <project> --repository <repo> --source-branch <source> --target-branch <destination> --title "<title>" --description "<body>" --work-items <team-sync-id>
   ```

   Different repos in the same workspace may live in different orgs/projects (a monorepo-of-repos
   workspace can mix hosting scopes) — read each repo's `origin` URL rather than assuming they all
   share one.
3. **The URL in the push output.** Most git hosts print a "Create a pull request" link when a new
   branch is pushed. Capture it and give the user a clickable list. This always works and needs no
   extra auth — a perfectly good outcome, not a failure.

## Phase 5 — restore working state

Run once the **whole hop** is finished — every PR for that hop raised, or that hop abandoned. Not
per repo. In chain mode this runs once per hop, before moving on to the next one — don't carry a
stash across hops; a chain run can span days waiting on PR review, and a stash left open that long
is exactly the kind of thing that gets forgotten or clashes with unrelated later work.

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/Invoke-RepoStateSnapshot.ps1 -Action Restore
```

Per manifest entry it returns to the recorded branch, re-applies the stash **by SHA**, and drops
it only once the apply succeeds. The manifest is deleted only when every repo restored cleanly —
otherwise it is kept so `-Action Restore` can be re-run after the blockers are cleared.

Four outcomes are not failures of the script and must be relayed to the user as-is:

| Outcome | Meaning | What to do |
| --- | --- | --- |
| `Blocked` (merge in progress) | a merge was never finished or aborted | user finishes/aborts, re-run Restore |
| `Blocked` (tree dirty) | new uncommitted work appeared since the snapshot | user decides; `-Force` applies over it |
| `Conflict` | the stash clashes with what the sync changed | **stash is kept** — user resolves, then drops it |
| `Failed` (stash MISSING) | the stash was dropped by something else | the detail line carries the raw `git stash apply <sha>` recovery command |

Never resolve a stash-apply conflict yourself — same rule as a merge conflict.

**Line endings on untracked files, if `core.autocrlf=true`.** `git stash -u` round-trips untracked
files through the object store, so under that setting an untracked file written with LF comes back
with CRLF. Verified on one such repo: a probe file's hash changed across a save/restore cycle for
exactly this reason, while tracked modifications round-tripped byte-identical. Harmless for normal
Windows source files; mention it if the user has untracked LF-sensitive files (shell scripts,
fixtures) in a repo with that setting.

## Phase 6 — shareable report

Produce a markdown file the user can paste straight into Teams, a wiki page, a PR description, or
an email. **Generate it with the script, never hand-write the tables** — hand-built tables drift in
columns and wording between runs, and a repo quietly missing from one is the exact failure this
skill exists to prevent.

First write the PR results the run produced, as a small JSON array:

```json
[
  { "repo": "SomeRepo", "prId": 12345, "prUrl": "https://dev.azure.com/...",
    "techStoryId": 85397, "techStoryUrl": "https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/85397" },
  { "repo": "OtherRepo", "prId": 12347, "prUrl": "https://dev.azure.com/...",
    "syncBranch": "sync/alex/1.1.0_to_1.2.0",
    "note": "Both migration files kept side by side; no SQL dropped",
    "techStoryId": 85397, "techStoryUrl": "https://dev.azure.com/EvolveMedical/Spesnet.Lumina/_workitems/edit/85397" }
]
```

Only `repo` is required. `syncBranch` and `note` are for conflicted repos — the note is the one
place a human explains *how* a conflict was resolved, so fill it in from what the user actually
did rather than paraphrasing the diff. `techStoryId`/`techStoryUrl` name the team-sync work item
that repo's PR was linked to (per *Work items on sync PRs*) — fill them in for every repo that got
a PR, so the report itself is proof of which record-keeping item covers it.

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/sync-team-branches/scripts/New-SyncReport.ps1 -ScanJson temp/sync-scan.json -PrResultsJson temp/sync-prs.json
```

Writes to `<root>/documents/sync-reports/sync-<src>-to-<dst>-<yyyyMMdd>.md` (falling back to
`<root>/temp/` if there is no `documents/`). `-OutputPath` overrides, `-PassThru` also echoes the
markdown.

**Chain mode:** run this once per hop, right after that hop's Phases 3–5 finish — the filename
already encodes `<src>-to-<dst>`, so each hop gets its own report and none overwrite each other.
Once the whole chain is done (or the user stops partway through), give them the plain list of
report file paths in order; there's no need for a script to build an index page for that, it's just
a short list.

The report has seven sections, each omitted when empty: **Synced** (repo, outcome, commits,
conflicts, linked PR), **Conflicts resolved** (per-file, with the sync branch and the human's
note), **Already up to date**, **Not applicable** (with the missing branch named), **Waiting on a
prior hop** (chain mode), **Locked (excluded)**, and **Needs attention** (fetch/merge failures).
Every scanned repo lands in exactly one of them.

If a synced repo has no PR recorded, the script emits an **Incomplete** callout naming it and
warns on the console. Do not suppress that — it is the honest signal that the sync is unfinished.

Tell the user the file path. Do not post it anywhere yourself: sharing is theirs to do, and the
report may name in-progress work.

## General wrinkles worth checking for, in any workspace

- A repo directory that's a plain clone rather than a git submodule still works — it still has
  `origin` and branches, and the scan picks it up like any other repo.
- Branch sets can differ per repo — a given source → destination sync may only apply to some of
  them. That is expected, not an error; `Skipped` exists for exactly this.
- **Watch for other people's pre-existing stashes** in a repo (`stash@{0}` already occupied before
  this skill runs). This is exactly why Phase 5 restores by commit SHA — a `stash pop` or
  `stash apply stash@{0}` in that repo would grab the wrong work.
- Version-scoped config/migration files (e.g. `Migrations/<version>/...`) are a common source of
  real conflicts, since both branches tend to edit their own version's folder — including
  modify/delete conflicts when a later branch renames or removes a file the older branch still
  edits. `git merge-tree`'s predicted paths should match what the real `git merge` reports; if they
  don't, treat that mismatch itself as worth investigating.
- If the workspace root itself is a git repo with submodule pointers but no remote (a personal
  snapshot repo, not something pushed anywhere), the pointer updates after submodule PRs complete
  can be committed there purely as a local record — never push that repo just because this skill
  ran.
- **The lock check is Azure DevOps-specific and per-repo**, not a workspace-wide setting. A
  workspace can mix hosting (or mix Azure DevOps projects, like this one's `HealthCodeIndex_V2`) —
  each repo's org/project is read from its own `origin` URL, and a repo whose origin isn't
  recognized as Azure DevOps simply has no lock concept applied (everything included, no warning
  needed beyond the general "az not found" one if that's the actual reason). Don't assume a whole
  workspace is or isn't Azure DevOps from looking at one repo.
- **A locked branch is usually locked on purpose, at the end of that version's life** — after
  everything on it has already been forward-merged, to stop anyone accidentally pushing to a
  branch nobody should touch again. Treating it as "doesn't exist" for sync purposes matches that
  intent. If the user believes a locked branch still holds unsynced content, that's a call for a
  human to make in Azure DevOps (unlock it, or read the branch directly with a one-off
  `git log`/`git diff`) — this skill does not unlock branches, per hard rule 10.
- **A repo's own version history skipping a version is normal, not a red flag.** A version bump is
  project-wide, but a branch for it is only cut in a repo that actually had changes for that
  release — a repo created partway through a project's life, or one with nothing to ship in a given
  release, will legitimately never carry that `team/{version}` branch. Phase 0 already builds each
  repo's own chain around this (its next hop simply lands on whatever version it has next), so this
  needs no special handling from you beyond reading the wave plan as given — don't second-guess it
  into a "gap to close" unless the user specifically believes something was actually missed.
- A chain can be long. A workspace with a year or more of releases can easily have 20–30 distinct
  `team/{version}` branches once every patch version is counted, giving that many waves — walking
  the whole thing in one sitting is unrealistic once PR review time is factored in. Bounding with
  `-FromVersion` to resume past the waves already confirmed landed is the normal way to pick a chain
  run back up, not a fallback for something going wrong.

## Example: wrinkles observed in one Lumina workspace run

These are illustrative, not universal — they held for one specific run of this skill and are kept
here as a worked example of the kind of thing Phase 1's scan and Phase 4's conflict list will
surface, not as assumptions to carry into a different workspace.

- A plain-clone repo (`Spesnet_Lumina_UI_PlayWright`) sat alongside git-submodule repos in the same
  `projects/` directory and synced identically to the others.
- Only 4 of 10 repos had both branches in a `1.1.0 → 1.2.0` sync; the other 6 were correctly
  `Skipped`.
- Two repos (`Spesnet_Lumina.Documents`, `Spesnet_Lumina_Gateway`) carried unrelated pre-existing
  stashes at `stash@{0}` from other work.
- `UserStore`'s `1.1.0 → 1.2.0` scan hit both a content conflict in
  `Migrations/1.1.0/Migrations.sql` and a modify/delete conflict on
  `Migrations/1.2.0/Migrations.sql`; the real `git merge` reproduced exactly the two paths
  `merge-tree` predicted.
- The remote already carried `sync/heinriche/1.0.2_to_1.1.0` branches from a previous round in two
  repos, alongside an older bare-form branch (`sync/1.0-to-1.1`) that predated the user-scoped
  naming convention and was not followed.
- A Phase 0 discovery run in this same workspace found **30 distinct `team/{version}` branches**
  from `0.0.0` up to `1.2.0` across 11 repos. Coverage varied widely: `Spesnet.Lumina` carried
  nearly every version, while `HealthCodeIndex_V2` and `WidgetLocalHarness` carried none (neither
  has adopted the `team/*` convention at all — every wave shows them `Skipped`, which is correct,
  not a bug). `Spesnet_Lumina.Reporting` carries `1.0.0` and `1.2.0` but never had `1.0.1`, `1.0.2`,
  `1.1.0`, `1.1.1`, or `1.1.2` — its own chain runs `1.0.0 -> 1.2.0` directly, as a **first hop**
  (nothing precedes it, so no `-PriorSource`/`-PriorDestination` gate applies), sitting in the
  `1.2.0` wave alongside — but in a different group from — repos going `1.1.x -> 1.2.0`. Bounded to
  `1.0.0` and up, that same run produced 7 waves and, in the `1.2.0` wave alone, five separate
  groups (repos jumping from `1.0.0`, two different `1.1.0` cohorts with different prior hops,
  `1.1.1`, and `1.1.2`) — a good illustration of why groups, not one uniform source per wave, are
  the unit Phase 1 actually scans.
- **Locked branches in this same workspace line up exactly with "shipped and done."** In
  `Spesnet_Lumina_Gateway`, `az repos ref list` reported `team/0.0.1` through `team/1.0.0` as
  locked and `team/1.0.1`, `team/1.1.0`, `team/1.2.0` as not — i.e. every version whose release
  cycle had fully closed out was locked, and only the three still-live ones were left open. A Phase
  0 run there dropped straight to a 3-version, 2-hop chain once the locked ones were excluded, with
  no further handling needed. A single-pair scan of a locked pair (`0.0.1 -> 0.0.2`) returned
  `Locked` immediately, without attempting `merge-tree` at all.
