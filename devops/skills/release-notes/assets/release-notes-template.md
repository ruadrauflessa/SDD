# Release Notes Markdown Template

Structural reference for the two required outputs:

1. **Repository file** — plain, portable markdown saved under `documents/release-notes/` (Step 11).
2. **Azure DevOps wiki pages** — a styled parent index plus a dated release page, using status badges and
   priority pills (Step 12).

Copy the relevant structure, populate every placeholder with real data gathered during the workflow, and
omit any section that has no entries. Omit `Database Migration Changes` entirely if the user opted out of
migration-change detection, or if detection was performed but found no matching files. Omit
`Skill Documentation Changes` entirely if the user opted out of skill-documentation-change detection, or if
detection was performed but found no matching files. This is a separate opt-in from migration detection.

Placeholders: `{org}`, `{project}` (URL-encoded), `{repo}`, `{version}` (e.g. `1.0.2`, from the release
branch), `{environment}` (one of `QA`, `UAT`, `STAGE`, `PROD` — the deployment environment this release
build targets, always asked up front, see `SKILL.md` "Required Clarification"), `{yyyy-MM-dd}` (generated
date), `{scope}` (e.g. `Bug Fixes`), `{assignee}` (the work item's `System.AssignedTo` display name, or
`Unassigned` if empty), `{tags}` (the work item's `System.Tags`, split on `;` and trimmed — omit the whole
tags note/badges for an item when it has none).

---

## 1. Repository file structure (plain markdown)

Saved to `documents/release-notes/release-notes-yyyyMMdd[-<scope-slug>]-N.md`. Keep this version badge-free so
it renders anywhere (Teams, GitHub, plain viewers).

````md
# Release {version} — {environment}

- Environment: {environment}
- Generated: {yyyy-MM-dd}
- Release branch: `release/{version}`
- Scope: {scope}
- Priority presentation: {presentation mode}

## Repositories

- {repo}

## Included Pull Requests

- [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}) - {repo} - {pr title}

## Database Migration Changes

- [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}) - {repo}
  - EF Core Migration: `source/Persistence/Migrations/20260401120000_AddInvoiceStatus.cs`
  - SQL Script: `SQL Scripts/2026-04-01-add-invoice-status.sql`

## Skill Documentation Changes

- [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}) - {repo}
  - Added: `docs/skills/tariff-search.md` — skill `tariff-search`
  - Modified: `docs/skills/cpt4-coding-rules.md` — skill `cpt4-coding-rules`

## Delivered Bug Fixes

