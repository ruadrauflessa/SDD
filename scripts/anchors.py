"""Design anchors against the code graph: each component design.md names is a node in the graph, or new.

design.md's "## Affected components" table names what the change touches, one row per component:

    | Component | Change | Graph node | Notes |
    | `Exporter/export.py` | modified | `exporter_export_fmt_total` | ... |
    | `Exporter/csv_writer.py` | new | new | ... |

The Graph node is the node id `graphify explain "<name>" --graph <folder>/graph/graph.json` prints
(several ids are separated by commas). `check` passes a row when:
  modified / removed  every id is a node of graph.json, and when the component is a path, each node's
                      source file lies at or under it
  new                 the node is `new`, and a component given as a path does not exist in src/ yet
`env.py anchors` runs it on the item's design.md and graph and records the result as the proof the
"Design agreed" gate needs (flows.json "proofs"). Plain functions: no git, no ADO.
"""
import json
import re
from pathlib import Path

HEADING = re.compile(r"^##\s+Affected components\s*$", re.I)
CHANGES = ("new", "modified", "removed")
PLACEHOLDER = re.compile(r"^\{.*\}$")


def _cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def _plain(cell):
    return re.sub(r"[`*]", "", cell or "").strip()


def parse(text):
    """The Affected components table -> (rows, problems). A row is {line, component, change, nodes}:
    `nodes` is the list of ids, or ["new"]. Problems are about the table itself."""
    lines = (text or "").splitlines()
    start = next((i for i, x in enumerate(lines) if HEADING.match(x)), None)
    if start is None:
        return [], ["design.md has no \"## Affected components\" section"]
    header, rows = None, []
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("## "):
            break
        cells = _cells(line)
        if cells is None:
            continue
        if header is None:
            header = [_plain(c).lower() for c in cells]
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue  # the |---| line
        row = dict(zip(header, cells))
        rows.append({"line": i + 1, "component": _plain(row.get("component")),
                     "change": _plain(row.get("change")).lower().split(" ")[0] if row.get("change") else "",
                     "nodes": [n for n in (_plain(x) for x in (row.get("graph node") or "").split(",")) if n]})
    if header is None:
        return [], ["the Affected components section has no table"]
    if "graph node" not in header:
        return [], ["the Affected components table has no Graph node column: add it (see assets/design.md.template)"]
    if not rows:
        return [], ["the Affected components table names no components"]
    return rows, []


def load_nodes(graph_json):
    """{node id: node} from a graphify graph.json (networkx node-link data)."""
    data = json.loads(Path(graph_json).read_text(encoding="utf-8"))
    return {str(n["id"]): n for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n}


def _norm(p):
    p = (p or "").replace("\\", "/").strip().strip("/")
    p = re.sub(r"^\./", "", p)
    return re.sub(r"^src/", "", p, flags=re.I)  # a path given from the work item folder


def is_path(component):
    return "/" in component or "\\" in component or re.search(r"\.\w{1,6}$", component) is not None


def under(source_file, component):
    """The node's source file is the component, inside it, or ends with it (a path without the repo)."""
    sf, comp = "/" + _norm(source_file).casefold() + "/", "/" + _norm(component).casefold() + "/"
    return comp != "//" and comp in sf


def exists(src, component):
    """The component's path is in src/, given from src/ or from inside one of its repos."""
    rel = _norm(component)
    if not rel or not Path(src).is_dir():
        return False
    return (Path(src) / rel).exists() or any((d / rel).exists() for d in Path(src).iterdir() if d.is_dir())


def check(rows, nodes, src):
    """-> (results, problems). Each result is the row with "ok" and, for a found node, "found":
    [(id, source_file, location)]."""
    results, problems = [], []
    for r in rows:
        comp, change, ids = r["component"], r["change"], r["nodes"]
        where = f"design.md:{r['line']} {comp or '(no component)'}"
        bad = []
        if not comp or PLACEHOLDER.match(comp):
            bad.append("the component is empty or still the template's placeholder")
        if change not in CHANGES:
            bad.append(f"Change is '{change or 'empty'}'; write new, modified or removed")
        found = []
        if change == "new":
            if [i.lower() for i in ids] != ["new"]:
                bad.append("a new component has no graph node yet: write `new` in Graph node")
            elif comp and is_path(comp) and exists(src, comp):
                bad.append("is marked new but already exists in src/: mark it modified and name its graph node")
        elif change in ("modified", "removed"):
            if not ids or [i.lower() for i in ids] == ["new"]:
                bad.append(f"a {change} component needs its graph node: find it with "
                           f"graphify explain \"<name>\" --graph <folder>/graph/graph.json")
            for i in ids:
                n = nodes.get(i)
                if n is None:
                    bad.append(f"no node '{i}' in the graph (rebuild it with env.py graph if the code changed, "
                               "or copy the ID line graphify explain prints)")
                    continue
                found.append((i, n.get("source_file") or "", n.get("source_location") or ""))
                if comp and is_path(comp) and not under(n.get("source_file") or "", comp):
                    bad.append(f"node '{i}' is in {n.get('source_file') or 'no file'}, not in {comp}")
        problems += [f"{where}: {b}" for b in bad]
        results.append({**r, "ok": not bad, "found": found})
    return results, problems
