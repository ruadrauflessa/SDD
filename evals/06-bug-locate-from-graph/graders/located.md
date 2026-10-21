---
type: llm
weight: 2
focus:
  source: file
  path: .claude/worktrees/501-export-drops-the-cents-from-totals/workitem.json
---

Pass if the Phase 4 record (its note, or the latest progress note) places the defect in fmt_total in
export.py, where the amount is cast with int(). Fail if Phase 4 is not recorded, or it names another
place.
