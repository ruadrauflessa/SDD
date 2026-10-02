// Static SVG diagrams for quick mode. No script, no network: the page shows the same on a phone,
// in a sandboxed viewer and offline. Colours come from the page's CSS tokens (see base.css .ve-*).
//   sequence (default) — nodes are participants, edges are messages in order
//   flow               — top-down flowchart, for business explanations
//   state              — top-down states with a start dot, for one thing's lifecycle
// ponytail: text width is estimated (CH px per char), not measured; long labels wrap early.

const CH = 7;      // estimated px per character at 12.5–13px
const LH = 17;     // line height
const PAD = 16;
const TONES = ["accent", "positive", "warning", "danger", "info"];
let seq = 0;

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function wrap(text, max) {
  const out = [];
  let line = "";
  for (let word of String(text ?? "").split(/\s+/).filter(Boolean)) {
    while (word.length > max) {
      if (line) { out.push(line); line = ""; }
      out.push(word.slice(0, max));
      word = word.slice(max);
    }
    if (!word) continue;
    if (!line) line = word;
    else if (line.length + 1 + word.length <= max) line += " " + word;
    else { out.push(line); line = word; }
  }
  if (line) out.push(line);
  return out;
}

const toneAttr = (t) => (TONES.includes(t) ? ` data-tone="${t}"` : "");

function text(lines, x, y, cls, anchor = "middle") {
  if (!lines.length) return "";
  return `<text class="${cls}" x="${x}" y="${y}" text-anchor="${anchor}">${lines
    .map((l, i) => `<tspan x="${x}" dy="${i ? LH : 0}">${esc(l)}</tspan>`).join("")}</text>`;
}

function markers(id) {
  return `<defs>${["none", ...TONES].map((t) => `<marker id="${id}-${t}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="ve-head" d="M0,0L10,5L0,10z"${toneAttr(t)}/></marker>`).join("")}</defs>`;
}

const head = (id, t) => `url(#${id}-${TONES.includes(t) ? t : "none"})`;

function svg(id, w, h, caption, body) {
  return `<svg class="ve-svg"${w > 340 ? ' data-wide="1"' : ""} xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(w)}" height="${Math.ceil(h)}" viewBox="0 0 ${Math.ceil(w)} ${Math.ceil(h)}" role="img" aria-labelledby="${id}-t"><title id="${id}-t">${esc(caption)}</title>${markers(id)}${body}</svg>`;
}

