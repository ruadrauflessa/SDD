---
name: release-notes
description: Generate release notes from currently Active Azure DevOps cloud PRs targeting `release/*` branches, or from a specific online PR/commit. Use when asked to generate release notes, create a changelog, summarize a release, list what was deployed, show release PRs, report what changed, prepare deployment notes, inspect a PR that exists only in Azure DevOps, or resolve a PR from a commit hash. Every release build is tagged with a deployment environment (`QA`, `UAT`, `STAGE`, or `PROD`) that is clearly visible in the title of the wiki page and the repository file, not just a footnote. Asks scope, priority-presentation, deployment-environment, migration-detection and skill-documentation-detection preferences together as one upfront batch of questions (never one at a time, never re-asked later) before any deep querying. Discovers Active release PRs project-wide in a single pass with `repo_list_pull_requests_by_repo_or_project` (status filtered to `Active`, repository filter omitted), maps commits to PRs with `repo_list_pull_requests_by_commits`, refreshes authoritative PR metadata with `repo_get_pull_request_by_id`, credits each work item to the person named in `System.AssignedTo`, shows each work item's ADO tags from `System.Tags`, optionally checks the local diff between each PR's source and target branches for EF Core and SQL migration changes and, independently, for added/modified skill markdown files under any `skill`/`skills` folder (each opted into separately in the upfront batch, since many repos never define skills and the check is otherwise wasted), verifying a matched markdown file's front matter (`name:` + `description:`) proves it is an actual skill definition (on this workspace, primarily `Spesnet_Lumina.Agent/docs/skills/*.md`) rather than an unrelated `.md` file that happens to live there, writes well-formed markdown (using the bundled `assets/release-notes-template.md` template) to `documents/release-notes/release-notes-yyyyMMdd-N.md`, publishes the same notes to the project's Azure DevOps wiki as a styled, badge-formatted dated page under a `Release Notes` parent (via `wiki_list_wikis` and `wiki_create_or_update_page`), and uses clickable Azure DevOps hyperlinks for PR and work item IDs.
---

# Release Notes Generator

Generate release notes for the latest release across all Azure DevOps repositories in the workspace, write the final output to a markdown file under `documents/release-notes`, **and** publish the same notes to the project's Azure DevOps wiki as a styled, badge-formatted dated page under a `Release Notes` parent page.

## When to Use This Skill

- User asks to generate, create, or update release notes
- User asks for a changelog, release summary, deployment summary, or release report
- User asks what changed, what shipped, what was deployed, or what was released
- User wants a markdown file containing release notes
- User wants PRs and linked Azure DevOps work items summarized for a release

## Prerequisites

- The `microsoft/azure-devops-mcp` integration must be available
- The working directory should provide enough Azure DevOps repository context to identify the cloud repositories to query
- Release PRs should have linked work items in Azure DevOps
- If the user opts in to migration-change detection, local clones of the relevant repositories should be present in the workspace to support it (see Step 5)
- If the user opts in to skill-documentation-change detection, local clones of the relevant repositories should also be present to support it (see Step 5b) — this is a separate opt-in from migration detection; ask both together upfront (see "Required Clarification")

If `microsoft/azure-devops-mcp` is unavailable, stop immediately.

- Do not try to continue with local git history as a fallback.
- Do not generate partial or guessed release notes.
- Instruct the user to install the Azure DevOps MCP integration or make it available in the current environment before retrying.

## Bundled Assets

- `assets/release-notes-template.md` — the required markdown structure for **both** the repository file (plain markdown) and the Azure DevOps wiki page (styled with status badges / priority pills). It also defines the `Release Notes` parent index page structure, the badge colour palette, the `Database Migration Changes` section (only populated when the user opted in to migration-change detection), and the `Skill Documentation Changes` section (only populated when the user separately opted in to skill-documentation-change detection). Use it as the structural reference in Step 9 (file) and Step 12 (wiki) instead of duplicating the template inline.

## Cloud-First Pull Request Resolution

All PR discovery and validation must come from Azure DevOps in the cloud.

- Do not infer PR existence, status, or metadata from local git branches, local refs, or local merge history.
- Do not assume a PR exists locally or has already been fetched to disk.
- A PR may still be `Active` and still be valid for user-requested reporting when the user identifies it directly by PR ID or commit hash.
- Use local repositories only as hints for Azure DevOps organization, project, and repository names when needed.

The following Azure DevOps MCP commands are mandatory when applicable:

- `repo_list_pull_requests_by_repo_or_project`: discover release PRs across the **entire project in one call** by omitting `repositoryId` and passing only `project`, with `status` filtered to `Active` only. This skill only reports on currently active PRs targeting `release/*` branches, so this is the default discovery method and must be used instead of looping over repositories one by one.
- `repo_get_repo_by_name_or_id`: resolve and validate a specific target repository only when the user explicitly names one, or when repository-scoped commands (e.g. commit lookup) require a repository ID.
- `repo_list_pull_requests_by_commits`: when the user provides a commit hash, find the associated cloud PR instead of searching local git history.
- `repo_get_pull_request_by_id`: fetch authoritative PR metadata directly from Azure DevOps for every explicitly referenced PR and for any PR selected for the final report.
- `wiki_list_wikis`: discover the project wiki before publishing (pass the `project`; the project wiki is typically named `<Project>.wiki`).
- `wiki_create_or_update_page`: create or update the `Release Notes` parent index page and the dated release page in the project wiki.

**Token-efficiency rule**: never call a repository-scoped PR listing command once per repository to search for release PRs. Always prefer a single project-scoped `repo_list_pull_requests_by_repo_or_project` call (paginated with `skip`/`top` if needed) over per-repository iteration.

## Required Clarification

There are five things to pin down before any Azure DevOps querying beyond resolving the project (Step 1): scope, priority presentation, deployment environment, database migration detection, and skill documentation detection.

**Ask all five together, in a single turn, as one batch of questions — never one at a time and never spread across later steps.** This is a hard rule: once the batch has been asked and answered, do not ask any of these five questions again later in the same run, even if a later step would otherwise be a natural point to double-check (e.g. do not re-ask the migration or skill-documentation question at Step 5 / Step 5b — just apply the stored answer).

For each of the five, if the user already specified an answer in their original request, use it directly and do not include that one in the batch. Ask only the ones still unanswered, still together in one message, not individually.

1. **Scope** — one of:
   - `Only bugs`
   - `All tasks/items`
   - `Only tasks`
   - `Only stories`
   - `Only features`

   Question: `Should I include only bugs, all tasks/items, only tasks, only stories, or only features in the release notes?`

2. **Priority presentation** — one of:
   - `Do not divide or order by priority`
   - `Order by priority only`
   - `Divide into priority sections only`
   - `Divide into priority sections and order by priority`

   Question: `Should the release notes be divided and/or ordered by priority?`

