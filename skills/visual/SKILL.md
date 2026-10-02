---
name: visual
description: "Turn any explanation or plan into a self-contained HTML visual page that is easy to digest — diagrams, tables, before/after, risk matrices, slide decks. Use it EVERY time you present a plan, design, decomposition/task list, bug root cause, proposed or applied fix, code or PR review, investigation result, impact analysis, requirement summary, project recap, or comparison — inside the /sdd flows (sdd:spec, sdd:bug, sdd:impact), in ado-bug-fix and ado-pr-review, and in ordinary chat. Also for \"draw / diagram / visualise / explain visually / make slides / diff review / plan review / recap / fact-check this page\". Skip it only for one-line answers, yes/no confirmations and pure tool/setup chatter. `/sdd:visual <mode> [args]` runs a mode directly — modes: diagram, plan, slides [--pptx], diff-review, plan-review, recap, fact-check, bug, design, tasks, requirements, impact, review; add --quick or --full to force the renderer."
license: MIT (forked from nicobailon/visual-explainer 0.11.0 — see LICENSE)
---

> Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Files under this skill write it as `<plugin root>`.

# sdd:visual — show it, don't just say it

Our own fork of the `visual-explainer` plugin (0.11.0), tuned for the sdd flows. Every explanation
or plan the user has to read or approve gets a **visual page**: one self-contained HTML file, sent
to the user. **The page is the explanation.** Once it is sent, the chat does not explain it again —
the user opens the page and reads it there.

## When — the rule

Make a visual whenever you:

| Moment | Mode |
| --- | --- |
| Present requirements, open questions, gaps (sdd:spec Specify) | `requirements` |
| Present a design / approach (sdd:spec Design, tech story gate) | `design` |
| Present a decomposition / task list / implementation plan | `tasks` (or `plan` outside sdd) |
| Explain a bug: Gate 0 verdict, root cause, proposed fix (sdd:bug, ado-bug-fix) | `bug` |
| Report a finished fix before PR / manual verification | `diff-review` |
| Review code or a PR (ado-pr-review, `/code-review`, any review) | `review` |
| Present an impact / blast-radius analysis (sdd:impact) | `impact` |
| Report an investigation, an architecture or "how does X work" | `diagram` |
| Check an existing plan against the code | `plan-review` |
| Recap a project or a work item after a break | `recap` |
| Slides were asked for | `slides` |
| Verify a generated page against the code | `fact-check` |

**Skip it** for a one-line answer, a yes/no confirmation, progress pings, a choice between two
plain options (e.g. "which team version?"), and tool/setup questions (`/sdd init`, `/sdd help`).
When unsure, make it — a quick-mode page costs little.

Each mode's sections live in `modes/<mode>.md`. Read only the one you need. Those lists are the
**most** a page may hold, not a checklist to fill — see "Only what is needed" below.

## Renderer — quick or full

| Renderer | Use for | How |
| --- | --- | --- |
| **quick** (default for `bug`, `requirements`, `impact`, `tasks`, `review` at a gate) | Routine gate visuals. Cheap: you write a small JSON spec, a script writes the HTML. | Read `quick/README.md` + `quick/schema.json`. Write the spec to a `.json` file, then `node ${CLAUDE_PLUGIN_ROOT}/skills/visual/quick/render.mjs <spec.json> <out.html>` |
| **full** (default for `design`, `plan`, `diagram`, `diff-review`, `plan-review`, `recap`, `slides`, `fact-check`) | Pages that need custom layout or more than the schema can say. | Write the complete HTML yourself, following the rules below and the templates. |

Quick-mode block choice: test and verification results → `cards` in a `"layout": "stack"` section, one per
row (tone = pass/fail, `meta` = the command); `evidence` only for short proof values with a source. `files` draw a fixed-size status
icon (added, modified, deleted, reviewed, planned) with a one-line key.

`--quick` / `--full` in the args overrides the default. Quick mode supports cards, tables, risks,
files, steps, simple flows, callouts and evidence. If the content does not fit the schema, or
validation or rendering fails, fall back to full. Never use quick for slides, fact-check or themes.

## Where the file goes, and how the user sees it

1. **Path.**
   - In an sdd work item: the item's spec folder, `{specRoot}/**/{id}-{TYPE}-{slug}/visuals/<mode>[-<n>].html`
     (resolve the folder by glob, as the flows do). It survives `/sdd done` and sits next to
     `requirements.md` / `design.md`. Overwrite the same name when you revise; add `-2`, `-3` only
     when the user should be able to compare versions.
   - Anywhere else: `~/.agent/diagrams/<descriptive-name>.html`.
   - Quick-mode spec JSON: next to the HTML, same base name, `.json`.
