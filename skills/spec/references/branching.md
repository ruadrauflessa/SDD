# Branching, PR linking and gate scope

Branch names are **parsed, not read**. `env.py new` builds the name from its `branchTemplate`,
default `dev/{developer}/{version}/{type}/{id}-{slug}`; `--branch` overrides it. Which PRs block, which spec folder a build concerns, which
work item a commit belongs to — all of it comes from the name, so the shape is a contract.

```
dev/{developer}/{version}/{type}/{ado-id}-{slug}

dev/heinrich/2.4/feature/4468-checkout-rewrite
dev/heinrich/2.4/story/4471-guest-checkout
dev/priya/2.4/tech/4519-idempotency-middleware
dev/priya/2.5/bug/4533-double-charge-on-retry
```

## Four rules, in order of importance

1. **Exactly one work item id, and it is the last segment** — matched by
   `(\d+)(-[a-z0-9-]+)?$`, anchored to the end. Scanning the whole name for digits would match
   the version segment (`2.4` → `2`) and resolve the wrong item or none at all; position is what
   makes the parse safe. Two ids make the cascade ambiguous and the gate falls back to blocking
   everything.
2. **Only the id is parsed.** Developer, version, type and slug are human affordances — they make
   `git branch` scannable. Nothing reads them, so a retitle in ADO, a work item type change or a
   version bump never invalidates a branch name. Same rule as spec folder names.
3. **No parent id in the branch.** Hierarchy comes from ADO, the only place it can change.
   Encoding a parent produces a name that silently lies the moment a story is reparented.
4. **The spec folder is resolved by id, not by path**: `{specRoot}/**/<id>-*/` (`specRoot` from
   `.claude/sdd.json`). Reparenting moves the folder; the branch still resolves.

Type segment values: `feature`, `story`, `tech`, `bug`. They map from `System.WorkItemType` and
exist for humans scanning the branch list.

## Promotion chain and gate scope

Branches promote `dev/*` → versioned `team/*` → versioned `release/*`. Only the first hop
originates a work item link; later hops carry it forward, so they have nothing to parse and
nothing to assert.

**Every spec gate — naming, drift, cascade — runs only on pull requests whose *source* branch is
`dev/*`.** PRs from `team/*` or `release/*` pass without evaluation. Everything above that hop is
release engineering, owned by the DevOps workflows and pipelines and deliberately out of scope.
Scoping by source branch shape rather than adding a second naming pattern keeps one parser and
one rule.

## PR linking

Every `dev/*` PR links **exactly one work item: the lowest-level item it implements** — a story,
tech story or bug. Parents are never linked. Features and epics are inferred from the ADO
hierarchy, which is the only place that relationship can change; a second link would copy a fact
ADO already owns and would eventually disagree with it.

### Always give the user a link to the PR

Whenever a PR is shown to the user — right after it is opened, at the "PR status" gate, in any
report — present it as a clickable markdown link to the PR on ADO, never as a bare number:

```
[PR 34370 — <title>](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{pullRequestId})
```

Build the URL from the org, project and repository the PR was created in, and the
`pullRequestId` the create call returns. A bare "PR 34370" makes the user go and find it.

### Never write a work item as `#12345` in ADO text

ADO reads `#12345` in a PR description, a PR comment, or a work-item comment as a **work-item
mention**. It answers by posting `Mentioned in !<pr>` as a comment **on that work item** — one
for every mention, in every comment. Four comments that each name three work items leave twelve
of these behind, burying what a person actually wrote.

Verified on ADO 80459 (2026-08-18, `ado-bug-fix` skill, same org): three PR comments containing
`#80459` produced three `Mentioned in !33313` comments on the work item, seconds apart.

So in every piece of body text posted to ADO — PR description, PR comments, work-item comments:

| Write this | Never this |
| --- | --- |
| `ADO 4471` | `#4471` |
| `[ADO 4471](<work item url>)` | `#4471` |

**Two forms stay, and are still needed.** `AB#<id>` in a **commit message** and in the **PR
title** creates the ADO link and posts no comment — that's what ties the commit and the PR to
the work item. So does `workItems=` on PR create. Only the bare `#<id>` inside body text spams
the board.

