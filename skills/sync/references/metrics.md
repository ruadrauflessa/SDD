# metrics.json — every work item's decision facts, and what the last sync changed

`{specRoot}/.index/metrics.json` is written by every `spec.py sync`, from the index alone: no ADO
call of its own, no model, no tokens. `spec.py metrics` rebuilds it without a sync and keeps the
last sync's `changes`. Read it instead of asking ADO when you need to weigh items against each
other — `/sdd next`, a status question, "what changed?".

It is a snapshot: as current as the last sync of each item. Items outside every synced scope are
not in it.

## `changes` — the delta of the last sync that changed something

One entry per item that sync found changed. A sync that finds nothing new (`/sdd next` runs one
every time) keeps the delta before it: `changesAt` says when that delta was found, `sync.at` when
the last sync ran.

| Field | Meaning |
| --- | --- |
| `kind` | `new` (first synced), `material` (the requirement changed), `incidental` (a tracked field changed, the requirement did not), `missing` (ADO no longer returns it) |
| `fields` | For `material`: which requirement parts changed — Title, Description, AcceptanceCriteria, ReproSteps, WorkItemType, relations |
| `diff` | `{column: [was, now]}` for the tracked columns: title, state, board, assigned, priority, severity, effort, rank, target, blocked, tags, iteration, area, parent |
| `affects` | For `new` and `material`: `[{id, why}]` — items linked within two hops, and the five strongest shared-term matches. The candidates `sdd:impact` would judge; nothing is judged here |

An incidental rev bump that touched no tracked column (a comment, an untracked field) is left out.

## `items` — one entry per synced work item, by id

| Field | Meaning |
| --- | --- |
| `type`, `title`, `state`, `board`, `assigned`, `assigned_email` | As in ADO at the last sync; `board` is `Custom.BoardColumnTitle` |
| `tags`, `versions` | All tags; the ones that look like a team version (`1.1.0`) |
| `priority`, `severity` | 1 (highest) … 4, or null |
| `effort`, `complexity` | The ADO effort (story points, effort, size); the same on a 1–5 scale, null without effort |
| `rank`, `target`, `iteration`, `area`, `created`, `changed` | Backlog order, target date, and the rest as in ADO |
| `parent`, `ancestors` | The parent id; the chain up to the epic: `[{id, type, title}]`, nearest first |
| `done`, `inProgress`, `removed`, `missing` | Done = a `doneStates` state or Removed. In progress = `next.inProgress` (Active, or Dev In Progress) |
| `children` | Everything under it: `total`, `open`, `done`, `inProgress`, `bugsOpen` (open bugs and issues) |
| `blockers` | `[{id, kind, state}]` — evidence only: a predecessor link, or an item named in its text, that is not done. Whether it really blocks is a judgement (`/sdd next` records one) |
| `blocking` | The open items that list this one as a blocker |
| `links` | How many links go `out` of it and come `in` to it |
| `lastChange` | The last change any sync saw: `{at, kind, fields, diff}` — kept from sync to sync |
