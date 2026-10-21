---
name: pre-pr-verify
description: >-
  Start the local application stack with the worktrees for the bug currently being worked on, so the USER
  can manually test the fix before giving permission to raise the pull request. Invoked ON REQUEST
  ONLY — typically at the ado-bug-fix Phase 9a manual-verification gate, when the user says "start
  the environment". The agent's job is to prepare and prove the environment, not to test it: work
  out which repos the fix touches and which services exercise it, bring them up from the worktrees
  with the workspace run script and -Worktree, PROVE the worktree build is the one answering rather
  than the main checkout, hand the user a short brief of what to test and where, then STOP and
  wait. It never drives the reproduction, never logs in, never raises the PR, and leaves the stack
  running so the user can test. USE THIS SKILL when asked to "start the environment", "start the
  environment for testing", "bring up the stack with my worktree", "spin up the env so I can test",
  "run the stack with the fix so I can check it", "set up manual testing for this bug", "let me test
  before the PR", or "start it with the 80459 worktree". Triggers - start the environment, manual
  testing, worktree run, before the PR, let me test it, bring up the stack, is the right code
  running, hand over for testing.
---

# Start the environment for manual verification

The user tests; this skill gets them a trustworthy environment to test in. That means two things the
agent must do properly and nothing more: run the right code, and **prove** it is the right code.

Invoked only when asked. It is the natural answer to the `ado-bug-fix` Phase 9a gate, but it works
standalone for any worktree.

## Non-negotiables

1. **The user does the testing.** Do not drive the reproduction, click through the app, or declare
   the fix good. Prepare, prove, brief, stop.
2. **Never log in on the user's behalf.** Authentication is the real Azure AD B2C tenant. Hand over
   at the login screen.
3. **Prove which build is answering.** "UP" is not evidence. A worktree redirect that silently
   served the main-checkout build makes the user's whole test session worthless — Gate D below.
4. **Leave the stack running.** The user needs it up. Do not tear down, restore the main checkout,
   or stop
   anything after handing over.
5. **Never raise the PR from here.** This skill ends at the handover. Publishing needs a separate,
   explicit go-ahead.
6. **State what you could not set up.** A service you left out, a database gap, an unreachable
   dependency — say it in the brief. A surprise mid-test costs the user more than the caveat does.
7. **Anything you generate goes in `.claude/scripts/`, never in `scripts/`.** `scripts/` is tracked
   and shared with the team; a generated launcher is machine-specific. Confirm `.claude/scripts/` is
   gitignored before you write the first file. Reading an existing `scripts/run-*.ps1` is fine —
   writing there is not.
8. **Write the brief in plain English.** One idea per sentence. Active voice. Small words. The user
   reads it at the end of a long day and then has to go and test something. Keep every path, port,
   command and log location exact. Full rules:
   `${CLAUDE_PLUGIN_ROOT}/references/writing-style.md`.

## Step 1 — Read the workspace facts

Look for `## Claude skills — workspace facts` in the workspace root `CLAUDE.md`. A previous run
records the durable things there: the run script and its flags, the repo→service key map, the
service dependency graph, the database default, the UI URL and where the logs land.

Treat it as a **starting point, not a truth**. Anything cheap to check, check anyway. Whatever you
had to work out yourself, write back at Phase 6.

## Step 2 — The run script: find it, or build it

Everything below drives one script. Find it in this order:

| Look for | Then |
| --- | --- |
| 1. The script named in the workspace facts | Use it. |
| 2. `scripts/run-*.ps1` in the workspace root | Use it. Read its `param(...)` block for the real flag names — never assume them. |
| 3. `.claude/scripts/run-stack.ps1` | A previous run built it. Use it. |
| 4. Nothing | Build it. Ask first — see below. |

Below, `<run-script>` means whichever one this step resolved.

### Building one

**Ask before you write it.** A launcher is a change to the workspace, not to the fix. Say what it
will start and where it will live, then wait.

Write it to **`.claude/scripts/run-stack.ps1`**, never to `scripts/`. `scripts/` is tracked and
shared; a generated launcher is machine-specific and belongs outside git. Confirm the folder is
ignored *before* you write the file:

```bash
git check-ignore -v .claude/scripts
```

No output means it is **not** ignored. Add it first:

```bash
printf '.claude/scripts/\n' >> .git/info/exclude
```