2. **Show it.** `SendUserFile` with `display: "render"` and `status: "normal"` when that tool exists
   (desktop app, phone). Otherwise open it: `Start-Process <path>` on Windows, `open` / `xdg-open`
   elsewhere. **Always** also give a clickable link to the file in chat, as a `file:///` URL with
   forward slashes, e.g. `[design.html](file:///C:/Users/me/.agent/diagrams/design.html)`, so the
   user can open it in their own browser. This link is the one line that names the page.
3. **At an sdd gate** pass the page as a ref too: `env.py progress … --status waiting --ref
   visuals/<mode>.html` (or `env.py refs`). Refs resolve against the spec folder, so the page lands
   in the Links block and in the "Send with SendUserFile" list. The `--status waiting` checkpoint
   **refuses to run without an `.html` ref**, unless you pass `--no-visual "<reason>"` for a gate
   that has nothing to show (a plain two-option choice, a PR-status check).
4. **No second explanation in chat.** After sending the page, the chat holds only: one line naming
   the page (e.g. "The design is on the page."), the Links block when an sdd gate needs it, and the
   question (`AskUserQuestion` in an sdd flow). All links stay in the chat — never inside the question. No summary, no restated findings, no verdict recap,
   no bullet list of what the page says. If something is not on the page, put it on the page and
   re-send — do not add it in chat.
5. **Markdown companion** only when the user asks for AI-readable output or a source brief:
   `<name>.md` beside `<name>.html`. HTML stays the source of truth; ask before overwriting an
   existing companion.

## Write it the ELI5 way

All text on the page follows the user's **ELI5 output style** (`~/.claude/output-styles/ELI5.md`
— read it if it is not active in this session). That means:

- ASD-STE100 Simplified Technical English: approved plain words, active voice, one idea per sentence.
- Small words, short sentences, short paragraphs. Explain a big word right after it.
- If the user must decide: 2 options at most, the context needed to pick fast, and which one you
  recommend.
- Paths, commands, file:line and code names stay exact — never simplify those.

## TL;DR first — on every page

Every page starts with a **TL;DR** box, right under the title, before anything else: 1–3 short ELI5
lines. Usually: what is wrong (or what is proposed), what the fix or plan is, and what the user does
now. The user should be able to stop reading after the TL;DR and still know the point.

- Quick mode: the `tldr` array is **required** (1–3 strings); the renderer draws the box.
- Full mode: write the same box by hand, first in `<main>`, styled as the page's most prominent block.
- The TL;DR does not repeat the title, and the rest of the page does not repeat the TL;DR.

## Links right under the TL;DR

Directly under the TL;DR, every page has a **Links** box with every work item, pull request,
commit and branch the page mentions anywhere — so the reader never hunts for an id in the text.

- Quick mode: the top-level `links` array, each `{ "kind", "label", "url" }`; kind is `workitem`,
  `pr`, `commit`, `branch`, `build`, `file`, `page` or `other`. The box sorts them in that order.
- Full mode: the same box by hand, right after the TL;DR.
- Real URLs only, built from facts (sdd `workitem.json`, `git`, ADO): work item
  `https://dev.azure.com/{org}/{project}/_workitems/edit/{id}`; PR
  `https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}`; commit
  `https://dev.azure.com/{org}/{project}/_git/{repo}/commit/{full 40-char sha}`; branch
  `https://dev.azure.com/{org}/{project}/_git/{repo}?version=GB{branch}`. The project is the one the
  item lives in — not always the default. A commit link needs the full sha; resolve a short one
  with `git rev-parse`.
- Label = what the reader recognises: `ADO 93210 — ApiExceptionHandler never logs`, `PR 33600`,
  `96e16cb — log unhandled exceptions`, `dev/…/93210-…`.
- Sample or demo pages with invented ids use `#` as the URL, so the box still shows.
- Mentions in the text become links too. Quick mode does it for you (`quick/autolink.mjs`): every
  `ADO 93210` / bare `93210`, `PR 34449`, short or full commit id and branch name that is in the
  Links box is linked where it appears — TL;DR, subtitle, cards, tables, steps. Page and section
  titles and diagrams stay plain. An id that is not in the box is never linked, so put every
  referenced item in the box. Full mode: link those mentions by hand to the same URLs.
- Nothing referenced → no Links box. A link that cannot be built from facts is left out, never
  guessed. The page text may still name the id; the box is where it is clickable.

## Only what is needed

The page answers one question: what does the user need to understand or decide now? Leave out
everything else.

