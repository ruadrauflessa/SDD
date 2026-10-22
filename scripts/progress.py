"""progress.json: how far each epic (and each feature without an epic) is, from the synced specs.

Written by `spec.py progress` and after every sync to {specRoot}/.index/progress.json; the /sdd-progress page
reads it. Deterministic, from the index only: no ADO call, no model, no tokens. Pure functions, tested without ADO.

What counts. Features and stories (`work` types) are the work; bugs and issues (`defects`) are their own
metric and never part of an epic's completion. A work item counts once, as a leaf: a feature with stories
counts through its stories, a feature with none counts as itself. Each leaf is done, active (in progress),
todo (not started) or ignored (left out of every count), by the project's rules, in this order:

    removed in ADO                                   -> ignored
    "rules": the first that matches, top to bottom   -> its "as"
        {"field": "Custom.BoardColumnTitle", "values": ["Dev Completed", "QA Deployed"], "as": "done"}
        {"field": "System.State", "values": ["Active"], "and": {"Custom.BoardColumnTitle": ["New"]}, "as": "todo"}
      A field is any field of the item, by its reference name (the sync keeps every short field's value);
      values match whole, case aside; "and" adds fields that must match too.
    its state in "ignore" / "done" (or its board column in "doneBoards") / "todo"
    anything else                                    -> active

Three measures, all computed so the page switches at once; `measure` says which a project shows first:

    count     each leaf is 1
    points    each leaf's story points (the `effort` planning field); a leaf without them adds 0 and is counted in `missing`
    criteria  each leaf's acceptance criteria (struck-through ones are withdrawn, not counted); a leaf
              without any counts 1 and is counted in `missing`

    {
      "generated_at", "measures": [...], "projects": {"<project>": {rules, states: [{state, rule, count}]}},
      "tops": [ node ], "orphans": {"defects": n}
    }
    node = {id, type, title, state, status, project, url, assigned, partial,
            units: {count, points, criteria}            (a leaf's own)
            measures: {count|points|criteria: {total, done, active, todo, missing}},
            defects: {total, done, active, todo, high, items: [...]}, kids: [node]}
"""
import json
import re
from datetime import datetime, timedelta, timezone

MEASURES = ("count", "points", "criteria")
STATUSES = ("done", "active", "todo")
HISTORY_DAYS = 120
RULE_KEYS = ("measure", "work", "defects", "done", "todo", "ignore", "doneBoards", "rules")
AS = ("done", "active", "todo", "ignored")
# The index columns a field falls back to, for an item synced before the index kept every field's value
COLUMNS = {"System.State": "state", "System.WorkItemType": "type", "System.AreaPath": "area", "System.IterationPath": "iteration",
           "System.Tags": "tags", "System.AssignedTo": "assigned", "Custom.BoardColumnTitle": "board",
           "Microsoft.VSTS.Common.Priority": "priority", "Microsoft.VSTS.Common.Severity": "severity"}
