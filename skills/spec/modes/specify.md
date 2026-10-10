# Mode: Specify

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

0. **Full or short path — settle it first.** The user picks how many stops the flow makes:
   - **Full** — Design and Decompose each stop for approval.
   - **Short** — Design runs straight into Decompose, and one stop approves the design and the tasks
     together. For a small, well-understood change.

   Did the user already say which (`/sdd <id> short`, `/sdd spec <id> full`, "do this one on the
   short path")? Record it with their words: `env.py path --id <id> --set short|full --confirmed
   "<their words>"`. If not, **ask before anything else**: show the work item's ADO link
   (`env.py refs --id <id> --ref ado`), then `AskUserQuestion` with "Full path" / "Short path", one
   sentence on each, and record the answer the same way. Never pick it for the user, and never
   infer it from the size of the change. No later stage starts until it is recorded (`env.py can`
   refuses). Short can change to full at any point; full to short only before Decompose starts.
1. **Mirror it:** `spec.py sync --id <id>`. It pulls the item, everything under it, its parents
   and one hop of links out of that tree, and writes each `requirements.md` into place under
   `{specRoot}`. Never write or edit `requirements.md` yourself — the next sync overwrites it.
   Don't read the requirement yet.
2. **Claim the work item, before you read it:** `spec.py claim --id <id>`. It assigns you, sets
   `Dev In Progress` and `Active` in one rev-tested write, and re-syncs the mirror. **Exit 3 means
   stop and ask**: someone else is working on it (never take it), it is on someone else's name but
   not started (free under the team's rule: after the user's yes — picking it in `/sdd next` is one
   — `claim --id <id> --take`), or it is already `Resolved` or `Closed` (after the user's yes,
   `claim --id <id> --reopen`).
3. **Read the mirrored file** — resolve it by glob, `{specRoot}/**/<id>-*/requirements.md` — and
   its parent's. Put every gap and open question in `questions.md` next to it, never in
   `requirements.md`. One question per line, as an unticked checkbox:
   `- [ ] Q1: <the question> (context: <why it matters>)`. The Open Questions stage counts those
   lines; a question written any other way is never asked.
4. **Run the `sdd:impact` flow for this item** (`spec.py impact --id <id>`, then its
   `impact.md`), so blast-radius gaps against other specs are raised now, before the requirement
   is agreed, not at PR time. **Copy each blast-radius gap that needs an answer into
   `questions.md` as a `- [ ]` line**: `impact.md` is read, but only `questions.md` is counted.
5. **Do not soften a thin work item.** Missing acceptance criteria stay missing and get raised
   as a question in `questions.md` — inventing them puts intent in the repo that no PM ever agreed to.
6. **Hand over.** Specify makes no approval. Record `env.py progress --phase Specify --status done`.
   If `questions.md` has an unticked `- [ ]` line, go to **Open Questions**. If not, record Open
   Questions as skipped (`--phase "Open Questions" --status skipped`, no user's words needed) and go
   to **Requirements**.
