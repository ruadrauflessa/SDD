# ADO sync: mirror schema, classification, drift, writes

## Mirror schema

`spec.py sync` writes every `requirements.md`; the agent never does. Its frontmatter records what
the mirror was built from:

```yaml
---
id: 4471
type: User Story
project: Payments
state: Active
parent: 4468
fields_hash: 8f2c11ae        # material fields + relations, see below
synced_by: sdd-spec-sync@1
links:
  - Parent 4468
  - Related 4502
---
```

The body follows: title, a link to the item in ADO, a field table (type, state, project, area,
iteration, tags, assignee, and the planning fields below where the item has them), then `## Description`, `## Acceptance criteria` and `## Repro steps`
converted from ADO's HTML to Markdown by pandoc, and `## Links`. Sections ADO leaves empty are
omitted. `design.md`, `tasks.md`, `questions.md` and `impact.*` in the same folder are never
touched by the sync and move with the folder when the item is reparented.

- **Material fields** are `System.WorkItemType`, `System.Title`, `System.Description`,
  `Microsoft.VSTS.Common.AcceptanceCriteria`, `Microsoft.VSTS.TCM.ReproSteps`, plus the item's
  relations. `fields_hash` is the first 8 hex characters of the SHA-256 over them, normalised
  (CRLF to LF, trailing whitespace stripped). The script is the only implementation — never
  compute one by hand.
- **The index, `{specRoot}/.index/spec.db`, holds `rev` and the hash per item**, plus a hash per
  material field, links and key terms. Drift is decided there, not by reading frontmatter.
- `System.Rev` increments on *every* change, including comments and bulk edits. A rev bump with an
  equal hash is **incidental**; a changed hash is **material**, and the sync names the fields that
  changed.
- A sync of one item also pulls everything under it, its parents and one hop of links out of that
  tree, so a child's own sync sees a material parent change — no PR enumeration needed.
- `synced_by` records the extraction version, so a change in the script can be told apart from a
  change in the work item.

## Field classification

A rev bump alone must never block; within two sprints that gate would be ignored.

| ADO field | Class | On change |
| --- | --- | --- |
| `System.Title` | Material | Block, show diff |
| `System.Description` | Material | Block, show diff |
| `Microsoft.VSTS.Common.AcceptanceCriteria` | Material | Block, show diff |
| `System.WorkItemType` | Material | Block |
| Relations (Parent, Child, Related) | Material | Block, re-run link walk |
| `System.State` | Incidental | Refresh the index, the field table and the frontmatter `state:` |
| `System.AssignedTo` | Incidental | Refresh the index (`assigned`, `assigned_email`) and the field table |
| `System.IterationPath`, `System.AreaPath`, `System.Tags` | Incidental | Refresh the index and the field table |
| Planning fields (see below) | Incidental | Refresh the index and the field table |
| `System.History` (comments) | Incidental | Ignore — not mirrored |

### Planning fields

What someone weighs to pick the next item. Each is a column in the index (`spec.py query show`
prints it) and a row in the field table when the item has it. Process templates name some fields
differently, so each column takes the first of its fields the item carries (`PLANNING` in
`spec.py`):

| Index column | ADO field(s) |
| --- | --- |
| `board` | `Custom.BoardColumnTitle` — the team's workflow column, not the board-managed `System.BoardColumn` |
| `priority` | `Microsoft.VSTS.Common.Priority` |
| `severity` | `Microsoft.VSTS.Common.Severity` |
| `rank` | `Microsoft.VSTS.Common.StackRank`, else `Microsoft.VSTS.Common.BacklogPriority` (backlog order; index only) |
| `effort` | `Microsoft.VSTS.Scheduling.StoryPoints`, `.Effort`, `.Size`, else `.OriginalEstimate` |
| `target` | `Microsoft.VSTS.Scheduling.TargetDate`, else `.DueDate` |
| `blocked` | `Microsoft.VSTS.CMMI.Blocked` |
| `created` | `System.CreatedDate` (index only) |

They are snapshots, as of the last sync. An index built before these columns existed gets them on
its next sync.

Only material fields feed `fields_hash`. An incidental change bumps `rev`, leaves the hash equal,
and the sync records the new rev and reports it as `incidental` without a human needing to act.

Two cases bypass the classification:

- **Deleted, moved to a project you cannot read, or no access** — the sync reports it as
  `MISSING`. The spec now references nothing; a human decides.
- **Type changed** (a Task promoted to a User Story) — blocks even though no prose changed,
  because the hierarchy assumptions are invalidated.

Diffs come from the work item revisions API, which returns full history per item. Showing what
actually changed between rev 9 and rev 12 is the difference between a gate people act on and a
gate people click through.

