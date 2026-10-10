# Phase 15 — PR review

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

The PR is open and waits on its reviewers. Record the wait as soon as Phase 14 is done:
`env.py progress --id <id> --flow bug --phase "Phase 15" --status waiting --gate "PR status: not yet
approved / approved / merged / rejected" --ref ado --no-visual "PR status is a plain choice"`.

The user answers in the chat, or with the **Approved**, **Merged** and **Rejected** buttons of the sdd
view, which post the answer as the user's own message `sdd review for <id>: approved` / `: merged` /
`: rejected: <why>`. Treat both the same. When the answer did not come from the view, show the PR's
clickable ADO link, then ask with `AskUserQuestion`: "Not yet approved" / "Approved" / "Merged" /
"Rejected". Never assume it, and never poll ADO for it silently.

1. **"Not yet approved"** — nothing changes; Phase 15 keeps waiting.
2. **"Approved"** — `env.py progress --id <id> --flow bug --phase "Phase 15" --status done --passed
   "PR approved"`. Phase 13 already handed it to QA; nothing more in ADO.
3. **"Merged"** — the same `--passed "PR approved"`, then `env.py remove --id <id>` (dry run), show
   the user what it lists, and run it with `--yes` only after they agree. It refuses while any PR is
   not `completed` — see `references/branch-and-pr.md`.
4. **"Rejected"** — the reason is the feedback. `env.py reopen --id <id> --phase "Phase 8" --note
   "PR rejected: <why>"` (Red test stays; Verified, Manual verification and PR approved fall). Read
   the PR's review comments, fix in `src/{Repo}/`, and come back through Phase 9 and Phase 11. The open
   PR takes the new commits; `env.py pr` is not run again for it. Ask before moving
   `Custom.BoardColumnTitle` back from `Dev Completed`, since QA may already have it. No reason given →
   ask for it first; never guess what the reviewers want.
