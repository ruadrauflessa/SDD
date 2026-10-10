# Mode: Sync check

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

```
spec.py sync
```

With no id it refreshes every synced item and scope root and reports `new`, `material` (with the
fields that changed), `incidental`, `unchanged` and `missing`. Incidental changes (state, tags,
iteration, assignment) refresh silently. Report every `MATERIAL` and `MISSING` line to the user —
a material change on an item in flight, or on its parent, needs review before more work. A new
child is simply mirrored. Classification in `references/ado-sync.md`.

A CI gate that runs this on a pull request is not provided by the shared scripts yet; until it
is, the Verify drift check is the gate.
