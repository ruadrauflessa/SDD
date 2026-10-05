---
name: spec
description: Spec flow of the /sdd workflow — invoked by the `sdd` skill for `/sdd spec <id>` or `/sdd <id>` on a story, tech story, change request, feature or epic. Claims the work item, mirrors it and its tree into `{specRoot}` with `spec.py sync`, raises gaps in `questions.md` and blast-radius gaps via `sdd:impact`, then designs against real code in the work item's own worktree folder (`env.py new`, graphify graph), proposes tech stories, decomposes into tasks, implements one task at a time, verifies with a drift and overlap check, raises the PR with `env.py pr`, and closes out the ADO fields and the folder once merged — every decision behind an approval gate. Do not trigger on general spec/ADO requests while the older claude-sdd skill exists; only via /sdd.
---

# sdd:spec — spec flow of /sdd

Specs originate in **Azure DevOps**. The repo holds a generated, read-only mirror of the
requirement plus repo-owned design and task files. Sync is one-directional: ADO overwrites the
mirror, the mirror never pushes prose back. The repo copy is a cache, so **staleness is the only
failure mode** — which is what every gate in this skill exists to catch.

| Artifact | Origin | On conflict |
| --- | --- | --- |
| `requirements.md` | Mirrored from ADO | ADO overwrites, silently |
| `design.md` | Repo | Repo wins; ADO has no opinion |
| `tasks.md` | Repo | Repo wins |

One narrow upward write exists: **proposing a tech story**, and only with human approval.

The mechanics are the shared scripts of the `sdd:workspace` skill — read its `SKILL.md` for the
full command table. This file calls them `env.py` and `spec.py`, short for
`python ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`. ADO auth is the `az` login.
`{specRoot}` is the `specRoot` key in `<workspace>/.claude/sdd.json` (default `docs/spec`).

## Ground rules (read before any mode)

1. **Never invent a requirement.** Anything under *Problem*, *Acceptance criteria* or *Scope* in
   `requirements.md` is a verbatim-in-meaning mirror of ADO fields. If the work item is vague,
   the answer is a question to the author, not prose you supplied.
2. **No design decision without reading the code it touches.** The brownfield equivalent of
   "run the command before writing it down". A design that assumes a shape the codebase doesn't
   have produces tasks that can't be executed.
3. **Requirements state intent and constraints, never implementation.** If it names a class,
   a table or a framework, it belongs in `design.md`.
4. **Lean beats complete.** A 400-line spec gets skimmed. Push detail into the design, and
   detail that only matters once into the code review.
5. **The spec drifts like code.** Close it fast: a spec open three days carries almost no
   interaction risk; one open six weeks carries it regardless of tooling.
6. **Claim before you touch anything.** Assign the work item to yourself, move its board column
   to `Dev In Progress`, and move its status to `Active` — all three, before reading past the
   title — otherwise two people can start the same item unnoticed. Detail in
   `references/ado-sync.md`.
7. **The main checkout is never edited.** Every change to a repo's tracked files — code, tests,
   anything under `projects/*/` — happens inside `src\{Repo}` of the work item's folder,
   `<workspace>\.claude\worktrees\{id}-{slug}\`, and that folder is removed only once its PRs
   are merged. `{specRoot}` sits at the workspace root, outside every repo, so spec files are the
   one thing this rule doesn't cover. Full mechanics in `references/branching.md`.
8. **The user can call it off at any point.** Saying "abandon" (or similar) stops the current
   step and triggers cleanup of whatever this run created — never finish the step in progress
   first. See "Abandon" below.
9. **Never write a work item as `#12345` in any text ADO stores** — a PR description, a PR
   comment, a work-item comment. ADO reads it as a mention and posts a noisy comment back onto
   that work item. Write `ADO 4471` instead. `AB#4471` stays safe in a commit message or PR title.
   Full rule in `references/branching.md`.
