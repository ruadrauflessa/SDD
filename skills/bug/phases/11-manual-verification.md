# Phase 11 — Manual-verification gate  🛑 **STOP HERE**

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

The branch is pushed and ready, but **do not create the PR.** Automated gates prove the unit; they
do not prove the product. The user verifies the fix by hand before it is offered to anyone else.

Report that Phase 9 passed — with an `sdd:visual` **diff-review** page of the fix (including its "How
to test it by hand" section) — then stop and wait. Say plainly that the PR has not been created and
that you are waiting on their manual verification.

Those three things — what you changed, whether the gates passed, what the user does now — are on the
**diff-review** page. The chat gets one line naming the page and the statement that the PR is not
raised yet. Nothing else.

They will do one of four things:

| They say | You do |
| --- | --- |
| "Start the environment" (or similar) | Invoke the **`pre-pr-verify`** skill — it brings the stack up with this bug's worktrees and hands the app back to them for testing. Then stop again and wait. |
| "Verified / go ahead / raise the PR" | Proceed to Phase 12. |
| Reports a problem | Return to the phase their finding points at — Phase 5 if the symptom persists, Phase 8 if the fix has a side effect. Re-run Phase 9, then come back to this gate. |
| "Abandon" (or similar) | Follow Abandon in `flow-rules.md` — the branch is pushed, so its cleanup includes asking before deleting the remote branch. |

**Never start the environment uninvited, and never skip ahead to Phase 12 on your own.** Approval to
fix is not approval to publish. If the user has already verified manually before reaching this point
and says so, take that as the approval and continue.
