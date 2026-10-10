# Mode: bug — explain a defect, its root cause and the fix

Used at: sdd:bug Phase 3 (Gate 0, when the verdict is not a plain "yes, a bug") and the Phase 6
approval gate; ado-bug-fix Phase 5; any "why is this broken?" explanation. Default renderer: quick
(full when the page needs layout the schema cannot express).

The page mirrors the Phase 6 summary, but drawn. Use only the sections with something the user needs:

1. **Verdict strip** (first viewport): ADO link + title, Gate 0 verdict, reproduced or inferred,
   one-sentence root cause, one-sentence fix.
2. **What the user saw** — the symptom in the reporter's words.
3. **The broken path** — a **sequence diagram** from the trigger to the symptom; mark the faulty
   message (`danger` tone / red band) with `path/File.cs:123`.
4. **Evidence** — failing assertion, log line, query result, blame; each with its source.
5. **Ruled out** — alternatives and why not.
6. **Blast radius** — repos/services and other call sites with the same flaw.
7. **The fix** — before/after of the faulty step; what deliberately stays unchanged.
8. **Regression test** — what it asserts, where, and that it fails today.
9. **Out of scope** — related defects found, each needing its own work item.

Quick-spec mapping: verdict → `summary` + `callouts`; broken path → `flow`; evidence → `evidence`;
ruled out / blast radius → `cards` or `table`; fix → `files` (status `planned`) + `cards`
(before = `danger`, after = `positive`); test → `steps`.
