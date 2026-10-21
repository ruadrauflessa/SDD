---
type: regex
target:
  source: file
  path: .claude/worktrees/501-export-drops-the-cents-from-totals/src/Exporter/export.py
match: contains
---

int\(amount\)
