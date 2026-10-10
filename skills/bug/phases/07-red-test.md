# Phase 7 — Failing regression test  *(before the fix)*

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

Write the test that encodes the defect, then run it and **watch it fail** — through the script, so
the failure is on record:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/env.py run --id <id> --gate "Red test" --expect fail [--repo <Repo>] -- <test command>
```

It runs the command in the worktree, prints the last 40 lines and saves them with the exit code in
`workitem.json`. `progress --passed "Red test"` refuses until such a run exists.

- Target the *cause*, not the click-path: assert on the unit that misbehaves.
- Where a story or CR governs the behaviour, assert what **it** specifies — the acceptance criterion
  is the oracle, not the bug reporter's wording. Name the criterion in a comment on the test.
- **Verify it fails for the right reason.** Read the failure output. An assertion failure showing
  expected-vs-actual is correct; a `NullReferenceException`, compile error, missing-fixture error,
  or DI resolution failure means the test is broken, not the code. Fix the test and re-run.
- The recorded output is the failure message the PR quotes as proof the test guards something.
- **Have it checked by someone who did not write it.** Hand **`sdd:skeptic`** (mode `test`) the
  test, the failure output and the planned fix. You wrote the test, so you are the worst judge of
  whether it is a tautology. Fix what it finds before Phase 8. Pass `Red test` only after that.

Test placement, per-repo commands, and the flakiness rules are in `references/test-integrity.md`.