# Fields no rule is about: ids, counters, people stamps, text. The Rules panel does not offer them.
NOT_RULES = {"system.id", "system.rev", "system.title", "system.teamproject", "system.parent", "system.commentcount",
             "system.watermark", "system.createdby", "system.changedby", "system.authorizedas", "system.personid",
             "system.nodename", "system.areaid", "system.iterationid", "system.arealevel1", "system.iterationlevel1",
             "system.history", "system.description", "system.tags"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rules_for(cfg, project):
    """The progress rules of one project: sdd.json "progress", its "projects.<project>" over it."""
    base = cfg["progress"]
    own = (base.get("projects") or {}).get(project) or {}
    r = {k: base.get(k) for k in RULE_KEYS}
    r.update({k: v for k, v in own.items() if k in RULE_KEYS})
    if not r.get("done"):
        r["done"] = list(cfg["doneStates"])
    if r.get("measure") not in MEASURES:
        r["measure"] = "count"
    r["rules"] = [x for x in (norm_rule(y) for y in (r.get("rules") or [])) if x]
    return r


def _low(xs):
    return {str(x).lower() for x in xs or []}


def norm_rule(r):
    """{"when": {field: [values]}, "as"} from {"field", "values", "and", "as"} (or {"when", "as"}); None when it is
    not a usable rule."""
    if not isinstance(r, dict) or r.get("as") not in AS:
        return None
    when = {}
    if isinstance(r.get("when"), dict):
        when.update(r["when"])
    if r.get("field"):
        when[r["field"]] = r.get("values")
    if isinstance(r.get("and"), dict):
        when.update(r["and"])
    out = {}
    for k, vs in when.items():
        vs = vs if isinstance(vs, list) else [vs] if vs is not None else []
        if str(k).strip() and vs:
            out[str(k).strip()] = [str(v) for v in vs]
    return {"when": out, "as": r["as"]} if out and len(out) == len(when) else None


def saved_rule(n):
    """A normalised rule as sdd.json keeps it: the first field as field/values, the rest under "and"."""
    (first, values), *rest = list(n["when"].items())
    out = {"field": first, "values": values}
    if rest:
        out["and"] = dict(rest)
    out["as"] = n["as"]
    return out


def fields_of(row):
    """{field, lowercase: value}: the values the index kept (fieldvals), and the index's own columns for the rest."""
    if "_f" not in row:
        try:
            kept = json.loads(row.get("fieldvals") or "{}")
        except ValueError:
            kept = {}
        out, names = {}, {}
        for k, v in (kept if isinstance(kept, dict) else {}).items():
            out[k.lower()], names[k.lower()] = v, k
        for name, col in COLUMNS.items():
            if name.lower() not in out and row.get(col) not in (None, ""):
                out[name.lower()], names[name.lower()] = row[col], name
        row["_f"], row["_names"] = out, names
    return row["_f"]


def matches(row, when):
    f = fields_of(row)
    for name, values in when.items():
        v = f.get(name.lower())
        have = "" if v is None else str(v).strip().lower()
        if have not in {str(x).strip().lower() for x in values}:
            return False
    return True


def status_of(row, rules):
    """done, active, todo or ignored, by the rules above."""
    if row.get("removed"):
        return "ignored"
    for r in rules.get("rules") or []:
        if matches(row, r["when"]):
            return r["as"]
    state = (row.get("state") or "").lower()
    if state in _low(rules["ignore"]):
        return "ignored"
    if state in _low(rules["done"]) or (row.get("board") or "").lower() in _low(rules.get("doneBoards")):
        return "done"
    if state in _low(rules["todo"]):
        return "todo"
    return "active"


def section(body, label):
    """The text under `## <label>` in an index row's body, up to the next `## `."""
    m = re.search(r"(?ms)^## " + re.escape(label) + r"\s*$(.*?)(?=^## |\Z)", body or "")
    return m.group(1).strip() if m else ""


def count_criteria(body):
    """(criteria, withdrawn) in a row's `## Acceptance criteria`. Struck-through text (~~...~~) is withdrawn.
    Numbered "Acceptance Criteria N" headings count first, then Given/Scenario lines, then list items, then
    paragraphs."""
    text = section(body, "Acceptance criteria")
    if not text:
        return 0, 0
    live = re.sub(r"~~.*?~~", "", text, flags=re.S)

    def count(t):
        named = set(re.findall(r"(?i)acceptance\s+criteri(?:a|on)\s*#?\s*(\d+)", t))
        if named:
            return len(named)
        given = re.findall(r"(?im)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?(?:scenario\b|given\b)", t)
        if given:
            return len(given)
        items = re.findall(r"(?m)^\s{0,3}(?:[-*+]|\d+[.)])\s+\S", t)
        if items:
            return len(items)
        return len([p for p in re.split(r"\n\s*\n", t) if p.strip()])
    total, kept = count(text), count(live)
    return kept, max(0, total - kept)


def points_of(row):
    v = row.get("effort")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def empty_measures():
    return {m: {"total": 0.0, "done": 0.0, "active": 0.0, "todo": 0.0, "missing": 0} for m in MEASURES}


def add(into, units, status, missing):
    for m in MEASURES:
        into[m]["total"] += units[m]
        into[m][status] += units[m]
        into[m]["missing"] += missing[m]


def build(rows, cfg, scopes=(), org="", previous=None):
    """rows {id: index row as a dict}; scopes: the synced scope roots ('123' or 'all:<project>')."""
    rules = {}

    def r_of(row):
        p = row.get("project") or ""
        if p not in rules:
            rules[p] = rules_for(cfg, p)
        return rules[p]
    kids = {}
    for row in rows.values():
        if row.get("parent") in rows:
            kids.setdefault(row["parent"], []).append(row["id"])
    for k in kids.values():
        k.sort()
    roots = {str(s) for s in scopes}

    def covered(wid, project):
        if f"all:{project}" in roots:
            return True
        seen, cur = set(), wid
        while cur is not None and cur not in seen:
            if str(cur) in roots:
                return True
            seen.add(cur)
            cur = (rows.get(cur) or {}).get("parent")
        return False

    def is_work(row):
        return row["type"] in r_of(row)["work"]

    def is_defect(row):
        return row["type"] in r_of(row)["defects"]

    def url(row):
        return f"https://dev.azure.com/{org}/{row.get('project', '')}/_workitems/edit/{row['id']}" if org else ""

    def defects_under(wid):
        out, todo = [], list(kids.get(wid, []))
        while todo:
            k = todo.pop()
            row = rows[k]
            if is_defect(row):
                out.append(row)
            todo += kids.get(k, [])
        return out

    def defect_metric(items):
        d = {"total": 0, "done": 0, "active": 0, "todo": 0, "high": 0, "items": []}
        for row in sorted(items, key=lambda x: x["id"]):
            st = status_of(row, r_of(row))
            if st == "ignored":
                continue
            d["total"] += 1
            d[st] += 1
            sev = str(row.get("severity") or "")
            high = st != "done" and (sev[:1] in ("1", "2") or str(row.get("priority") or "") == "1")
            d["high"] += int(high)
            d["items"].append({"id": row["id"], "type": row["type"], "title": row["title"], "state": row["state"],
                               "status": st, "high": high, "assigned": row.get("assigned") or "", "url": url(row)})
        return d

    def node(wid):
        row = rows[wid]
        rl = r_of(row)
        st = status_of(row, rl)
        work_kids = [k for k in kids.get(wid, []) if is_work(rows[k]) and status_of(rows[k], r_of(rows[k])) != "ignored"]
        n = {"id": wid, "type": row["type"], "title": row["title"], "state": row["state"], "status": st,
             "project": row.get("project") or "", "assigned": row.get("assigned") or "", "url": url(row),
             "board": row.get("board") or "", "measures": empty_measures(), "kids": []}
        if work_kids:
            for k in work_kids:
                child = node(k)
                n["kids"].append(child)
                for m in MEASURES:
                    for key in ("total", "done", "active", "todo", "missing"):
                        n["measures"][m][key] += child["measures"][m][key]
        elif st != "ignored" and is_work(row):  # a leaf: it counts as itself
            pts = points_of(row)
            crit, withdrawn = count_criteria(row.get("body"))
            n["units"] = {"count": 1, "points": pts or 0.0, "criteria": crit or 1}
            n["withdrawn"] = withdrawn
            add(n["measures"], n["units"], st, {"count": 0, "points": int(pts is None), "criteria": int(not crit)})
        n["defects"] = defect_metric(defects_under(wid))
        return n

    def top(row):
        """An epic, or a work item with no epic above it whose parent is not synced: the bars the page lists."""
        if row["type"] == "Epic":
            return True
        if not is_work(row) or (row.get("parent") in rows):
            return False
        return bool(kids.get(row["id"]))
    tops = []
    for wid in sorted(rows):
        row = rows[wid]
        if not top(row) or row.get("missing"):
            continue
        n = node(wid)
        n["partial"] = not covered(wid, row.get("project") or "")
        tops.append(round_tree(n))
    states = {}
    for row in rows.values():
        if is_work(row) or is_defect(row):
            p = row.get("project") or ""
            s = states.setdefault(p, {})
            s[row["state"]] = s.get(row["state"], 0) + 1
    plain = lambda p: dict(rules_for(cfg, p), rules=[])  # a state alone, as the rules' fallback reads it
    projects = {p: {"rules": dict(rules_for(cfg, p), rules=[saved_rule(x) for x in rules_for(cfg, p)["rules"]]),
                    "states": [{"state": st, "count": c, "rule": status_of({"state": st}, plain(p))}
                               for st, c in sorted(states.get(p, {}).items(), key=lambda kv: (-kv[1], kv[0]))],
                    "fields": field_catalog([r for r in rows.values() if (r.get("project") or "") == p and (is_work(r) or is_defect(r))])}
                for p in sorted(set(states) | set(rules))}
    placed = {d["id"] for t in tops for d in walk_defects(t)}
    orphans = sum(1 for row in rows.values() if is_defect(row) and row["id"] not in placed)
    return {"generated_at": now(), "measures": list(MEASURES), "projects": projects, "tops": tops,
            "orphans": {"defects": orphans}}


def field_catalog(rows, most=40):
    """[{field, values: [{value, count}]}]: the fields a rule can test in these items, with the values they hold.
    Only fields with a short list of values (a pick list, a board column, a state), never ids, dates or text."""
    seen, names = {}, {}
    for row in rows:
        f = fields_of(row)
        for k, v in f.items():
            if k in NOT_RULES or v in (None, "") or isinstance(v, bool):
                continue
            text = str(v)
            if len(text) > 80 or re.match(r"\d{4}-\d{2}-\d{2}T", text):
                continue
            names[k] = row["_names"].get(k, k)
            seen.setdefault(k, {})
            seen[k][text] = seen[k].get(text, 0) + 1
    first = {"system.state": 0, "custom.boardcolumntitle": 1, "system.boardcolumn": 2}
    out = [{"field": names[k], "values": [{"value": v, "count": c} for v, c in sorted(vals.items(), key=lambda kv: (-kv[1], kv[0]))]}
           for k, vals in seen.items() if 1 <= len(vals) <= most]
    return sorted(out, key=lambda x: (first.get(x["field"].lower(), 9), x["field"].lower()))


def walk_defects(n):
    return list(n["defects"]["items"])


def round_tree(n):
    for m in MEASURES:
        n["measures"][m] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in n["measures"][m].items()}
    for k in n["kids"]:
        round_tree(k)
    return n


