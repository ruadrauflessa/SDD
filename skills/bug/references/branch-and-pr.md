# Branch, commit and PR mechanics

## Branch name

```
dev/{developer}/{version}/bug/{work item id}-{slug}
```

| Part | How to derive | Example |
| --- | --- | --- |
| `{developer}` | local part of `git config user.email` | `heinriche@evolvemed.co.za` → `heinriche` |
| `{version}` | **ask the user** — the target team-branch version, without the `team/` prefix | `team/1.1.0` → `1.1.0` |
| `{work item id}` | the ADO id, digits only | `79714` |
| `{slug}` | lowercase kebab slug of the title, ~3–6 words, no punctuation | `gateway-missing-app-key-header` |

```
dev/heinriche/1.1.0/bug/79714-gateway-missing-app-key-header
```

`env.py new` derives this name itself from the `branchTemplate` in `<workspace>/.claude/sdd.json`
(default `dev/{developer}/{version}/{type}/{id}-{slug}`). Do not build it by hand. `--branch <name>`
overrides it — use that only when the user asks.

Existing history in these repos also contains `development/{user}/{version}/{id}`,
`development/{user}/bugfixes/{version}/{id}` and the older underscore form
`dev/{user}/{version}/{id}` + `_` + `{slug}`. The scheme above is the one specified for **this**
workflow — use it, and don't "correct" it to match older branches.

### `{version}` is always asked, never derived

It sets the base commit, the branch name and the PR target at once, so Phase 1 asks the user
outright — before any investigation, so Phases 2–4 read the right code from the start. Enumerate
the real options per repo before asking:

```bash
cd <repo path> && git fetch origin && git branch -r | grep -oiE 'team/[0-9.]+$' | sort -uV
```

**The scheme is the same in every repo. The available versions are not.** A repo can skip a version,
or carry no `team/*` branches at all. So run the command above in **each** affected repo, every time.
Never carry a version list from one fix to the next, and never copy one from a document.

Check the chosen version exists in **every** affected repo before you run `env.py new`. Where a
repo does not have it, say so and ask again. Never substitute the nearest version quietly. The
script also stops on a missing version and lists the team branches it did find.

A repo with no `team/*` branches needs a different base. Ask which one — do not invent it — then
pass it as `--base <Repo>=<branch>`.

## Work in the work item folder

**Do not `git checkout` in the submodule itself.** That switches the shared working tree, disturbs
whatever else is in flight there, and moves the commit the root snapshot points at. The work item
folder holds a worktree per repo instead, so the fix is isolated and other work continues untouched.

**If the repo is a git submodule, check its `.git` first.** A real `.git` **directory** means
`git worktree` behaves exactly as it does in a standalone repo. A `.git` *file* pointing into
`.git/modules/` brings the usual submodule-worktree awkwardness — flag it immediately, before you
create anything. This runs at Phase 1, before the approval gate exists, so there is no summary to
attach the warning to yet; say it plainly in chat instead.

### Layout

```
<workspace root>\.claude\worktrees\{id}-{slug}\
    workitem.json    id, type, title; per repo: source, ADO project/repo, base branch, dev branch, PR
    CLAUDE.md        generated; says "work only here" and lists the paths
    src\{Repo}\      a git worktree per repo, with a copy of that repo's CLAUDE.md
    graph\           graphify code graph of src\
```

```
C:\GitProjects\Lumina\.claude\worktrees\79714-gateway-missing-app-key-header\src\Spesnet_Lumina_Gateway
```