### What to derive, and where from

| You need | Read |
| --- | --- |
| Which services exist | the solution files, or the service project folders |
| A short key per service | the project folder name, lowercased |
| Port and launch profile | each `Properties/launchSettings.json` — take the `https` profile where there is one |
| Connection strings to override | each `appsettings.json`, `ConnectionStrings` section |
| Which service needs which | `appsettings.json` keys ending in `BaseUrl` — each one names a dependency |
| The UI dev command | `package.json`, the `scripts` block |

**Inject config as environment variables. Never edit `appsettings.json`.** Those files are
committed, so editing one dirties a shared repo.

### The four switches it must support

The rest of this skill does not work without them:

| Switch | Must do |
| --- | --- |
| `-Only <keys>` | start exactly those services, and nothing else |
| `-Worktree <id>` | run the named services from the worktree build, not the main checkout |
| `-Status` | list each service, its port and whether it is up — **and tag any service whose binary came from a worktree** |
| `-Stop` | stop everything it started |

**The worktree tag in `-Status` is the whole point of Gate D.** A launcher without it cannot prove
which build is answering, so this skill cannot hand over.

## Phase 0 — Work out what to run

Do not ask the user which services to start; derive it, then tell them what you chose.

**Find the worktrees.** The ADO id is the handle. Confirm what actually exists rather than assuming:

```bash
ls '.claude/worktrees'
cd projects/<Repo> && git worktree list
```

Two layouts exist under **`<workspace root>\.claude\worktrees\`**:

- **sdd (new):** `{id}-{slug}\src\{Repo}`, made by the `sdd@sdd` plugin. `{id}-{slug}\workitem.json`
  lists every repo in the fix with its branch, so read it instead of guessing:
  `/sdd status {id}` (the plugin's `scripts/env.py status --id {id}`).
- **Old:** `{Repo}\{id}_{slug}`, made by `ado-bug-fix`.

A single id can have worktrees in several repos — that is a cross-repo fix, and all of them need
redirecting. `-Worktree {id}` handles both layouts. Read the fix's diff in each worktree; it tells
you which services matter.

**Map changed repos to service keys.** The workspace facts hold this map. If they do not, derive it
and record it at Phase 6:

- Run `<run-script> -Status`. It lists every key the script knows.
- Match each key to the repo whose project it starts. The key is usually the project folder name,
  lowercased.
- **One repo can own several keys.** A backend repo often holds an API, a hub, a scheduler and a
  worker, and each is a separate key.

**Then add the dependencies — `-Only` starts exactly what you name and nothing else.** The workspace
facts hold the graph. To derive it, read each service's `appsettings.json` for keys ending in
`BaseUrl`: every one names a service it calls and cannot work without.

Two traps that are true in most stacks:

- A **UI** key needs its API gateway, and whichever backend services the screen under test calls.
- A service behind an **auth or application-key middleware** needs the identity service, or every
  call it receives is rejected before it reaches any code.

**When the dependency graph is unclear, start everything.** Omit `-Only`. A couple of extra minutes
beats the user hitting a missing service halfway through a test.

## Phase 1 — Preflight

### Database

**Which database, and does it need a VPN?** The workspace facts hold the default and the check. Read
them before you start anything.

The usual shape: a **shared test database** is the safe default, because local databases are seeded
too thinly for login and for config-driven features. If the shared database sits behind a VPN, prove
the VPN is up *before* you start services — otherwise every service starts, every port answers, and
every data call fails at runtime. That reads like a code bug and burns the user's whole session.

Check the network adapter, not the VPN client's settings list — the settings list is often empty
even when the tunnel is up.

If the database is unreachable, say so and stop. A good run script aborts anyway, but telling the
user up front saves a round trip.

### UI worktrees need their own install

`node_modules` is not tracked, so a fresh UI worktree has none and the dev server dies on start.
Tracked config files such as `.env` and a public `config.js` *do* carry over.

```bash
npm --prefix '.claude\worktrees\{id}-{slug}\src\<UI repo>' install   # sdd layout
npm --prefix '.claude\worktrees\<UI repo>\{id}_{slug}' install       # old layout
```

## Phase 2 — Launch

Stop first, always — leftover services hold the ports, and the replacement then dies quietly in its
log while the old build keeps answering:

```bash
<run-script> -Stop
```

Then start, redirecting this bug's repos. The `-Worktree` value is normally just the ADO id:

```bash
<run-script> -Worktree {id} -Database uat -Only {keys}
```

**Do not pass `-NoBuild` on the first run.** A worktree has its own `bin/obj`; nothing is shared with
the main checkout.

Read the header. It names each redirected repo, its worktree path, and the services affected — and
says so explicitly when a redirect affects nothing, which means either the id matched a repo with no
service (Playwright) or the `-Only` keys are wrong.

## Phase 3 — Gate D 🛑 prove the worktree code is live

```bash
<run-script> -Status
```

Every redirected .NET service must carry a worktree tag:

```
mainapi   Main API   7097   UP   (pid 58332)  worktree: 80459_disclaimer-close-icon-and-collapse
```

**No tag means the main-checkout build is answering.** Do not hand over. Check that `-Stop` really
freed the port, read that service's error log for a bind failure, and confirm the `-Only` keys
cover the redirected repo.

The UI has no binary to inspect, so there is no tag. Confirm from the start-up header that Vite was
launched from the worktree path.

Do not hand over until every redirected service is accounted for.

## Phase 4 — Hand over, then stop

Give the user a short brief and **stop**. No testing, no PR, no teardown.

```markdown
## Environment ready — ADO {id}

