# Phase 3 — Validate against the linked story / change request  *(read-only)*

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

## Gate 1 — is this actually a bug?

**Mirror the requirement first.** For each linked story / CR, and for the bug itself:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/spec.py sync --id <linked item id>
python ${CLAUDE_PLUGIN_ROOT}/scripts/spec.py sync --id <bug id>
python ${CLAUDE_PLUGIN_ROOT}/scripts/spec.py impact --id <bug id>     # optional
```

`sync` writes the item, its tree, parents and one hop of links to
`{specRoot}/**/{id}-{TYPE}-{slug}/requirements.md` (`specRoot` comes from `<workspace>/.claude/sdd.json`;
in Lumina it is `documents/spec`). Read the requirement from that file. `impact` lists items that
link to the bug, share its key terms, or are close in meaning — a quick way to find a governing
story nobody linked. If the sync is not possible (no `az login`, no `sdd.json`), stop and ask the
user to fix it with `/sdd init` — never read the items from ADO instead.

Walk the `## Links` list in the bug's `requirements.md` for linked requirements — `System.LinkTypes.Hierarchy-Reverse`
(parent) and `System.LinkTypes.Related` are both in use here. Follow parents up the tree; the spec
usually lives on a **User Story** (`Microsoft.VSTS.Common.AcceptanceCriteria`, Given/When/Then) or a
**Change Request** (`System.Description`, numbered Functional Requirements). Features in this project
are typically title-only — don't expect a spec there.

Read the governing requirement, then classify the ticket against it:

| Verdict | Meaning | Action |
| --- | --- | --- |
| **Consistent** | Reported behaviour deviates from what the story/CR specifies | Proceed to Phase 4 |
| **Contradicts** | The "wrong" behaviour is what the story/CR explicitly specifies | 🛑 **Stop** — requirements conflict, not a defect |
| **Withdrawn** | It targets an acceptance criterion that was struck through / descoped | 🛑 **Stop** — the requirement was deliberately removed |
| **Superseded** | A later story/CR changed the behaviour; the bug cites the old spec | 🛑 **Confirm which spec governs** before fixing |
| **Unspecified** | The story/CR is silent on this behaviour | Proceed, but the correct behaviour is a **product decision** — propose it and get it confirmed at Phase 6 |
| **Scope creep** | A real defect bundled with new requirements | Fix the defect only; split the rest into its own work item |
| **No link** | Nothing linked (common) | Say so, search for a relevant story, then treat the ticket's own description as the only spec |

For the three 🛑 verdicts, **stop and report** rather than fixing — with an `sdd:visual` **bug** page
that shows the requirement next to the reported behaviour. Present the requirement text
alongside the bug text and let the user decide — a contradiction is resolved by a product owner, not
by a code change. Never resolve one by quietly picking whichever the ticket happens to prefer.

**Struck-through acceptance criteria mean withdrawn.** Real stories here carry `<strike>` around
descoped criteria. Naïvely stripping HTML erases that and turns a withdrawn requirement into an
active one — read the raw HTML, not a flattened version. The `spec.py` mirror keeps them as `~~…~~`
only when pandoc is installed; without it the sync strips tags. So the strike check needs pandoc.
Not installed (`env.py doctor` says so)? Ask the user to install it, then run `/sdd sync <id>`
again. Never read the raw field from ADO instead.

Mechanics, field-by-type mapping, and worked examples of each verdict are in
`references/requirement-alignment.md`.