function sequence(flow, caption) {
  const id = `ve${++seq}`;
  const S = 150;                                       // lane width
  const idx = new Map(flow.nodes.map((n, i) => [n.id, i]));
  const cx = (i) => PAD + S / 2 + i * S;
  const heads = flow.nodes.map((n) => ({ t: wrap(n.label, 17), d: wrap(n.detail, 19) }));
  const headH = Math.max(...heads.map((h) => (h.t.length + h.d.length) * LH + 18));
  let y = PAD + headH + 26;
  const rows = flow.edges.map((e, k) => {
    const a = idx.get(e.from), b = idx.get(e.to), self = a === b;
    const span = self ? S - 30 : Math.abs(b - a) * S - 36;
    const lines = wrap(e.label, Math.max(10, Math.floor(span / CH)));
    const lineY = y + lines.length * LH + 6;
    const row = { e, a, b, self, lines, top: y, lineY, n: k + 1 };
    y = lineY + (self ? 26 : 0) + 24;
    return row;
  });
  const W = PAD * 2 + flow.nodes.length * S, H = y;
  let out = "";
  for (const r of rows) {
    if (!TONES.includes(r.e.tone)) continue;
    const lo = Math.min(r.a, r.b), hi = r.self ? lo : Math.max(r.a, r.b);
    out += `<rect class="ve-band"${toneAttr(r.e.tone)} x="${cx(lo) - S / 2 + 6}" y="${r.top - 10}" width="${cx(hi) - cx(lo) + S - 12}" height="${r.lineY - r.top + (r.self ? 26 : 0) + 18}" rx="4"/>`;
  }
  flow.nodes.forEach((n, i) => {
    out += `<line class="ve-life" x1="${cx(i)}" y1="${PAD + headH}" x2="${cx(i)}" y2="${H - 8}"/>`;
    out += `<rect class="ve-box"${toneAttr(n.tone)} x="${cx(i) - S / 2 + 10}" y="${PAD}" width="${S - 20}" height="${headH}" rx="4"/>`;
    out += text(heads[i].t, cx(i), PAD + 9 + LH - 4, "ve-t");
    out += text(heads[i].d, cx(i), PAD + 9 + LH - 4 + heads[i].t.length * LH, "ve-d");
  });
  for (const r of rows) {
    const x1 = cx(r.a), cls = `ve-edge${r.e.reply ? " ve-reply" : ""}`;
    if (r.self) {
      out += `<path class="${cls}"${toneAttr(r.e.tone)} d="M${x1},${r.lineY} h44 v22 h-42" marker-end="${head(id, r.e.tone)}"/>`;
      out += text(r.lines, x1 + 14, r.top + 12, "ve-l", "start");
    } else {
      const x2 = cx(r.b) + (r.b > r.a ? -2 : 2);
      out += `<line class="${cls}"${toneAttr(r.e.tone)} x1="${x1}" y1="${r.lineY}" x2="${x2}" y2="${r.lineY}" marker-end="${head(id, r.e.tone)}"/>`;
      out += text(r.lines, (x1 + cx(r.b)) / 2, r.top + 12, "ve-l");
    }
    out += `<g class="ve-num"><circle cx="${x1}" cy="${r.lineY}" r="9"/><text x="${x1}" y="${r.lineY + 3.5}" text-anchor="middle">${r.n}</text></g>`;
  }
  return svg(id, W, H, caption, out);
}