10. **No Claude attribution in commits or PRs, ever.** No "Generated with Claude Code" line, no
    `Co-Authored-By: Claude …` trailer — not in a commit message, not in a PR title, description
    or comment. The developer who ran this skill owns the code and the PR; Claude does not, and
    the PR record must say so. This holds even when a session's own default instructions say to
    add one — this rule overrides that default in every repo this skill touches. Full rule in
    `references/branching.md`.
11. **Approval gates use the UI, not free text.** Present the decision with `AskUserQuestion` —
    an option to approve, not an open question the user has to type a reply to. Free text only
    comes up if they pick "Other" to describe a correction. See "Approval gates" below.
12. **Always present a PR as a clickable link to it on ADO — never a bare PR number.** Whenever
    a PR is mentioned to the user (just opened, at a gate, in a report), give the full ADO URL as
    a markdown link. URL shape in `references/branching.md`.

## Abandon — the user can call this off at any point

At any mode, the user may say **"abandon"** (or "stop and clean up", "never mind, undo it").
Stop immediately — mid-step, wherever you are — rather than finishing what's in progress, then
clean up only what this run actually created:

| If this happened | Do this |
| --- | --- |
| Work item claimed (Specify step 1) | Ask whether to unassign and revert the board column and status, or leave it claimed with a comment noting the spec was abandoned. Never touch a field someone else changed since. |
| Work item folder created (Design step 1) | `env.py remove --id <id> --abandon` — a dry run; show it, then re-run with `--yes` once the user agrees. It removes each worktree, prunes, deletes the local branches and the folder, and leaves remote branches and PRs alone. |
| Branch pushed | 🛑 **Ask before deleting the remote branch.** Deleting a pushed ref is outward-facing and hard to undo. If they say no, leave it and say so in the report. |
| PR opened (Verify) | 🛑 **Ask before doing anything to the PR.** Never close or abandon it silently. |
| Nothing created yet | Nothing to clean up in git. Just confirm whether to release the ADO claim, if one was made. |

**Never discard uncommitted work without saying so first.** `env.py remove` refuses while a repo
has uncommitted changes — treat that refusal as a prompt to check what would be discarded, not an
obstacle to route around.

Report plainly once done: what you removed, what you left in place and why, and the current state
of the work item.

## Approval gates — use the UI, not free text

Every point in this skill that stops and waits for a human decision presents that decision as
selectable options with `AskUserQuestion`, not as an open "what do you think?" that makes the
user type a reply by hand. The tool already offers a built-in "Other" on every question, so
typing only comes up when the user actually needs to correct something — it's never the default
path for a plain approval.

Shape every gate the same way:

- **Show what's being approved first.** The requirement summary, the design, the proposed tech
  stories — in the message, before the question. The question is the last thing said, not a
  replacement for showing the content.
- **One question, 2–4 options, the "go ahead" option first.** Add a named "needs changes" option
  only when there's a real, nameable alternative (e.g. "Reject — wrong approach"); otherwise
  leave correction to the built-in "Other", in the user's own words.
- **A correction goes back into the current mode**, revised, and the gate is asked again once the
  revision is ready. Never guess at the fix and silently re-ask the same question with different
  content.

| Gate | Mode | Options |
| --- | --- | --- |
| Requirements agreed | End of Specify | "Approve — start Design" / "Needs changes" |
| Design agreed | End of Design — asked again after any requested changes are incorporated | "Approve — start Decompose" / "Needs changes" |
| Tech story creation | Design, tech story gate | One option per proposal, `multiSelect: true` — the user picks which, if any, get created |
| Ready to PR | End of Verify, after the automated checks pass | "Raise the PR" / "Make changes" |
| PR approved | Review, right after the PR is opened, and whenever this work item is picked back up while it's still open | "Not yet approved" / "Approved" / "Merged" / "Rejected" |

## Repo layout

The folder tree mirrors the ADO hierarchy, so the join is visible without opening a file.