3. **Deployment environment** — one of:
   - `QA`
   - `UAT`
   - `STAGE`
   - `PROD`

   Question: `Which deployment environment is this release build for — QA, UAT, STAGE, or PROD?`

   This is never guessed or defaulted from the release branch name or version number — a `release/1.2.0`
   branch can be built and tagged for QA today and PROD next week. Ask a multiple-choice question
   (`AskUserQuestion`), not free text, since this drives the page title and cannot be corrected after
   publishing without confusing anyone who already saw the old title.

4. **Database migration detection** — one of:
   - `Yes, check for database migration changes`
   - `No, skip database migration checks`

   Question: `Should I check the local diff of each PR for EF Core or SQL migration changes and list them separately?`

5. **Skill documentation detection** — one of:
   - `Yes, check for skill documentation changes`
   - `No, skip skill documentation checks`

   Question: `Should I check the local diff of each PR for added/modified skill markdown files (e.g. under a docs/skills folder) and list them separately? Not every repo defines skills, so say no if the repos in scope don't have any — it costs an extra local diff per PR for no benefit there.`

All five are asked (or skipped, per already-known answers) the same way — together, once, upfront.

If the answer is `No, skip database migration checks`, skip Step 5 entirely, omit the `Database Migration Changes` section from the output, and do not run any local git diff commands for migration detection.

## Key Rules

### House Writing Style
Every sentence this skill writes itself (summaries, descriptions, the chat report) follows the house
style: ASD-STE100 Simplified Technical English. One idea per sentence, active voice, small words.
Read `${CLAUDE_PLUGIN_ROOT}/references/writing-style.md` before Step 9.

Text copied from Azure DevOps (PR titles, work item titles, tags, names) stays as written. So do
paths, branch names, IDs, URLs and commands. Do not rewrite them.

### MCP Availability Is Mandatory

The release notes workflow depends on Azure DevOps cloud data and must not continue without `microsoft/azure-devops-mcp`.

- If the MCP is unavailable, stop the work immediately.
- Tell the user that release note generation cannot proceed until `microsoft/azure-devops-mcp` is installed or made available.
- Do not substitute local repository inspection for Azure DevOps cloud queries.

### Release Selection

A release is derived from Azure DevOps cloud PR data, not from local repository state.

- By default, select the most recent cluster of currently **Active** PRs targeting `release/*` branches across all resolved Azure DevOps repositories. Do not include `Completed`, `Abandoned`, or other non-Active statuses in this default discovery.
- If the user explicitly identifies a PR ID, repository + PR ID, or commit hash, treat the resolved online PR as in scope regardless of its status.

- Sort candidate PRs by creation date descending.
- Start a new cluster whenever the gap between consecutive PRs exceeds **2 hours** by default.
- Use only the newest cluster unless the user explicitly requests a different release.

### Hierarchy Resolution

Resolve directly linked work items upward through parent links to Epic when needed.

Typical hierarchy:

```text
Epic
  └── Feature
        └── Product Backlog Item / User Story / Bug
              └── Task
```

### Priority Presentation

Priority presentation is optional and must be driven by the user's answer.

- If the user says `Do not divide or order by priority`, keep the existing section layout with no priority-based grouping or sorting.
- If the user says `Order by priority only`, sort items within each section by priority before title.
- If the user says `Divide into priority sections only`, split each populated work item section into priority subsections without changing the order inside each subsection unless another rule applies.
- If the user says `Divide into priority sections and order by priority`, split items into priority subsections and place higher priority subsections first.

Use Azure DevOps work item priority fields when available. If multiple priority-like fields exist, prefer the one most consistently populated for the repository or project and apply it consistently across the document.

If no priority field is available for an item, place it in an `Unspecified Priority` group when grouping is enabled, or after explicitly prioritized items when sorting is enabled.

### Deployment Environment Tag

Every release build this skill reports on targets exactly one deployment environment — `QA`, `UAT`, `STAGE`, or `PROD` — resolved from the "Required Clarification" batch (never guessed from the release branch name or version number).

- **The environment must be clearly visible in the title**, not buried in a metadata line or badge row alone:
  - Repository file title: `# Release {version} — {environment}`.
  - Wiki page title: `# Release {version} — {environment} — {yyyy-MM-dd}`.
  - Wiki page path: `/Release Notes/Release <version> [<environment>] - <yyyy-MM-dd>` — the environment sits in the path itself, so it is visible in the wiki's page tree and in any link to the page, not just after opening it.
  - Parent index (`/Release Notes`) list entry: bold the environment inline, e.g. `— **QA** — {scope}`.
- Also show it as its own `Environment` badge in the wiki metadata badge row (colour per environment — see the palette in `assets/release-notes-template.md`), and as an `- Environment: {environment}` line under the repository file's title.
- If the same version is later built again for a different environment (e.g. `1.2.0` goes to QA today and PROD next week), that is a **separate dated page** with its own environment in the path and title — never overwrite an existing environment's page with a different environment's content.

### Work Item Tags Display

Every work item line in the report (bug, story, task, feature, epic — in both the repository file and the wiki page) must show that item's ADO tags, sourced from `System.Tags` (Step 7).

- Split `System.Tags` on `;` and trim whitespace to get individual tag labels.
- In the repository file (plain markdown), append `— Tags: {tag1}, {tag2}` to the item's line, comma-separated, after the `Handled by {assignee}` part.
- On the wiki page, render each tag as its own small badge/pill (neutral colour `6B7280`, same shields.io style as the priority pills) — see "Wiki Card Layout" below for where it sits in the row.
- If a work item has no tags (`System.Tags` empty), omit the tags note/badges for that item entirely — do not show `Tags: none` or an empty badge.

### Wiki Card Layout

On the wiki page only (the repository file keeps its plain-text line — see the template), each work item renders as a `####` heading plus a badge row beneath it:

- **Heading**: `#### [#{workItemId}](.../_workitems/edit/{workItemId}) {area} — {short headline}` — the work item ID is a clickable `#{id}` prefix on the heading itself, not on the badge row below it.
- **Badge row**, left to right:
  1. The priority badge (a two-tone shields.io badge: grey `555` label half reading `Priority {n}`, coloured message half reading the severity word — `critical`/`high`/`medium`/`low` per the palette).
  2. One neutral-colour (`6B7280`) tag badge per entry in `System.Tags`, if any.
  3. The `Handled by` badge — also a two-tone shields.io badge, grey `555` label half reading `Handled by`, message half reading the assignee's display name (or `Unassigned`) in colour `2B6CB0`.

This replaces both the earlier plain-text `Handled by **{assignee}**` and the earlier plain-hyperlink placement of the work item ID on the badge row — the ID now lives in the heading (as a clickable `#{id}` prefix) and the assignee is always a badge, never plain text, on the wiki page. The repository file is unaffected: it keeps `[{id}](...) - {title} — Handled by {assignee}` as a single plain-text line (no heading, no badges — portability over styling).

