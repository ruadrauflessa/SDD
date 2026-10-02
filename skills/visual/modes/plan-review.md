# Mode: plan-review — compare a plan against the current code

Args: plan path or plan text; ask for it if missing. Default renderer: full (`--quick` allowed).

## Data gathering before HTML

Read the plan in full. Extract goals, assumptions, proposed files/functions/types, migrations,
tests, rollout/release notes, explicit risks. Read every referenced file plus importers/dependents.
Search for existing patterns, similar implementations, API boundaries, config/schema files, tests.

## Source verification

For each proposed change: do the files/functions/types exist, does current behaviour match the
plan, what ripple effects are missing, does the test plan fit the repo's test style. Cite plan
sections and file:line.

## Page sections — use only those with something the user needs

1. Plan summary: problem, core idea, scope.
2. Accuracy verdict: correct, stale, risky, unsupported, missing.
3. Current architecture: the affected subsystem only.
4. Proposed architecture: a matching visual diff against current.
5. Gap/risk matrix: correctness, tests, API, data model, UX, security/privacy, performance, maintainability, release.
6. File-by-file review: proposed edit, current reality, recommendation.
7. Better plan: concrete corrections or simplifications.
8. Decision: approve, revise, or reject, with rationale.

Current-vs-planned visual language. Responsive nav.
