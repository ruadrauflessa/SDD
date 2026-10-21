---
name: release-prep
description: >-
  Prepare a release across every repo in a workspace: find which repos have work on the
  integration branch that has not reached the matching release branch, dry-run each merge with
  `git merge-tree` BEFORE anything is opened, resolve the exact remote branch casing, gather and
  validate the linked work items, get the user's approval on a written plan, then raise one
  pull request per repo and hand off to the `release-notes` skill. Also refreshes an
  already-open release PR when late commits land on the source branch, re-syncing its
  description and work-item links. Works on any workspace with sibling git repos under a shared
  directory (submodules or plain clones), a single repo, and any pair of branch names. USE THIS
  SKILL when asked to "prep the release", "prepare release 1.1.0", "which repos have changes not
  yet in release", "what is not in the release branch yet", "raise the team to release PRs",
  "set up the release pull requests", "cut the release", "get 1.2.0 ready to release", or
  "update the release PR, more commits came in". Triggers - release prep, release readiness,
  team to release, integration to release, release PR, cut a release, what is pending for
  release, release train, forward-merge to release, release notes chain, refresh release PR,
  late commits on a release PR.
---

# Release prep (integration branch → release branch, then notes)

Answers one question first — **"what is actually going out?"** — and only then creates anything.

In a multi-repo workspace each repo is independently versioned and merges separately. A release
is therefore N pull requests with no shared commit, and the failure mode is a repo silently
missing from the train. This skill enumerates every repo, proves each merge is clean before it is
proposed, and ends by handing a complete PR set to `release-notes`.

```
scan every repo ─┬─ Ready ─────→ check PRs still headed INTO the source branch ─→ approval gate ─→ PR per repo ─→ verify work-item links ─┐
                 ├─ Conflicts ─→ STOP, hand to user (see sync-team-branches Phase 4)                                                      ├─→ release-notes
                 ├─ UpToDate ──→ report, no PR                                                                                            │
                 └─ Skipped ───→ report loudly (missing branch)                                                                           ┘
```

## Where this runs

Installed through the `devops` plugin, so it is offered in every project. It fits:

- a **multi-repo workspace** — sibling git repos under one shared directory, submodules or plain
  clones, mixed freely;
- a **single repo** — point `-Root` at it and pass `-ReposDir ''`.

The scan locates the workspace by walking up from the **current directory** for an ancestor
holding the repos directory (`-ReposDir`, default `projects`) or a `.gitmodules`. It cannot infer
this from its own path. Pass `-Root` / `-ReposDir` / `-Repos` to override.

Branch names are not assumed. `-SourcePattern` and `-TargetPattern` take a `{0}` version
placeholder and default to `team/{0}` and `release/{0}`. Anything works: `develop` → `main`,
`release/{0}` → `main`, `Team/{0}` → `Release/{0}`. Casing in the pattern does not matter — the
scan resolves the real casing from the server (see hard rule 2).

## Hard rules

Violating any of these creates something outward-facing that is wrong, or misses a repo.

0. **Always confirm the version before scanning.** If the user's request already names one
   (e.g. "prep the release", "cut the release", "what is not in release branch yet") with no
   version attached, ask them which team branch version to prepare — do not guess it, and do not
   reuse a version from an earlier run, a file in `temp/`, or the most recent `team/*` branch. If
   the request already names a version (e.g. "prepare release 1.1.0"), use that one and skip the
   question. See Phase 0 below.
1. **Confirm before opening any PR.** Show the exact list — repo, source → target, commit count,
   work items — then ask once. A PR is visible to the whole team and triggers pipelines. This is
   the gate; nothing before it writes anything.
2. **Never send a hand-typed branch name to the forge.** Use the `SourceBranch` / `TargetBranch`
   the scan resolved from `git ls-remote`. On Windows the filesystem is case-insensitive, so
   `origin/team/1.1.0` cheerfully resolves a ref that is really `origin/Team/1.1.0` — and Azure
   DevOps then rejects the lower-cased name with `TF401398: the source and/or the target branch no
   longer exists`. This is real and it is in this workspace, not hypothetical.
3. **Fetch immediately before scanning.** A clean result is a snapshot and goes stale the moment
   anyone pushes. Never reuse a scan from earlier in the session to justify creating a PR.
4. **Never resolve a merge conflict.** A conflicted integration → release merge is unusual and
   means someone committed straight onto the release branch. Stop, show the conflicted paths, and
   let the user decide. `sync-team-branches` Phase 4 already implements the
   local-merge-user-resolves flow if they want it.
5. **Never push to the release branch**, never force-push, and never `git checkout` inside the
   repos. Every phase here reads remote refs only; nothing needs a working tree.
