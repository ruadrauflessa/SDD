# Building a run script (only when none exists)

**Ask before you write it.** A launcher is a change to the workspace, not to the fix. Say what it will
start and where it will live, then wait.

Write it to **`.claude/scripts/run-stack.ps1`**, never to `scripts/` (tracked and shared; the guard
refuses a new `scripts/run-*.ps1`). `devops.py env find` says whether `.claude/scripts` is ignored. If
not, add it first: `printf '.claude/scripts/\n' >> .git/info/exclude`.

## What to derive, and where from

| You need | Read |
| --- | --- |
| Which services exist | the solution files, or the service project folders |
| A short key per service | the project folder name, lowercased |
| Port and launch profile | each `Properties/launchSettings.json`, the `https` profile where there is one |
| Connection strings to override | each `appsettings.json`, `ConnectionStrings` section |
| Which service needs which | `appsettings.json` keys ending in `BaseUrl`: each names a dependency |
| The UI dev command | `package.json`, the `scripts` block |

**Inject config as environment variables. Never edit `appsettings.json`:** it is committed.

## The four switches it must support

| Switch | Must do |
| --- | --- |
| `-Only <keys>` | start exactly those services, and nothing else |
| `-Worktree <id>` | run the named services from the worktree build, not the main checkout; both layouts below |
| `-Status` | list each service, its port, UP or not, and `worktree: <folder name>` for a binary from a worktree |
| `-Stop` | stop everything it started |

The worktree tag in `-Status` is what `devops.py env gate` reads (Gate D). Without it the build that
answers cannot be proven, so the skill cannot hand over.

Worktree layouts under `<workspace>\.claude\worktrees\`: sdd `{id}-{slug}\src\{Repo}` (its
`workitem.json` lists the repos and bases) and the old `{Repo}\{id}_{slug}`.