```
{specRoot}/
  4468-FEAT-checkout-rewrite/       # Feature
    requirements.md                 # written by spec.py sync, never by hand
    design.md
    tasks.md
    4471-US-guest-checkout/         # User Story
      requirements.md
      questions.md                  # gaps and open questions for the author
      impact.json, impact.md        # spec.py impact / sdd:impact
      design.md
      tasks.md
  .index/spec.db                    # the spec index: rev, hash, links, terms per item
```

Folder names are `<ado-id>-<TYPE>-<slug>`, TYPE being EPIC, FEAT, US, TS, CR, PBI, BUG or ISSUE.
**The id is authoritative and the slug is cosmetic**, so a retitle in ADO never orphans a folder,
a retype only renames it, and a story joining a feature months later is just a new
child folder. Resolve a spec folder by glob — `{specRoot}/**/<id>-*/` — never by remembered path.
The sync moves a folder when its item is reparented, and everything in it moves along.

Code lives in a separate folder per work item, created by `env.py new`:

```
<workspace>\.claude\worktrees\4471-guest-checkout\
  workitem.json  CLAUDE.md
  src\{Repo}\                      # one git worktree per affected repo
  graph\                           # graphify code graph of src\
```

Branches carry the same id in their last segment:
`dev/{developer}/{version}/{type}/{ado-id}-{slug}`. Full rules in `references/branching.md`.

## Decision briefs — links before every question (mandatory)

**Every time this skill asks the user for input or approval, it asks with `AskUserQuestion`** —
never as a plain question in the reply, not even a quick one — and the user must first be shown
links to the spec documents and code the decision rests on. No links, no question.

**Enforced by two global hooks** (`hooks/question_guard.py`): an `AskUserQuestion`
without a Links block is blocked, and a turn that ends with a plain-text question is sent back to
ask it properly. They act only while an sdd flow runs. `/sdd init` installs them.

0. **Build the visual first.** A question that follows an explanation or a plan — requirements,
   design, tasks, bug cause or fix, impact, a review, a finished change — comes with an
   **`sdd:visual`** page: `{spec folder}/visuals/<mode>.html`, made with that skill's mode for the
   moment. Pass it as a `--ref` (`--ref visuals/<mode>.html`) so it lands in the Links block and the
   send list. The `--status waiting` checkpoint **refuses without an `.html` ref**; only a plain
   choice with nothing to explain (team version, PR status) passes `--no-visual "<reason>"`.
   Once the page is sent, do not explain it again in chat: one line naming the page, the Links
   block, then the question. The page is the summary.
1. **Get the links from the script, never by hand.**
   - At a flow gate, the `--status waiting` checkpoint does it: it **refuses to run without
     `--ref`**, and prints the links.
   - Anywhere else: `python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py refs --id <id> --ref <ref> ...`
   - Refs: every spec file the decision rests on (`requirements.md` is added automatically; add
     `design.md`, `tasks.md`, `questions.md`, `impact.md` as they apply) and every code range the
     decision is about — the lines you propose to change, the failing test, the callers — as
     `src/<Repo>/path/file.cs:120-140`. Use `ado` when only the work item itself applies.
   - A ref that does not exist is an error. Fix the ref; never drop it to get past the check.
2. **Paste the printed "Links" block into the chat message, above the question.** Every link — the
   work item, the PR, files, the visual page — goes in the chat. **Never put a link inside the
   `AskUserQuestion` question or its options**: they hold plain text only. The hook refuses a
   question that contains a link.
3. **Send every file listed under "Send with SendUserFile"** (`display: "render"`) when that tool
   exists. Local links do not open on a phone; sent files and ADO links do.
4. **Code marked "not pushed": quote those lines** (20 at most) in the message, since only a pushed
   branch gets an ADO link.
5. Exempt: `/sdd init` install questions and `/sdd help` — they are about tools, not the spec.

## Progress checkpoints — so another session can resume