6. **Report `Skipped` repos out loud.** A repo missing from a release because its branch pair
   does not exist is exactly the failure this skill exists to prevent. Never let it pass as a
   silent absence from a table.
7. **Never merge, approve, or complete someone else's PR into the source (team) branch.** Phase 2
   only reports what is still pending — deciding whether a pending fix should ride this release is
   the user's call (and often a reviewer's, not the person running this skill).
8. **Write for a tired reader, in plain English.** The PR description, the plan the user approves
   and every report in chat follow the house style (ASD-STE100 Simplified Technical English):
   one idea per sentence, active voice, small words. Read `${CLAUDE_PLUGIN_ROOT}/references/writing-style.md`
   before Phase 5. Paths, branch names, work-item titles and commands stay exact.

## Phase 0 — confirm the version

Before running anything, make sure the version is known and confirmed with the user.

- If the user's request already states a version (e.g. "prepare release 1.1.0", "get 1.2.0 ready
  to release"), use it and move on — no need to ask again.
- If it does not (e.g. "prep the release", "cut the release"), ask which team branch version to
  prepare **as a multiple-choice question (`AskUserQuestion`), not free text** — a typed version
  number is a typo waiting to happen (e.g. `1.1.0` vs `1.10.0`), and this answer drives every
  branch name for the rest of the run. Enumerate the live `team/*` branches first (e.g.
  `git branch -r | grep -oiE 'team/[0-9.]+$'` — case-insensitive, see the `HealthCodeIndex_V2`
  trap) and offer each as an option so the user picks rather than types.
- Never infer the version from a stale scan file in `temp/`, the highest-numbered branch found, or
  a version mentioned earlier in the conversation for a different purpose. Each run asks fresh
  unless the current request already answered it.

Only once the version is confirmed does Phase 1 run.

## Phase 1 — scan

One command classifies the whole workspace. It fetches with prune, resolves exact branch casing
from the server, measures divergence, dry-runs the merge with `git merge-tree --write-tree`
(entirely in the object database — no ref, no index, no working tree), flags database-migration
files, extracts work-item candidates from commit subjects, and parses the Azure DevOps
org/project/repo out of each `origin` URL.

```bash
pwsh -File ${CLAUDE_PLUGIN_ROOT}/skills/release-prep/scripts/Scan-ReleasePrep.ps1 -Version 1.1.0 -JsonPath temp/release-prep-scan.json
```

Useful overrides: `-Root`, `-ReposDir`, `-Repos`, `-SourcePattern`, `-TargetPattern`, `-NoFetch`.

Exit 0 = nothing blocking, 1 = at least one repo conflicts, 2 = at least one repo errored.

Do **not** fan this out to subagents. It is pure shell over a handful of repos and finishes in
seconds; one agent per repo would be slower, cost more, and add nothing — there is no reasoning
per repo.

| Status | Meaning | Path |
| --- | --- | --- |
| `Ready` | source has commits the target lacks, merge is clean | PR |
| `Conflicts` | `merge-tree` reported conflicted paths | STOP — hard rule 4 |
| `UpToDate` | target already has every source commit | no PR |
| `Skipped` | one or both branches absent on origin | no PR, report loudly |
| `Skipped` + `MissingTargetBranch` | source (team) branch exists but the release branch does not | STOP — surface the ADO branches link, see below |
| `FetchFailed` / `MergeError` | auth, network, or unrelated histories | investigate, don't guess |

**`Behind` is not a problem.** It counts commits on the release branch that the integration
branch lacks, which is normal — hotfixes land on release and flow back later. Report it, do not
act on it. If the user wants that direction merged, that is `sync-team-branches`, not this skill.

Present the table before doing anything else.

### Missing release branch — a `Skipped` repo the user must act on

`Skipped` has two very different causes, and they need different messages:

- **Source (team) branch missing** — this version has no work in that repo. Normal, not a
  problem. Report it and move on (hard rule 6 — still say it out loud, just without urgency).
- **Target (release) branch missing while the source branch exists** — this repo has real
  commits waiting for this release, but nobody has cut the release branch yet. This is a `git`
  problem the skill cannot fix for the user: creating a branch is a write to the forge, and this
  skill never pushes or creates branches (hard rule 5). Only the user can create it, in the ADO
  web UI or with their own `git push`.

The scan script already tells the two apart — each repo row carries `MissingSourceBranch` /
`MissingTargetBranch`, and prints a "MISSING RELEASE BRANCH" block at the end with a direct link
per repo. Always relay that block to the user, not just the table: for every repo where only the
target is missing, state plainly that they need to create `<target>` from `<source>` themselves,
and give them the clickable ADO branches-page link (`Repo.BranchesUrl` in the JSON, e.g.
`https://dev.azure.com/{org}/{project}/_git/{repo}/branches`) — that page has the "New branch"
button already scoped to the right repo. Do this **before** the approval gate (Phase 5): a repo
stuck on a missing release branch cannot get a PR this run, and the user needs to know now, not
after everything else is already approved and created.

