"""Which work item to take next, under an epic or feature: the team's rules as plain functions.

A candidate is an implementable item (a Bug, Issue, User Story, Tech Story, Change Request or PBI)
under the scope, tagged with the dev's team version, not done, not past dev on the board, and not
someone else's work in progress (assigned to someone else AND Active or in Dev In Progress).

Blocking is a judgement, never ADO's Blocked field: this file gathers the evidence (a predecessor
link, a mention of another item in the text, both not done) and the agent decides, with a reason
(spec.py next-judge). A judgement holds while its evidence is unchanged.

Order: bugs and issues first, then the rest (`types` in sdd.json "next"); within each, the dev
priority — a weighted score of priority, severity and complexity, 0–100, highest first.
Complexity comes from the effort field, else from the agent's estimate (1–5, with a reason).
"""
import hashlib
import json
import re

MENTION = re.compile(r"\b(?:ADO|CR|US|TS|PBI|Bug|Issue|Story|item)\s*#?(\d{3,})\b|(?<![\w&/])#(\d{3,})\b", re.I)
PREDECESSOR = {"predecessor", "dependency-reverse"}


def low(s):
    return (s or "").strip().lower()


def tags_of(row):
    return {t.strip() for t in (row.get("tags") or "").split(";") if t.strip()}


def level(v):
    """ADO's 1 (highest) … 4 (lowest): from 2, or from "2 - High". None when absent."""
    m = re.match(r"\s*(\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else None


def complexity_from_effort(effort):
    """Story points (or effort, size) on a 1–5 scale; None when the item has no number."""
    try:
        e = float(effort)
    except (TypeError, ValueError):
        return None
    if e <= 0:
        return None
    return 1 if e <= 1 else 2 if e <= 2 else 3 if e <= 3 else 4 if e <= 5 else 5


def tier(row, rule):
    """0 for the first group in `types` (bugs and issues), 1 for the next, …; None when not a work type."""
    for i, group in enumerate(rule["types"]):
        if row["type"] in group:
            return i
    return None


def availability(row, version, me, rule, done_states):
    """(available, why not, note). `me` is the dev's email."""
    if low(row.get("state")) in {low(s) for s in done_states} | {"removed"} or row.get("removed"):
        return False, f"{row['state']}", ""
    if low(row.get("board")) in {low(b) for b in rule["pastDev"]}:
        return False, f"board column {row['board']}", ""
    if version not in tags_of(row):
        vs = sorted(t for t in tags_of(row) if re.fullmatch(r"\d+(\.\d+)+", t))
        return False, f"tagged {', '.join(vs)} not {version}" if vs else f"no {version} tag", ""
    who = low(row.get("assigned_email")) or low(row.get("assigned"))
    mine = bool(who) and who == low(me)
    if who and not mine:
        busy = (low(row.get("state")) in {low(s) for s in rule["inProgress"]["states"]}
                or low(row.get("board")) in {low(b) for b in rule["inProgress"]["boards"]})
        if busy:
            return False, f"{row.get('assigned') or who} is working on it ({row['state']}, {row.get('board') or 'no board column'})", ""
        return True, "", f"on {row.get('assigned') or who}'s name, not started: taking it needs claim --take"
    return True, "", "yours" if mine else "unassigned"


def evidence(row, out_links, items, done_states):
    """What might block `row`: predecessor links and mentions in its text of items that are not done.
    `out_links` [(rel name, target id)], `items` {id: index row}. -> [{id, kind, state, title, text}]"""
    done = {low(s) for s in done_states} | {"removed"}
    found, seen = [], set()

    def add(wid, kind, text=""):
        t = items.get(wid)
        if wid == row["id"] or wid in seen or not t or low(t.get("state")) in done:
            return
        seen.add(wid)
        found.append({"id": wid, "kind": kind, "state": t.get("state"), "board": t.get("board") or "",
                      "title": t.get("title"), "text": text})

    for name, dst in out_links:
        if low(name).replace(" ", "-") in PREDECESSOR:
            add(dst, "predecessor link")
    body = row.get("body") or ""
    for m in MENTION.finditer(body):
        wid = int(m.group(1) or m.group(2))
        a, b = max(0, m.start() - 60), min(len(body), m.end() + 60)
        add(wid, "named in the text", " ".join(body[a:b].split()))
    return found


def evidence_key(evs):
    return hashlib.sha256(json.dumps([[e["id"], e["kind"], e["state"]] for e in evs]).encode()).hexdigest()[:12]


def dev_priority(row, complexity, rule):
    """0–100: the weighted mean of priority, severity and complexity, each 0..1, higher sooner.
    An absent priority or severity counts as the middle (0.5)."""
    w = rule["weights"]
    p, s = level(row.get("priority")), level(row.get("severity"))
    ps = (4 - min(max(p, 1), 4)) / 3 if p else 0.5
    ss = (4 - min(max(s, 1), 4)) / 3 if s else 0.5
    c = (complexity - 1) / 4 if complexity else 0.5
    cs = c if rule["complexity"] == "complex-first" else 1 - c
    total = w["priority"] + w["severity"] + w["complexity"]
    return round(100 * (w["priority"] * ps + w["severity"] * ss + w["complexity"] * cs) / total, 1)


def plan(rows, links, scope, version, me, rule, done_states, judged):
    """Sort the scope's items into ranked / needs a judgement / blocked / not available.
    rows {id: index row}, links {id: [(rel name, target)]}, judged {id: {...}} from next.json."""
    kids = {}
    for r in rows.values():
        kids.setdefault(r.get("parent"), []).append(r["id"])
    under, todo = [], [scope]
    while todo:
        for k in sorted(kids.get(todo.pop(), [])):
            under.append(k)
            todo.append(k)
    ranked, needs, blocked, unavailable = [], [], [], []
    for wid in under:
        r = rows[wid]
        t = tier(r, rule)
        if t is None:
            continue
        ok, why, note = availability(r, version, me, rule, done_states)
        if not ok:
            unavailable.append({"id": wid, "type": r["type"], "title": r["title"], "why": why})
            continue
        j = judged.get(str(wid)) or {}
        evs = evidence(r, links.get(wid, []), rows, done_states)
        key = evidence_key(evs)
        item = {"id": wid, "type": r["type"], "title": r["title"], "tier": t, "note": note,
                "priority": level(r.get("priority")), "severity": level(r.get("severity")),
                "assigned": r.get("assigned") or "", "evidence": evs}
        ask = []
        b = j.get("blocked")
        if evs and not (b and b.get("key") == key):
            ask.append("blocked")
        c = complexity_from_effort(r.get("effort"))
        item["complexitySource"] = f"effort {r.get('effort')}" if c else ""
        if not c:
            est = j.get("complexity")
            if est and est.get("hash") == r.get("hash"):
                c, item["complexitySource"] = est["value"], f"estimated: {est['reason']}"
            else:
                ask.append("complexity")
        item["complexity"] = c
        if ask:
            needs.append({**item, "ask": ask})
        elif evs and b["value"]:
            blocked.append({**item, "reason": b["reason"]})
        else:
            item["devPriority"] = dev_priority(r, c, rule)
            if evs:
                item["notBlocked"] = b["reason"]
            ranked.append(item)
    ranked.sort(key=lambda x: (x["tier"], -x["devPriority"], x["id"]))
    return {"scope": scope, "version": version, "ranked": ranked, "needs": needs, "blocked": blocked,
            "unavailable": unavailable}
