# Phase 8 — Apply the fix

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Smallest change that removes the cause. Match surrounding code style. Respect the layer
boundaries — a cross-layer reference fails the ArchUnit test run, not the compile. Resist fixing
adjacent things you noticed; they were listed as out of scope in Phase 6.

After the edits, refresh the graph so later queries see the new code:
`env.py graph --id <id>` (AST only, seconds).
