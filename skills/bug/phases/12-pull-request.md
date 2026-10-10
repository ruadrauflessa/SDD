# Phase 12 — Pull request

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Create the PR against `team/{version}` in the **submodule's** ADO repo, with the shared script.
Write the description (template below) to `<folder>\pr-description.md`, then run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py pr --id <id> --title "<title> [AB#<id>]" \
  --description-file '<folder>\pr-description.md' --work-items <every covered id, comma-separated>
```

It pushes each repo that has commits, opens one PR per repo against its base, links the work items,
and records each PR in `workitem.json`. It refuses a description over 4,000 characters. It prints
each PR URL — report every one as a clickable link. Re-running is safe: repos that already have a
PR are skipped.

**Link every relevant work item to the PR, not just one.** Pass every id this session is handling
in the same batch, e.g. `--work-items 81921,82216,82217`, even though only one of them has code in
this diff. A PR that links only the id named
first under-reports what it actually covers, and a reviewer or QA person opening a sibling ticket
sees no PR at all. If a PR was created before you realised a
sibling belonged on it too, add the missing link with `wit_work_item_link_write
action=link_to_pull_request` for each missing id — it works after the fact, merged or not.

**Move every linked work item to the current sprint.** A PR against a work item still sitting in an
old sprint (or one that never had an iteration set) reads as work nobody is doing. Do this for
every id the PR touches, not just the one named first — including a sibling bug that got no new
code because it was already fixed (see Phase 1.2 on batches).

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/spec.py sprint --id <id> --id <sibling id> ... [--team "<team>"]
```

It finds the team's current sprint (default team: `<project> Team`). For a team with no iteration
schedule, which happens here, it takes the iteration whose dates hold today. It then sets
`System.IterationPath` on each item, rev-tested. No iteration holds today? It exits 3: ask the user
which sprint.

**The description must be easy to digest.** A reviewer reads it in 30 seconds and knows what this
change does. Anyone who wants more opens the comments. Three short headings, and nothing else:

| Heading | Holds | Size |
| --- | --- | --- |
| **What broke** | ADO {id}, and what the user saw, in plain words | 2 sentences |
| **Why** | The cause, in plain words. No file, no line, no class name | 2 sentences |
| **What changed** | One line per file — what the code does now | one bullet each |

150 words for the whole description. No code snippets, no sub-bullets, no tables. End it with "More
detail is in the comments below."

Everything else goes in its own comment on the PR, posted straight after you create it:

| Comment | Holds |
| --- | --- |
| Reported and requirement basis | The report, the environment, the linked story or CR and its criterion |
| Verification | The six Phase 9 gate results, with real output |
| Design notes | The file and line, ruled-out causes, why this approach, what you left alone, how you reproduced it |
| Out of scope | Related defects you found and did not fix here |

Post them without being asked. Set `status=Closed` on each — they are notes from the author, not open
review feedback. The first two are always posted. Skip Design notes or Out of scope only when there
is genuinely nothing to say.

**Never write a work item as `#12345` in any ADO text.** ADO reads it as a mention and answers by
posting `Mentioned in !<pr>` as a comment **on that work item** — one per mention, per comment. Four
comments naming three bugs leave twelve of them, burying what a person actually wrote. Write
`ADO 80459` or `CR 79387` in plain text instead. Keep `AB#<id>` in the **commit message** and the
**PR title**: those make the link and post no comment. This applies to the PR description, every PR
comment, and every work-item comment. Proven on ADO 80459 — see `references/branch-and-pr.md`.

**The comments carry the depth. The description carries the point.** Both follow the house style:
one idea per sentence, active voice, 25 words maximum. See `references/writing-style.md`.

Templates and the exact tool calls are in `references/branch-and-pr.md`.
