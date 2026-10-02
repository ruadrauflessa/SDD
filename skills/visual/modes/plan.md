# Mode: plan — a visual implementation plan (outside the sdd flows)

Args: what to plan. Default renderer: full. Inside sdd use `design` / `tasks` instead.

## Research first

Read relevant repo files before planning. Identify entry points, existing patterns, affected
modules, public APIs, tests, config/schema/data model, similar features, and constraints from
README/CHANGELOG/docs/CLAUDE.md.

## Page sections — use only those with something the user needs

1. Goal and scope: what will change and what is intentionally out.
2. Current state: short diagram/table of existing architecture.
3. Proposed design: architecture/data/control flow, preferably a static SVG diagram or cards.
4. Implementation sequence: ordered phases with dependencies.
5. File map: files to create/edit/delete and why.
6. Interface/contracts: types, APIs, schemas, CLI flags, config, events.
7. Risk and decision matrix: correctness, tests, migration, release, UX, security/privacy, performance.
8. Test plan: unit/integration/e2e/edge cases mapped to files.
9. Acceptance checklist: observable done criteria.

Hierarchy: overview and architecture dominate; file/test/reference sections stay compact or
collapsible. Responsive nav (4+ sections).
