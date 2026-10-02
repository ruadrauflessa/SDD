# Quick renderer

Quick mode moves repeated HTML and CSS out of the agent response. The agent emits a compact JSON spec. `render.mjs` validates it and creates one complete, self-contained HTML document.

SKILL.md says which modes default to quick; `--quick` / `--full` override it. Use full mode if the content does not fit the schema or if validation or rendering fails.

## Example spec

```json
{
  "title": "Authentication flow",
  "tldr": ["The browser sends a token to the API."],
  "sections": [
    {
      "title": "Request path",
      "flow": {
        "nodes": [
          {
            "id": "browser",
            "label": "Browser"
          },
          {
            "id": "api",
            "label": "API",
            "tone": "positive"
          }
        ],
        "edges": [
          {
            "from": "browser",
            "to": "api",
            "label": "token"
          }
        ]
      }
    }
  ]
}
```

## Render

Save the spec as JSON and run:

```bash
node <plugin root>/skills/visual/quick/render.mjs spec.json <out>.html
```

Send the result with SendUserFile (`display: "render"`) or open it. If the renderer exits with an error, continue with the normal full HTML workflow.

## Schema

`schema.json` is the authoritative JSON Schema. A spec has a `title`, a required `tldr` (1–3 short lines, shown first), optional `subtitle` and `summary`, and one or more `sections`. Each section can contain:

- `cards`: compact findings or concepts;
- `table`: columns and string rows;
- `risks`: severity-tagged risk items;
- `files`: paths, details, and change status;
- `steps`: ordered work or timeline items;
- `flow`: nodes and directed edges, drawn as static inline SVG (no script, works offline) — a **sequence diagram** by default (nodes = participants, edges = messages in order; edges take `reply` and `tone`); `"kind": "flow"` gives a flowchart, `"kind": "state"` a state diagram (nodes take `start` / `end`). Nodes take `tone`; `caption` states the claim;
- `callouts`: notes, decisions, or warnings;
- `evidence`: a label, value, and optional source.

All agent text is HTML-escaped. Unknown properties, invalid enum values, bad flow references, and table rows with the wrong column count fail validation.
