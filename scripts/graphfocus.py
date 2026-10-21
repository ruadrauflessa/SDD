"""Which nodes of a work item's code graph its design or its implementation touch: the logic behind `env.py graph-focus`.

Plain functions over graphify's graph.json (nodes with `source_file` "<Repo>/path" and `source_location` "L<line>", links with
`source` and `target`), the text of design.md / tasks.md, and the line ranges git says changed. No git, no files here: the
caller passes them in, so a test needs nothing but strings.

  design          the nodes design.md and tasks.md name: a path (with or without :line) or a symbol in backticks
  implementation  the nodes whose lines the work changed; what the design named and the work has not touched is "planned"

Four tiers come out, each a list of node ids: `primary`, `planned`, `secondary` (the rest of the files it touched) and
`neighbors` (one hop from a primary node). `render` puts them on graphify's own graph.html, which it leaves as it is.
"""
import json
import re

BACKTICK = re.compile(r"`([^`\n]{2,200})`")
EXT = "cs|py|ts|tsx|js|jsx|mjs|java|kt|go|rs|rb|php|swift|c|cc|cpp|h|hpp|sql|json|yaml|yml|xml|md|html|css|scss|sh|ps1|psm1|tf|csproj|razor|cshtml|vue|scala|gradle|toml|ini|cfg"
FILEISH = re.compile(r"^[\w .@()\\/-]*[\\/][\w .@()\\/-]*(:\d+(-\d+)?)?$|^[\w@-][\w.@-]*\.(" + EXT + r")(:\d+(-\d+)?)?$")
SYMBOL = re.compile(r"^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*(\(\))?$")
LOCATION = re.compile(r"^(?P<path>.+?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?)?$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_AMBIGUOUS = 6        # a symbol name that matches more nodes than this, in no file the text names, is left out
MODES = ("design", "implementation", "none")


def _slash(path):
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _line(node):
    m = re.match(r"^L(\d+)", str(node.get("source_location") or ""))
    return int(m.group(1)) if m else None


def _name(label):
    """`.run()` -> `run`, `Totals` -> `totals`: what a name in the design is compared with."""
    return re.sub(r"\(\)$", "", (label or "").strip()).lstrip(".").lower()


def refs_from_text(text):
    """What a design or task list points at in backticks: {"files": [(path, first line, last line)], "symbols": [name]}.

    `src/Billing/Totals.cs:120` and `Totals.cs` are files; `Round`, `Totals.Round` and `Round()` are symbols (the last
    part of a dotted name). A command, a sentence or a number is neither."""
    files, symbols = [], []
    for tok in BACKTICK.findall(text or ""):
        tok = tok.strip()
        if " " in tok and not FILEISH.match(tok):
            continue
        if FILEISH.match(tok):
            m = LOCATION.match(_slash(tok))
            a = int(m.group("a")) if m and m.group("a") else None
            b = int(m.group("b")) if m and m.group("b") else a
            path = m.group("path") if m else _slash(tok)
            if (path, a, b) not in files:
                files.append((path, a, b))
        elif SYMBOL.match(tok):
            name = _name(tok.split(".")[-1] if not tok.endswith("()") else tok[:-2].split(".")[-1])
            if len(name) >= 3 and name not in symbols:
                symbols.append(name)
    return {"files": files, "symbols": symbols}


def changed_from_diff(diff_text, repo):
    """{"Repo/path": [(first, last)]} from `git diff -U0` text: the lines each file has now. A file with only deletions
    keeps a one-line range where the lines were."""
    out, cur = {}, None
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            cur = None if p == "/dev/null" else f"{repo}/{p[2:] if p.startswith('b/') else p}"
            if cur:
                out.setdefault(cur, [])
        elif cur and (m := HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
            out[cur].append((start, start + max(count, 1) - 1))
    return out


def _files_of(nodes):
    by = {}
    for n in nodes:
        if n.get("source_file") and n.get("file_type") not in ("rationale", "concept"):   # a docstring or an idea is no place in the code
            by.setdefault(_slash(n["source_file"]), []).append(n)
    for lst in by.values():
        lst.sort(key=lambda n: (_line(n) or 0))
    return by


def _file_match(by_file, path):
    """The graph's files a path in text names: the whole path, or the tail it shares (`src/Repo/a/b.cs` names `Repo/a/b.cs`,
    `b.cs` names every `b.cs`)."""
    want = _slash(path).lower().split("/")
    out = []
    for f in by_file:
        have = f.lower().split("/")
        n = min(len(want), len(have))
        if want[-n:] == have[-n:]:
            out.append(f)
    return out


def _at(nodes, a, b):
    """The nodes of one file (sorted by line) that lines a..b touch: those that start inside, and the one that holds line a."""
    hit = [n for n in nodes if _line(n) is not None and a <= _line(n) <= b]
    before = [n for n in nodes if _line(n) is not None and _line(n) <= a]
    if before and not any(_line(n) == _line(before[-1]) for n in hit):
        hit.append(before[-1])
    return hit


def focus(graph, mode, design=None, changed=None):
    """The tiers for `mode`. `design` is refs_from_text(...); `changed` is {"Repo/path": [(a, b)] | None} (None: a new file, all of it)."""
    nodes = graph.get("nodes") or []
    by_file = _files_of(nodes)
    ids = {n["id"] for n in nodes}
    skipped = []

    def mark(group, node, why):
        group.setdefault(node["id"], why)

    named, named_files = {}, set()
    for path, a, b in (design or {}).get("files", []):
        for f in _file_match(by_file, path):
            named_files.add(f)
            if a:
                for n in _at(by_file[f], a, b or a):
                    mark(named, n, f"named in the design: {path}")
            else:
                for n in by_file[f]:
                    if _name(n.get("label")) == f.split("/")[-1].lower():
                        mark(named, n, f"named in the design: {path}")
    for sym in (design or {}).get("symbols", []):
        hits = [n for n in nodes if _name(n.get("label")) == sym and n.get("source_file")]
        inside = [n for n in hits if _slash(n["source_file"]) in named_files]
        use = inside or (hits if len(hits) <= MAX_AMBIGUOUS else [])
        if not use:
            if hits:
                skipped.append(sym)
            continue
        for n in use:
            mark(named, n, f"named in the design: {sym}")

    done = {}
    for f, ranges in (changed or {}).items():
        for g in (f2 for f2 in by_file if f2.lower() == _slash(f).lower()):
            if ranges is None:
                for n in by_file[g]:
                    mark(done, n, f"new file {g}")
                continue
            for a, b in ranges:
                for n in _at(by_file[g], a, b):
                    mark(done, n, f"changed lines {a}-{b} of {g}" if a != b else f"changed line {a} of {g}")

    if mode == "design":
        primary, planned = named, {}
    elif mode == "implementation":
        primary = done
        planned = {k: v for k, v in named.items() if k not in done}
    else:
        primary, planned = {}, {}

    files = {_slash(n["source_file"]) for n in nodes if n["id"] in primary and n.get("source_file")}
    files |= named_files if mode == "design" else set()
    secondary = {n["id"]: f"in {_slash(n['source_file'])}" for n in nodes
                 if n.get("source_file") and _slash(n["source_file"]) in files and n["id"] not in primary and n["id"] not in planned}
    marked = set(primary) | set(planned) | set(secondary)
    neighbors = {}
    for l in graph.get("links") or []:
        s, t = l.get("source"), l.get("target")
        if s in primary and t in ids and t not in marked:
            neighbors.setdefault(t, "linked to a node above")
        if t in primary and s in ids and s not in marked:
            neighbors.setdefault(s, "linked to a node above")
    label = {n["id"]: n.get("label") or n["id"] for n in nodes}
    reasons = {**{k: v for k, v in primary.items()}, **{k: v for k, v in planned.items()}}
    return {"mode": mode, "primary": list(primary), "planned": list(planned), "secondary": list(secondary), "neighbors": list(neighbors),
            "reasons": reasons, "labels": {k: label[k] for k in reasons}, "files": sorted(files), "skipped": skipped}


TITLE = {"design": "Design: what design.md and tasks.md name",
         "implementation": "Implementation: what the work changed"}

PANEL_JS = r"""
(function () {
  var F = __FOCUS__;
  if (typeof nodesDS === 'undefined' || typeof edgesDS === 'undefined' || typeof network === 'undefined') return;
  var COL = { a: '#f5b301', p: '#4fc3f7', s: '#7f9fc4', n: '#8a8a9a' };
  var tier = {};
  F.neighbors.forEach(function (id) { tier[id] = 'n'; });
  F.secondary.forEach(function (id) { tier[id] = 's'; });
  F.planned.forEach(function (id) { tier[id] = 'p'; });
  F.primary.forEach(function (id) { tier[id] = 'a'; });
  var orig = {};
  nodesDS.get().forEach(function (n) { orig[n.id] = { color: n.color, size: n.size, font: n.font }; });
  var origEdge = {};
  edgesDS.get().forEach(function (e) { origEdge[e.id] = e.color; });
  var on = true, only = false;
  function paint() {
    var ups = nodesDS.getIds().map(function (id) {
      var o = orig[id], t = tier[id];
      if (!on) return { id: id, color: o.color, size: o.size, font: o.font, opacity: 1, hidden: false };
      if (!t) return { id: id, color: o.color, size: o.size, font: o.font, opacity: 0.1, hidden: only };
      var c = COL[t], big = t === 'a' || t === 'p';
      return { id: id, opacity: t === 'n' ? 0.55 : 1, hidden: false,
        color: { background: c, border: c, highlight: { background: '#ffffff', border: c } },
        size: big ? Math.max((o.size || 10) * 1.8, 20) : o.size,
        font: big ? { size: 14, color: (o.font && o.font.color) || '#ffffff' } : o.font };
    });
    nodesDS.update(ups);
    edgesDS.update(edgesDS.getIds().map(function (id) {
      var e = edgesDS.get(id);
      var lit = on && tier[e.from] !== undefined && tier[e.to] !== undefined;
      return { id: id, color: !on ? origEdge[id] : lit ? { color: COL.a, opacity: 0.8 } : { opacity: 0.03 }, hidden: on && only && !lit };
    }));
    btn1.textContent = on ? 'Show everything' : 'Highlight again';
    btn2.textContent = only ? 'Show the rest dimmed' : 'Only the highlighted';
  }
  var panel = document.createElement('div');
  panel.style.cssText = 'position:fixed;left:12px;bottom:12px;max-width:340px;max-height:60vh;overflow:auto;z-index:9;padding:12px;border-radius:8px;font-size:13px;line-height:1.5;background:var(--panel,#1a1a2e);color:var(--text,#e0e0e0);border:1px solid var(--border,#2a2a4e);box-shadow:0 4px 18px rgba(0,0,0,.4)';
  var h = document.createElement('div'); h.style.fontWeight = '600'; h.textContent = F.title; panel.appendChild(h);
  function line(color, text) {
    var d = document.createElement('div'); var s = document.createElement('span');
    s.style.cssText = 'display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:' + color;
    d.appendChild(s); d.appendChild(document.createTextNode(text)); panel.appendChild(d);
  }
  line(COL.a, F.primary.length + (F.mode === 'design' ? ' named in the design' : ' changed'));
  if (F.planned.length) line(COL.p, F.planned.length + ' named in the design, not changed yet');
  line(COL.s, F.secondary.length + ' more in the same files');
  line(COL.n, F.neighbors.length + ' linked to them');
  if (F.skipped.length) { var sk = document.createElement('div'); sk.style.cssText = 'color:var(--text-2,#aaa);margin-top:4px'; sk.textContent = 'Too common to place: ' + F.skipped.join(', '); panel.appendChild(sk); }
  var row = document.createElement('div'); row.style.cssText = 'margin:8px 0;display:flex;gap:6px;flex-wrap:wrap';
  var btn1 = document.createElement('button'), btn2 = document.createElement('button');
  [btn1, btn2].forEach(function (b) { b.style.cssText = 'cursor:pointer;padding:3px 8px;border-radius:5px;border:1px solid var(--border,#2a2a4e);background:var(--bg,#0f0f1a);color:var(--text,#e0e0e0);font-size:12px'; row.appendChild(b); });
  btn1.onclick = function () { on = !on; paint(); };
  btn2.onclick = function () { only = !only; on = true; paint(); };
  panel.appendChild(row);
  F.primary.concat(F.planned).slice(0, 60).forEach(function (id) {
    var a = document.createElement('div');
    a.style.cssText = 'cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:1px 4px;border-radius:3px';
    a.textContent = (F.labels[id] || id) + ' · ' + (F.reasons[id] || '');
    a.title = a.textContent;
    a.onmouseenter = function () { a.style.background = 'var(--border,#2a2a4e)'; };
    a.onmouseleave = function () { a.style.background = ''; };
    a.onclick = function () { on = true; paint(); network.selectNodes([id]); network.focus(id, { scale: 1.1, animation: true }); };
    panel.appendChild(a);
  });
  document.body.appendChild(panel);
  paint();
  var fitted = false;
  function fit() { if (fitted || !F.primary.length) return; fitted = true; try { network.fit({ nodes: F.primary, animation: true }); } catch (e) {} }
  network.once('stabilized', fit);
  setTimeout(fit, 3500);
})();
"""


def render(html, result):
    """graphify's graph.html with the tiers painted on and a panel to turn them on and off. The original is not changed."""
    if result["mode"] not in TITLE:
        return html
    data = dict(result, title=TITLE.get(result["mode"], "Code graph"))
    js = PANEL_JS.replace("__FOCUS__", json.dumps(data, ensure_ascii=True).replace("</", "<\\/"))
    block = f"<script id=\"sdd-graph-focus\">{js}</script>\n"
    i = html.rfind("</body>")
    return html[:i] + block + html[i:] if i >= 0 else html + block
