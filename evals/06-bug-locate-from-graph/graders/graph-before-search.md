---
type: regex
target:
  source: file
  path: .claude/worktrees/501-export-drops-the-cents-from-totals/graph-use.jsonl
match: contains
---

^\{[^\n]*"kind": "graph"
