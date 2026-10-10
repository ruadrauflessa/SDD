---
type: llm
weight: 2
focus:
  source: file
  path: .claude/worktrees/501-export-drops-the-cents-from-totals/src/Exporter/export.py
---

Pass if fmt_total now shows the cents with two decimals (12.40 becomes "12.40", 12 becomes "12.00")
and still returns text. Fail if it still truncates the amount with int().
