# Mode: design — present an sdd design for approval

Used at: sdd:spec Design, before the "Design agreed" gate (and again after every revision), plus the
tech story gate. Source: `design.md` in the spec folder and the code in `src/{Repo}/`. Default
renderer: full.

Sections — use only those with something the user needs:

1. **Approach in one paragraph** + the decision being asked for (first viewport).
2. **Current vs proposed** — two matching diagrams of the affected subsystem only, the change
   highlighted (green new, amber changed, red removed).
3. **Affected components** — cards per repo/module, each with its anchors (files, symbols, routes,
   tables, migrations, config/feature-flag keys).
4. **Contracts and data** — API/DTO/schema changes as before/after tables.
5. **Risks** — severity-tagged.
6. **Rejected alternatives** — each with the edge it would add or remove, and why not.
7. **Proposed tech stories** — one card each, so the multi-select gate matches the page.
8. **Links** — requirements.md, design.md, parent feature design (by reference).

When re-presenting after "Needs changes", add a **What changed since last time** strip at the top.
