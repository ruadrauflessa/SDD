# settings.json, allowlists, hooks, and MCP scope

## The settings file map

| File | Scope | Committed? | Use for |
| --- | --- | --- | --- |
| `<root>/.claude/settings.json` | Project, whole team | Yes | Shared allowlist, shared hooks |
| `<root>/.claude/settings.local.json` | Project, this machine | No (gitignored) | Personal permissions, machine-specific paths |
| `~/.claude/settings.json` | User, all projects | — | Personal defaults everywhere |
| Managed/enterprise settings | Org | — | Policies that override everything |

Precedence (highest first): managed → local project → shared project → user. When deciding
where a rule goes: *would a teammate want this too?* → shared project file; *is it about my
machine or my tolerance for prompts?* → local.

## Permission rules

```json
{
  "permissions": {
    "allow": [
      "Bash(dotnet build *)",
      "PowerShell(dotnet build *)",
      "Bash(git status *)",
      "mcp__github__get_issue",
      "WebFetch(domain:learn.microsoft.com)"
    ]
  }
}
```

- `Tool(prefix *)` matches commands by prefix; a bare `mcp__server__tool` allows that MCP tool.
- There are also `ask` and `deny` lists; `deny` wins over `allow`. Use `deny` sparingly, for
  genuinely dangerous patterns you never want auto-run.

**Building the allowlist empirically** — don't invent it up front:

1. Start with read-only git (`status`, `diff`, `log`, `branch`) and the stack's build/test/lint
   commands — the things sessions run dozens of times a day.
2. Add entries when the same *safe* command prompts repeatedly in real sessions.
3. Never blanket-allow state-changing commands: `git push`, `git commit`, package installs,
   database migrations, deletions. The prompt on those is the safety net working as intended.
4. Keep entries narrow: `Bash(npx vitest *)` not `Bash(npx *)`.

**Windows note:** sessions have both a Bash tool and a PowerShell tool. An allowlist entry for
one does nothing for the other — mirror every command entry in both forms, or the prompts come
back through the other shell.

### Starter allowlists by stack

.NET: `dotnet build|test|restore|list|format`. Node: `npm run|test`, `npx tsc|eslint|vitest|playwright`.
Python: `pytest`, `ruff check|format`, `uv run|sync`. All stacks: read-only git. Trim what the
repo doesn't use; a dead allowlist entry is clutter that hides real gaps.

### Azure DevOps MCP tools (sdd workflow)

Allowlist the **read** tools only — `wit_work_item`, `wit_query`,
`wit_backlog`, `search_workitem`. Sessions hit
these constantly once specs are in play, and none of them change anything.

Never allowlist a work item **write** (`wit_work_item_write`, `wit_work_item_comment_write`,
`wit_work_item_link_write`). Two reasons beyond the usual one: the sdd flows make their ADO writes
themselves, each behind an approval gate by design, and
stock ADO MCP servers do not send a revision test with their patches, so an unattended write can
silently overwrite someone's concurrent edit.

## Hooks

Hooks run shell commands on harness events. The ones that matter most for harness maintenance:

| Event | Fires | Good for |
| --- | --- | --- |
| `SessionStart` | Once per session | Drift checks, sync scripts, environment sanity |
| `PreToolUse` / `PostToolUse` | Around tool calls | Guardrails, formatters |
| `UserPromptSubmit` | Each user message | Injecting dynamic context |
| `Stop` | Agent finishes a turn | Notifications |

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"<abs-path>\\audit-coverage.ps1\" -Root \"<workspace-root>\" -Quiet"
          }
        ]
      }
    ]
  }
}
```

The sdd plugin installs its own hooks (the question guard, via `/sdd init`); do not duplicate
them here. Keep any hook you add fast and silent when healthy.

Rules of thumb — hooks run on **every** session, so:

- **Fast**: a slow hook taxes every session start. Keep it under a couple of seconds.
- **Silent when healthy**: output only when something is wrong (that's what `-Quiet` modes are
  for). A hook that always prints noise trains everyone to ignore it, then gets deleted.
- **Absolute paths**: hooks don't inherit your shell profile or cwd assumptions.
- Registering a hook needs the user's awareness — it's standing configuration. Propose, don't
  sneak.

## MCP server scope

| Scope | Stored in | Choose when |
| --- | --- | --- |
| `user` | `~/.claude.json` | You want it in every project (e.g. your org's ADO/Jira server) |
| `project` | `<root>/.mcp.json` (committed) | The whole team needs it for this project |
| `local` | Project-local, not committed | Trying something out |

`claude mcp add <name> -s user|project|local ...` — then allowlist the specific read-only tools
you use constantly (`mcp__<server>__<tool>` entries) so they stop prompting.