def pct(m):
    return round(100.0 * m["done"] / m["total"], 1) if m.get("total") else 0.0


# ---------------------------------------------------------------- history: one line a day, for the trend

def snapshot(data):
    """{id: {measure: pct}} of every top."""
    return {str(t["id"]): {m: pct(t["measures"][m]) for m in MEASURES} for t in data["tops"]}


def add_history(lines, data, today=None):
    """The history with today's line put in (or replaced), oldest first, the last HISTORY_DAYS days."""
    day = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    kept = [x for x in lines if isinstance(x, dict) and x.get("day") and x["day"] != day]
    kept.append({"day": day, "pct": snapshot(data)})
    kept.sort(key=lambda x: x["day"])
    cut = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    return [x for x in kept if x["day"] >= cut]


def trend(lines, data, days=7, today=None):
    """{id: {measure: {delta, since}}}: the change since the newest line at least `days` old, else since the
    oldest line before today. Nothing for a top with no earlier line."""
    day = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    edge = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    before = [x for x in lines if x.get("day", "") < day]
    old = [x for x in before if x["day"] <= edge]
    ref = old[-1] if old else (before[0] if before else None)
    out = {}
    if not ref:
        return out
    now_ = snapshot(data)
    for wid, ms in now_.items():
        was = (ref.get("pct") or {}).get(wid)
        if not was:
            continue
        out[wid] = {m: {"delta": round(ms[m] - was.get(m, 0.0), 1), "since": ref["day"]} for m in MEASURES}
    return out


