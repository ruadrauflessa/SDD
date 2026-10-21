---
name: pre-pr-verify
description: >-
  On request only: start the local stack with the worktrees of the bug being fixed, PROVE the worktree
  build is the one answering, hand the user a short test brief, then stop and wait. Never tests, logs
  in, raises the PR or tears down. Use for "start the environment", "bring up the stack with my
  worktree", "let me test before the PR", "start it with the 80459 worktree".
---

# Start the environment for manual verification

The user tests. You give them an environment they can trust: the right code, **proven** to be the
right code. Below, `devops.py` means `python "${CLAUDE_PLUGIN_ROOT}/scripts/devops.py"`.

## Non-negotiables

1. The user does the testing. Prepare, prove, brief, stop.
2. Never log in for the user. Hand over at the login screen.
3. Prove which build answers (Gate D). "UP" is not evidence.
4. Leave the stack running. No teardown after the hand-over.
5. Never raise the PR here. That needs a separate go-ahead.
6. Say what you could not set up: a service left out, a database gap, a dependency down.
7. Anything you generate goes in `.claude/scripts/`, never `scripts/` (the guard refuses).
8. The brief is plain English: one idea per sentence; paths, ports and commands exact.

## Steps

1. **Find everything**: `devops.py env find --id <id>`. It lists each worktree (both layouts), its
   branch and changed files, a UI worktree missing `node_modules`, the run script and its real
   parameters, whether `.claude/scripts` is ignored, and the workspace facts from `CLAUDE.md`
   (`## Claude skills — workspace facts`): a starting point, not the truth. No run script: read
   `${CLAUDE_PLUGIN_ROOT}/skills/pre-pr-verify/references/build-launcher.md` and ask before building one.
2. **Pick the services.** Do not ask the user. Map each changed repo to its service keys (the facts, or
   `<run-script> -Status`; one repo can own several keys), then add their dependencies (`BaseUrl` keys:
   a UI needs its gateway and the backends the screen calls; a service behind auth or app-key
   middleware needs the identity service). Unclear: start everything (omit `-Only`).
3. **Preflight.** The database from the facts; if the shared database sits behind a VPN, check the
   network adapter is up before starting anything. Unreachable: say so and stop. A UI worktree:
   `npm --prefix <worktree> install` first.
4. **Launch.** `<run-script> -Stop` first (old services hold the ports), then
   `<run-script> -Worktree <id> -Database <db> -Only <keys>`. No `-NoBuild` on the first run. Read the
   header: it names each redirected repo and the services it affects.
5. **Gate D**: `devops.py env gate --id <id>`. FAIL: do not hand over. Check `-Stop` freed the port,
   read that service's error log for a bind failure, check the `-Only` keys cover the repo. A UI has no
   tag: confirm from the start-up header that Vite started from the worktree path.
6. **Brief, then stop:**

   ```markdown
   ## Environment ready — ADO {id}

   **Your fix is running from:** {repo} → {worktree}   *(confirmed answering, pid {pid})*
   **Database:** {db} · **Started:** {names} · **Not started:** {names, or "none"}

   **Open this:** {UI URL}. Log in yourself. I do not enter credentials.

   **Test these three things**
   1. {what went wrong, in the reporter's words}
   2. {what right looks like now}
   3. {one nearby screen, to check nothing else broke}

   **Know this first**
   - {a service that is off, a shared live database, anything this stack cannot show}
   - Logs: {log path}

   **When you are done, tell me:** **verified** (I raise the PR) or **what went wrong** (I go back to the cause).
   ```

   For a UI fix add: open the browser console too (a dev server does not typecheck, so a missing import
   shows only there). Then wait.

## On the verdict

| They say | You do |
| --- | --- |
| verified | Back to the calling flow's PR step. One line in the PR's verification comment: the user tested the worktree build by hand and it passed. Write a work item as `ADO 80459`, never `#80459`. |
| something's wrong | Back to the calling flow: the cause step if the symptom stays, the side-effect step if a new one appeared. Re-run the automated gates, then offer this again. |
| can't reach the screen | Usually a missing dependency or the wrong database: your problem, not the fix's. Fix and re-brief. |

Teardown only when the user says they are finished: `<run-script> -Stop`, then `<run-script> -Only
<keys>`, and `-Status` shows no worktree tag. Leave the worktree on disk.

## Record what you had to work out

New durable facts go in the workspace `CLAUDE.md` under `## Claude skills — workspace facts` (add to
it; never a second heading): the run script and its flags, the repo → key map, the dependency graph,
the database default and its VPN check, the UI URL and the log path. Never one bug's ids or paths,
never secrets, never anything you did not verify. Ask before the first write; stamp the date.