`.claude/worktrees/` is where Claude Code already puts its own worktrees, so the fix sits beside
them instead of in a second place nobody remembers. The `{Repo}` folder under `src\` must match the
repo's folder name in the workspace — tooling such as `run-lumina-full.ps1 -Worktree <id>` reads
the repos from `workitem.json` and relies on it.

### Creating it

```bash
python <plugin root>/scripts/env.py new --id 79714 --repos Spesnet_Lumina_Gateway --version 1.1.0
```

The script fetches each repo, bases off `origin/team/{version}` freshly fetched (matched
case-insensitively), creates the worktree with `--no-track`, copies each repo's `CLAUDE.md` in,
writes `workitem.json` and builds the graph. Never base off whatever the main tree happens to be
on, which may be months behind. All subsequent phases (test, fix, `dotnet test`, commit, push) run
**inside `src\{Repo}\`**, never in the main checkout.

A second repo found later: run `new` again with the same `--id` and `--version` and only that repo
in `--repos`. Repos already in the folder are skipped. `env.py status --id <id>` shows each repo's
branch, base, commits ahead, clean or dirty, and PR.

### Why `--no-track` matters (the script passes it)

Without it, a worktree branched from `origin/team/1.1.0` gets **`origin/team/1.1.0`** — the team
branch — as its upstream. `push.default` is unset on this machine (so `simple` applies) and a bare
`git push` therefore *errors* rather than pushing to the team branch — but the error message
helpfully suggests `git push origin HEAD:team/1.1.0`, and pasting that pushes your fix straight onto
the shared integration branch, bypassing the PR entirely.

So never create a worktree for this flow by hand, and always push with the branch named explicitly:

```bash
git push -u origin dev/heinriche/1.1.0/bug/79714-gateway-missing-app-key-header
```

### What a fresh worktree does *not* have

Everything gitignored is absent, because a worktree only materialises tracked files. The one
exception is `CLAUDE.md`, which the script copies in:

| Missing | Consequence |
| --- | --- |
| `.claude/` | **No per-repo settings or skills in the worktree.** Expected — they are usually gitignored. Read them from the main checkout instead. `CLAUDE.md` *is* there, copied by `env.py new` |
| `bin/`, `obj/` | First `dotnet test`/`build` is a full cold build — don't pass `--no-build` on the first run |
| `node_modules/` | `npm ci` needed before any UI work — the script says so when it sees `package.json` |
| `.env` | Playwright credentials are absent — matters only if the fix needs the e2e suite |

`appsettings.json` **is** committed, so it comes across; and the `EvolveNuget` feed is registered
per machine, so restore works without extra setup.

### Concurrency caveats

- **Ports are machine-wide.** Two work items cannot run the same service at once — the port table in
  the root `CLAUDE.md` applies globally, not per worktree. Stop one stack before starting another.
- **UAT SQL is shared.** Nothing about a worktree isolates the database.
- **The root snapshot is unaffected** until you deliberately update it. The root records the commit
  checked out in the *main* tree, so a fix committed in a worktree won't show as a pointer change —
  which is the isolation you want, but it also means the root snapshot won't record the fix.

### Cleanup, after the PR merges

```bash
python <plugin root>/scripts/env.py remove --id 79714          # dry run — show the user
python <plugin root>/scripts/env.py remove --id 79714 --yes    # after they agree
```

`--yes` removes each worktree, prunes, deletes the local branch and deletes the folder. It refuses
while any repo has uncommitted changes, commits without a PR, or a PR that is not `completed` —
that is a feature. Don't route around it by hand without checking what would be discarded. Leave
cleanup until the PR is actually merged; removing it earlier throws away the branch you may still
need to push fixups to.

This is normal end-of-life cleanup, distinct from an **abandoned** fix — see the Abandon section in
`SKILL.md`, which uses `remove --id <id> --abandon` (dry run, then `--yes`) mid-flow instead. That
skips the merged-PR check but leaves pushed remote branches and open PRs alone — ask before touching
either.

`env.py status --id <id>` shows what exists, and `git worktree list` inside a repo is the quickest
way to spot an abandoned worktree from a previous fix.

## Commit

One repo per commit — **a change spanning two repos can never share a commit.** If the fix touches
two submodules, that is two commits, two branches and two PRs. One `env.py pr` call opens both
with the same description; cross-reference them in a PR comment on each once both URLs exist.

Commit inside the submodule. Reference the work item with `AB#<id>` so ADO links the commit:

```
fix(gateway): forward X-Application-Key on the lumina_Userstore route [AB#79714]

The Ocelot route for lumina_Userstore has no upstream header transform. So the
gateway drops the X-Application-Key header. UserStore then rejects every proxied
call with E200801.

Adds the header to the route's UpstreamHeaderTransform. Adds a regression test
that checks the header is on the outgoing request.
```