# ---------------------------------------------------------------- the Rules panel: a project's rules, checked

def rules_problems(done, todo, ignore, measure, rules=()):
    """What makes a rule set unusable: a rule with no field, values or outcome; nothing that counts as done; a
    state in two lists; an unknown measure."""
    out = []
    if measure not in MEASURES:
        out.append(f"measure must be one of {', '.join(MEASURES)}")
    normed = []
    for i, r in enumerate(rules, 1):
        n = norm_rule(r)
        if not n:
            out.append(f"rule {i} needs a field, at least one of its values, and what it counts as ({', '.join(AS)})")
        normed.append(n)
    if not [s for s in done if s.strip()] and not any(n and n["as"] == "done" for n in normed):
        out.append("at least one state or rule must count as done")
    seen = {}
    for name, xs in (("done", done), ("todo", todo), ("ignore", ignore)):
        for s in xs:
            k = s.strip().lower()
            if k in seen and seen[k] != name:
                out.append(f"{s.strip()} is both {seen[k]} and {name}")
            seen[k] = name
    return out


def set_project_rules(cfg_json, project, rules=None):
    """sdd.json (as a dict) with "progress.projects.<project>" set to `rules`, or taken out when rules is None.
    Every other key stays as it was."""
    out = json.loads(json.dumps(cfg_json))
    prog = out.get("progress") if isinstance(out.get("progress"), dict) else {}
    projects = prog.get("projects") if isinstance(prog.get("projects"), dict) else {}
    if rules is None:
        projects.pop(project, None)
    else:
        projects[project] = rules
    prog["projects"] = projects
    out["progress"] = prog
    return out
