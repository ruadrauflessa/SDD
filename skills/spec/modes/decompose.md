# Mode: Decompose

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

1. **Write `tasks.md`** from `assets/tasks.md.template`: ordered units of 2–5 minutes of agent
   work, each naming the files it touches and how it is verified. **Write a Verify line as a
   command in backticks wherever one exists** (`` `dotnet test --filter Tags` ``): `env.py verify`
   runs every one, and Ready to PR needs them all to pass. Write a plain sentence only for what a
   person must look at. A work item with several repos: add `- Repo: <name>` to a task whose
   Files path does not name its repo.
2. Every task traces to an acceptance criterion or to an explicit design decision. A task that
   traces to neither is scope creep — drop it or raise it.
3. Tests are tasks, not a trailing afterthought.
4. **Once `design.md` and `tasks.md` both exist, write the implementation plan back to ADO** —
   but only if this work item's type actually carries an Implementation Plan field. Never assume
   it does; check per type and cache the answer. Field lookup, content shape and the write path
   are in `references/ado-sync.md`.
5. **Show the plan.** Build the `sdd:visual` **tasks** page (`visuals/tasks.html`) and send it, with no
   recap in chat. Re-render it with live statuses when the user asks where Implement stands.
6. **Stop and ask.** Run the "Tasks agreed" gate with `AskUserQuestion` (`--status waiting`,
   `--ref visuals/tasks.html`). It passes no recorded gate — `Tasks written` is read from disk —
   but Implement starts only on "Approve — start Implement". On "Needs changes", rework `tasks.md`
   and ask again.

   **Short path:** this one stop approves the design and the tasks together. Send both pages and
   pass both as refs (`--ref visuals/design.html --ref visuals/tasks.html`), and say in the gate that
   it covers the design too. On "Approve — start Implement", record it with
   `--passed "Design agreed"`: Implement needs that gate. On "Needs changes", rework `design.md`,
   `tasks.md` or both, and ask again.
