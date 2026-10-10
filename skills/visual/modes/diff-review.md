# Mode: diff-review — explain a code change

Args: branch, commit, range, PR, or `HEAD`; none = working tree vs the base branch (`team/{version}`
in an sdd worktree, else `main`/`master`). Default renderer: full (`--quick` allowed).

Used for: sdd:bug Phase 11 / ado-bug-fix Phase 9a (what the fix changed, before manual testing), sdd:spec
Verify ("Ready to PR"), and any "what did this change?" request.

## Data gathering before HTML

Run the git commands for: diff stats, name-status, changed files, line counts, public
API/type/function changes, added/removed files, docs/changelog changes, tests touched,
dependency/config changes. Read changed files in full plus the code paths needed to judge
behaviour. Read commit messages for committed work. If this session made the change, use the
design/tasks/summary for rationale.

## Source verification

Know and cite: exact changed files and line counts; every function/type/module named; before/after
behaviour for important changes; likely coupling and test impact. Use file paths, command output or
file:line. Never invent rationale or code paths.

## Page sections — use only those with something the user needs

1. Executive summary: intuition, problem solved, factual scope.
2. File map: full tree, colour-coded new/modified/deleted; `<details>` if long.
3. Architecture impact: static SVG diagram when relationships matter.
4. Before/after behaviour: side by side.
5. Risk review: correctness, tests, API compatibility, security/privacy, performance, maintainability.
6. Coupling map: dependencies, hidden coupling, migration/release concerns.
7. Recommendation: ready or not, blockers, follow-ups. For a fix at Phase 11 add **"How to test it
   by hand"** — the screen or call, the steps, what you should see.

Diff colours: red before, green after, amber risk, blue context. Responsive nav.

**Verification results** (red run, green run, revert-check, repeat runs, full suite, live checks)
are `cards` in a section with `"layout": "stack"` (one per row, never side by side), one per check: title = the check, body = the result, `meta` = the command, tone
`positive` for a pass and `danger` for an expected or real failure. Never `evidence` blocks — their
large bold value breaks the page flow. File status shows as an icon, never as a word in a box.
