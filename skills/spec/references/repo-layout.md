# Repo layout

> Part of the `sdd:spec` flow (`../SKILL.md`).

The folder tree mirrors the ADO hierarchy, so the join is visible without opening a file.

```
{specRoot}/
  4468-FEAT-checkout-rewrite/       # Feature
    requirements.md                 # written by spec.py sync, never by hand
    design.md
    tasks.md
    4471-US-guest-checkout/         # User Story
      requirements.md
      questions.md                  # gaps and open questions: `- [ ]` open, `- [x]` answered
      impact.json, impact.md        # spec.py impact / sdd:impact
      design.md
      tasks.md
  .index/spec.db                    # the spec index: rev, hash, links, terms per item
```

Folder names are `<ado-id>-<TYPE>-<slug>`, TYPE being EPIC, FEAT, US, TS, CR, PBI, BUG or ISSUE.
**The id is authoritative and the slug is cosmetic**, so a retitle in ADO never orphans a folder,
a retype only renames it, and a story joining a feature months later is just a new
child folder. Resolve a spec folder by glob — `{specRoot}/**/<id>-*/` — never by remembered path.
The sync moves a folder when its item is reparented, and everything in it moves along.

Code lives in a separate folder per work item, created by `env.py new`:

```
<workspace>\.claude\worktrees\4471-guest-checkout\
  workitem.json  CLAUDE.md
  src\{Repo}\                      # one git worktree per affected repo
  graph\                           # graphify code graph of src\
```

Branches carry the same id in their last segment:
`dev/{developer}/{version}/{type}/{ado-id}-{slug}`. Full rules in `references/branching.md`.