## Drift detection

A pull check with no infrastructure: `spec.py sync` re-reads the items, compares rev and hash with
the index, and reports each one as `new`, `material` (with the fields that changed),
`incidental`, `unchanged` or `missing`. No subscriptions, no inbound path to a developer machine.

```
spec.py sync --id 4471
  → rev unchanged?          → unchanged
  → rev bumped, hash equal? → incidental, index updated, pass
  → hash differs?           → MATERIAL 4471 User Story — <title>: Description, relations
```

Two run points, same script:

1. **Sync check** (`spec.py sync`, no id) — advisory. Catches drift before effort is wasted.
2. **Verify** (`spec.py sync --id <id>`) — a `MATERIAL` line for the item or its parent blocks
   the PR until reviewed. A CI gate on the PR is not provided by the shared scripts yet.

### Cascade to child specs

A material change to a feature propagates down to the story specs beneath it, scoped by blast
radius rather than by relevance:

- **In-flight children block.** A child with an open `dev/*` PR is blocked until it is reviewed
  against the new parent text. Once that PR merges to `team/*` the child is no longer in flight —
  a requirements change after that point is new work, not a spec to regenerate.
- **Closed children refresh silently.** The change is history to them.
- **Unstarted children are not blocked.** They will be generated from the current text anyway.

A feature with twelve stories and three in flight blocks three pull requests. Blocking twelve is
the version people learn to bypass.

Relevance scoping — blocking only children whose prose references the changed section — is
deliberately not attempted. Blast radius is mechanical; relevance is not, and a gate whose
behaviour nobody can predict gets switched off.

To be actionable the block shows three things: the parent field diff, the sections of the child
`design.md` that depend on it, and any `tasks.md` items **already marked done**. Work already
built against the old intent is the reason this blocks rather than warns.

The cascade is asymmetric: a child changing does not block its parent. A feature spec is an
aggregate; it gets a warning and nothing more.

## Write path

