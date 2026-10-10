# Mode: Design

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

1. **Create the work item's folder first:** `env.py new --id <id> --repos <affected repos>
   --version <version>` (`--base Repo=main` for a repo without `team/*` branches). It branches
   each repo off the freshly fetched `team/{version}` into `src\{Repo}` and builds the graph.
   Design is read against the branch the change will actually land on, not against whatever the
   main checkout happens to have. Mechanics in `references/branching.md`.
2. **Read the code** — inside `src\{Repo}` — the modules, contracts and data the change touches.
   Start from `graph\GRAPH_REPORT.md`, then `graphify query "<question>" --graph
   <folder>\graph\graph.json` and `graphify affected "<node>" --graph …` for what depends on it.
   The graph is a map: confirm everything it says by reading the file. Note what actually
   exists, not what the requirement implies. Across several modules or repos, hand the survey to
   **`sdd:investigator`** and keep only its anchored findings. **A second affected repo turns up here?** Re-run
   `env.py new` with that repo in `--repos` before reading further into it — existing repos are
   skipped.
3. **Write `design.md`** from `assets/design.md.template`: approach, affected components,
   contracts and data changes, risks, rejected alternatives with the reason.
4. **Name the anchors deliberately** — file paths, exported symbols, API routes, tables,
   migrations, config and feature-flag keys. These are what overlap detection compares across
   branches, so vague ones cost you a real gate.
5. **Run the tech story gate** before closing: enumerate what this design *creates* that didn't
   exist, search ADO for existing coverage, and propose only what survives. Present what's left
   as the "Tech story creation" gate — one `AskUserQuestion` option per proposal, `multiSelect:
   true`. Full procedure in `references/tech-stories.md`. **Nothing is created in ADO without
   an explicit approval.**
6. A story spec inherits its parent feature's design **by reference, not by copy**. Link to it.

   **Second opinion.** Hand **`sdd:skeptic`** (mode `design`) `requirements.md` and `design.md`.
   It checks every criterion is covered, nothing is scope creep, and every anchor exists or is
   marked new. On `does not hold`, revise `design.md` first. Show any gap you leave open on the
   design page.
7. **Stop and ask.** Build the `sdd:visual` **design** page (`visuals/design.html`, tech story
   proposals included) from `design.md` — the approach and the anchors — and send it (no recap in
   chat), then run the "Design
   agreed" gate with `AskUserQuestion` (see "Approval gates" in `../SKILL.md`). Decomposing before that
   answer risks tasks built against a design that's about to change.
   **Short path** (`env.py status` shows `path: short`): do not stop here. Build the design page,
   record Design `done` with **no** `--passed "Design agreed"`, and go straight to Decompose — its
   one stop approves the design and the tasks together. The tech story gate (step 5) still asks,
   because it writes to ADO.
8. **"Needs changes"?** Revise `design.md` to address what was asked for, then re-run step 7 —
   present what changed and run the same gate again. Never guess at the fix and move on to
   Decompose without a fresh approval; a design that changed since it was last agreed to hasn't
   actually been agreed to.
