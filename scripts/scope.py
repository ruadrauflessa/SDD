"""The feature or epic around a work item, for the spec and bug flows: the designs agreed above an item (so its
own work starts from them and does not ask again what they settled), and the items a feature or epic built as one
piece of work covers (so the flow claims, links and hands over each of them).

Pure functions of metrics.json's items (spec.py writes it on every sync) and of file texts; env.py does the I/O.

    an agreed design   {specFolder}/design-agreed.json, written by env.py when "Design agreed" passes on any spec item,
                       taken away when the gate is revoked
    members            workitem.json "members": the items under a Feature or Epic that a whole build covers,
                       picked by the user (env.py members --set)
"""
import re

CONTAINERS = ("Feature", "Epic")
DONE_FILE = "design-agreed.json"


def ancestors(items, wid):
    """[{id, type, title}] of `wid`, nearest first, from metrics.json items."""
    return list((items.get(str(wid)) or {}).get("ancestors") or [])


def under(items, wid):
    """Every item with `wid` among its ancestors, in id order."""
    return sorted((int(k) for k, v in items.items() if any(a["id"] == int(wid) for a in v.get("ancestors") or [])))


def direct_children(items, wid):
    return sorted(int(k) for k, v in items.items() if v.get("parent") == int(wid))


def mentions(text, wid):
    """`ADO 603` (or AB#603) in a text: how a design or a task list names a work item."""
    return bool(re.search(r"(?i)(?:\bADO\s*|AB#)" + str(int(wid)) + r"\b", text or ""))


def points_to(design_text, ancestor_id, folder_name):
    """Whether a design names the design above it: by `ADO <id>`, or by its spec folder's name."""
    return mentions(design_text, ancestor_id) or (folder_name and folder_name in (design_text or ""))


def answered_for(questions_text, wid):
    """The ticked questions of a design above that hold for `wid`: those tagged `(ADO <wid>)`, and the untagged ones
    (they are about the whole feature). [(question line without the box)]."""
    out = []
    for ln in (questions_text or "").splitlines():
        m = re.match(r"\s*[-*]\s*\[[xX]\]\s*(.+)", ln)
        if not m:
            continue
        tags = re.findall(r"\(ADO\s*(\d+)\)", m.group(1))
        if not tags or str(int(wid)) in tags:
            out.append(m.group(1).strip())
    return out


def open_children(items, wid, done_states):
    """The items directly under `wid` that are not done: what a design-only pass must think through."""
    low = {s.lower() for s in done_states} | {"removed"}
    return [c for c in direct_children(items, wid) if (items[str(c)].get("state") or "").lower() not in low]


def candidates(items, wid, work_types, me_email=""):
    """What a whole build of feature or epic `wid` could cover: the items under it that are work (stories, tech stories,
    bugs, issues; never a container), each with whether it is free, already yours, someone else's in progress, or done.
    [{id, type, title, state, assigned, parent, status}]."""
    me = (me_email or "").lower()
    out = []
    for i in under(items, wid):
        it = items[str(i)]
        if it.get("type") in CONTAINERS or it.get("type") not in work_types or it.get("removed") or it.get("missing"):
            continue
        mail = (it.get("assigned_email") or "").lower()
        if it.get("done"):
            status = "done"
        elif mail and me and mail == me:
            status = "yours"
        elif it.get("inProgress") and it.get("assigned"):
            status = "taken"
        else:
            status = "free"
        out.append({"id": i, "type": it.get("type"), "title": it.get("title"), "state": it.get("state"),
                    "assigned": it.get("assigned") or "", "parent": it.get("parent"), "status": status})
    return out


def uncovered(tasks_text, members):
    """The members no task in tasks.md names (`ADO <id>`)."""
    return [m for m in members if not mentions(tasks_text, m)]
