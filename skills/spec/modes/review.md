# Mode: Review

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

The PR is open and waits on its reviewers. The user answers in the chat, or with the **Approved**,
**Merged** and **Rejected** buttons of the sdd view, which post the answer as the user's own message
`sdd review for <id>: approved` / `: merged` / `: rejected: <why>`. Treat both the same.

1. **Stop and ask** (when the answer did not come from the view): show the PR's clickable ADO link
   first (ground rule 12), then ask with `AskUserQuestion`: "Not yet approved" / "Approved" /
   "Merged" / "Rejected". Don't assume the answer, and don't silently poll ADO for it; ask directly,
   whenever you next pick this work item back up.
2. **"Not yet approved"** — nothing changes; Review keeps waiting.
3. **"Approved" or "Merged"** — `env.py progress --id <id> --flow spec --phase Review --status done
   --passed "PR approved"`. Then hand over: `spec.py handover --id <id> --tag <version>`, with the
   version segment the branch carries (the `team/{version}` it was branched from). It sets
   `Dev Completed` and `Resolved` and appends the tag, in one rev-tested write.
4. **"Merged" only** — `env.py remove --id <id>` (dry run, shown to the user), then `--yes`, then
   archive this session: `mcp__ccd_session_mgmt__archive_session`, `session_id: "self"`, `reason`
   naming the merged PR. This is cleanup, done together, no separate question — the "Merged" answer
   is already the explicit human confirmation the archive step needs.
5. **"Rejected"** — the reason is the feedback. Go back to Implement through the feedback route:
   `env.py reopen --id <id> --phase Implement --note "PR rejected: <why>"` (it revokes Ready to PR and
   PR approved), read the PR's review comments, fix in `src/{Repo}/`, and come back through Verify's
   "Ready to PR" gate. The open PR takes the new commits; `env.py pr` is not run again for it.
   No reason given → ask for it first; never guess what the reviewers want.
