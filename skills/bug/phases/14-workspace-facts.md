# Phase 14 — Record what you learned about the workspace

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

This skill derives per-repo facts at run time so it never carries a stale table between workspaces.
Deriving the **same** facts again next week is waste. So write the durable ones into the workspace
root `CLAUDE.md`, under one marked heading, and read them back at Phase 1.1.

## What to record, and what never to record

| Record it | Never record it |
| --- | --- |
| Test projects per repo, and which repo has an ArchUnit project | **`team/*` versions** — they change every release. Always enumerate live. |
| The run-stack script, its flags, and what it starts | Anything about one bug: ids, branch names, worktree paths |
| Which ADO project owns which repo | Anything you did not verify this session |
| The worktree root this workspace uses | Passwords, connection strings, tokens, personal data |
| A trap that cost you time and would cost the next person the same | Your analysis of this defect — that lives on the work item and the PR |

**The volatile-facts rule is the point.** A cached `team/*` table is exactly the thing that goes
stale and sends the next run at the wrong base branch. Cache what is structural. Enumerate what moves.

## The block

Write, or update in place, one heading — never a second copy:

```markdown
## Claude skills — workspace facts

*Written by the `sdd:bug` skill. Last verified {yyyy-MM-dd}. Check anything cheap before you
trust it. `team/*` versions are deliberately absent — always enumerate them live.*

| Fact | Value |
| --- | --- |
| Worktree root | `<workspace root>\.claude\worktrees\{id}-{slug}\src\{Repo}` — created by `scripts/env.py` |
| Run-stack script | `./scripts/<script>.ps1 <flags>` — starts N services |
| ADO project | which project owns which repo |

### Test projects per repo

| Repo | Unit-test projects | ArchUnit |
| --- | --- | --- |
| … | … | … |

### Traps

- One line each. Only what cost real time.
```

## Rules for writing it

1. **Ask before the first write.** The root `CLAUDE.md` is usually tracked and shared. Show the block
   and wait. After the user agrees once, later updates need no new permission.
2. **Update, never append a duplicate.** One `## Claude skills — workspace facts` heading per file.
3. **Stamp the date.** A block older than about a month is a hint, not a fact — re-verify it.
4. **Keep it under 40 lines.** It loads into every session in that workspace. It is a lookup table,
   not a write-up.
5. **No workspace `CLAUDE.md`?** Say so and ask whether to create one. Do not create it silently.
6. Write it in the house style, like everything else.

Skip this phase when you learned nothing new — an unchanged block is not worth a commit.
