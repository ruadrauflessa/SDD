# Phase 13 — Write back to the work item

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Write the two texts as HTML files in the work item folder, then hand over with one command:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/spec.py handover --id <id> \
  --root-cause-details-file '<folder>\root-cause.html' --resolution-file '<folder>\resolution.html' \
  [--root-cause "Coding Error"]
```

It sets the fields below and `System.State` → `Resolved` in one rev-tested write. It refuses an
`Issue` without both texts, and any text with a `#<id>` mention (exit 3).

| Field | Reference name | Obligation |
| --- | --- | --- |
| Root Cause Details | `Custom.RootCauseDetails` | **Required for `Issue`**; fill for `Bug` too |
| Resolution | `Microsoft.VSTS.Common.Resolution` | **Required for `Issue`**; fill for `Bug` too |
| Root Cause | `Microsoft.VSTS.CMMI.RootCause` | Picklist — set when it is clear |
| Board Column Title | `Custom.BoardColumnTitle` | **Always → `Dev Completed`.** This is the QA hand-over signal |

**`Custom.BoardColumnTitle` → `Dev Completed` is the hand-over to QA** — the team drives the QA queue
off this field, so skipping it means the fix is never picked up for testing no matter what `State`
says. Set it once the PR exists (Phase 12), together with `State` → `Resolved`; the two pair up on
real items. Set the **custom** field, never the board-managed `System.BoardColumn`.

**Keep both fields to a summary — 1–3 plain sentences each.** Root Cause Details says *why it broke*;
Resolution says *what was changed*. No file/line anchors, no code, no verification traces, no
cross-references, no out-of-scope notes — all of that is already in the PR and its comments, and a
reader who wants depth follows the PR link. Anything important that is neither cause nor fix goes in
a **comment on the work item**, not in these fields.

**Write both fields for the reporter, not for a developer.** These two fields are the strictest use
of the house style in the whole skill:

- One idea per sentence. Break every "and", "however" and "thus" into a new sentence.
- Active voice. Name the thing that did it. "The gateway dropped the header", not "the header was
  not forwarded".
- Small words. Say "check", not "validate". Say "change", not "modify".
- Explain a technical word once, in brackets, right after you use it.
- Never simplify an error code, a field name or a value the reader must recognise.

Verified reference names, the picklist values in real use, and worked house-style examples are in
`references/ado-fields.md`. Read it before writing — the two fields carry different content, and
getting them backwards is the common mistake. The full style rules are in
`references/writing-style.md`.

Add a comment linking the PR: write it as HTML, then
`spec.py comment --id <id> --file '<folder>\comment.html'`. `handover` already moved `System.State`
to `Resolved` (states: New → Active → Resolved → Closed). **Leave closing to the reporter** —
resolution is yours, verification is theirs.

The comment follows the same style. Give the PR link, then say in one or two sentences what the
reporter must check to verify the fix. Say it in their words, not in code terms. **One comment, and
no `#<id>` in it** — name sibling bugs and the linked CR as `ADO 80455` and `CR 79387`, or you post
a `Mentioned in` comment onto each of their boards too.

**Leave the work item folder in place.** It is still needed for review fixups. Mention to the user
that it is still on disk so it doesn't become an orphan. Removing it is Phase 15's, once the PR has
merged.
