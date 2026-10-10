# Workspace facts cache

> Part of the `sdd:spec` flow (`../SKILL.md`).

Some facts cost real effort to derive and barely change — per-repo test/build commands not
already obvious from that repo's own `CLAUDE.md`, which repos actually carry `team/*` branches,
a trap that cost time. Deriving them again every session is waste, so write the durable ones back
to the **workspace root** `CLAUDE.md`, under one marked heading, and read that heading back at
session start alongside the Sync check.

| Record it | Never record it |
| --- | --- |
| Per-repo test/build commands, if not already obvious from that repo's own `CLAUDE.md` | `team/*` versions — they change every release; always enumerate live |
| Which repos actually carry `team/*` branches versus branching straight off `main` | Anything about one work item: ids, branch names, worktree paths |
| The worktree root convention (`.claude/worktrees/{id}-{slug}/src/{Repo}`) | Passwords, connection strings, tokens, personal data |
| Which work item types carry an Implementation Plan field, and its reference name | Any work item's actual implementation plan content — that's written to ADO, not cached here |
| A trap that cost real time and would cost the next run the same | Your analysis of one spec — that lives in `{specRoot}`, not here |

```markdown
## Claude skills — workspace facts

*Written by the `sdd:spec` skill. Last verified {yyyy-MM-dd}. Check anything cheap before you
trust it. `team/*` versions are deliberately absent — always enumerate them live.*

| Fact | Value |
| --- | --- |
| Worktree root | `<workspace>\.claude\worktrees\{id}-{slug}\src\{Repo}` — confirm it is gitignored |
| ADO org / projects | From `.claude/sdd.json` — not copied here |

### Per-repo notes

| Repo | Test/build command | `team/*` branches? | Notes |
| --- | --- | --- | --- |
| … | … | … | … |

### Implementation Plan field, by work item type

| Type | Present? | Reference name |
| --- | --- | --- |
| … | yes / no | `Custom.…` or — |

### Traps

- One line each. Only what cost real time.
```

Rules for writing it:

1. **Ask before the first write.** The root `CLAUDE.md` may be shared outside git — show the
   block and wait. Later updates need no new permission once the user has agreed once.
2. **Update in place, never append a duplicate.** One `## Claude skills — workspace facts`
   heading per file — the same heading `ado-bug-fix` writes in other workspaces, so the two
   skills never fight over the block if a workspace ever uses both.
3. **Stamp the date.** A block older than about a month is a hint, not a fact — re-verify it.
4. **Keep it under 40 lines.** It loads into every session in this workspace; it's a lookup
   table, not a write-up.
5. **No workspace `CLAUDE.md`?** Say so and ask whether to create one. Never create it silently.

Skip writing it when nothing new was learned this session — an unchanged block isn't worth a
commit.