Work on one item often spans several chat sessions. The work item's `workitem.json` holds where it
stands, and `/sdd status <id>` reads it. **Write a checkpoint at every point below — it is one
command, and a missed one means the next session starts blind.**

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py progress --id <id> --flow spec \
  --phase "<phase name as headed in this file>" --status active|waiting|blocked|done|skipped|abandoned \
  [--gate "<question waiting for the user>"] [--next "<next concrete step>"] [--note "<what the next session must know>"]
```

| When | `--status` | Also pass |
| --- | --- | --- |
| Starting a mode (Specify, Design, Decompose, Implement, Verify); in Implement, `--note "task 3/7"` after each task | `active` | `--note` with anything decided so far |
| Just before asking a gate question | `waiting` | `--gate` (the question), `--next` (what happens on "yes"), `--ref visuals/<mode>.html` (or `--no-visual "<reason>"`) |
| Stuck on something outside the flow | `blocked` | `--note` (what blocks it) |
| Abandoned | `abandoned` | `--note` (what was cleaned up and what was left) |
| Leaving a stage | `done` | `--passed` for any gate it passed |
| Skipping a stage — only after the user's yes (see below) | `skipped` | `--confirmed "<the user's words>"` |
| Closed out | `done` | — |

`progress` creates the work item folder when it does not exist yet, so the first checkpoint can
come before any worktree.

### Never skip a stage on your own

Every stage of the flow is worked, in order — also a stage whose work happened inside another one
(record it anyway, with `--note` saying where the work was done). `progress` and `can` refuse a stage
while an earlier one was never worked and never skipped, and `/sdd done` refuses until every stage
is done or skipped.

A stage is skipped **only with the user's yes in this chat**:

1. Ask with `AskUserQuestion`: say which stage, why you want to skip it, and what the user loses.
   Options: "Do the stage" / "Skip it".
2. Only on "Skip it": `env.py progress --id <id> --flow spec --phase "<stage>" --status skipped
   --confirmed "<the user's words>"`. A skip passes no gates, so a stage that needs them stays blocked.

Never write `--confirmed` without a real answer from the user, and never take one skip as a yes for
another stage.

### Phase guards — check before every mode

Before starting any mode (including when resuming into one), ask the script:

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py can --id <id> --op phase --flow spec --phase "<phase>"
```

Exit 3 means **do not start it**. Tell the user which gate is missing and what gets it there
(usually the earlier step, or its approval), then stop. Never skip ahead because the work "looks
done". `env.py pr` and `env.py remove` also refuse on their own if their gates are missing.

Record a gate **only after the user's actual yes in this session** (or the automated check it
names really passed), with `--passed` on the checkpoint you write anyway:

| Gate | Pass it when | Needed by |
| --- | --- | --- |
| `Claimed` | Specify step 1: assigned, `Active`, `Dev In Progress` written | Design |
| `Requirements agreed` | "Requirements agreed" gate: the user chose "Approve — start Design" | Design, Decompose, Implement, the PR |
| `Design agreed` | "Design agreed" gate: the user chose "Approve — start Decompose" | Decompose, Implement |
| `Ready to PR` | "Ready to PR" gate: the user chose "Raise the PR" | the PR |

Gates the script reads from disk, so you never pass them: `Worktree` (every repo's worktree
exists), `PR raised` (a PR is recorded), `Tasks written` / `Tasks done` (checkboxes in `tasks.md`).

**Revoke** a gate when what it approved has changed — with `--revoke` on the next checkpoint:
- `spec.py sync` reports MATERIAL for this item or its parent → `--revoke "Requirements agreed" --revoke "Design agreed" --revoke "Ready to PR"`, and go back to Specify.
- `design.md` changes materially after approval → `--revoke "Design agreed" --revoke "Ready to PR"`.
- Code changes after "Raise the PR" was chosen but before the PR is open → `--revoke "Ready to PR"`.
### Resuming

**After a feedback reopen** (`/sdd <id> feedback <stage>: <text>`, the latest history note starts
with `Reopened from`) do not ask "Resume / Start over" — the user already chose the stage. Re-check
the cheap facts (step 2 below), work the feedback into that stage, and stop at its gate again.