Never try to create the release branch yourself, even if asked to "just create it" — that write
belongs to hard rule 5. Tell the user it is a manual step and hand them the link.

## Phase 2 — check for pull requests still headed INTO the source branch

The scan only sees commits already on the source (team) branch. It is blind to work that is
reviewed but not yet merged — and that work will silently miss this release if the release PR
gets completed first. Before anything else, list open PRs **targeting** the source branch:

```
repo_pull_request  action=list  project=<project>  targetRefName=refs/heads/<source>  status=Active
```

Query **per distinct `AdoProject`**, project-wide (omit `repositoryId` so one call covers every
repo in that project at once — this is what caught it in practice: four pending PRs into
`team/1.1.0`/`Team/1.1.0` across four different repos, found by two calls, not ten).

For every result:

- If that repo has no `Ready` entry from Phase 1 (it showed `UpToDate`), say plainly that once
  this PR merges, the repo will need a release PR that this run did **not** raise.
- If that repo does have a `Ready` entry (a release PR is about to be opened, or already exists),
  say plainly that this pending PR will be picked up automatically **only if it merges before the
  release PR is completed** — Azure DevOps keeps a branch-to-branch PR's diff live. If the release
  PR is completed first, the fix rides the next release instead.

Report the full list in the same message as the Phase 1 table — repo, PR id, title, and which of
the two cases above applies. Never merge or approve any of them yourself (hard rule 7); this is
information for the user's approval decision in Phase 5, not a task to execute.

## Phase 3 — check for pull requests that already exist

The scan is pure git and cannot see the forge. Before proposing anything, list open PRs into the
target branch so a second one is never raised for the same repo.

```
repo_pull_request  action=list  project=<project>  targetRefName=refs/heads/<target>  status=Active
```

Query **per distinct `AdoProject`** in the scan output — a workspace can span several projects
(here `HealthCodeIndex_V2` has its own). Match on repository plus source branch.

- Already open, source unchanged → nothing to do, say so.
- Already open, but the scan shows new commits → **refresh mode**, see below. Do not open a second PR.

## Phase 4 — resolve the work items

`WorkItemCandidates` in the scan JSON are *candidates* scraped from commit subjects
(`#12345`, `AB#12345`, `ADO 12345`, `Fix 12345`). They are unverified — a `#` number could be
anything.

Validate them in one batch call and keep only what comes back:

```
wit_work_item  action=get_batch  project=<project>  ids=[...]
fields=["System.Id","System.Title","System.WorkItemType","System.State","System.Parent",
        "System.Tags","System.AreaPath","Microsoft.VSTS.Common.Priority"]
```

Two things to notice while you are here:

- **Work items can live in a different project from the repo.** In this workspace all work items
  sit in the main project even for `HealthCodeIndex_V2`. Query the work-item project, not the
  repo's project, or you get nothing back.
- **Commits with no work item are normal** (dependency bumps, config, `.gitignore`). List them in
  the PR body by short SHA and subject so nothing is invisible.

## Phase 5 — approval gate

Write the plan out and ask once. Per repo: source → target (exact casing), commit count, files
changed, the validated work items with their titles, and any migration files the scan flagged.
Call out `Skipped` and `Conflicts` repos, and the Phase 2 pending-PR findings, in the same message.
Repeat the missing-release-branch links here too (not just earlier) — this is the last message
before anything gets created, and it is the user's reminder to go create those branches, whether
now or after this run's PRs go out.

Migrations deserve their own line. A release carrying a schema change needs a deployment decision,
and the scan already knows — do not make the user discover it in review.

Then stop and wait. **Do not create anything until the user says go.**

## Phase 6 — create the pull requests

One PR per `Ready` repo, using the scan's resolved branch names:

```
repo_pull_request_write  action=create
  project=<AdoProject>   repositoryId=<AdoRepo>
  sourceRefName=refs/heads/<SourceBranch>   targetRefName=refs/heads/<TargetBranch>
  title="Merge <SourceBranch> into <TargetBranch>"
  workItems="78167 79799 80459"          # space-separated, CREATE ONLY
  description=<body>
```

Body (plain English, see rule 8): a one-line summary (commit count, files, `+`/`-`, and that the merge is clean), then a
`## Fixes included` list of `**#id** — title`, then any commits with no work item. Keep it under
4000 characters — that is a hard API limit.

Create them **in parallel** — they are independent calls.

