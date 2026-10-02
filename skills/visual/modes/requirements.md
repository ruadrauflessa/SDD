# Mode: requirements — present the requirement before the "Requirements agreed" gate

Used at: sdd:spec Specify, step 6. Source: `requirements.md` (+ parent), `questions.md`, `impact.md`.
Default renderer: quick.

Sections — use only those with something the user needs:

1. **What is asked** — the requirement in 2–3 plain sentences; type, state, parent (first viewport).
2. **Acceptance criteria** — table; a missing or vague criterion shown as a `warning` row, never
   filled in by you.
3. **Open questions** — from `questions.md`, numbered, each with why it matters.
4. **Impact gaps** — Direct items from `impact.md` (cards, `warning` tone for conflicts).
5. **Tree** — parent / siblings / linked items as a small flow, each an ADO link.