**Your fix is running from:** {repo} → {worktree name}   *(confirmed answering, pid {pid})*
**Database:** {uat|local}
**Started:** {names}
**Not started:** {names, or "none"}

**Open this:** {the UI URL from the workspace facts}
Log in yourself. I do not enter credentials.

**Test these three things**
1. {what used to go wrong, in the reporter's own words}
2. {what right looks like now}
3. {one nearby screen, to check nothing else broke}

**Know this first**
- {a service that is off, or that UAT is shared and live, or anything this stack cannot show you}
- Logs: {the log path the run script writes to}

**When you are done, tell me one of two things:**
- **verified** — I raise the PR.
- **what went wrong** — I go back to the cause.
```

Keep the brief this short. Three test steps, not seven. Say what to do, not why you chose it.

**For a UI fix, add one line:** open the browser console too. A dev server such as Vite does not
typecheck, and many UI repos have no working typecheck gate. So a missing import passes every
automated test. It only shows up as a runtime error in the console.

Then wait. **Do not act again until the user replies.**

## Phase 5 — On their verdict

| They say | You do |
| --- | --- |
| **Verified** | Return to the calling flow (`ado-bug-fix` or `sdd-bug`) Phase 10 and raise the PR. Add a line to the PR's **Verification comment** — not the description — saying the user tested the worktree build by hand and it passed. Write any work item in that line as `ADO 80459`, never `#80459`: ADO turns a `#` mention into a `Mentioned in` comment on that work item's board. |
| **Something's wrong** | Return to the calling flow — Phase 4 if the symptom persists (the cause was wrong or incomplete), Phase 7 if a side effect appeared, Phase 8 Gate C item 6 if a sibling behaviour regressed. Re-run the automated gates, then offer this environment again. |
| **Can't reach the screen** | Usually a missing dependency service or the wrong database. Fix the environment and re-brief — this is your problem, not a fix defect. |

**Teardown is not automatic.** Restore the main checkout only when the user says they are finished:

```bash
<run-script> -Stop
<run-script> -Only {keys}
```

Confirm with `-Status` that no worktree tag remains. **Leave the worktree itself on disk** —
`ado-bug-fix` still needs it for review fixups.

## Phase 6 — Record what you had to work out

Anything you derived this run that the next run would derive again goes in the workspace root
`CLAUDE.md`, under `## Claude skills — workspace facts`. `ado-bug-fix` Phase 12 owns that heading —
add to it, never start a second one.

| Record | Never record |
| --- | --- |
| The run script, its real flag names, and how many services it starts | Anything about one bug: ids, worktree paths, branch names |
| The repo → service key map | Anything you did not verify this run |
| The service dependency graph | Passwords, connection strings, tokens |
| The database default, and how to check the VPN or network it needs | A port you assumed but never saw answer |
| The UI URL, and where the run script writes its logs | |

Same rules as `ado-bug-fix` Phase 12: ask before the first write, update in place, stamp the date,
keep it short. Skip this phase when you learned nothing new.