If the MCP server is not connected, fall back in this order: `az repos pr create` (needs the
`azure-devops` extension — ask before installing), then the "Create a pull request" URL that
Azure Repos prints on push. Handing the user a clickable list is a perfectly good outcome, not a
failure. Azure Repos does **not** support `git push -o` — that is GitLab.

## Phase 7 — verify the work-item links

`workItems` only works on **create**, and it can silently drop cross-project ids. Always read the
links back:

```
repo_pull_request  action=get  pullRequestId=<id>  includeWorkItemRefs=true
```

Anything missing gets linked explicitly:

```
wit_work_item_link_write  action=link_to_pull_request
  workItemId=<id>
  projectId=<GUID of the WORK ITEM's project>
  pullRequestProjectId=<GUID of the PR's project>
  repositoryId=<repo GUID>   pullRequestId=<id>
```

Both GUIDs are required for a cross-project link, and they are genuinely different values. Get
them from `repo_repository action=get`, which returns the repo GUID and its project GUID.

**`[AB#12345]` in a commit message does not auto-link inside Azure DevOps.** That syntax is for
the GitHub-to-ADO integration. A commit that reads `[AB#80459]` produces no link at all in an ADO
repo — verified. Always link explicitly rather than trusting the commit convention.

## Phase 8 — hand off to release-notes

Invoke the `release-notes` skill with the PR ids and their projects. It will ask its own questions
(scope, priority presentation, migration detection, wiki publishing) — do not pre-answer them, but
do pass forward what this run already knows so it is not recomputed:

- the PR ids and which project each lives in;
- the validated work items;
- the migration finding — the scan already checked the same diffs, so say plainly whether any
  migration files were found rather than making that pass run again.

`release-notes` writes `documents/release-notes/…` and publishes to the project wiki. Wiki
publishing is shared, team-visible content — it asks first, and that is deliberate.

## Refresh mode — late commits on an open PR

Common and easy to miss: a PR is raised, then someone pushes another commit to the source branch.
Azure DevOps folds the commit into the existing PR automatically, but the **description and the
work-item links do not update**, so the release notes go stale and traceability breaks.

Re-run Phase 1, then for each repo whose open PR has new commits:

1. Validate the new work items (Phase 4).
2. `wit_work_item_link_write action=link_to_pull_request` for each new one (Phase 7).
3. `repo_pull_request_write action=update` with a corrected description — commit count, file
   count, and the new fix in the list. A stale "2 commits, 9 files" on a PR that now moves 11
   files misleads every reviewer who reads it.
4. Update the release-notes file **and** the wiki page if they were already produced. Adding a
   fix changes the item count in the wiki intro line too.

Say explicitly whether the extra commits change the review burden. A PR that doubles in size after
someone approved it needs looking at again.

## Traps

- **Branch casing differs per repo.** `HealthCodeIndex_V2` uses `Team/1.1.0` and `Release/1.1.0`;
  every sibling uses lowercase. Local git hides it, Azure DevOps does not. Hard rule 2 exists for
  this. The scan reports the resolved name in `SourceBranch` — use that string verbatim.
- **A repo with no branch pair is not an error.** Version sets differ per repo, so a 1.1.0 release
  legitimately covers a subset. Report which, and why (`Skipped` carries the missing branch name).
- **A missing release branch (target only) IS something to act on, just not by this skill.** The
  skill never creates branches (hard rule 5) — it hands the user the ADO branches-page link
  (`Repo.BranchesUrl`) and tells them to create `<target>` from `<source>` by hand. Don't silently
  fold this into the generic `Skipped` explanation; it reads very differently from "no work this
  version" and needs its own line with a clickable link.
- **PR descriptions cap at 4000 characters.** A repo with 30 commits will blow it. Summarise by
  work item rather than listing every commit.
- **Migration files are the signal worth surfacing.** The scan flags `.sql`, anything under a
  `Migrations/` folder, and EF Core's `^\d{14}_.*\.cs$` naming. A release carrying one needs a
  deployment decision before the PRs complete, not after.
- **Do not read a completed PR as a failed scan.** If a repo shows `UpToDate` when you expected
  work, someone probably completed the PR already. Check PR status with `status=All` before
  concluding anything was lost.
- **The workspace root repo (if it has no remote) is never pushed.** After the submodule PRs
  complete, the updated pointers can be committed at the root purely as a local snapshot.
- **Phase 2 is not optional and not rare.** First real run of this skill (2026-08-21, release
  1.1.0) found 4 open PRs into `team/1.1.0`/`Team/1.1.0` across 4 different repos — none of them
  visible to the Phase 1 git scan, because none had merged yet. Two of those repos had already
  shown `UpToDate` in Phase 1 and would have silently needed a second release PR later. Skipping
  Phase 2 to save two API calls is how a fix quietly misses a release.
