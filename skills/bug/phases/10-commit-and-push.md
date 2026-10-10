# Phase 10 — Commit and push

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Commit **from inside the worktree** — one repo per commit, and never the root (see the
non-negotiables). Reference the work item so ADO links the commit:

```
fix(<area>): <what now works> [AB#<id>]
```

Body: the cause in one or two sentences, then the fix. Push to the branch created at Phase 2, named
explicitly (`env.py status --id <id>` shows it): `git push -u origin <branch>`.