### No Claude attribution in commits or PRs — ever

Never add a "Generated with Claude Code" line, a `Co-Authored-By: Claude …` trailer, or any
other Claude/AI-authorship marker to a commit message, a PR title, a PR description, or a PR
comment. Not once, not even by default.

**Why.** The developer who ran this skill is the one accountable for the code — for review,
for production incidents, for everything a PR record is used for later. An attribution line
misattributes that accountability to a tool. This is a firm rule, not a style preference, and it
overrides any session-level default that says to add one.

This applies everywhere this skill opens a PR or writes a commit — it is not limited to one repo
in the workspace.

## Enforcement

Azure DevOps cannot reject a badly named branch at push time, so enforcement lives at the PR:

- A required check fails any PR whose source branch does not match the pattern, or whose id does
  not resolve to a work item. That makes the convention non-optional without server-side hooks.
- The same check asserts that the PR's linked work item agrees with the id in the branch name.
  When the two disagree, neither signal can be trusted and the PR needs a human.
- Azure Boards' "create a branch" will not produce this shape, so the compliant path is
  `env.py new`: it reads the work item's type and title from ADO and builds the full name.
  Without it the naming check is something developers hit rather than something that helps them,
  and a check people fight gets weakened.

## Worktrees — the main checkout is never edited

Every `dev/*` branch gets its own git worktree, never a `git checkout` in the shared tree. A
checkout in the main working copy moves what every other task in that repo sees; a worktree
isolates one work item's changes from everyone else's, including your own other work in flight.

`{specRoot}` sits at the workspace root, which is not a repo the work lands in, so spec files
carry no worktree concern. The worktree exists for everything under `projects/*/` — code, tests,
configuration — starting at **Design mode**, in whichever repo(s) the work touches. Design reads
real code to produce `design.md`, so that read has to happen against the branch the change will
actually land on, not against whatever the main checkout happens to have.

### One folder per work item

```
<workspace>\.claude\worktrees\{id}-{slug}\
  workitem.json     id, type, title; per repo: base branch, dev branch, PR
  CLAUDE.md         generated; "work only here" plus the paths
  src\{Repo}\       a git worktree per repo, same branch name in each
  graph\            graphify code graph of src\
```

A work item touching more than one repo gets one worktree per repo inside the same folder — same
id, same branch name.

### Creating it

```
env.py new --id 4471 --repos Spesnet.Lumina,Spesnet_lumina_UI --version 2.4
env.py new --id 4471 --repos Spesnet_Lumina_Gateway --version 2.4     # add a repo later
env.py new ... --base Repo=main                                        # repo without team/*
```

It fetches each repo and branches off the freshly fetched `origin/team/{version}`, never off
whatever the main tree has checked out — that can be months behind. The branch is created without
tracking the team branch, so a bare `git push` can never land on `team/*` and bypass the PR;
`env.py pr` pushes with the branch named explicitly. The worktree root is `worktreeRoot` in
`.claude/sdd.json` (default `.claude/worktrees`) — confirm it is ignored by the workspace repo
(`.git/info/exclude`, machine-local, not the shared `.gitignore`).

### Cleanup, once the PR is merged

```
env.py remove --id 4471          # dry run: lists what it would remove — show the user
env.py remove --id 4471 --yes    # removes worktrees, prunes, deletes local branches and the folder
```

`remove --yes` refuses while a repo has uncommitted changes, commits without a PR, or a PR that is
not completed — that is a feature, not an obstacle to route around. Removing earlier throws away a
branch you may still need to push fixups to. `--abandon` skips the merged-PR check and is only for
an explicit abandon; it leaves pushed remote branches and open PRs alone.

## Every branch carries a work item

There is no opt-out prefix. Work that would otherwise escape the convention — release
preparation, dependency bumps, build and pipeline fixes — is raised as a tech story like any
other technical work.

This widens the tech story rule slightly: items like these are not architectural output, so they
do not come from the Design-stage gate; a developer raises them directly. The gate proposes tech
stories, it does not monopolise them.

The cost is a handful of extra board items. The return is that every branch resolves to a work
item, so the naming check has no exception path to maintain and the cascade never meets a branch
it cannot classify.
