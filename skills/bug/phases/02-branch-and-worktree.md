# Phase 2 — Pick the branch, then create the worktree

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Do this **immediately after claiming the item, before validating or investigating it.** Everything
that follows — is this really a bug (Phase 3), can it still be reproduced (Phase 4), where does it
live in code (Phase 5) — must be checked against the branch the fix will actually land on, not
against whatever commit the main checkout happens to have. Investigating against the wrong code is
how a stale reproduction or a since-fixed line gets reported as still-broken.

This is not a violation of "no code changes before approval" (non-negotiable 3). Creating a worktree
touches nothing in the main checkout and commits nothing; it is a read-only vantage point for
Phases 3–5, exactly like mirroring the work item was in Phase 1. The first *edit*, test, or commit
still waits for Phase 6.

## Identify the repo(s) to start from

Use whatever Phase 1 already gave you — the `area`, the title, a repo named outright in the
description, or a similar prior ticket. Say which repo(s) you're starting from and why.

**A symptom can live one repo over from where it shows** — Phase 4 (Reproduce and locate) may turn
up a second repo you didn't expect. Don't wait to be certain of every repo before proceeding: create
the folder for what you can identify now, and add a repo to it the moment Phase 4 finds a second one.
Reuse the team version chosen below for it — ask again only if that repo lacks the branch.

## Ask which team version to branch from

**Always ask. Never infer it, never default it, never carry it over from a previous fix.** It decides
three things at once: the base commit, `{team}` in the branch name, and the PR target.

Enumerate what actually exists in each identified repo first, so the choice is made from real
branches:

```bash
cd <repo path> && git fetch origin && git branch -r | grep -oiE 'team/[0-9.]+$' | sort -uV
```

Present those as options (`AskUserQuestion`) and wait for an answer. Give **two options at most** —
usually the newest two versions that exist in every identified repo. Say which one you would pick,
and why, in one sentence. Show the other versions only if the user asks.

**The branch scheme is the same in every repo. The available versions are not.** A repo can skip a
version, or carry no `team/*` branches at all. So run the command above in **every** repo you touch,
including one discovered later in Phase 4. Never carry a version list from a previous fix or from a
document.

Where a repo lacks the chosen version, say so and ask again. Never pick the nearest one quietly. A
repo with no `team/*` branches needs a different base — ask which, do not invent it.

## Create the work item folder

One work item gets **one folder**, created by the shared `sdd:workspace` script:

```
<workspace root>\.claude\worktrees\{id}-{slug}\
    workitem.json    id, type, title; per repo: base branch, dev branch, PR
    CLAUDE.md        generated; says "work only here" and lists the paths
    src\{Repo}\      a git worktree per repo, with a copy of that repo's CLAUDE.md
    graph\           graphify code graph of src\
```

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py new --id <id> --repos <RepoA>,<RepoB> --version <chosen version>
```

It fetches each repo, creates each worktree with `--no-track` from `origin/team/{version}` (matched
case-insensitively, so `HealthCodeIndex_V2`'s `Team/1.1.0` resolves), writes `workitem.json` and the
folder's `CLAUDE.md`, and builds the graph. A repo that must base off something other than
`team/{version}` gets `--base <Repo>=<branch>` — only after the user named that branch. If the
chosen version is missing from a repo, the script stops and lists what it found; ask again.

Default branch: **`dev/{developer}/{version}/bug/{id}-{slug}`**, e.g.
`dev/heinriche/1.1.0/bug/79714-gateway-missing-app-key-header`. Do not hand-build a different one.

**A second repo found later** (Phase 4): run `env.py new` again with the same `--id` and
`--version` and only that repo in `--repos`. Existing repos are skipped.

Branch derivation, the `--no-track` reason, the missing-files table, port caveats and cleanup are
in `references/branch-and-pr.md`. Read it before the first `env.py` call.

**Every phase from here on — validation, reproduction, root cause, test, fix, `dotnet test`, commit,
push — runs inside `src\{Repo}\`**, never in the main checkout. Each repo's `CLAUDE.md` is copied into
its worktree. `.claude/` and other gitignored files are still absent; read those from the main
checkout when you need them.
