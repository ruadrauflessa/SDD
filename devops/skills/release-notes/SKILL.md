---
name: release-notes
description: >-
  Write release notes from the active Azure DevOps PRs into release/* branches (or a named PR or commit):
  a markdown file under documents/release-notes and a styled page in the project wiki, tagged with its
  deployment environment (QA, UAT, STAGE, PROD). Use for "generate release notes", "changelog", "what
  shipped", "summarize the release", "deployment notes", "release notes for PR 2360".
---

# Release notes

`devops.py` collects the PRs and work items, finds migrations and skill files, renders the file and the
wiki page from the template, and publishes after the user's Yes. You ask the questions, write one line
per bug fix, and relay. Below, `devops.py` means `python "${CLAUDE_PLUGIN_ROOT}/scripts/devops.py"`.

## 1. Ask once, all together

Ask every question the request has not answered in **one** AskUserQuestion call (up to four per call:
if all five are open, ask the first four, then the last one at once). Never ask one again later.

| Question | Options | Flag |
| --- | --- | --- |
| Scope? | Only bugs · All tasks/items · Only tasks · Only stories · Only features | `--scope bugs\|all\|tasks\|stories\|features` |
| Priority presentation? | None · Order only · Sections only · Sections and order | `--priority none\|order\|sections\|both` |
| Deployment environment? | QA · UAT · STAGE · PROD (never guess it from the branch) | `--env QA\|UAT\|STAGE\|PROD` |
| Check the diffs for EF Core / SQL migrations? | Yes · No | `--migrations` |
| Check the diffs for skill files (`skill`/`skills` folders)? | Yes · No (say no if the repos have none) | `--skills` |

Scope has five options: offer the four most likely and let "Other" carry the fifth.

## 2. Collect

`devops.py notes collect` lists the active PRs into `release/*` project-wide in one call, keeps the
newest group (a gap of 2 hours starts a new one), and reads the linked work items up to Epic. A PR or
commit the user named: `--pr <id>` (repeat it) or `--commit <sha> --repo <name>`. `--project`/`--org`
when the workspace repos do not tell. It prints a run id. No PR found: say so and stop.

No `az` login: read `${CLAUDE_PLUGIN_ROOT}/references/mcp-fallback.md`, section *release-notes*. Setup in doubt:
`devops.py doctor` names what is missing and the fix.

## 3. Detect (only what the user opted into)

`devops.py notes detect --run <id> [--migrations] [--skills]`. A skill file counts only with front
matter holding `name:` and `description:`. A repo with no local clone is a gap, reported, not a stop.

## 4. Render

`devops.py notes render --run <id> --scope <s> --priority <p> --env <e>`. It writes the file
(`documents/release-notes/release-notes-yyyyMMdd[-scope]-N.md`, never over an older one) and the wiki
page, and prints the bugs that lack a one-line fix summary. Write those lines to a JSON file
(`{"80459": "Closing the disclaimer no longer collapses the panel."}`): the resolved behaviour, one
sentence, plain English (`${CLAUDE_PLUGIN_ROOT}/references/writing-style.md`). Render again with
`--run <id> --texts <file>` (it keeps the run's scope, priority and environment); it rewrites the same file. A BLOCKED line (a secret, a placeholder, a local path)
means fix the data, not the check.

## 5. Approve and publish

Tell the user the file path. Ask with AskUserQuestion using the question render printed, word for word,
options "Yes, go ahead" / "No". Then `devops.py notes publish --run <id>`: it writes the dated page
`/Release Notes/Release <v> [<env>] - <date>` and puts it first in the `/Release Notes` index. A
missing project wiki: the user creates it (Overview > Wiki > Create project wiki); the file is
delivered either way. Never write the page by hand: the guard refuses a page that differs from the
approved one.

## 6. Report

The file path; both wiki URLs (or why not published); the scope, priority mode and environment; that
PR and work item ids are links; any `Unassigned` items; migration and skill files found (or that the
check was skipped, and any gaps); for a named PR or commit, that it came from ADO, not local git.

Badges not showing on the wiki: the org blocks external images. Offer the plain file instead.
