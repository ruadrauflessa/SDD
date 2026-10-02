# Mode: recap — rebuild the mental model after a break

Args: optional repo, work item id, or scope. Default renderer: full (`--quick` allowed).

For an sdd work item, start from `workitem.json` progress/history, `requirements.md`, `design.md`,
`tasks.md`, `questions.md` and the worktree branches; `/sdd status` gives the verdict.

## Data gathering before HTML

Project identity files (README, changelog, package/build files, CLAUDE.md), top-level tree, git
status, recent commits, unmerged/stale branches, TODO/FIXME in recent files, progress notes, key
entry points. Focus on what a returning developer needs.

## Verify before generating

Cite command output or file:line for project state, names, recent activity, blockers and next
steps. Never fabricate momentum or rationale.

## Page sections — use only those with something the user needs

1. Identity: what this is, stack, entry points.
2. Architecture snapshot: static SVG diagram of the current modules.
3. Recent activity: grouped narrative, not a raw log.
4. Current state: uncommitted work, branches, TODOs, blockers.
5. Mental model map: key modules, data flow, command/test/deploy paths.
6. Risks and cognitive debt: hotspots and gotchas.
7. Useful commands and files (compact table).
8. Likely next steps, from evidence only.

Responsive nav.
