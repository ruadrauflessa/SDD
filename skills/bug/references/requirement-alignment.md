# Checking a bug against its story or change request

A bug report asserts that behaviour is wrong. Only a requirement can settle whether it *is* wrong.
When a story or Change Request governs the area, read it before investigating — some tickets end
here, and finding that out after a fix is written is expensive.

Verified against project `Spesnet.Lumina` (org `EvolveMedical`) on 2026-08-17.

## Finding the linked requirement

**Mirror it first.** `python <plugin root>/scripts/spec.py sync --id <id>` writes the
item, its tree, its parents and one hop of links to `{specRoot}/**/{id}-{TYPE}-{slug}/requirements.md`
(`specRoot` is in `<workspace>/.claude/sdd.json`; Lumina uses `documents/spec`). Read the
requirement there. `spec.py impact --id <bug id>` finds likely governing items nobody linked.
**Never read these items with `wit_work_item` get or get_batch.** The sync is the only read path;
when it cannot run, stop and ask the user to fix it with `/sdd init`.

The `## Links` list in `requirements.md` (and `spec.py query links --id <id>`) holds the item's
links. Two link types carry requirements in this project — both are in active use, so check for both:

| Link | Meaning |
| --- | --- |
| `System.LinkTypes.Hierarchy-Reverse` | **Parent** — the bug sits under a Story/Feature |
| `System.LinkTypes.Related` | **Related** — a sibling Story, CR, or another defect |

`AttachedFile` relations are screenshots, not requirements. The mirror counts them under "Not
specs, counted only". A work item with only those has **no linked requirement** — a common and
legitimate state.

Follow parents upward: `Bug` → `User Story` → `Feature` → `Epic`. To sweep for links across many
items at once:

```
SELECT [System.Id] FROM WorkItemLinks
WHERE ([Source].[System.TeamProject] = @project AND [Source].[System.WorkItemType] IN ('Bug', 'Issue'))
  AND ([Target].[System.WorkItemType] IN ('User Story', 'Change Request', 'Feature'))
MODE (MustContain)
```

Results are `workItemRelations`, where entries with `rel: null` are the source items themselves.

## Where the specification actually lives

| Type | Spec field | Shape |
| --- | --- | --- |
| **User Story** | `Microsoft.VSTS.Common.AcceptanceCriteria` (HTML) | Numbered `Acceptance Criteria N - <name>`, each Given / When / Then. Plus `System.Description`. |
| **Change Request** | `System.Description` (HTML) | Overview → Business Objective → numbered **Functional Requirements**. **No AcceptanceCriteria field.** |
| **Feature** | — | Title only in practice. Don't expect a spec; go to the Story or CR. |

The sync mirrors the acceptance criteria into the story's `requirements.md`, under
`## Acceptance criteria`. Read them there — no ADO call.

## ⚠ Struck-through criteria are withdrawn

Acceptance criteria are HTML, and descoped ones are wrapped in `<strike>` rather than deleted. Real
example from User Story 60184 (*Chat Management – Archived Screen Option*):

```html
<strike><b>Acceptance Criteria 3  - Handling Empty Thread</b>s<br></strike>
<strike>Given the admin user views the “Archive” section,<br></strike>
<strike>When archived chats are displayed,<br></strike>
<strike>Then no empty threads should appear within the section …</strike>
```

Flatten that HTML and it reads as an active requirement. A bug reporting "empty threads appear in the
Archive section" is then reported against a criterion the team **deliberately removed** — verdict
**Withdrawn**, not a defect. With pandoc installed, the sync keeps struck text as `~~…~~` in
`requirements.md`. Look for `~~` before treating any criterion as binding. Without pandoc the sync
strips the tags: ask the user to install pandoc and run `/sdd sync <id>` again. Never read the raw
field from ADO instead.

## The verdicts, with real cases

### Consistent → proceed

The ticket describes a deviation from what the requirement specifies. Normal path.

### Contradicts → stop

The behaviour the reporter calls wrong is what the requirement demands. Change Request 79871
(*Organisation-Level Entity Relationships and Access Isolation Rules*) requires:

> the operation must be rejected; no partial cross-Organisation relationship or update may be
> persisted

A ticket asking to *permit* a cross-organisation assignment because an administrator is blocked
contradicts that CR outright. Fixing it would undo an accepted security requirement. Report the
conflict with both texts side by side; a product owner resolves it, not a commit.

Note the same CR also says UI filtering "must not constitute the sole enforcement mechanism" — so a
ticket reporting that a *direct API call* bypasses an organisation boundary is **Consistent** with
it, and a fix that only hardens the dropdown would satisfy the ticket while still violating the CR.
This is exactly what Gate 4's requirement re-check is for.

### Withdrawn → stop

See the `<strike>` case above.

### Superseded → confirm which spec governs

A later CR changed the behaviour and the ticket cites the older story. Ask which governs before
fixing; the answer decides what the regression test asserts.

### Unspecified → proceed as a product decision

The story is silent. The bug may well be real, but "correct" is now a judgement call. Say so at the
approval gate, propose the behaviour you would implement, and get it agreed — don't encode a guess
into a test and present it as a defect fix.

### Scope creep → fix the defect, split the rest

The most common contamination: a genuine defect arrives bundled with new requirements. Issue 76784
(*Incorrect Lumina Response*) reported procedure queries returning ICD-10 diagnosis codes — a real
defect. The same ticket also carried a QA reviewer's broader ask, that a vague question should
prompt for clarification instead of answering confidently. That second item is a feature.

Fix the defect, name the remainder, and give it its own work item. Record the split in the **PR**
(its out-of-scope section) and, if the reporter needs to know before verifying, in a **comment** on
the work item — not in Root Cause Details, which stays a short summary of the cause itself.

### No link → say so and proceed

Issue 76784 has only `AttachedFile` relations — no story, no CR. This is the common case. Search for
a story covering the area (`search_workitem`, or WIQL on the area path) in case the link is merely
missing; if there genuinely is none, state that explicitly at the approval gate and treat the
ticket's own description as the only specification. Note that scope creep is still detectable without
a linked requirement — 76784's was visible in the ticket body itself.

## Reporting a 🛑 verdict

Do not fix. Present:

1. The bug's claim, quoted.
2. The governing requirement, quoted, with its work-item id and state.
3. Which verdict applies and why.
4. The options — amend the requirement, reject the bug, or raise a new CR — without picking one.

Then stop and wait. Requirement conflicts are resolved by people, and a fix that silently picks a
side buries the disagreement in a diff where nobody will find it.