function graph(flow, caption) {
  const id = `ve${++seq}`;
  const state = flow.kind === "state";
  const NW = 184, GX = 36;
  const byId = new Map(flow.nodes.map((n) => [n.id, n]));
  const outs = new Map(flow.nodes.map((n) => [n.id, []]));
  flow.edges.forEach((e) => outs.get(e.from).push(e));
  const hasIn = new Set(flow.edges.map((e) => e.to));
  let starts = flow.nodes.filter((n) => n.start);
  if (!starts.length) starts = flow.nodes.filter((n) => !hasIn.has(n.id));
  if (!starts.length) starts = [flow.nodes[0]];
  // layer = breadth-first depth from the start nodes; unreachable nodes go to a last layer
  const depth = new Map(starts.map((n) => [n.id, 0]));
  const queue = starts.map((n) => n.id);
  while (queue.length) {
    const from = queue.shift();
    for (const e of outs.get(from)) if (!depth.has(e.to)) { depth.set(e.to, depth.get(from) + 1); queue.push(e.to); }
  }
  const last = Math.max(...depth.values()) + 1;
  flow.nodes.forEach((n) => { if (!depth.has(n.id)) depth.set(n.id, last); });
  const layers = [];
  flow.nodes.forEach((n) => (layers[depth.get(n.id)] ??= []).push(n));
  const compact = layers.filter(Boolean);
  const forward = (e) => compact.findIndex((l) => l.includes(byId.get(e.to))) > compact.findIndex((l) => l.includes(byId.get(e.from)));
  const fwd = flow.edges.filter(forward), back = flow.edges.filter((e) => !forward(e));
  const labelLines = (e, max) => wrap(e.label, max);
  // a label sits on the lower half of its arrow (just above its target), so the half-gap must hold it
  const GY = Math.max(64, ...fwd.map((e) => 2 * (labelLines(e, 22).length * LH + 6) + 20));
  const size = new Map(flow.nodes.map((n) => {
    const t = wrap(n.label, 24), d = wrap(n.detail, 26);
    return [n.id, { t, d, h: (t.length + d.length) * LH + 22 }];
  }));
  const contentW = Math.max(...compact.map((l) => l.length * NW + (l.length - 1) * GX));
  const top0 = PAD + (state ? 34 : 0);
  const pos = new Map();
  let y = top0;
  for (const layer of compact) {
    const lw = layer.length * NW + (layer.length - 1) * GX;
    const lh = Math.max(...layer.map((n) => size.get(n.id).h));
    layer.forEach((n, i) => {
      const h = size.get(n.id).h;
      pos.set(n.id, { x: PAD + (contentW - lw) / 2 + i * (NW + GX), y: y + (lh - h) / 2, w: NW, h });
    });
    y += lh + GY;
  }
  const H = y - GY + PAD + (state ? 8 : 0);
  const laneX = PAD + contentW + 22;
  const W = laneX + (back.length ? back.length * 16 + 150 : 0) + PAD;
  let out = "";
  const box = (n) => pos.get(n.id);
  if (state) for (const n of starts) {
    const p = box(n), x = p.x + p.w / 2;
    out += `<circle class="ve-dot" cx="${x}" cy="${PAD + 7}" r="7"/><line class="ve-edge" x1="${x}" y1="${PAD + 14}" x2="${x}" y2="${p.y - 2}" marker-end="${head(id)}"/>`;
  }
  let labels = "";
  for (const e of fwd) {
    const s = box(byId.get(e.from)), t = box(byId.get(e.to));
    const sx = s.x + s.w / 2, sy = s.y + s.h, tx = t.x + t.w / 2, ty = t.y;
    const my = sy + (ty - sy) / 2;
    const d = sx === tx ? `M${sx},${sy} V${ty - 2}` : `M${sx},${sy} V${my} H${tx} V${ty - 2}`;
    out += `<path class="ve-edge"${toneAttr(e.tone)} d="${d}" marker-end="${head(id, e.tone)}"/>`;
    const lines = labelLines(e, 22);
    if (lines.length) {
      const lw = Math.max(...lines.map((l) => l.length)) * CH + 14, lh = lines.length * LH + 6;
      const lx = tx, ly = sx === tx ? my : (my + ty) / 2;
      labels += `<rect class="ve-lbg" x="${lx - lw / 2}" y="${ly - lh / 2}" width="${lw}" height="${lh}" rx="3"/>` + text(lines, lx, ly - lh / 2 + LH - 2, "ve-l");
    }
  }
  back.forEach((e, k) => {
    const s = box(byId.get(e.from)), t = box(byId.get(e.to)), lane = laneX + k * 16;
    const sy = s.y + s.h / 2 + 6, ty = t.y + t.h / 2 - 6;
    out += `<path class="ve-edge"${toneAttr(e.tone)} d="M${s.x + s.w},${sy} H${lane} V${ty} H${t.x + t.w + 2}" marker-end="${head(id, e.tone)}"/>`;
    labels += text(labelLines(e, 18), lane + 8, (sy + ty) / 2 - 4, "ve-l", "start");
  });
  for (const n of flow.nodes) {
    const p = box(n), sz = size.get(n.id);
    const pill = !state && (n.start || n.end);
    out += `<rect class="ve-box"${toneAttr(n.tone)} x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="${pill ? p.h / 2 : 4}"/>`;
    if (state && n.end) out += `<rect class="ve-box ve-inner"${toneAttr(n.tone)} x="${p.x + 4}" y="${p.y + 4}" width="${p.w - 8}" height="${p.h - 8}" rx="3"/>`;
    out += text(sz.t, p.x + p.w / 2, p.y + 11 + LH - 4, "ve-t");
    out += text(sz.d, p.x + p.w / 2, p.y + 11 + LH - 4 + sz.t.length * LH, "ve-d");
  }
  return svg(id, W, H, caption, out + labels);
}

export function flowSvg(flow, caption) {
  return (flow.kind || "sequence") === "sequence" ? sequence(flow, caption) : graph(flow, caption);
}

// CLI for full-mode pages: node diagram.mjs <flow.json> [caption]  -> prints the <svg> to paste into the page.
// The page needs the .ve-* rules from base.css (copy that block into the page's <style>).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const flow = JSON.parse(readFileSync(process.argv[2], "utf8"));
  process.stdout.write(flowSvg(flow, process.argv[3] || flow.caption || "Diagram") + "\n");
}
