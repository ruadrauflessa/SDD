"""metrics.json: every synced work item with the facts a decision needs, and what the last sync changed.

Written by spec.py after every sync (and by `spec.py metrics`) to {specRoot}/.index/metrics.json.
Deterministic, from the index only — no model, no tokens. The judging half of an impact analysis
(sdd:impact) stays on demand: `changes[].affects` lists the candidates it would start from.

    {
      "generated_at": ..., "sync": {"at": ..., "scope": ...},
      "changes": [ {id, type, title, kind: new|material|incidental|missing,
                    fields: [material fields that changed], diff: {column: [was, now]},
                    affects: [{id, why}] } ],
      "items": { "<id>": { type, title, state, board, assigned, assigned_email, tags, versions,
                           priority, severity, effort, complexity, rank, target, iteration, area,
                           created, changed, parent, ancestors: [{id, type, title}], path,
                           done, inProgress, children: {total, open, done, inProgress, bugsOpen},
                           blockers: [...], blocking: [ids], links: {out, in},
                           lastChange: {at, kind, fields, diff} } }
    }
"""
import json
import re
from datetime import datetime, timezone

import nextpick

# columns compared between the old and the new row: what a person tracks, beside the requirement text
TRACKED = ["title", "state", "board", "assigned", "priority", "severity", "effort", "rank", "target", "blocked",
           "tags", "iteration", "area", "parent"]
BUGS = {"Bug", "Issue"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def diff(old, new):
    """{column: [was, now]} over TRACKED. A column the old row never had (NULL, from before it existed)
    is not a change."""
    if not old:
        return {}
    out = {}
    for c in TRACKED:
        if c not in old.keys() or old[c] is None:
            continue
        a, b = old[c], new.get(c)
        if str(a if a is not None else "") != str(b if b is not None else ""):
            out[c] = [a, b]
    return out


def build(rows, links, changes, prev, cfg, scope=None):
    """rows {id: index row}, links {id: [(rel, target)]}, changes [this sync's change records],
    prev = the last metrics.json (for lastChange) or {}."""
    done_states = {s.lower() for s in cfg["doneStates"]} | {"removed"}
    busy = cfg["next"]["inProgress"]
    is_done = lambda r: (r.get("state") or "").lower() in done_states or bool(r.get("removed"))
    is_busy = lambda r: ((r.get("state") or "").lower() in {s.lower() for s in busy["states"]}
                         or (r.get("board") or "").lower() in {b.lower() for b in busy["boards"]})
    kids = {}
    for r in rows.values():
        if r.get("parent"):
            kids.setdefault(r["parent"], []).append(r["id"])
    inbound = {}
    for src, outs in links.items():
        for _, dst in outs:
            inbound[dst] = inbound.get(dst, 0) + 1

    def descendants(wid):
        out, todo = [], [wid]
        while todo:
            for k in kids.get(todo.pop(), []):
                out.append(k)
                todo.append(k)
        return out

    blockers = {wid: nextpick.evidence(r, links.get(wid, []), rows, cfg["doneStates"]) for wid, r in rows.items()
                if not is_done(r)}
    blocking = {}
    for wid, evs in blockers.items():
        for e in evs:
            blocking.setdefault(e["id"], []).append(wid)
    last = {str(c["id"]): {"at": c["at"], "kind": c["kind"], "fields": c.get("fields", []), "diff": c.get("diff", {})}
            for c in changes}
    old_items = (prev or {}).get("items") or {}

    items = {}
    for wid, r in sorted(rows.items()):
        anc, p, seen = [], r.get("parent"), set()
        while p and p in rows and p not in seen:
            seen.add(p)
            anc.append({"id": p, "type": rows[p]["type"], "title": rows[p]["title"]})
            p = rows[p].get("parent")
        sub = [rows[k] for k in descendants(wid)]
        tags = sorted(nextpick.tags_of(r))
        items[str(wid)] = {
            "type": r["type"], "title": r["title"], "state": r["state"], "board": r.get("board") or "",
            "assigned": r.get("assigned") or "", "assigned_email": r.get("assigned_email") or "",
            "tags": tags, "versions": [t for t in tags if re.fullmatch(r"\d+(\.\d+)+", t)],
            "priority": nextpick.level(r.get("priority")), "severity": nextpick.level(r.get("severity")),
            "effort": r.get("effort") if r.get("effort") != "" else None,
            "complexity": nextpick.complexity_from_effort(r.get("effort")),
            "rank": r.get("rank") if r.get("rank") != "" else None, "target": r.get("target") or "",
            "iteration": r.get("iteration") or "", "area": r.get("area") or "", "created": r.get("created") or "",
            "changed": r.get("changed") or "", "parent": r.get("parent"), "ancestors": anc,
            "path": r.get("path"), "done": is_done(r), "inProgress": is_busy(r) and not is_done(r),
            "removed": bool(r.get("removed")), "missing": bool(r.get("missing")),
            "children": {"total": len(sub), "open": sum(not is_done(x) for x in sub),
                         "done": sum(is_done(x) for x in sub),
                         "inProgress": sum(is_busy(x) and not is_done(x) for x in sub),
                         "bugsOpen": sum(x["type"] in BUGS and not is_done(x) for x in sub)},
            "blockers": [{k: e[k] for k in ("id", "kind", "state")} for e in blockers.get(wid, [])],
            "blocking": sorted(blocking.get(wid, [])),
            "links": {"out": len(links.get(wid, [])), "in": inbound.get(wid, 0)},
            "lastChange": last.get(str(wid)) or (old_items.get(str(wid)) or {}).get("lastChange"),
        }
    return {"generated_at": now(), "sync": {"at": now(), "scope": scope}, "changes": changes, "items": items}