The subject line says what now works, in the present tense, in 72 characters or fewer. The body
follows the house style — one idea per sentence, active voice, 25 words maximum. First paragraph:
the cause. Second paragraph: the change. See `writing-style.md`.

Then push:

```bash
git push -u origin dev/heinriche/1.1.0/bug/79714-gateway-missing-app-key-header
```

### Never push or PR the workspace root

The root repo **has no remote by design** — it is a personal snapshot recording which submodule
commits went together. After the submodule commit you may optionally commit the updated pointer at
the root, locally. Do not propose pushing it or opening a PR against it.

## Pull request

Create it in the **submodule's** ADO repo, targeting the team branch, with the work items linked.
Write the description (template below) to a file in the work item folder, then:

```bash
python <plugin root>/scripts/env.py pr --id 79714 \
  --title "fix(gateway): forward X-Application-Key on the lumina_Userstore route [AB#79714]" \
  --description-file '<folder>\pr-description.md' \
  --work-items 79714
```

For each repo with commits ahead and a clean tree, the script pushes the branch (`git push -u
origin <branch>`), opens the PR against that repo's base branch, links the work items, and records
the PR in `workitem.json`. `--repos A` limits it to one repo, `--draft` opens a draft. Re-running is
safe: repos with a PR are skipped, and an already-open PR is picked up. It prints each PR URL —
report every one as a clickable link.

**Repos do not all live in the same ADO project.** The script reads each repo's ADO project from
`workitem.json`. The PR comments and work-item calls below do not — pass the right `project` on
every one of them. A wrong project fails the call or creates nothing.

**The description is capped at 4000 characters** — the script refuses a longer file. That is now easy to fit, because the description
holds the change and nothing else. Everything else goes in a comment on the PR — see the split below.
Do not spill any of it into the work item's Root Cause Details / Resolution: those stay a 1–3
sentence summary (see `ado-fields.md`).

### Never write a work item as `#12345` in ADO text

ADO reads `#12345` in a PR description, a PR comment or a work-item comment as a **work-item
mention**. It answers by posting `Mentioned in !<pr>` as a comment **on that work item** — one for
every mention, in every comment. Four PR comments that each name three bugs leave twelve of these
on the board. They carry nothing, and they bury the comments a person actually wrote.

Verified on ADO 80459 (2026-08-18): three PR comments containing `#80459` produced three
`Mentioned in !33313` comments on the work item, seconds apart. The Verification comment named no
work item with `#`, and produced none.

So in every piece of body text you post to ADO — PR description, PR comments, work-item comments:

| Write this | Never this |
| --- | --- |
| `ADO 80459` | `#80459` |
| `CR 79387 — Disclaimer Character Limit Increase` | `#79387` |
| `[ADO 80459](<work item url>)` | `#80459` |

**Two forms stay, and you still need them.** `AB#<id>` in a **commit message** and in the **PR
title** creates the ADO link and posts no comment — that is what ties the commit and the PR to the
work item. So does `--work-items` on `env.py pr`. Only the bare `#<id>` inside body text spams the
board. Do not "tidy" the `AB#` forms away.

### The split — description versus comments

| Goes in | What it holds |
| --- | --- |
| **Description** | What broke, the cause, and what you changed. Nothing else. |
| **Comment 1 — Reported and requirement basis** | The report, the environment, the linked story or CR |
| **Comment 2 — Verification** | The Phase 8 gate results, with real output |
| **Comment 3 — Design notes** | The file and line, ruled-out causes, why this approach, what you left alone |
| **Comment 4 — Out of scope** | Related defects you found and did not fix here |

A reviewer opens the description to answer one question: *what does this change, and why?* The
comments hold the report, the evidence and the reasoning. They are there when the reviewer wants
them, and out of the way when the reviewer does not.

Post the comments straight after you create the PR. Do not wait to be asked.

### Description template