The `Features` and `Epics` sections use the same `####` card treatment as `Delivered Bug Fixes` and `Delivered User Stories` on the wiki — heading with the `#{id}` prefix, then the same badge row (priority, tags if any, `Handled by`). They are not left as plain bullet lists on the wiki, even though a Feature or Epic has no one-sentence "fix" description to add below the badge row — omit that description line for these two sections rather than inventing one.

A shields.io two-tone badge URL is `https://img.shields.io/badge/{label}-{message}-{color}?style=flat-square`. Encode both `{label}` and `{message}` per shields.io syntax: spaces become `_`, and a literal `-` in the text must be escaped as `--` (or the badge splits in the wrong place). E.g. assignee "Heinrich Etsebeth" → `Handled_by-Heinrich_Etsebeth-2B6CB0`.

### Markdown Output Is Mandatory

The final release notes must be written to a file in `documents/release-notes`.

- Create the folder if it does not exist.
- Do not only print the notes in chat.
- After writing the file, provide the saved path and a short summary in chat.

### Wiki Publishing Is Mandatory

After the file is saved, the same release notes must also be published to the **project's Azure DevOps wiki**. The file and the wiki page are both required outputs, not alternatives.

- Discover the project wiki with `wiki_list_wikis` (pass the `project`). The project wiki is normally named `<Project>.wiki`.
- **If no project wiki exists, do not attempt to auto-provision one.** The Azure DevOps MCP has no create-wiki tool, and provisioning one is a structural change the user should own. Stop the wiki step, tell the user to create the project wiki once (**Overview → Wiki → Create project wiki**), and continue once they confirm it exists. The repository markdown file is still produced regardless.
- Publish with `wiki_create_or_update_page` (it fetches the `etag` automatically for updates).
- Publishing to the wiki modifies shared content. Treat it as expected behaviour of this skill, but still report exactly what was created or updated afterward.

### Wiki Page Structure

The wiki uses a parent index page plus one dated page per release build:

- **Parent index** — path `/Release Notes`. A short intro plus a `Releases` list, newest first, each linking to its dated child page. Recreate/update this page on every run so the new release appears in the list.
- **Dated release page** — path `/Release Notes/Release <version> [<environment>] - <yyyy-MM-dd>`. Naming `Release <version> [<environment>] - <yyyy-MM-dd>` lets multiple builds of the same version, or the same version built for different environments, coexist. Derive `<version>` from the release branch (e.g. `release/1.0.2` → `1.0.2`); `<environment>` is the answer from "Required Clarification" (`QA`/`UAT`/`STAGE`/`PROD`) — see "Deployment Environment Tag" above.

When linking to a child page from the parent, remember Azure DevOps encodes a literal `-` in a page name as `%2D` in the git path (e.g. `/Release-Notes/Release-1.0.2-%5BQA%5D-%2D-2026%2D07%2D17`). Prefer verifying the link target from the `gitItemPath` returned by `wiki_create_or_update_page`.

### Wiki Styling — Badges and Pills

Match the styled format defined in `assets/release-notes-template.md`:

