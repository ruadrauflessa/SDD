# Best-effort PPTX export

`pptx/export.mjs` converts a generated sdd:visual HTML slide deck into a static `.pptx` file.

The HTML deck remains the source of truth. This exporter is intentionally best-effort and supports simple decks with `<section class="slide">` elements. It extracts slide titles, short text, bullets, simple tables, code blocks, and Mermaid source placeholders.

It does not preserve:

- animations or transitions;
- reader rail, outline, help, deep links, or resume state;
- responsive layout;
- custom web fonts;
- live Mermaid rendering, Chart.js, SVG, canvas, or JavaScript behavior.

## Usage

Once, ask the user first: `npm install --no-package-lock` in `<plugin root>/skills/visual`. Then:

```bash
node <plugin root>/skills/visual/pptx/export.mjs deck.html deck.pptx
```

If you omit the output path, the exporter writes beside the input with a `.pptx` suffix.

Use the HTML output for final fidelity. Use the `.pptx` as a portable static handoff when a presentation file is required.
