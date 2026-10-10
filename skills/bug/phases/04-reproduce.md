# Phase 4 — Reproduce and locate  *(read-only)*

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

- Map the symptom to the owning repo or repos. A symptom in the UI is often a defect in a backend
  service; expect to cross a repo boundary and note every repo involved.
- **Start from the code graph.** Read `<folder>\graph\GRAPH_REPORT.md` for the overview, then
  `graphify query "<question>" --graph <folder>\graph\graph.json` to find where the symptom lives.
  The graph is a map, not the truth — confirm every lead by reading the file it points at. For a
  symptom that could live in several places, hand the search to **`sdd:investigator`** ("where does
  <symptom> originate? return file:line anchors") and keep only its findings here.
- **If this turns up a repo with no worktree yet**, add it before reading further into that repo:
  `env.py new --id <id> --repos <that repo> --version <same version>`. Reuse the team version
  already chosen, and ask again only if that repo lacks the branch.
- Reproduce it. Preferred order: a failing unit test → a local run of the stack against the shared
  test database → a read-only `SELECT` on that database to confirm the data state → reasoning from
  logs and code when none of those is possible.
- **To run the stack, look for the workspace's own run script first** (`scripts/run-*.ps1` at the
  workspace root, or whatever the root `CLAUDE.md` names). If there is none, you can build one from
  the workspace: each service's `launchSettings.json` gives its profile and port, and its
  `appsettings.json` gives the connection strings to override. Inject config as **environment
  variables**, never by editing a committed `appsettings.json`. Propose the script at the approval
  gate before you write it — it is a change to the workspace, not to the fix. **Write it to
  `.claude/scripts/`, never to `scripts/`**: `scripts/` is tracked and shared, and a generated
  launcher is machine-specific. Confirm `.claude/scripts/` is gitignored first, and add it to
  `.git/info/exclude` if it is not.
- **Any service you start must run from the worktree, never from the main checkout.** Pass the run
  script's worktree-redirect flag for every repo this fix touches (e.g. `-Worktree <id>` — see
  `pre-pr-verify`), even at this reproduction stage, before the fix exists. In Lumina,
  `run-lumina-full.ps1 -Worktree <id>` finds the repos through the folder's `workitem.json`. The main checkout is not
  a safe substitute: it may be mid-way through a different fix or hold uncommitted edits of its own,
  so a service started from it can quietly answer with the wrong code and any result you record
  against it is worthless. If the run script cannot redirect a repo, start that one service by hand
  from inside its worktree folder — do not fall back to the main checkout.
- **When the symptom shows in the UI, reproduce it by hand in a real browser too.** Don't rely on
  the sandboxed in-app browser pane for this — it has no route to internal/corporate sites (no VPN,
  no corporate DNS), so an internal UAT/STAGE URL fails there with `ERR_BLOCKED_BY_CLIENT`, which
  looks like a site outage but isn't one. Use the **Claude in Chrome** browser plugin
  (`mcp__claude-in-chrome__*`) instead — it drives the user's actual Chrome, with their VPN and login
  session already in place. Call `list_connected_browsers` first; if more than one is connected, ask
  the user which one, or use `switch_browser` and have them click Connect in the browser they want.
  A connected browser can still misbehave (a non-Chromium browser posing as Chrome, e.g. Opera, has
  been seen to connect but not drive pages correctly) — if actions fail repeatedly right after
  connecting, say so and ask the user to reconnect from a different browser rather than retrying
  blindly. Navigate to the environment named in the ticket (its `Environment` note, e.g. a UAT URL),
  then follow the ticket's own **Steps to Reproduce** by hand. Never type a password yourself — ask
  the user to sign in, then carry on. Record the exact result (which codes/fields/message appeared)
  so Phase 9 can compare against it 1:1.
- **State plainly whether you reproduced it or not.** A cause inferred from reading code is a
  hypothesis; label it as one. Never present inference as observation.
- Prefer the narrowest reproduction. A unit test that fails is worth more than a UI click-path,
  and it is the seed of the Phase 7 regression test.