- [{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) - {area} - {fix summary} (Priority {n}) — Handled by {assignee} — Tags: {tag1}, {tag2}

## Delivered User Stories

- [{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) - {title} — Handled by {assignee} — Tags: {tag1}, {tag2}

## Delivered Tasks

- [{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) - {title} — Handled by {assignee} — Tags: {tag1}, {tag2}

## Features

- [{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) - {title} — Handled by {assignee} — Tags: {tag1}, {tag2}

## Epics

- [{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) - {title} — Handled by {assignee} — Tags: {tag1}, {tag2}
````

Drop the trailing `— Tags: …` from a line entirely when that work item has no tags — never write `— Tags:` with nothing after it.

---

## 2. Wiki release page (styled with badges + pills)

Published at `/Release Notes/Release {version} [{environment}] - {yyyy-MM-dd}`. Same content as the file,
presented as cards with a metadata badge row and priority pills. **The environment tag must be visible in
the page title itself** (the `#` heading), not only in the badge row — a reader scanning the wiki page list
must be able to tell QA from PROD without opening the page.

````md
# Release {version} — {environment} — {yyyy-MM-dd}

![Release](https://img.shields.io/badge/Release-{version}-2B6CB0?style=flat-square) ![Environment](https://img.shields.io/badge/Environment-{environment}-{env_color}?style=flat-square) ![Generated](https://img.shields.io/badge/Generated-{yyyy--MM--dd}-6B7280?style=flat-square) ![Scope](https://img.shields.io/badge/Scope-{scope}-2B6CB0?style=flat-square) ![Branch](https://img.shields.io/badge/branch-release%2F{version}-475467?style=flat-square)

> **Pull request:** [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}) — {pr title}

---

## Delivered Bug Fixes

#### [#{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) {area} — {short headline}

![Priority 1](https://img.shields.io/badge/Priority_1-critical-D92D20?style=flat-square) &nbsp; ![Tag](https://img.shields.io/badge/{tag1}-6B7280?style=flat-square) ![Tag](https://img.shields.io/badge/{tag2}-6B7280?style=flat-square) &nbsp; ![Handled by](https://img.shields.io/badge/Handled_by-{assignee}-2B6CB0?style=flat-square)

{One-sentence description of the fix, phrased as the resolved behaviour.}

#### [#{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) {area} — {short headline}

![Priority 2](https://img.shields.io/badge/Priority_2-high-DC6803?style=flat-square) &nbsp; ![Handled by](https://img.shields.io/badge/Handled_by-{assignee}-2B6CB0?style=flat-square)

{One-sentence description of the fix. This item had no tags, so no tag badges are shown.}

## Features

#### [#{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) {title}

![Priority 2](https://img.shields.io/badge/Priority_2-high-DC6803?style=flat-square) &nbsp; ![Handled by](https://img.shields.io/badge/Handled_by-{assignee}-2B6CB0?style=flat-square)

## Epics

#### [#{workItemId}](https://dev.azure.com/{org}/{project}/_workitems/edit/{workItemId}) {title}

![Priority 2](https://img.shields.io/badge/Priority_2-high-DC6803?style=flat-square) &nbsp; ![Handled by](https://img.shields.io/badge/Handled_by-{assignee}-2B6CB0?style=flat-square)

---

_Sourced from Azure DevOps PR [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}) and its linked work items._
````

For non-bug scopes, replace the `Delivered Bug Fixes` heading and cards with the appropriate section(s) from
the Recommended Section Order, keeping the same card + pill styling. Add `Database Migration Changes` (when
opted in), `Skill Documentation Changes` (when separately opted in), and `Included Pull Requests`
sections as needed, mirroring the file structure.

---

## 3. Wiki parent index page

Published at `/Release Notes`. Recreated/updated every run so the newest release appears at the top.

````md
# Release Notes

Release notes for the {project} platform, one page per release build. Pages are named
`Release <version> [<environment>] - <yyyy-MM-dd>` so multiple builds of the same version, or the same
version deployed to different environments, can coexist.

## Releases

- [Release {version} [{environment}] - {yyyy-MM-dd}](/Release-Notes/Release-{version}-%5B{environment}%5D-%2D-{yyyy}%2D{MM}%2D{dd}) — **{environment}** — {scope} (PR [{prId}](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{prId}))
````

> **Link encoding:** Azure DevOps encodes a literal `-` in a page name as `%2D` in the git path. Prefer building
> the index link from the `gitItemPath` returned by `wiki_create_or_update_page` rather than hand-encoding it.

---

## Badge colour palette

Keep these consistent across all wiki release pages.

| Element | shields.io colour | Example label |
|---|---|---|
| Release / scope (accent) | `2B6CB0` | `Release-1.0.2` |
| Environment — `QA` | `7C3AED` | `Environment-QA` |
| Environment — `UAT` | `2563EB` | `Environment-UAT` |
| Environment — `STAGE` | `D97706` | `Environment-STAGE` |
| Environment — `PROD` | `DC2626` | `Environment-PROD` |
| Generated date / neutral | `6B7280` | `Generated-2026--07--17` |
| Branch | `475467` | `branch-release%2F1.0.2` |
| Priority 1 | `D92D20` | `Priority_1-critical` |
| Priority 2 | `DC6803` | `Priority_2-high` |
| Priority 3 | `CA8A04` | `Priority_3-medium` |
| Priority 4 / unspecified | `6B7280` | `Priority_4-low` |
| Tag (ADO `System.Tags`) | `6B7280` | `Widget`, `Regression` |
| Handled by (assignee) | `2B6CB0` | `Handled_by-Heinrich_Etsebeth` |

Notes on shields.io syntax: `_` renders as a space and `--` renders as a single `-`, so encode dates as
`2026--07--17` and slashes as `%2F`.

**External-image caveat:** shields.io badges are external images. If an Azure DevOps organization blocks
external images, the badges will not render. Fall back to either badge SVGs committed to the wiki's
`.attachments/` folder (served internally) or native colour emoji + bold text (🔴 `P1`, 🟠 `P2`). Do not leave
broken images in place.

---

## Formatting Rules

- Use `#` for the document title, `##` for sections, `###` for per-item cards or priority subsections.
- **The deployment environment (`QA`/`UAT`/`STAGE`/`PROD`) is always part of the `#` title** — on the
  repository file (`# Release {version} — {environment}`), on the wiki page
  (`# Release {version} — {environment} — {yyyy-MM-dd}`), in the wiki page's own path, and as its own line
  in the parent index list. This is not optional styling — it is how a reader tells which environment a
  release build targets without opening the page. Colour the `Environment` badge per the palette above.
- On the wiki page, lead with the metadata badge row directly under the `#` title.
- On each wiki card, the work item ID is a clickable `#{id}` prefix on the `####` heading itself (never a
  badge, never on the badge row). The badge row beneath the heading is, in order: the priority badge, any
  tag badges, then the `Handled by` badge. The repository file keeps the plain-text
  `[{id}](...) - ... — Handled by {assignee}` line instead — no heading, no badges there.
- Add one neutral-colour tag badge (`6B7280`) per entry in the item's `System.Tags`, next to the priority
  pill. In the repository file, use the plain-text form `— Tags: {tag1}, {tag2}` at the end of the item's
  line instead. Omit tags entirely (no badges, no `— Tags:` text) for an item with no tags.
- `Handled by` is a two-tone badge on the wiki (`Handled_by` label, assignee name as the message, colour
  `2B6CB0`) — never plain text on the wiki page. Encode the assignee name per shields.io syntax (spaces
  → `_`, a literal `-` → `--`).
- Omit empty sections, including `Database Migration Changes` when no migration files were detected, and
  `Skill Documentation Changes` when no matching skill file was detected.
- Keep section order stable — see the "Recommended Section Order" list in `SKILL.md`.
- When priority ordering is enabled, list higher priority items before lower priority items.
- When priority grouping is enabled, use `###` priority subsections inside the affected section.
- Every PR and work item ID must be a clickable Azure DevOps hyperlink (never a bare number or a raw `#id`
  mention — `#id` only auto-links when typed live in the wiki editor, not from pushed markdown).
- Use a blank line between headings, badges, and lists.
- Under `Database Migration Changes`, nest matched file paths as a sub-list beneath each PR entry, labelling
  each `EF Core Migration:` or `SQL Script:` by detected type.
- Under `Skill Documentation Changes`, nest matched file paths as a sub-list beneath each PR entry, labelling
  each `Added:` or `Modified:`, followed by an em dash and the skill's captured `name:` front-matter value.
  Only list a file here if its front matter had both `name:` and `description:` — otherwise it is not an
  actual skill and does not belong in this section.
