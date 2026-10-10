# Mode: Implement

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

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
