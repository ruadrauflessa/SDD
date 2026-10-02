# Mode: tasks — present a decomposition / task list

Used at: sdd:spec Decompose, after `tasks.md` is written, and whenever a task plan is shown. Source:
`tasks.md`, `design.md`, acceptance criteria in `requirements.md`. Default renderer: quick.

Sections — use only those with something the user needs:

1. **Summary** — how many tasks, repos touched, where tests sit (first viewport).
2. **Order** — `steps` timeline (status `next` / `current` / `done` / `blocked`), dependencies named.
3. **Trace matrix** — table: task → acceptance criterion or design decision it serves. A task with
   no trace is shown as a `warning` row (scope creep — drop or raise it).
4. **File map** — `files` with status `planned`, per repo.
5. **Verification** — per task, how it is checked.

During Implement, re-render the same file with updated statuses when the user asks "where are we?".
