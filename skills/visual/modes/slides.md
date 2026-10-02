# Mode: slides — a slide deck as one HTML page

Args: the topic, optional `--pptx`. Renderer: always full.

Before writing HTML, read `templates/slide-deck.html`, `references/slide-patterns.md`, and only the
shared CSS/library sections the source needs.

Plan the deck first: inventory the source, map every item to slides, choose a narrative arc, and
assign a composition to each slide. Use the 10 slide types — Title, Section Divider, Content,
Split, Diagram, Dashboard, Table, Code, Quote, Full-Bleed — and the nav chrome from the template:
prev/next, slide count with reading percent, carousel dots, keyboard navigation, expandable reader
rail, outline/help overlays, `#slide-N` deep links, resume state.

Rules:

- Each slide gets one `100dvh` viewport budget, no page scrolling. `overflow: hidden` clips excess
  silently, so check under `prefers-reduced-motion: reduce` at the target size **and** a short
  landscape height; fix every overflow or `autoFit()` warning before delivery.
- Larger type, fewer objects per slide, varied compositions (three centred slides in a row is a smell).
- Never drop content to fit a slide count — add slides.
- Visual-first: diagrams, charts, tables, SVG accents; `surf` images only when they clarify.

## `--pptx`

Remove the flag from the topic. Build the HTML deck first — it stays the source of truth. Then run
`node <plugin root>/skills/visual/pptx/export.mjs <deck.html> <deck.pptx>` (output defaults to the
input name with `.pptx`).

It needs `node-html-parser` and `pptxgenjs`. If `<plugin root>/skills/visual/node_modules` is
missing, ask the user before installing (it downloads packages), then run
`npm install --no-package-lock` in `<plugin root>/skills/visual`. If they decline, deliver the HTML
only and say why. Always tell the user the PPTX is static: no animations, reader navigation,
responsive layout, custom fonts, live Mermaid/Chart.js/SVG/canvas or JavaScript.

## Checklist

Slides fit one viewport, carry the reader rail plus outline/help navigation, keep every source item,
and pass the overflow/autoFit check under reduced motion; PPTX, if asked, was made after the HTML
and its limits were stated.