**Reads of a work item go through the sync, not an MCP server.** `spec.py sync --id <id>` refreshes
the local copy; `spec.py query show --id <id>` then gives `rev`, state, tags and assignee, and
`requirements.md` gives the text. Never call `wit_work_item action=get` or `action=get_batch` for
an item the sync covers. The one MCP read left is `action=get_type` (a type's field list).

**Writes are stricter.** Every write asserts the revision it expects, via a JSON
Patch test operation:

```json
[
  { "op": "test",    "path": "/rev", "value": 42 },
  { "op": "replace", "path": "/fields/System.State", "value": "Active" }
]
```

If another writer moved the item first, the whole patch is rejected atomically (HTTP 412) rather
than silently overwriting their edit. The same test works on the batch endpoint, guarding each
item independently.

Stock ADO MCP servers do not do this — Microsoft's `azure-devops-mcp` has an open request for an
`expectedRev` parameter that is not planned. So the workflow writes go through `scripts/adowrite.py`,
behind `spec.py claim`, `handover`, `sprint` and `comment`. It always prepends the rev test. On a
412 it reads the item again, decides again from what is there now, and retries up to three times.
A conflict that survives that, or a state that says stop (someone else's item, an Issue without
its root cause, a `#<id>` mention), exits 3 for a human to decide: two writers disagreeing is not a
merge problem. `--dry-run` prints the patch and writes nothing.

Agent writes stay narrow — assignment, board column, state, tags, comments, commit and PR links,
and tech story creation. The agent never rewrites descriptions or acceptance criteria; those are
ADO-owned and a human authored them. A create has no prior revision, so tech story creation needs
no rev test.

## Workflow fields — claim and close-out

Two points in the workflow write fields on the work item itself, outside the mirror. Both use the
rev-tested patch above.

| Display name | Reference name | Type | Notes |
| --- | --- | --- | --- |
| Assigned To | `System.AssignedTo` | identity | Write the email; resolve ambiguous names with `core_get_identity_ids`. |
| Board Column Title | `Custom.BoardColumnTitle` | picklist | The team's real workflow position. **Not the same field as `System.BoardColumn`** — that's a standard, board-managed field that looks similar but is unrelated; it mirrors board state and is never written by this skill. Confirmed on this project's process; write `Custom.BoardColumnTitle`. |
| Status | `System.State` | state | Always written in the same call as `Custom.BoardColumnTitle` — the two move together, never one without the other. |
| Tags | `System.Tags` | string | A PATCH replaces the whole field. Read the current value first (`spec.py query show --id <id>`, after a sync), append the new tag, write the full semicolon-separated string back — never a bare `add` with just the new tag. |

**Specify, right after the sync and before the requirement is read** (`spec.py claim`): `Custom.BoardColumnTitle` and `System.State` move
together — `Dev In Progress` pairs with `Active`, the same pairing Verify writes at close-out
(`Dev Completed` with `Resolved`). Setting one without the other leaves the two signals
disagreeing about whether work has actually started.

```json
[
  { "op": "test",    "path": "/rev", "value": 42 },
  { "op": "add",     "path": "/fields/System.AssignedTo", "value": "heinriche@evolvemed.co.za" },
  { "op": "add",     "path": "/fields/Custom.BoardColumnTitle", "value": "Dev In Progress" },
  { "op": "add",     "path": "/fields/System.State", "value": "Active" }
]
```

**Review, once the PR is approved** (`spec.py handover --tag <version>`): move `Custom.BoardColumnTitle` to `Dev Completed`,
`System.State` to `Resolved`, and add a tag equal to the version segment already carried in the
branch name (`references/branching.md`) — the `team/{version}` the branch was cut from, e.g. `2.4`.
That segment is the one fact the branch, the worktree and the work item all need to agree on, so
the tag is copied from the branch name rather than re-derived.

```json
[
  { "op": "test",    "path": "/rev", "value": 47 },
  { "op": "add",     "path": "/fields/Custom.BoardColumnTitle", "value": "Dev Completed" },
  { "op": "add",     "path": "/fields/System.State", "value": "Resolved" },
  { "op": "add",     "path": "/fields/System.Tags", "value": "<existing tags>; 2.4" }
]
```

## Implementation plan write-back

Once `design.md` and `tasks.md` both exist (end of Decompose), write a condensed implementation
plan back to the work item — but **only work item types that actually carry an Implementation
Plan field get one.** Never assume the field exists, and never guess its reference name; both
vary by work item type and by project, unlike the fixed fields above.

1. **Check once per type.** `wit_work_item action=get_type project=<project>
   type=<System.WorkItemType>` returns that type's field list. Look for a field whose *display
   name* reads as an implementation plan (read what the project actually calls it — don't assume
   the exact string) and record its reference name.
2. **No such field on this type?** Skip the write. This is the normal case, not an error — most
   types won't carry it. Don't re-check every run: cache the answer, per type, in the workspace
   facts block (see `references/workspace-facts.md`) so this lookup happens once per type,
   not once per work item.
3. **Field exists?** Write it with the rev-tested patch, `format=Html`:

```json
[
  { "op": "test", "path": "/rev", "value": 51 },
  { "op": "add",  "path": "/fields/<resolved reference name>", "value": "<div>…</div>" }
]
```

**Content is condensed, never copied.** A person reading the board sees this without opening the
repo:

- The approach, 2–3 sentences, from `design.md`.
- The affected components / anchors, one line each.
- The ordered task list from `tasks.md`, titles only — not the per-task verification detail that
  lives in the repo file.

Don't paste `design.md` verbatim into it; the field is a summary, the repo file stays the source
of truth. Because a PATCH replaces the field outright, re-write it whenever `design.md` or
`tasks.md` changes materially before Implement starts — a plan describing a design that has since
moved on is worse than an empty field.

## Moving the work item to the current sprint

Done at Verify, when the PR is opened — `System.IterationPath`, another Incidental field:
`spec.py sprint --id <id> [--id ...] [--team "<team>"]`. It takes the team's current iteration
(default team `<project> Team`). For a team with no iteration schedule it takes the iteration
whose dates hold today, the shortest such range. No iteration holds today: exit 3, ask the user.

An item still sitting in an old sprint — or with no iteration ever set — reads as work nobody is
doing, even once the PR exists.

## Cross-spec interaction

The mirror cannot catch a work item that isn't linked to this one. `spec.py impact --id <id>`
covers all three tiers in one call and writes the candidates to `impact.json`; the
`sdd:impact` skill judges them into `impact.md` with gap questions.

| Tier | Mechanism | Precision | Blocks |
| --- | --- | --- | --- |
| 1 | Link walk over the index (`spec.py impact`, links, up to `--hops`) | High | Yes |
| 2 | File and symbol overlap: design anchors vs the candidates `spec.py impact` lists | High | Yes |
| 3 | Shared key terms and similar meaning (`spec.py impact`, FTS and embeddings) | Low | No |

Tier 1 is near-free — the links are already in the index — and its coverage is exactly as good as
the team's linking hygiene. Tier 2 needs no ADO access at all: the design anchors already name
files, symbols, routes and tables, and comparing them across open specs is pure repo work. Tier 3
returns noise and must never gate; `sdd:impact` collapses its hits into the few that matter.

Log every flagged interaction and whether it turned out to be real. If precision on a blocking
tier falls below roughly half, tighten the anchors rather than adding signals.
