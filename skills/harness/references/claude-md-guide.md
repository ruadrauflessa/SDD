# Writing a CLAUDE.md

## How loading works (why size matters)

- `~/.claude/CLAUDE.md` (user) and the project root `CLAUDE.md` — plus everything they
  `@import` — are injected into **every session's context** before the first prompt.
- A `CLAUDE.md` in a subdirectory is loaded **on demand**, when Claude works with files under
  that directory. In a multi-repo workspace this is the mechanism that makes per-repo
  CLAUDE.md files cheap: they cost nothing until you work in that repo.
- Consequence: root file = small and universal; subdirectory files = specific and as detailed
  as they need to be; anything long-form = a separate file that is linked (loaded only when
  Claude chooses to read it) rather than imported (always loaded).

## What belongs — and why

| Content | Why it earns its place |
| --- | --- |
| Build / test / run commands (verified!) | Highest-frequency need; wrong or missing = wasted first 10 minutes of every session |
| Port allocations, local URLs | Not discoverable without launching everything |
| Where environment config actually lives | Often *not* in the repo (external config repos, vaults) — undiscoverable |
| Branching & deployment rules | which branches trigger which deployments is invisible in the code |
| Conventions that deviate from defaults | Claude follows ecosystem defaults unless told otherwise (e.g. "fluent config only, never attributes") |
| Architecture that isn't discoverable | Cross-service routes, which service owns what — spans repos |
| Skills catalogue (root, workspaces) | Sessions can't use skills they don't know exist |
| Spec workflow conventions (where sdd is used) | Where requirements live, which files are mirrors, the branch/spec join key — invisible in the code |
| Gotchas that cost someone an hour | The whole point of writing things down |

## What does NOT belong

- **Anything a linter/formatter enforces.** The tool corrects it; the text is dead weight.
- **Restating code structure.** Claude reads code faster than prose about code.
- **Long API/domain documentation.** Link it; don't import it.
- **Volatile state** — current sprint, in-flight branches, TODO lists. It rots in weeks. That's
  what work trackers and auto-memory are for.
- **Secrets or credentials.** Ever. CLAUDE.md is committed and pasted into model context.
- **Aspirational rules nobody follows.** If the codebase contradicts the rule, the rule loses —
  and teaches sessions to distrust the rest of the file.

## Root vs per-repo split (multi-repo workspaces)

The root file answers: *what is this workspace, what are the pieces, what rules cross repo
boundaries?* The repo file answers: *how do I work inside this one repo?*

| Root CLAUDE.md | Repo CLAUDE.md |
| --- | --- |
| Repo map table (folder → what it is) | Build / test / run commands |
| "Is the root a git repo?" + commit boundaries | Repo-specific layout surprises |
| Branching/deploy rules shared by all repos | Repo-specific conventions |
| Environment domains, config-repo location | Repo gotchas |
| Skills catalogue | Pointers to repo docs |
| Spec workflow conventions (`{specRoot}`, branch shape, join key) | — |
| Shared-shell/OS notes | — |

State explicitly in the root file that each repo has its own CLAUDE.md and that it takes
precedence when working inside that repo. Duplicating a fact in both places guarantees they
eventually disagree.

## Imports

`@path/to/file.md` on its own line imports that file's content at load time.

- Use it to share one source of truth with other AI tooling (e.g. `@.github/copilot-instructions.md`)
  instead of maintaining parallel docs that drift apart.
- Everything imported by the root file is part of the every-session tax — import only what is
  universally needed; link the rest.
- After any restructure, verify import targets still exist (the audit checklist covers this).

## Style

- Short declarative bullets. Imperative mood. No marketing prose.
- Put commands in backticks, exactly as runnable — copy-paste fidelity matters more than
  grammar.
- Date-stamp fragile facts ("as of 2026-07, the X feed requires VPN") so future audits can tell
  stale from stable.
- When a fact is a warning, say what happens if ignored — consequences are remembered,
  rules are not.

## Annotated skeleton (repo level)

```markdown
# Payments.Service                      ← name, not "CLAUDE.md instructions"

Handles card processing for Acme; sits behind the API gateway at /api-payments.
                                        ← one sentence of "where am I"
## Build / test / run
- Build: `dotnet build source/Payments.sln`          ← ran it, it worked
- Test: `dotnet test source/Payments.sln`            ← runs all *.UnitTest projects
- Run: `dotnet run --project source/Presentation/...` ← serves on https://localhost:7031

## Conventions
- Clean architecture; Presentation never references Persistence directly.
- EF Core fluent configuration only — never data annotations.  ← deviation from default

## Gotchas
- Integration tests need the local RabbitMQ container up first (`docker compose up mq`).
- appsettings.json here is dev-only; staging/prod configs live in a separate config repo.
```

Everything in that skeleton is either a verified command, a non-default convention, or an
undiscoverable fact. Nothing restates the code.