- **Drop a section that has nothing important to say.** No "Ruled out" with nothing ruled out, no
  "Risks" with only trivial risks, no "Out of scope" when nothing is. Never write "None" or "N/A"
  to fill a section — remove it.
- **Fewest blocks that carry the point.** One diagram, not three views of the same thing. One
  evidence item per claim, not every log line you read.
- **No background the user already knows**, no process narration ("I then searched…"), no
  restating the same fact in two sections, no generic advice.
- **Test each block:** would the user miss it if it was gone? If not, delete it.
- A short page is a good page. Detail the user may want but does not need goes in a collapsed
  `<details>` (full mode) or is left out (quick mode).

## Facts first — the page is evidence, not decoration

- Gather and verify before writing a line of HTML: file paths, symbol names, line ranges, command
  output, ADO ids. Cite `path/file.cs:120` on the page. Never invent rationale, behaviour or code paths.
- Inside an sdd work item, read code only in `src/{Repo}/`, never the main checkout.
- For a big topic, scout with an `Explore` subagent first ("return findings, key entities/flows,
  and a suggested visual structure; do not edit files"), then build the page in the main agent.
- After building a full-mode page with many claims (`design`, `diff-review`, `recap`), run the
  `fact-check` mode over it before sending.
- Link every ADO artifact (work items, PRs, commits, branches) with full URLs, as in chat.

## Design judgment

Before writing any HTML:

- Calibrate treatment: reviews, bug explainers, audits and recaps get polished-utilitarian (real
  hierarchy, considered spacing, no flashy hero); narrative decks get editorial. A well-composed
  page is never wrong; an over-designed one sometimes is.
- Precedence: the user's words, then the project's existing design system (theme/token files,
  component styles), then this skill's choices. A project default theme/font can live in
  `sdd-visual.config.md` (see `references/themes.md` → Default config).
- Plan first: 4–6 named hex values, type roles, a one-sentence layout concept. Audit once — "would
  I produce this plan for any similar page?" — and revise the generic parts.
- Structure must encode something true: 01/02/03 markers only when order matters, eyebrow labels
  only when they classify, dividers only at real seams.
- **First viewport = the answer.** The decision, verdict or root cause is readable without
  scrolling; detail goes below or into `<details>`.

## Reference routing

Read only what the current page needs:

| Need | Read |
|---|---|
| Text-heavy architecture/cards | `templates/architecture.html` |
| Sequence, flowchart and state diagrams | `quick/diagram.mjs` (see "Diagrams are static SVG") |
| Data tables, comparisons, audits | `templates/data-table.html` |
| Slide decks | `templates/slide-deck.html`, `references/slide-patterns.md` |
| CSS layout, type scale, overflow, depth, collapsibles, SVG connectors, generated images | `references/css-patterns.md` |
| Pages with 4+ major sections | `references/responsive-nav.md` |
| Switchable themes or fonts, a named palette (Dracula, Nord, Gruvbox…), project default theme | `references/themes.md` |
| Prose-heavy pages | "Prose Page Elements" in `css-patterns.md`, typography sections in `libraries.md` |

## Choose the representation

| Content | Default representation |
|---|---|
| Execution path, process flow, bug path | Static SVG sequence diagram |
| Business process, decision tree, pipeline | Static SVG flowchart |
| Lifecycle / status changes of one thing | Static SVG state diagram |
| ER/schema, class, C4, topology | Semantic `<table>` or CSS cards (the drawer has no ER/class shapes) |
| Text-heavy architecture, module internals, implementation plans | CSS grid cards, optionally with a small static diagram |
| Comparison/audit/status matrix | Semantic HTML `<table>` |
| Before/after (bug, fix, diff) | Side-by-side panels, red before / green after |
| Timeline/roadmap/task order | CSS timeline or steps |
| Dashboard/metrics | CSS grid + charts/KPIs |
| Slide deck | `100dvh` slides using slide template patterns |

A table with 4+ rows or 3+ columns goes on the page, not in chat.

## Paths and processes are always drawn

When an explanation contains an **execution path** or a **process flow** — a request through
services, a call chain, a job's lifecycle, a status change, the path from trigger to bug, a
business process — the page **must** draw it as a diagram. Prose or a numbered list alone is not
enough.

- **Prefer a sequence diagram**: the participants are the real actors (user, UI, gateway, service,
  class, database, queue), the messages are the real calls in order, labelled with the method,
  route or event; return messages are dashed; messages are numbered. Use it for execution paths,
  process flows, error paths and bug paths.
- **Use a flowchart** for functional business explanations — who does what, in which order, with
  decisions.
- A **state diagram** only for a lifecycle or status changes of one thing.
- Mark the faulty or changed step with a tone (danger = broken, warning = risk, positive = fixed):
  a toned message gets a coloured band, a toned participant or box a coloured border.

## Diagrams are static SVG — no script, no network

Every page must look the same on a phone, in a sandboxed file viewer and offline. Those block
scripts from the internet, so **never load Mermaid or any other diagram library from a CDN**.
Diagrams are drawn at build time as inline SVG by `quick/diagram.mjs`:

- **Quick mode:** a section `flow` is drawn automatically — sequence by default (nodes are
  participants, edges are messages in order; `reply: true` for a return, `tone` to highlight),
  `"kind": "flow"` for a flowchart, `"kind": "state"` for a state diagram (`start` / `end` on
  nodes); `caption` states the claim.
- **Full mode:** write the same flow JSON to a file, run
  `node ${CLAUDE_PLUGIN_ROOT}/skills/visual/quick/diagram.mjs <flow.json> "<caption>"`, paste the printed
  `<svg>` into a `<figure class="diagram-wrap"><div class="diagram">…</div><figcaption>…</figcaption></figure>`,
  and copy the "Static SVG diagrams" block (`.diagram`, `.ve-*` rules) from `quick/base.css` into
  the page's `<style>`.
- A wide diagram keeps its natural size and scrolls sideways inside its box; on a phone the page
  shows "Swipe or drag sideways to see the whole diagram". With a mouse, click and drag pans it
  (`quick/drag.js`, inlined — no network). Full-mode pages paste that script before `</body>`.
- The Mermaid material in `templates/` and `references/libraries.md` is reference only. Use
  Mermaid only when the user explicitly asks for it, and then say the page needs internet access.

What to draw:

- Depict the mechanism, not its name: the path a request takes through a cache says more than a box labeled "cache".
- Label every arrow (`writes`, `invalidates`, `polls every 30s`); an unlabeled arrow only says "related somehow".
- To compare options, draw the difference — the edge each adds or removes. Match complexity to what the decision turns on.
- One figure, one claim; the caption states it.
- Keep it small: about 6 participants or 10 boxes. More than that, split it or use cards.

## Layout and style invariants

- Use semantic HTML where it helps accessibility and copy/paste: `<table>`, headings, lists, `<details>`, captions.
- Use CSS custom properties for palette: `--bg`, `--surface`, `--border`, `--text`, `--text-dim`, and 3–5 accents.
- Pages meant to persist ship both color schemes: tokens on `:root`, the `prefers-color-scheme` media query redefines tokens only, components styled through tokens. Pick the second theme's values; never invert. Single-theme is fine when deliberate (one-shot pages, quick mode, `themes.md` picker).
- Commit to one palette (with its light and dark scheme variants) and one font pair. Add a runtime picker only when the user asks to switch themes or fonts, or names a prebuilt palette; see `references/themes.md`.
- Anchor the aesthetic direction to the content's domain: CLI/infra → terminal or IDE-inspired; metrics/audits → data-dense; plans/architecture → blueprint; recaps → editorial; prose → paper/ink. Warm cream + serif + terracotta on everything is itself a cliché.
- Avoid generic defaults when choosing freely (a project's existing design system overrides this list): no body font that is only Inter, Roboto, Arial, Helvetica, or system-ui; no violet/fuchsia Tailwind-default accents as the main palette (`#8b5cf6`, `#7c3aed`, `#a78bfa`, `#d946ef`); no cyan+magenta+purple neon dashboard; no gradient-mesh blobs; no purple-to-blue gradient heroes, emoji section markers, centered-everything layouts, uniform large border-radius, or default accent bars on rounded cards.
- Set type deliberately: running text near 65ch, a committed type scale, `text-wrap: balance` on headings, letter-spacing on uppercase labels.
- For non-slide, scrollable pages, use a rem-based type scale with one root knob: set `html { font-size: 16px }` (choose a value in the 16–18px range) and express ordinary page text in `rem`. Minimum effective sizes at the chosen root: body/reading text ≥ 14px, secondary text and labels ≥ 11px, code/mono ≥ 12px. Never hard-code reading text below 14px in px. Diagram SVG labels stay in px. Slide decks are the exception: keep their `clamp(...px, ...vw, ...px)` typography and `autoFit()` runtime fitting from `slide-patterns.md` and `slide-deck.html`. Re-scale px values when copying reference snippets into ordinary pages.
- Bias neutrals toward the accent hue; pure mid-grey reads as unconsidered. Space siblings with flex/grid `gap`, not collapsing margins; `tabular-nums` where digits align in columns; watch specificity so classes do not silently cancel each other's spacing.
- Microcopy is design material: name things by what readers recognize, not internal structure; controls say exactly what happens; specific beats clever.
- Dashboards are scanned, not read: summary before detail; encode state in form (pills, chips, severity stripes); keep semantic color separate from the accent hue; interactive things look interactive.
- Diff colour language, everywhere: red = removed/before, green = added/after, amber = modified/risk, blue = neutral context.
- Good font pair families: DM Sans + Fira Code; Instrument Serif + JetBrains Mono; IBM Plex Sans + IBM Plex Mono; Bricolage Grotesque + JetBrains Mono; Plus Jakarta Sans + Azeret Mono.
- Load every font weight the CSS uses, including mono labels. Do not rely on faux-bold for 500, 600, or 700 weights. Always give a local fallback stack — the page must still read when the font CDN is blocked.
- Good accent directions: terracotta+sage, teal+slate, rose+cranberry, amber+emerald, deep blue+gold.
- **Every block wraps its text.** Long code tokens, paths, URLs and identifiers must break inside their card, never spill out of it. Set `overflow-wrap: anywhere` on `body` (it inherits; `break-word` does **not** stop grid/flex items from growing past their track), `min-width: 0` on every grid/flex child, `white-space: normal` on inline `code` inside cards, and scroll containers only for wide tables and `<pre>` blocks. Check a card with a 60-character identifier before sending.
- Do not set `display: flex` directly on `<li>` when list markers matter.
- Corners match: every block uses the same small radius on all four corners (sections 5px, cards,
  tables and diagrams 4px). No odd-corner shapes such as a large bottom-right only.
- Use depth sparingly: hero/elevated only for primary sections; flat/recessed for reference material.
- Use entrance/hover animation only when it clarifies hierarchy. Respect `prefers-reduced-motion`. Do not use continuous glow, pulse, or breathing effects on static content.
- Every page has `<html lang="en">`, a viewport meta tag, and a self-contained favicon (inline SVG data URI). In display math (`$$…$$`) escape raw `<` / `>`.
- No secrets or personal data on a page: no connection strings with passwords, keys, tokens or patient data. Pages under `documents/` are kept in the workspace snapshot.

## Slide deck mode

Use slides only when explicitly requested (`slides` mode). Slides are a different medium, not a
paginated article. Rules and the PPTX export are in `modes/slides.md`.

## Optional generated images

If `surf` (surf-cli) is available, generated images may be embedded as base64 for hero banners,
conceptual illustrations, or educational visuals. Skip images for data-heavy, structural, or
diagram/CSS-suitable content. Pages must stand on CSS, typography, and diagrams without images.

## Final checklist

Before sending, verify:

- complete HTML document, written to the path above;
- no console errors when opened (open it in the Browser pane and read the console when in doubt);
- no horizontal overflow at normal desktop width, and it reads at phone width;
- no text spills out of any card, table cell or evidence block;
- every execution path or process in the explanation is drawn as a diagram (sequence diagram preferred);
- fonts load with fallbacks; self-contained favicon; `lang` and viewport set;
- tables preserve rows/columns and wrap long text;
- interactive elements have visible keyboard focus states;
- diagrams are static inline SVG (no `<script>`, no CDN) in a `<figure>` with a claim-stating `figcaption`; the SVG carries `role="img"` and a `<title>`;
- both color schemes hold up, or single-theme was deliberate;
- the page has no `<script>` that loads anything from the internet;
- a runtime picker, if present, swaps palette and font variables;
- slides: see `modes/slides.md` checklist;
- non-slide page type uses rem with one root knob and meets the minimum sizes;
- the main idea — decision, verdict, root cause — is obvious in the first viewport;
- styling would still be recognizable if compared against a generic dark/violet template;
- every fact on the page is backed by a file:line, command output or ADO link;
- the page opens with a TL;DR of 1–3 lines;
- every work item, PR, commit and branch the page mentions is in the Links box under the TL;DR;
- text follows the ELI5 style, and every section and block passes the "would they miss it?" test;
- if requested, the Markdown companion matches the delivered HTML without becoming its source;
- the page was sent (`SendUserFile`) or opened, and the chat does not repeat it.

## Bundled files

| File | Read when |
| --- | --- |
| `modes/*.md` | The mode you are running — required sections per page |
| `quick/README.md`, `quick/schema.json`, `quick/render.mjs` | Quick renderer |
| `templates/*.html` | Full renderer — the matching template |
| `references/*.md` | See Reference routing |
| `pptx/export.mjs`, `pptx/README.md`, `package.json` | `slides --pptx` only |
| `LICENSE` | Original MIT licence — keep it with the fork |