**The description must be easy to digest.** A reviewer reads it in 30 seconds and knows what this
change does. Anyone who wants more opens the comments. Three short headings, nothing else.

Fill it in the house style — see `writing-style.md`. One idea per sentence, active voice, 25 words
maximum.

The title uses the same rule as the commit subject: say what now works, present tense, 72 characters
or fewer.

```markdown
## What broke

ADO {id}. One or two sentences, in plain words. Say what the user saw.

## Why

One or two sentences. Say the cause in plain words. No file, no line, no class name here.

## What changed

One line per file. Say what the code does now, not what it used to do.

- `path/to/File.cs` — the route now copies `X-Application-Key` onto the call it sends on.
- `path/to/FileTests.cs` — new regression test.

More detail is in the comments below.
```

**Limits, and they are hard:**

| Rule | Limit |
| --- | --- |
| Whole description | 150 words |
| Each of the first two sections | 2 sentences |
| Code snippets | none |
| Nesting, sub-bullets, tables | none |

A section that will not fit belongs in a comment. Do not shrink the type — move the content.

### A filled example

```markdown
## What broke

ADO 79714. Users could not open the admin user list. The page showed "Application not found".

## Why

The gateway did not pass the application key on to UserStore. UserStore rejects any call without it.

## What changed

- `configuration/ocelot.json` — the `lumina_Userstore` route now copies `X-Application-Key` onto the
  call it sends on.
- `GatewayRouteTests.cs` — new regression test.

More detail is in the comments below.
```

### The comments

Create each one as its own thread, so a reviewer can read and resolve them one at a time:

```
repo_pull_request_thread_write action=create
  repositoryId=<submodule repo name>
  project=<the ADO project that owns this repo>
  pullRequestId=<id>
  status=Closed
  content=<one of the templates below>
```

**Use `status=Closed`.** These are notes from the author, not review feedback. An `Active` thread
reads as an open question and shows on the PR as unresolved.

**Comment 1 — Reported and requirement basis.** Where the defect came from, and what the fix is
measured against. Always post this one.

```markdown
**Reported**

ADO {id}: what the reporter saw, and where — environment, user, organisation.

**Requirement basis**

The linked User Story or Change Request (`ADO {id} — title`), and the criterion this fix is measured
against. Write "no linked requirement" when there is none.
```

**Comment 2 — Verification.** This is what lets a reviewer trust the fix without re-deriving it.
Fill it with real output. Never write "tests pass".

```markdown
**Verification**

- Regression test: `Namespace.ClassTests.Method_Expected_Condition`
- Before the fix: `<verbatim failure message>`
- After the fix: passing
- Revert-check: the test fails again with the fix stashed. It guards the defect.
- Flakiness: 5 runs in a row, no variation
- Full suite: `dotnet test <solution>` — unit and ArchUnit green
- Symptom re-check: how you confirmed the reported symptom is gone
```

**Comment 3 — Design notes.** Why this fix, and not another one.

```markdown
**Design notes**

**Where it broke** — the mechanism, anchored to `path/to/File.cs:123`. Say why the value, route or
state was wrong. Give the commit and date if `git blame` found the change.
**Ruled out** — the other causes you considered, and why each one is not it.
**Why this approach** — why the symptom is now impossible, not merely unseen.
**Left alone** — anything you deliberately did not change, and why.
**Reproduction** — the narrowest path that shows the defect. Say **observed** or **inferred**.
```

Skip this comment only when there was nothing to rule out and no choice to make.

**Comment 4 — Out of scope.**

```markdown
**Out of scope**

Related defects you found and did not fix here. One line each, with its own work item number —
written `ADO 80123`, never `#80123`.
```

Skip this comment when you found nothing.

## After the PR

Comment the PR link on the work item, then set the fields in `ado-fields.md` and move the state to
`Resolved`. Leave `Closed` to the reporter.

**One comment on the work item, and no `#` in it.** The sibling bugs and the linked CR belong in
that comment as `ADO 80455`, `CR 79387` — plain text. Written as `#80455` they each post a
`Mentioned in !<pr>` comment onto that sibling's board. See the rule above.
