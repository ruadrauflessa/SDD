# Mode: diagram — explain a topic, an architecture, or an investigation

Args: the topic. Default renderer: full (quick with `--quick`).

Pick the representation that fits (see SKILL.md): static SVG diagrams for connected flows, CSS
cards for text-heavy explanations, tables for matrices, timelines for linear history.

For an **investigation** ("why does X happen", "how does Y work"), the page has (only the parts with something to say):

1. The answer — one or two sentences, first viewport.
2. The mechanism — a sequence diagram of the real path (request, data, calls), every arrow labelled;
   a flowchart instead when it is a business process.
3. Evidence — file:line, log lines, query results that prove each step.
4. What was ruled out, and why.
5. Open questions / next step, only if they exist.