- A **metadata badge row** at the top (release, environment, generated date, scope, branch) using [shields.io](https://img.shields.io) flat-square badges — the environment badge sits right after the release badge, but remember the title itself (see "Deployment Environment Tag") is the primary place a reader sees it, not this row.
- **Priority pills** on each work item (e.g. `Priority 1` in red, `Priority 2` in amber), also shields.io badges.
- **Per-item sections** (area heading + pill + description) rather than a bare table, so each fix reads as a card.

Badge colour palette (keep consistent across pages):

| Element | Label / colour |
|---|---|
| Release / scope (accent) | `2B6CB0` |
| Environment — `QA` | `7C3AED` |
| Environment — `UAT` | `2563EB` |
| Environment — `STAGE` | `D97706` |
| Environment — `PROD` | `DC2626` |
| Generated date / neutral | `6B7280` |
| Branch | `475467` |
| Priority 1 — `critical` | `D92D20` |
| Priority 2 — `high` | `DC6803` |
| Priority 3 — `medium` | `CA8A04` |
| Priority 4 / unspecified — `low` | `6B7280` |
| Tag (ADO `System.Tags`) | `6B7280` |
| Handled by (assignee) | `2B6CB0` |

**External-image caveat:** shields.io badges are external images. Some Azure DevOps organizations block external images in the wiki, in which case the badges will not render for viewers. If the user reports badges not showing, fall back to either (a) committing equivalent badge SVGs into the wiki's `.attachments/` folder via the wiki git repo so they are served internally, or (b) native colour emoji + bold text (🔴 `P1`, 🟠 `P2`) in the tables. Do not silently leave broken images.

### File Naming Convention

Use these file name patterns:

```text
release-notes-yyyyMMdd-N.md
release-notes-yyyyMMdd-<scope-slug>-N.md
```

Examples:

- `release-notes-20260401-1.md`
- `release-notes-20260401-2.md`
- `release-notes-20260401-only-bugs-1.md`
- `release-notes-20260401-only-stories-1.md`

File naming rules:

- When the selected scope is `All tasks/items`, do not add a scope segment.
- When the selected scope is anything else, append a scope slug before the counter.
- Use these exact scope slugs:
      - `Only bugs` → `only-bugs`
      - `Only tasks` → `only-tasks`
      - `Only stories` → `only-stories`
      - `Only features` → `only-features`

### Counter Algorithm

1. Use the current local date for `yyyyMMdd`.
2. Determine the file prefix from the selected scope.
3. Inspect `documents/release-notes` for files matching that prefix:
       - `release-notes-<today>-*.md` for `All tasks/items`
       - `release-notes-<today>-<scope-slug>-*.md` for any other scope
4. Parse the numeric suffix `N`.
5. Set `N` to the next available integer starting at `1`.
6. Never overwrite an existing file for that day and scope.

## Workflow

### Step 0: Verify Azure DevOps MCP Availability

Before doing any repository, PR, or work item lookup:

- Verify that `microsoft/azure-devops-mcp` is available
- If it is not available, stop immediately
- Tell the user to install the Azure DevOps MCP integration or make it available, then retry the request

### Step 1: Resolve the Azure DevOps Project

Inspect workspace folders only to discover the likely Azure DevOps organization and project context (repository names are no longer needed for the default project-wide scan).

Extract:

- Organization
- Project

Do not call `repo_get_repo_by_name_or_id` for every repository in the workspace. Only resolve an individual repository with `repo_get_repo_by_name_or_id` when:

- The user explicitly names a specific repository, or
- A repository ID is required for a repository-scoped command such as `repo_list_pull_requests_by_commits`.

If the user already specifies the repository, resolve that repository directly in Azure DevOps and do not rely on the local folder contents.

### Step 2: Resolve Explicit PR References First

If the user provides a PR ID:

- Resolve the repository with `repo_get_repo_by_name_or_id`
- Fetch the PR using `repo_get_pull_request_by_id`
- Use the returned Azure DevOps PR metadata as the source of truth

If the user provides a commit hash:

- Resolve the repository with `repo_get_repo_by_name_or_id`
- Call `repo_list_pull_requests_by_commits` to find the associated PR in Azure DevOps
- Fetch the resulting PR using `repo_get_pull_request_by_id`
- Use that PR as the source of truth even if it is not present in any local repository

### Step 3: Collect Recent Release PRs

When the user did not explicitly identify a PR or commit, collect recent release PRs from Azure DevOps for the whole project in a single project-scoped query instead of scanning repositories one by one.

- Call `repo_list_pull_requests_by_repo_or_project` with only `project` set (omit `repositoryId`) so the search spans every repository in the project at once.
- Set `status` to `Active` only — this skill exclusively reports on currently active PRs targeting `release/*` branches, so `Completed`, `Abandoned`, and `All` must not be used for this default discovery query. Set `top` to a value large enough to support clustering, defaulting to `50`.
- Page through results with `skip` if more candidates are needed and the first page does not cover the expected release window.
- Filter the returned PRs locally to those whose target branch starts with `refs/heads/release/`, since the tool's `targetRefName` filter matches a single exact branch rather than a wildcard pattern.
- Only fall back to a per-repository `repositoryId` call if the user explicitly restricts the request to one or more named repositories.

For each candidate PR chosen for release analysis, refresh the metadata with `repo_get_pull_request_by_id` before using it in the final report.

### Step 4: Cluster PRs and Pick the Latest Release

Combine all candidate release PRs across repositories.

- Sort by creation date descending
- Split into clusters when the time gap exceeds the cluster gap threshold
- Use the newest cluster as the release in scope

If no release PRs are found, report that clearly and stop.

### Step 5: Detect EF Core / SQL Migration Changes in the Local Diff (Optional)

Only perform this step if the user answered `Yes, check for database migration changes` to the upfront clarifying question. If the user opted out, skip this step entirely, omit the `Database Migration Changes` section from the output, and proceed directly to Step 6.

When opted in, for each PR resolved in Steps 2–4, use the repository already identified for that PR (the PR's own repository reference) to check the local diff between its source and target branches for database migration changes.

- Resolve the local clone path for that repository from the current workspace (for example, a folder under `projects/` or `All Code Repositories/` whose name matches the Azure DevOps repository name). If no local clone can be found, skip diff detection for that PR, leave its `Database Migration Changes` entries empty, and note the gap in the final summary — do not fail the workflow.
- Fetch the latest refs for the PR's `sourceRefName` and `targetRefName` (e.g. `git fetch origin <branch>`) without checking out a branch or modifying the working tree, per the git pre-flight and operational safety rules.
- Compute the changed file list with a non-destructive diff, for example:
  `git diff --name-only origin/<targetRefName>...origin/<sourceRefName>`
- Classify each changed file as a migration change when it matches either:
  - **EF Core migration**: path contains a `Migrations` folder and the file is a `.cs` file (including its paired `.Designer.cs`), or the filename matches the EF Core migration naming pattern `^\d{14}_.*\.cs$`.
  - **SQL migration**: the file has a `.sql` extension, especially under folders such as `SQL Scripts`, `Migrations`, or `db/migrations`.
- Record, per PR: the repository name, the PR ID, and the list of matched migration files with their type (`EF Core Migration` or `SQL Script`).
- If the git commands fail (branch not found locally, shallow clone, no local repository, etc.), treat it as a soft failure: note it and continue with the rest of the workflow.

These results feed the `Database Migration Changes` section in Step 9.

### Step 5b: Detect Skill Documentation Changes in the Local Diff (Optional)

Only perform this step if the user answered `Yes, check for skill documentation changes` to the upfront clarifying question (asked together with the others in "Required Clarification"). If the user opted out, skip this step entirely, omit the `Skill Documentation Changes` section from the output, and proceed directly to Step 6. This answer is independent of the migration-detection answer — either can be on while the other is off.

- Resolve the local clone path for the PR's repository the same way as Step 5 (a folder under `projects/` or `All Code Repositories/` whose name matches the Azure DevOps repository name). If no local clone can be found, skip this check for that PR, leave its `Skill Documentation Changes` entries empty, and note the gap in the final summary — do not fail the workflow.
- Reuse the same fetch and `git diff --name-only origin/<targetRefName>...origin/<sourceRefName>` already computed in Step 5 for that PR when available, instead of re-running it.
- From the changed-file list, keep only files that are:
  - a `.md` file, **and**
  - located under a path segment named exactly `skill` or `skills` (case-insensitive) at any depth — e.g. `docs/skills/tariff-search.md`, `Skills/foo.md`. This is intentionally generic so the same rule works on any repo, not just this workspace.
- A path match alone is not enough to report the file — confirm it is **an actual skill**, not just any markdown that happens to sit in that folder (a `README.md` dropped into `docs/skills/` would fail this check):
  - Read the file's content at the PR's source ref (e.g. `git show origin/<sourceRefName>:<path>`).
  - Confirm it opens with a YAML front matter block (`---` on the first line, a closing `---` later in the file).
  - Confirm that block contains both a `name:` key and a `description:` key. Only count the file if both are present.
  - Capture the `name:` value as the skill's display label for the report.
- Record, per PR: the repository name, the PR ID, and each matched skill file's path and captured `name:` value, tagged as `Added` or `Modified` per the diff.
- If the git or file-read commands fail (branch not found locally, shallow clone, no local repository, etc.), treat it as a soft failure: note it and continue with the rest of the workflow.
- On this workspace, this resolves primarily to markdown under `projects/Spesnet_Lumina.Agent/docs/skills/` — but do not hard-code that path; apply the generic `skill`/`skills` folder rule to every repo so the check stays valid if other repos gain their own skills folder later.

These results feed the `Skill Documentation Changes` section in Step 9.

### Step 6: Collect Linked Work Items

For each in-scope PR:

- Retrieve linked work item references
- Collect unique work item IDs

### Step 7: Fetch Work Item Details

Fetch work items in batches where possible.

Minimum fields to capture:

- `System.Id`
- `System.Title`
- `System.WorkItemType`
- `System.State`
- `System.Parent`
- `System.Tags`
- `System.AssignedTo` — the person who handled the item; use `displayName` from the returned identity object
- Priority field when available

If `System.AssignedTo` is empty, use `Unassigned` instead of leaving the credit blank.

`System.Tags` comes back as one semicolon-separated string (e.g. `Widget; Regression; UAT`). Split it into individual tag labels, trimming whitespace from each. If `System.Tags` is empty, the item has no tags — do not show a tags note for it.

### Step 8: Resolve Parent Hierarchy

Walk parent links upward as required by the chosen scope.

Scope rules:

- `Only bugs`: include only bugs. If a PR links only to tasks, resolve those tasks upward and include parent bugs where possible.
- `All tasks/items`: include directly linked items and every parent item up to Epic.
- `Only tasks`: include only task items unless the user explicitly asks for hierarchy.
- `Only stories`: include only `User Story` and `Product Backlog Item` items.
- `Only features`: include only `Feature` items.

### Step 9: Build Well-Formed Markdown

The final file content must be valid markdown, not plain Teams text.

Use headings, bullet lists, and blank lines consistently, following the required structure in `assets/release-notes-template.md`. That template includes the `Database Migration Changes` section, populated from Step 5 only when the user opted in — omit the section entirely if the user opted out, or if no PR had matching migration files. It also includes the `Skill Documentation Changes` section, populated from Step 5b only when the user separately opted in — omit the section entirely if the user opted out, or if opted in but no PR had matching skill files.

Every work item line (bug, story, task, feature, epic) must show its tags — see "Work Item Tags Display" under Key Rules.

### Step 10: Hyperlink ID Rules

Every PR ID and every work item ID included in the markdown must be a clickable Azure DevOps hyperlink.

Required link format:

- PR: `[2360](https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/2360)`
- Work item: `[11279](https://dev.azure.com/{org}/{project}/_workitems/edit/11279)`

Rules:

- The visible link text for the ID must be the numeric ID itself.
- Do not output bare numeric IDs when a URL is available.
- URL-encode project names when building the link.
- Use the correct repo name for PR links.

### Step 11: Save the File

Write the markdown to:

`documents/release-notes/release-notes-yyyyMMdd-N.md` for `All tasks/items`

or

`documents/release-notes/release-notes-yyyyMMdd-<scope-slug>-N.md` for any other scope.

After saving, continue to Step 12 (do not stop at the file).

### Step 12: Publish to the Project Wiki

Publish the same release notes to the project's Azure DevOps wiki, styled per `assets/release-notes-template.md`.

1. Call `wiki_list_wikis` with the `project` to find the project wiki (`<Project>.wiki`). Capture its `id`/`name`.
2. If no wiki exists, follow the **Wiki Publishing Is Mandatory** rule: pause the wiki step, ask the user to create the project wiki once, and continue after they confirm. Do not auto-provision it.
3. Build the **dated release page** at `/Release Notes/Release <version> - <yyyy-MM-dd>` from the template's wiki format:
       - metadata badge row (release, generated date, scope, branch),
       - per-item sections with priority pills,
       - PR and work item IDs as clickable Azure DevOps links (see Step 10).
       - Honour the same scope and priority-presentation choices used for the file.
4. Create/update it with `wiki_create_or_update_page`.
5. Update the **parent index** `/Release Notes` so the new release appears in the `Releases` list (newest first), linking to the dated page. Use the `gitItemPath` from step 4 to form the correct encoded link.
6. Capture the `remoteUrl` of both pages for the final summary.

If the wiki step cannot complete (no wiki, or the user declines to create one), still treat the file from Step 11 as delivered, and clearly state that the wiki page was not published and why.

## Recommended Section Order

Use this order when sections are present:

1. `Repositories`
2. `Included Pull Requests`
3. `Database Migration Changes` (only when the user opted in to migration-change detection)
4. `Skill Documentation Changes` (only when the user opted in to skill-documentation-change detection)
5. `Delivered Bug Fixes`
6. `Delivered User Stories`
7. `Delivered Tasks`
8. `Features`
9. `Epics`

For `All tasks/items`, include the higher-level sections when available.

## Edge Cases

### Azure DevOps MCP Not Available

Stop immediately and do not continue the workflow.

- Do not use local branches, commits, or local PR assumptions as a fallback
- Tell the user that `microsoft/azure-devops-mcp` must be installed or made available
- Resume only after the MCP is available in the current environment

### PR Exists Only Online

If the PR is not present in any local repository, continue.

- Resolve the repository in Azure DevOps with `repo_get_repo_by_name_or_id`
- Fetch the PR with `repo_get_pull_request_by_id`
- Do not treat the lack of a local branch, local ref, or local merge commit as an error

### Commit Hash Provided Instead of PR ID

Use `repo_list_pull_requests_by_commits` to find the online PR first, then use `repo_get_pull_request_by_id` to fetch the authoritative PR details.

### No Release PRs Found

State clearly that no matching online PRs targeting `release/*` were found in Azure DevOps and suggest checking repository selection, branch naming, or PR status.

### Multiple Releases in One Day

Still use the same date in the file name. The counter distinguishes multiple generated release note files for that day.

### Work Item Linked to Multiple PRs

List the work item once in its section. Do not duplicate it for every PR.

### Missing Parent Items

If a bug, story, or feature has no resolvable parent, still include the item itself.

### No Local Clone Available for Migration Diff Detection

Only relevant when the user opted in to migration-change detection. If a PR's repository has no matching local clone in the workspace, skip diff detection for that PR only.

- Do not fail the workflow.
- Omit that PR from `Database Migration Changes` and note in the final summary that migration detection was skipped for it.

### No Migration Changes Detected

If the user opted in but no in-scope PR contains EF Core or SQL migration file changes, omit the `Database Migration Changes` section entirely rather than including it empty.

### User Opted Out of Migration-Change Detection

If the user answered `No, skip database migration checks`, do not run Step 5, do not run any local git diff commands for migration classification, and omit the `Database Migration Changes` section from the output and from the recommended section order. This is independent of the skill-documentation-detection answer — Step 5b runs or not purely on its own opt-in.

### No Local Clone Available for Skill Documentation Diff

Only relevant when the user opted in to skill-documentation-change detection (Step 5b). If a PR's repository has no matching local clone in the workspace, skip skill-documentation detection for that PR only.

- Do not fail the workflow.
- Omit that PR from `Skill Documentation Changes` and note in the final summary that skill-documentation detection was skipped for it.

### No Skill Documentation Changes Detected

If the user opted in but no in-scope PR contains a markdown file under a `skill`/`skills` folder with valid front matter (`name:` + `description:`), omit the `Skill Documentation Changes` section entirely rather than including it empty.

### User Opted Out of Skill-Documentation Detection

If the user answered `No, skip skill documentation checks`, do not run Step 5b, do not run any local git diff or file-read commands for skill-documentation classification, and omit the `Skill Documentation Changes` section from the output and from the recommended section order. This is independent of the migration-detection answer.

### Markdown File in a Skills Folder Without Front Matter

If a changed `.md` file sits under a `skill`/`skills` folder but does not open with a YAML front matter block containing both `name:` and `description:`, do not report it under `Skill Documentation Changes` — it is not an actual skill definition (e.g. a stray `README.md` or notes file).

### Missing Assigned-To Value

If a work item has no `System.AssignedTo` value, show `Unassigned` in its place instead of omitting the credit.

### Missing Tags Value

If a work item has no `System.Tags` value, omit the tags note/badges for that item entirely. Unlike a missing assignee, there is no placeholder to show — an item with no tags simply shows none.

### Missing Priority Values

If some or all work items do not expose a usable priority value, continue generating the release notes.

- Do not fail the workflow because priority is missing.
- Use `Unspecified Priority` when grouping is enabled.
- Otherwise place items with missing priority after prioritized items within the same section.

## Configuration Defaults

| Setting | Default |
|---|---|
| Release branch pattern | `release/*` |
| Cluster gap threshold | `2 hours` |
| PR status filter | `Active` only (this skill reports exclusively on currently active PRs) |
| PR discovery scope | Project-wide via `repo_list_pull_requests_by_repo_or_project` (repository omitted) |
| Explicit PR lookup source | `Azure DevOps cloud only` |
| Default priority presentation | `Do not divide or order by priority` |
| Max PRs per project query | `50` (paginate with `skip` if more are needed) |
| Output folder | `documents/release-notes` |
| File naming pattern | `release-notes-yyyyMMdd-N.md` or `release-notes-yyyyMMdd-<scope-slug>-N.md` |
| Wiki publishing | Mandatory — publish to the project wiki after saving the file |
| Wiki discovery | `wiki_list_wikis` (project-scoped); project wiki named `<Project>.wiki` |
| Wiki parent page | `/Release Notes` (index, updated every run) |
| Wiki release page pattern | `/Release Notes/Release <version> [<environment>] - <yyyy-MM-dd>` |
| Deployment environment | Always asked (`QA`/`UAT`/`STAGE`/`PROD`); never guessed from branch/version; shown in both titles, the wiki page path, and its own badge |
| Missing wiki behaviour | Do not auto-provision; ask the user to create the project wiki |
| Wiki styling | shields.io badges / priority pills per template (palette above) |
| Default migration-change detection | `Ask the user; do not assume` |
| Migration diff source (when opted in) | Local git diff between the PR's `sourceRefName` and `targetRefName` |
| EF Core migration match | `Migrations` folder + `.cs` file, or filename matching `^\d{14}_.*\.cs$` |
| SQL migration match | `.sql` file extension |
| Default skill-documentation-change detection | `Ask the user; do not assume` |
| Skill-documentation diff source (when opted in) | Local git diff between the PR's `sourceRefName` and `targetRefName`, reused from Step 5's diff when available |
| Skill markdown folder match | Path segment named `skill` or `skills` (case-insensitive) at any depth |
| Skill markdown validity check | YAML front matter containing both `name:` and `description:` |
| Skill markdown location on this workspace | `Spesnet_Lumina.Agent/docs/skills/*.md` (primary; rule still applies to any repo) |
| Work item tags | Always shown (not an opt-in); sourced from `System.Tags`, split on `;`, trimmed; omitted per-item when empty |
| Markdown template | `assets/release-notes-template.md` |

## Troubleshooting

| Issue | Action |
|---|---|
| Azure DevOps MCP unavailable | Stop immediately and instruct the user to install or make `microsoft/azure-devops-mcp` available before retrying |
| No project resolved | Verify the project name or organization context, then retry `repo_list_pull_requests_by_repo_or_project` with only `project` set |
| No PRs found from a commit | Use `repo_list_pull_requests_by_commits`, confirm the commit belongs to the intended repository, then re-fetch the resolved PR with `repo_get_pull_request_by_id` |
| No PRs found for a release | Check that Azure DevOps PRs target `refs/heads/release/*` and match the expected status; increase `top`/`skip` on `repo_list_pull_requests_by_repo_or_project` if the release window is deep in the history |
| Missing work items | Check that PRs have linked work items in Azure DevOps |
| Missing priorities | Continue without failing, and place the item under `Unspecified Priority` or after prioritized items depending on the selected presentation mode |
| Broken links | Verify organization, project, and repository names were derived correctly and project names were URL-encoded |
| File already exists | Increment the daily counter and save a new file instead of overwriting |
| No project wiki found | Do not auto-provision; ask the user to create the project wiki (Overview → Wiki → Create project wiki), then retry the wiki step. Still deliver the file. |
| Wiki badges not rendering for viewers | The org is likely blocking external (shields.io) images; fall back to `.attachments/` badge SVGs committed via the wiki git repo, or native emoji + bold text |
| Wiki child-page link broken from index | Rebuild the link from the `gitItemPath` returned by `wiki_create_or_update_page`; literal `-` in the page name encodes as `%2D` |
| No local clone found for migration diff | Skip diff detection for that PR only, note the gap in the summary, and continue the workflow |
| Local diff commands fail (missing branch, shallow clone) | Treat as a soft failure, note it, and continue without that PR's migration data |
| Unsure whether to check migrations | Ask the clarifying question in "Required Clarification"; never assume opt-in or opt-out |
| Unsure whether to check skill documentation | Ask it together with the other four in "Required Clarification"; never assume opt-in or opt-out, and never ask it separately or later |
| Unsure which deployment environment | Ask the clarifying question in "Required Clarification" as a multiple-choice question; never guess from the branch name or version number |
| No local clone found for skill-documentation diff | Skip Step 5b for that PR only, note the gap in the summary, and continue the workflow |
| Markdown found under a skills folder but no front matter | Do not report it — only files with both `name:` and `description:` in front matter count as an actual skill |
| Skill file renamed or moved out of a skills folder | Compare the diff's before/after path; only classify by the **new** path for `Added`/`Modified` reporting |

## Final Response Contract

After generating the release notes:

1. Save the markdown file first.
2. Confirm the saved file path.
3. Publish to the project wiki, then confirm the wiki page URL(s) — both the dated release page and the updated `Release Notes` index. If the wiki page could not be published (no wiki, or user declined), say so and why.
4. Mention the scope used.
5. Mention the priority presentation mode used.
5a. Mention the deployment environment tagged (`QA`/`UAT`/`STAGE`/`PROD`) and confirm it appears in both page titles and the wiki page path.
6. Mention that PR IDs and work item IDs were written as Azure DevOps hyperlinks.
6a. Mention that each work item shows who handled it (`System.AssignedTo`), and flag if any showed as `Unassigned`.
6b. Mention that each work item shows its ADO tags (`System.Tags`) where it has any.
7. If a PR or commit was explicitly provided, mention that the PR metadata was resolved from Azure DevOps cloud data rather than local repository state.
8. Mention whether migration-change detection was performed (based on the user's answer). If performed, mention whether any EF Core or SQL migration changes were detected, and note any PRs skipped due to a missing local clone.
9. Mention whether skill-documentation-change detection was performed (based on the user's answer). If performed, mention whether any skill markdown files were detected, name them and their captured `name:` value, and note any PRs skipped due to a missing local clone.

If the workflow stops because `microsoft/azure-devops-mcp` is unavailable:

1. State that the work was stopped.
2. State that Azure DevOps cloud data is required for this skill.
3. Instruct the user to install or make `microsoft/azure-devops-mcp` available.
4. Do not generate release notes until that prerequisite is satisfied.

<!-- BEGIN EMBEDDED-INSTRUCTION: markdown-accessibility.instructions.md -->

## Embedded Instruction: markdown-accessibility.instructions.md

---
description: 'Markdown accessibility guidelines based on GitHub''s 5 best practices for inclusive documentation'
applyTo: '**/*.md'
---

# Markdown Accessibility Review Guidelines

When reviewing markdown files, check for the following accessibility issues based on GitHub's [5 tips for making your GitHub profile page accessible](https://github.blog/developer-skills/github/5-tips-for-making-your-github-profile-page-accessible/) and the Smashing Magazine article [Improving The Accessibility Of Your Markdown](https://www.smashingmagazine.com/2021/09/improving-accessibility-of-markdown/). Flag violations and suggest fixes with clear explanations of the accessibility impact.

## 1. Descriptive Links

- Flag generic link text such as "click here," "here," "this," "read more," or "link."
- Link text must make sense when read out of context, because assistive technology can present links as an isolated list.
- Flag multiple links on the same page that share identical text but point to different destinations.
- Bare URLs in prose should be converted to descriptive links.

Bad: `Read my blog post [here](https://example.com)`
Good: `Read my blog post "[Crafting an accessible resume](https://example.com)"`

## 2. Image Alternative (alt) Text

- Flag images with empty alt text (e.g., `![](path/to/image.png)`) unless they are explicitly decorative.
- Flag alt text that is a filename (e.g., `img_1234.jpg`) or generic placeholder (e.g., `screenshot`, `image`).
- Alt text should be succinct and descriptive. Include any text visible in the image.
- Use "screenshot of" where relevant, but do not prefix with "image of" since screen readers announce that automatically.
- For complex images (charts, infographics), suggest summarizing the data in alt text and providing longer descriptions via `<details>` tags or linked content.
- When suggesting alt text improvements, present them as recommendations for the author to review. Alt text requires understanding of visual content and context that only the author can properly assess.

## 3. Heading Hierarchy

- There must be only one H1 (`#`) per document, used as the page title. Note: in projects where H1 is auto-generated from front matter, start content at H2.
- Headings must follow a logical hierarchy and never skip levels (e.g., `##` followed by `####` is a violation).
- Flag bold text (`**text**`) used as a visual substitute for a proper heading.
- Proper heading structure allows assistive technology users to navigate by section and helps sighted users scan content.

## 4. Plain Language

- Flag unnecessarily complex or jargon-heavy language that could be simplified.
- Favor short sentences, common words, and active voice.
- Flag long, dense paragraphs that could be broken into smaller sections or lists.
- When describing UI navigation, write actions as sequential steps in plain language first (e.g., "open Settings, then select Preferences"). Use generic, stable labels rather than icon names or visual descriptions.
- A parenthetical visual reference may follow as supplemental context (e.g., "(gear icon > Preferences)"), but never use visual breadcrumb notation or icon names as the sole way to describe a navigation path.
- When suggesting plain language improvements, present them as recommendations for the author to review. Language decisions require understanding of audience, context, and tone.

## 5. Lists and Emoji Usage

### Lists

- Flag emoji or special characters used as bullet points instead of proper markdown list syntax (`-`, `*`, `+`, or `1.`).
- Flag sequential items in plain text that should be structured as a proper list.
- Proper list markup allows screen readers to announce list context (e.g., "item 1 of 3").

### Emoji

- Flag multiple consecutive emoji, which are disruptive to screen reader users since each emoji name is read aloud in full (e.g., "rocket" "sparkles" "fire").
- Flag emoji used to convey meaning that is not also communicated in text.
- Emoji should be used sparingly and thoughtfully.

## 6. Multimedia

- Provide captions for videos and transcripts for recorded audio.
- Do not auto-play audio and video.
- It's recommended that animated images and other animations are paused on page load.

## 7. Other

- Links: Avoid opening links in a new tab or window.
- Bold and Italics: Screen readers often don't announce bold or italic emphasis, so critical information should not rely on this styling alone.
- Tables: Use tables for data only. Do not use tables for page layout. Avoid nested tables. Avoid complex tables as they are difficult to represent in an accessible format in standard Markdown.

## Review Priority

When multiple issues exist, prioritize in this order:

1. Missing or empty alt text on images
2. Skipped heading levels or heading hierarchy issues
3. Non-descriptive link text
4. Emoji used as bullet points or list markers
5. Plain language improvements
6. Multimedia
7. Other

## Review Tone

- Explain the accessibility impact of each issue, specifying which users are affected (e.g., screen reader users, people with cognitive disabilities, non-native speakers).
- Do not remove personality or voice from the writing. Accessibility and engaging content are not mutually exclusive.
- Keep suggestions actionable and specific.


<!-- END EMBEDDED-INSTRUCTION: markdown-accessibility.instructions.md -->

<!-- BEGIN EMBEDDED-INSTRUCTION: markdown-content-creation.instructions.md -->

## Embedded Instruction: markdown-content-creation.instructions.md

---
description: 'Markdown guidelines and content creation standards for blog posts'
applyTo: '**/*.md'
---

# Markdown Content Rules

The following markdown content rules are enforced in the validators:

1. **Headings**: Use appropriate heading levels (H2, H3, etc.) to structure your content. Do not use an H1 heading, as this will be generated based on the title.
2. **Lists**: Use bullet points or numbered lists for lists. Ensure proper indentation and spacing.
3. **Code Blocks**: Use fenced code blocks for code snippets. Specify the language for syntax highlighting.
4. **Links**: Use proper markdown syntax for links. Ensure that links are valid and accessible.
5. **Images**: Use proper markdown syntax for images. Include alt text for accessibility.
6. **Tables**: Use markdown tables for tabular data. Ensure proper formatting and alignment.
7. **Line Length**: Limit line length to 400 characters for readability.
8. **Whitespace**: Use appropriate whitespace to separate sections and improve readability.
9. **Front Matter**: Include YAML front matter at the beginning of the file with required metadata fields.

## Formatting and Structure

Follow these guidelines for formatting and structuring your markdown content:

- **Headings**: Use `##` for H2 and `###` for H3. Ensure that headings are used in a hierarchical manner. Recommend restructuring if content includes H4, and more strongly recommend for H5.
- **Lists**: Use `-` for bullet points and `1.` for numbered lists. Indent nested lists with two spaces.
- **Code Blocks**: Use triple backticks (```) to create fenced code blocks. Specify the language after the opening backticks for syntax highlighting (e.g., `csharp`).
- **Links**: Use `[link text](URL)` for links. Ensure that the link text is descriptive and the URL is valid.
- **Images**: Use `![alt text](image URL)` for images. Include a brief description of the image in the alt text.
- **Tables**: Use `|` to create tables. Ensure that columns are properly aligned and headers are included.
- **Line Length**: Break lines at 80 characters to improve readability. Use soft line breaks for long paragraphs.
- **Whitespace**: Use blank lines to separate sections and improve readability. Avoid excessive whitespace.

## Validation Checklist

Ensure compliance with the following validation requirements:

### Front Matter

- [ ] `post_title`: The title of the post.
- [ ] `author1`: The primary author of the post.
- [ ] `post_slug`: The URL slug for the post.
- [ ] `microsoft_alias`: The Microsoft alias of the author.
- [ ] `featured_image`: The URL of the featured image.
- [ ] `categories`: The categories for the post. These categories must be from the list in /categories.txt.
- [ ] `tags`: The tags for the post.
- [ ] `ai_note`: Indicate if AI was used in the creation of the post.
- [ ] `summary`: A brief summary of the post. Recommend a summary based on the content when possible.
- [ ] `post_date`: The publication date of the post.

### Content and Formatting

- [ ] Content follows the markdown content rules specified above.
- [ ] Content is properly formatted and structured according to the guidelines.
- [ ] Validation tools have been run to check for compliance with the rules and guidelines.


<!-- END EMBEDDED-INSTRUCTION: markdown-content-creation.instructions.md -->

<!-- BEGIN EMBEDDED-INSTRUCTION: markdown.instructions.md -->

## Embedded Instruction: markdown.instructions.md

---
description: 'Markdown formatting aligned to the CommonMark specification (0.31.2)'
applyTo: '**/*.md'
---

# CommonMark Markdown

Apply these rules per the [CommonMark spec 0.31.2](https://spec.commonmark.org/0.31.2/) when writing or reviewing `.md` files. CommonMark spec for reference only. Do not download CommonMark spec.

## Preliminaries

- A line ends at a newline (`U+000A`), carriage return (`U+000D`), or end of file. A blank line contains only spaces or tabs.
- Tabs behave as 4-space tab stops for block structure but are not expanded in content.
- Replace `U+0000` with the replacement character `U+FFFD`.
- **Backslash escapes**: `\` before any ASCII punctuation character renders the literal character. Not recognized in code spans, code blocks, or autolinks.
- **Entity and numeric character references**: `&amp;`, `&#123;`, `&#x7B;` — valid HTML5 entities only. Not recognized in code spans or code blocks. Cannot replace structural characters.

## Leaf Blocks

- **Thematic breaks**: 3+ matching `-`, `_`, or `*` characters on a line with 0–3 spaces indent. Only spaces or tabs allowed on the line otherwise. Can interrupt a paragraph.
- **ATX headings**: 1–6 `#` characters followed by a space or end of line. Optional closing `#` sequence (preceded by a space). 0–3 spaces indent allowed.
- **Setext headings**: Text underlined with `=` (level 1) or `-` (level 2). Cannot interrupt a paragraph — blank line required after a preceding paragraph.
- **Indented code blocks**: Lines indented 4+ spaces. Cannot interrupt a paragraph. Content is literal text, not parsed as Markdown.
- **Fenced code blocks**: Open with 3+ backticks or tildes (do not mix). Closing fence must use same character with at least the same count. Info string after backtick fence cannot contain backticks. Specify language identifier after the opening fence. Content is literal text.
- **HTML blocks**: Seven types defined by start/end tag conditions. Types 1–5 end at their matching end pattern. Type 6 ends at a blank line. Type 7 cannot interrupt a paragraph and ends at a blank line.
- **Link reference definitions**: `[label]: destination "title"`. Case-insensitive label matching (Unicode case fold). First definition wins for duplicate labels. Cannot interrupt a paragraph.
- **Paragraphs**: Consecutive non-blank lines not interpretable as other block constructs. Leading spaces up to 3 are stripped.
- **Blank lines**: Ignored between blocks; determine whether a list is tight or loose.

## Container Blocks

- **Block quotes**: Lines prefixed with `>` (optionally followed by a space). Lazy continuation allowed for paragraph text only. A blank line separates consecutive block quotes.
- **List items**: Bullet markers (`-`, `+`, `*`) or ordered markers (1–9 digits + `.` or `)`). Content column determined by marker width + spaces to first non-whitespace (1–4 spaces after marker). Sublists must be indented to the content column. An ordered list interrupting a paragraph must start with `1`.
- **Lists**: Sequence of same-type list items. Changing bullet character or ordered delimiter starts a new list. A list is loose if any item is separated by a blank line.

## Inlines

- **Code spans**: Backtick-delimited inline code. Line endings convert to spaces. Leading and trailing space stripped when both present (unless content is all spaces). Backslash escapes are literal inside code spans.
- **Emphasis and strong emphasis**: `*`/`_` for `<em>`, `**`/`__` for `<strong>`. `_` is not allowed for intraword emphasis. Left-flanking / right-flanking delimiter run rules apply. Delimiter run length sum must not be a multiple of 3 when one delimiter can both open and close (unless both lengths are multiples of 3).
- **Links**: Inline `[text](url "title")` or reference `[text][label]` / `[text][]` / `[text]`. Link text may contain inlines but not other links. Destination in `<…>` allows spaces; without angle brackets, balanced parentheses allowed. No whitespace between link text and `(` or `[`.
- **Images**: `![alt](src "title")` — same syntax as links prefixed with `!`. Alt text is the plain-string content of the description.
- **Autolinks**: `<URI>` or `<email>` in angle brackets. Scheme must be 2–32 characters starting with an ASCII letter. Bare URLs are not auto-linked in CommonMark (requires angle brackets).
- **Raw HTML**: Open/close tags, comments (`<!--` … `-->`), processing instructions (`<?` … `?>`), declarations (`<!` … `>`), CDATA (`<![CDATA[` … `]]>`) are passed through as literal HTML.
- **Hard line breaks**: Two+ trailing spaces or `\` before a line ending. Not recognized in code spans or HTML tags. Does not work at end of a block.
- **Soft line breaks**: A line ending not preceded by two+ spaces or `\`. Rendered as a space in browsers.

## Validation Checklist

- [ ] ATX headings use 1–6 `#` followed by a space.
- [ ] Fenced code blocks specify a language identifier and use matching fence characters and counts.
- [ ] Backtick fence info strings do not contain backtick characters.
- [ ] Indented code blocks are preceded by a blank line (they cannot interrupt a paragraph).
- [ ] Emphasis uses `*` for intraword; `_` only at word boundaries.
- [ ] Links use `[text](url)` or reference syntax with no whitespace before `(` or `[`.
- [ ] Images include non-empty alt text.
- [ ] Autolinks use angle brackets (`<URL>`); bare URLs are not CommonMark autolinks.
- [ ] No unbalanced parentheses in bare link destinations (use `<…>` or escape).
- [ ] HTML block type 7 (custom/inline-level tags) is preceded by a blank line when following a paragraph.


<!-- END EMBEDDED-INSTRUCTION: markdown.instructions.md -->
