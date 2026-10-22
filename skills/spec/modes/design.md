# Mode: Design

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

1. **Create the work item's folder first:** `env.py new --id <id> --repos <affected repos>
   --version <version>` (`--base Repo=main` for a repo without `team/*` branches). It branches
   each repo off the freshly fetched `team/{version}` into `src\{Repo}` and builds the graph.
   Without graphify it stops after the worktrees: fix graphify (`env.py doctor`), then
   `env.py graph --id <id>`. Decompose, Implement and Verify need the graph.
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
   contracts and data changes, risks, rejected alternatives with the reason. In the Affected
   components table, give each modified or removed component its **Graph node**: the `ID:` line of
   `graphify explain "<name>" --graph <folder>\graph\graph.json`. A new component gets `new`.
4. **Name the anchors deliberately** — file paths, exported symbols, API routes, tables,
   migrations, config and feature-flag keys. These are what overlap detection compares across
   branches, so vague ones cost you a real gate.
   **Check them against the graph:** `env.py anchors --id <id>`. It fails on a node the graph does
   not have, a node in another file than the component, a "new" component that already exists, and
   a graph older than the code (`env.py graph --id <id>` rebuilds it). Fix `design.md` until it
   prints `anchors OK`. "Design agreed" passes only on that run, and only while `design.md` is
   unchanged since it: after any edit, run it again.
5. **Run the tech story gate** before closing: enumerate what this design *creates* that didn't
   exist, search ADO for existing coverage, and propose only what survives. Present what's left
   as the "Tech story creation" gate — one `AskUserQuestion` option per proposal, `multiSelect:
   true`. Full procedure in `references/tech-stories.md`. **Nothing is created in ADO without
   an explicit approval.**
6. A story spec inherits its parent feature's design **by reference, not by copy**. Link to it.
   **A design agreed above** (`env.py upstream --id <id>` lists it) is where this design starts:
   name it (`ADO <id>`, with a link to its `design.md`), follow it, and say plainly where this one
   departs from it and why. Stay inside this item's part of it: start where its plan says the work
   starts, stop where it stops, and build nothing its plan puts out of scope. Name each such item
   under an **Out of scope** heading (`PDF output: ADO 902 builds it`). `env.py` refuses "Design
   agreed" while `design.md` does not name the design above, or an item its plan puts out of scope.

   **A Feature or Epic: the work item plan.** Its `design.md` ends with a `## Work item plan`: one
   entry per item under it. Every open item directly under it needs one; an item further down may
   have one too. Each entry is what that item's own flow will read, and nothing more:

   ```
   ## Work item plan

   ### ADO 901 CSV export
   - Starts: the exporter interface ADO 902 builds
   - Stops: a CSV file the user downloads
   - In scope: the CSV writer
   - Out of scope: PDF output (ADO 902)
   - Out of scope: scheduled exports (not planned)
   - Needs: ADO 902 (the exporter interface)
   - Gives: ADO 903 (the CSV writer, for the scheduler)
   - Decision: amounts in cents
   ```

   - **Starts / Stops:** where the work begins and where it is done.
   - **In scope / Out of scope:** each out-of-scope line names the item that builds it
     (`ADO <id>`), or says `not planned`.
   - **Needs / Gives:** what this item needs from other items and what they need from it, each
     naming the item. The plan's order comes from these lines and becomes predecessor and
     successor links in ADO. They must not loop.
   - **Decision:** each decision this item must follow. An answered question that binds every item
     travels only through these lines: write it into each entry that needs it. A question about
     one item is tagged `(ADO <id>)` in `questions.md`, and goes to that item only.

   `env.py` refuses "Design agreed" until the plan holds. **A feature or epic built whole** also
   designs each item the build covers (`env.py members --id <id>` lists them).

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
   **Design path** (`env.py status` shows `path: design`): the "Design agreed" answer ends the flow.
   Record Design `done` with `--passed "Design agreed"`; `env.py` records the later stages skipped.
   Tell the user the design is ready for the stories under it, each through the flow on its own
   with `/sdd next <id>`, and that `/sdd done <id>` cleans up the folder when they want.
   **A Feature or Epic** (any path): once "Design agreed" passes, carry the design to the board
   (step 9) before anything else.
8. **"Needs changes"?** Revise `design.md` to address what was asked for, run `env.py anchors`
   again (step 4), then re-run step 7 —
   present what changed and run the same gate again. Never guess at the fix and move on to
   Decompose without a fresh approval; a design that changed since it was last agreed to hasn't
   actually been agreed to.
9. **Carry the design to the board** (a Feature or Epic). The other developers' flows read ADO, not
   this workspace, and never the discussion. `env.py plan --id <id>` writes what goes into each
   item's **Implementation Plan** field to `plans/` in the spec folder. This item gets the whole
   design. Each item in the work item plan gets only its own entry, the settled and open questions
   tagged for it, and the Needs and Gives other entries name it in. The command also lists the
   predecessor links it adds. Send the `plans/` files, then ask with `AskUserQuestion`: "Write the
   plan into these <N> items' Implementation Plan and add the <M> links?" On Yes: `env.py plan
   --id <id> --post --confirmed "<their words>"`. It replaces only its own block in each field and
   keeps anything else written there. `env.py can` refuses every stage after Design, and
   `/sdd done`, until the agreed design is on the board. A design agreed again after a change
   needs writing again.
