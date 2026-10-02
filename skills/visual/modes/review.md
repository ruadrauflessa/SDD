# Mode: review — present a code / PR review

Used by: ado-pr-review Step 6 (alongside its markdown summary), the built-in `/code-review`, and
any "review this" request. Default renderer: quick for a short review, full when there is an
architecture impact worth drawing.

Sections — use only those with something the user needs:

1. **Verdict strip** — Approve / Approve with comments / Request changes, plus counts per severity
   (first viewport). PR link, source → target branch, linked work items.
2. **Findings** — one card per finding, tone by severity (critical = `danger`, major = `warning`,
   minor = `info`, suggestion = `neutral`); each with file:line, what is wrong, the fix.
3. **File map** — changed files with status, findings count per file.
4. **Tests** — coverage of the change: what is tested, what is not.
5. **Complexity / security notes** — only when there is something to say.
6. **Not reviewed** — files or areas skipped and why.

The page is for the user. Posting comments or votes to ADO still needs the user's explicit yes.