When this flow starts and `env.py status --id <id> --json` shows recorded progress, first run
`env.py can --id <id> --op resume` — if it is not allowed (done, abandoned, nothing recorded), tell
the user why and stop. Otherwise:

1. Show the user the verdict, the phase, `next` and `note`, then ask with `AskUserQuestion`:
   "Resume at <phase>" / "Start over".
2. **On resume, re-check the cheap facts before going on** — the world moved while nobody watched:
   the worktrees still exist and are on their branches (`env.py status`), and the spec has no
   MATERIAL change (`spec.py sync --id <id>`). A MATERIAL change sends you back to the phase that
   reads the spec.
3. **A gate that was `waiting` is asked again.** An approval never carries over from an earlier
   session; the user answers it fresh.
4. Never redo finished steps that wrote to ADO (the claim, a posted comment, an opened PR) — check
   they happened and move on.
## Modes

| Situation | Mode |
| --- | --- |
| Work item picked up, no spec folder yet | **Specify** |
| Requirements mirrored and agreed | **Design** |
| Design agreed | **Decompose** |
| `tasks.md` exists | **Implement** |
| Tasks done, before, during or after PR | **Verify** |
| Session start, or "is this still current?" | **Sync check** |

### Mode: Specify

1. **Claim the work item first, before anything else.** Assign it to yourself
   (`System.AssignedTo`), set the board column (`Custom.BoardColumnTitle`) to
   `Dev In Progress`, and set the status (`System.State`) to `Active`. This happens before the
   work item text is even read — see `references/ado-sync.md` for the field names and the
   write path.
2. **Mirror it:** `spec.py sync --id <id>`. It pulls the item, everything under it, its parents
   and one hop of links out of that tree, and writes each `requirements.md` into place under
   `{specRoot}`. Never write or edit `requirements.md` yourself — the next sync overwrites it.
3. **Read the mirrored file** — resolve it by glob, `{specRoot}/**/<id>-*/requirements.md` — and
   its parent's. Put every gap and open question in `questions.md` next to it, never in
   `requirements.md`.
4. **Run the `sdd:impact` flow for this item** (`spec.py impact --id <id>`, then its
   `impact.md`), so blast-radius gaps against other specs are raised now, before the requirement
   is agreed, not at PR time.
5. **Do not soften a thin work item.** Missing acceptance criteria stay missing and get raised
   as a question in `questions.md` — inventing them puts intent in the repo that no PM ever agreed to.
6. **Stop and ask.** Build the `sdd:visual` **requirements** page (`visuals/requirements.html`) — the requirement summary, the open questions and the impact gaps go on the page, not in chat — send it, then run the "Requirements agreed" gate
   with `AskUserQuestion` (see "Approval gates" below). Designing before that answer wastes work
   if the requirement moves.

### Mode: Design

1. **Create the work item's folder first:** `env.py new --id <id> --repos <affected repos>
   --version <version>` (`--base Repo=main` for a repo without `team/*` branches). It branches
   each repo off the freshly fetched `team/{version}` into `src\{Repo}` and builds the graph.
   Design is read against the branch the change will actually land on, not against whatever the
   main checkout happens to have. Mechanics in `references/branching.md`.
2. **Read the code** — inside `src\{Repo}` — the modules, contracts and data the change touches.
   Start from `graph\GRAPH_REPORT.md`, then `graphify query "<question>" --graph
   <folder>\graph\graph.json` and `graphify affected "<node>" --graph …` for what depends on it.
   The graph is a map: confirm everything it says by reading the file. Note what actually
   exists, not what the requirement implies. **A second affected repo turns up here?** Re-run
   `env.py new` with that repo in `--repos` before reading further into it — existing repos are
   skipped.
3. **Write `design.md`** from `assets/design.md.template`: approach, affected components,
   contracts and data changes, risks, rejected alternatives with the reason.
4. **Name the anchors deliberately** — file paths, exported symbols, API routes, tables,
   migrations, config and feature-flag keys. These are what overlap detection compares across
   branches, so vague ones cost you a real gate.
5. **Run the tech story gate** before closing: enumerate what this design *creates* that didn't
   exist, search ADO for existing coverage, and propose only what survives. Present what's left
   as the "Tech story creation" gate — one `AskUserQuestion` option per proposal, `multiSelect:
   true`. Full procedure in `references/tech-stories.md`. **Nothing is created in ADO without
   an explicit approval.**
6. A story spec inherits its parent feature's design **by reference, not by copy**. Link to it.
7. **Stop and ask.** Build the `sdd:visual` **design** page (`visuals/design.html`, tech story
   proposals included) from `design.md` — the approach and the anchors — and send it (no recap in
   chat), then run the "Design
   agreed" gate with `AskUserQuestion` (see "Approval gates" above). Decomposing before that
   answer risks tasks built against a design that's about to change.
8. **"Needs changes"?** Revise `design.md` to address what was asked for, then re-run step 7 —
   present what changed and run the same gate again. Never guess at the fix and move on to
   Decompose without a fresh approval; a design that changed since it was last agreed to hasn't
   actually been agreed to.

### Mode: Decompose

1. **Write `tasks.md`** from `assets/tasks.md.template`: ordered units of 2–5 minutes of agent
   work, each naming the files it touches and how it is verified.
2. Every task traces to an acceptance criterion or to an explicit design decision. A task that
   traces to neither is scope creep — drop it or raise it.
3. Tests are tasks, not a trailing afterthought.
4. **Once `design.md` and `tasks.md` both exist, write the implementation plan back to ADO** —
   but only if this work item's type actually carries an Implementation Plan field. Never assume
   it does; check per type and cache the answer. Field lookup, content shape and the write path
   are in `references/ado-sync.md`.
5. **Show the plan.** Build the `sdd:visual` **tasks** page (`visuals/tasks.html`) and send it, with no
   recap in chat. Re-render it with live statuses when the user asks where Implement stands.

### Mode: Implement

1. **Edit only inside `src\{Repo}`** of the folder Design created, for every repo this task
   touches. No repo file is ever edited in the main checkout. If a task needs a repo with no
   worktree yet — one Design didn't touch — that's a scope surprise: go back to Design rather
   than adding it silently here.
2. **One task at a time**, in order. Tick it in `tasks.md` as it lands. After a significant edit
   (new files, moved symbols), `env.py graph --id <id>` so later graph queries see it.
3. Re-sync at session start (the Sync check does this for you) — building against a stale mirror
   is the expensive failure this workflow prevents.
4. A task that turns out to be wrong goes back to Decompose, not into improvisation.
5. Commit messages carry the work item id; the branch already does. No Claude attribution line
   or trailer in the commit message — the developer running this skill owns the commit.

### Mode: Verify

1. Walk the acceptance criteria one by one against observable behaviour, not against the code
   you wrote. Anything unmet is either an unfinished task or a requirement change.
2. **Drift check:** `spec.py sync --id <id>`. Any `MATERIAL` line for this item or its parent
   blocks the PR until it is reviewed against `design.md` and the done tasks.
3. **Overlap check:** `spec.py impact --id <id>`, then check the design's anchors against the
   candidates it lists for file and symbol overlap.
4. Report what was built, what was skipped and why; no silent scope changes — as an `sdd:visual`
   **diff-review** page (`visuals/diff-review.html`) per the worktree diff against its base branch.
5. **Stop and ask.** Implementation and the checks above are done — run the "Ready to PR" gate
   with `AskUserQuestion`: "Raise the PR" vs "Make changes". Never open a PR on the assumption
   that passing checks means go-ahead; only the user's answer does.
6. **"Make changes"?** Go back to Implement (or Decompose, if the fix is really a task-list
   problem), address it, then re-run step 5. Never guess at the fix and open the PR anyway.
7. **"Raise the PR"?** Write the description to `<folder>\pr-description.md`, then `env.py pr
   --id <id> --title "<title>" --description-file <folder>\pr-description.md` — it pushes each
   repo with commits ahead, opens its PR against the base branch and links the work item. Move the
   work item's `System.IterationPath` to the current sprint before or as you open it — an item
   still sitting in an old sprint (or with none set) reads as work nobody is doing. Lookup steps
   in `references/ado-sync.md`. Never write the work item as `#12345` anywhere in the PR text,
   and never add a Claude attribution line to the title, description or a comment — the
   developer owns the PR. `references/branching.md` has both rules and why.
8. Start **Review** at once: `env.py progress --id <id> --flow spec --phase Review --status waiting
   --gate "PR status: not yet approved / approved / merged / rejected" --ref ado --no-visual "PR status
   is a plain choice"`. Verify is done; the wait for the reviewers is Review's.

### Mode: Review

The PR is open and waits on its reviewers. The user answers in the chat, or with the **Approved**,
**Merged** and **Rejected** buttons of the sdd view, which post the answer as the user's own message
`sdd review for <id>: approved` / `: merged` / `: rejected: <why>`. Treat both the same.

1. **Stop and ask** (when the answer did not come from the view): show the PR's clickable ADO link
   first (ground rule 12), then ask with `AskUserQuestion`: "Not yet approved" / "Approved" /
   "Merged" / "Rejected". Don't assume the answer, and don't silently poll ADO for it; ask directly,
   whenever you next pick this work item back up.
2. **"Not yet approved"** — nothing changes; Review keeps waiting.
3. **"Approved" or "Merged"** — `env.py progress --id <id> --flow spec --phase Review --status done
   --passed "PR approved"`. Then set `Custom.BoardColumnTitle` to `Dev Completed`, move
   `System.State` to `Resolved`, and tag the work item with the version segment the branch carries
   (the `team/{version}` it was branched from). Field names and the write path in
   `references/ado-sync.md`.
4. **"Merged" only** — `env.py remove --id <id>` (dry run, shown to the user), then `--yes`, then
   archive this session: `mcp__ccd_session_mgmt__archive_session`, `session_id: "self"`, `reason`
   naming the merged PR. This is cleanup, done together, no separate question — the "Merged" answer
   is already the explicit human confirmation the archive step needs.
5. **"Rejected"** — the reason is the feedback. Go back to Implement through the feedback route:
   `env.py reopen --id <id> --phase Implement --note "PR rejected: <why>"` (it revokes Ready to PR and
   PR approved), read the PR's review comments, fix in `src/{Repo}/`, and come back through Verify's
   "Ready to PR" gate. The open PR takes the new commits; `env.py pr` is not run again for it.
   No reason given → ask for it first; never guess what the reviewers want.

### Mode: Sync check

```
spec.py sync
```

With no id it refreshes every synced item and scope root and reports `new`, `material` (with the
fields that changed), `incidental`, `unchanged` and `missing`. Incidental changes (state, tags,
iteration, assignment) refresh silently. Report every `MATERIAL` and `MISSING` line to the user —
a material change on an item in flight, or on its parent, needs review before more work. A new
child is simply mirrored. Classification in `references/ado-sync.md`.

A CI gate that runs this on a pull request is not provided by the shared scripts yet; until it
is, the Verify drift check is the gate.

## Workspace facts cache

Some facts cost real effort to derive and barely change — per-repo test/build commands not
already obvious from that repo's own `CLAUDE.md`, which repos actually carry `team/*` branches,
a trap that cost time. Deriving them again every session is waste, so write the durable ones back
to the **workspace root** `CLAUDE.md`, under one marked heading, and read that heading back at
session start alongside the Sync check.

| Record it | Never record it |
| --- | --- |
| Per-repo test/build commands, if not already obvious from that repo's own `CLAUDE.md` | `team/*` versions — they change every release; always enumerate live |
| Which repos actually carry `team/*` branches versus branching straight off `main` | Anything about one work item: ids, branch names, worktree paths |
| The worktree root convention (`.claude/worktrees/{id}-{slug}/src/{Repo}`) | Passwords, connection strings, tokens, personal data |
| Which work item types carry an Implementation Plan field, and its reference name | Any work item's actual implementation plan content — that's written to ADO, not cached here |
| A trap that cost real time and would cost the next run the same | Your analysis of one spec — that lives in `{specRoot}`, not here |

```markdown
## Claude skills — workspace facts

*Written by the `sdd:spec` skill. Last verified {yyyy-MM-dd}. Check anything cheap before you
trust it. `team/*` versions are deliberately absent — always enumerate them live.*

| Fact | Value |
| --- | --- |
| Worktree root | `<workspace>\.claude\worktrees\{id}-{slug}\src\{Repo}` — confirm it is gitignored |
| ADO org / projects | From `.claude/sdd.json` — not copied here |

### Per-repo notes

| Repo | Test/build command | `team/*` branches? | Notes |
| --- | --- | --- | --- |
| … | … | … | … |

### Implementation Plan field, by work item type

| Type | Present? | Reference name |
| --- | --- | --- |
| … | yes / no | `Custom.…` or — |

### Traps

- One line each. Only what cost real time.
```

Rules for writing it:

1. **Ask before the first write.** The root `CLAUDE.md` may be shared outside git — show the
   block and wait. Later updates need no new permission once the user has agreed once.
2. **Update in place, never append a duplicate.** One `## Claude skills — workspace facts`
   heading per file — the same heading `ado-bug-fix` writes in other workspaces, so the two
   skills never fight over the block if a workspace ever uses both.
3. **Stamp the date.** A block older than about a month is a hint, not a fact — re-verify it.
4. **Keep it under 40 lines.** It loads into every session in this workspace; it's a lookup
   table, not a write-up.
5. **No workspace `CLAUDE.md`?** Say so and ask whether to create one. Never create it silently.

Skip writing it when nothing new was learned this session — an unchanged block isn't worth a
commit.

## Gates at a glance

| Signal | Sync check | Verify | Action |
| --- | --- | --- | --- |
| Primary item material change | Warn + fields | Block | Re-sync, review design and tasks |
| Parent material change, this child in flight | Warn + fields | Block | Review design + done tasks against new parent |
| Linked item material change (non-parent) | Warn + fields | Review | Revise design if affected |
| Work item missing (deleted, moved, no access) or retyped | Warn | Block | Human decision |
| Incidental change only | Silent | Pass | Index rev updated |
| File or symbol overlap with another active spec (`spec.py impact`) | Warn | Block | Coordinate with the other branch |
| Shared-term / similarity hit (`spec.py impact`) | Triage | Comment only | Human reads `impact.md` |

Gates run **only on pull requests whose source branch is `dev/*`**. `team/*` and `release/*`
promotion is release engineering and out of scope.

The cascade needs no PR enumeration: `spec.py sync --id <id>` re-pulls the item's parents too,
so the child's own drift check catches a material parent change. "In flight" is
therefore whatever has an open `dev/*` PR — by construction, not by query.

## Bundled resources

| File | Read when |
| --- | --- |
| `references/ado-sync.md` | Mirror schema, field classification, drift, write path, claim/close-out fields, implementation plan write-back |
| `references/branching.md` | Branch naming, work item folder, PR linking, promotion chain, enforcement |
| `references/spec-authoring.md` | Writing requirements, design or tasks well |
| `references/tech-stories.md` | The Design-stage tech story gate |
| `assets/design.md.template` | Design |
| `assets/tasks.md.template` | Decompose |
| `assets/tech-story.md.template` | Proposing a tech story |
| `${CLAUDE_PLUGIN_ROOT}/skills/workspace/SKILL.md` | `env.py` and `spec.py` commands, folder layout |
| `${CLAUDE_PLUGIN_ROOT}/skills/visual/SKILL.md` | The visual page for every gate: requirements, design, tasks, diff-review |
