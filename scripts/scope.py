"""The feature or epic around a work item, for the spec and bug flows: the designs agreed above an item (so its
own work starts from them and does not ask again what they settled), and the items a feature or epic built as one
piece of work covers (so the flow claims, links and hands over each of them).

Pure functions of metrics.json's items (spec.py writes it on every sync) and of file texts; env.py does the I/O.

    an agreed design   {specFolder}/design-agreed.json, written by env.py when "Design agreed" passes on any spec item,
                       taken away when the gate is revoked
    members            workitem.json "members": the items under a Feature or Epic that a whole build covers,
                       picked by the user (env.py members --set)
    the work item plan "## Work item plan" in a Feature's or Epic's design.md: per item under it, where its work
                       starts and stops, what is in and out of its scope, what it needs from other items and what
                       they need from it, the decisions made. env.py plan writes each item's part to that item's
                       Implementation Plan field (the whole design to the feature or epic itself), and links the
                       items it orders as predecessor and successor
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
    return questions(questions_text, wid, ticked=True)


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


# --- the work item plan: a feature's or epic's agreed design, cut per work item into its Implementation Plan ---------
#
# Another developer's workspace has none of this one's spec files; the board is what both see. So when "Design agreed"
# passes on a Feature or Epic, env.py plan writes one block into the Implementation Plan field of the item itself (the
# whole design) and of each item its plan names (only that item's part). env.py upstream reads them back. A block
# opens and closes with a line that says where it is from, so the field keeps anything else written in it:
#
#     sdd plan: Feature ADO 900 for ADO 901, agreed 2026-10-22
#     ...
#     end of sdd plan from ADO 900
#
# The plan in design.md, one entry per item (a heading naming it, then `- Key: value` lines; an indented `-` line
# under a key adds to it):
#
#     ## Work item plan
#     ### ADO 901 CSV export
#     - Starts: the exporter interface ADO 902 builds
#     - Stops: a CSV file the user downloads
#     - In scope: the CSV writer
#     - Out of scope: PDF output (ADO 902); scheduled exports (not planned)
#     - Needs: ADO 902 (the exporter interface)
#     - Gives: ADO 903 (the CSV writer, for the scheduler)
#     - Decision: amounts in cents

PLAN_HEADING = re.compile(r"(#{1,6})\s+work\s+item\s+plan\b", re.I)
KEYS = {"starts": "starts", "start": "starts", "stops": "stops", "stop": "stops", "in scope": "in",
        "out of scope": "out", "needs": "needs", "need": "needs", "gives": "gives", "give": "gives",
        "decision": "decisions", "decisions": "decisions"}
PARTS = [("starts", "Where the work starts"), ("stops", "Where the work stops"), ("in", "In scope"),
         ("out", "Out of scope: built by other work items, or not planned"),
         ("needs", "Needs from other work items (its predecessors)"),
         ("gives", "Required by other work items (its successors)"), ("decisions", "Decisions already made"),
         ("settled", "Settled questions: do not ask again"), ("open", "Open questions for this item"),
         ("design", "The whole design")]
TITLES = {t: k for k, t in PARTS}
MAX_BLOCK = 30000  # characters of HTML a block may take; the field holds others' blocks and text too
_HEAD = re.compile(r"sdd plan:\s*([A-Za-z][\w ]*?)\s+ADO\s+(\d+)\s+for\s+ADO\s+(\d+)(?:,\s*agreed\s+([\d-]+))?", re.I)


def ids_in(text):
    """The `ADO <id>` (or AB#<id>) a text names, in order, once each."""
    out = []
    for m in re.finditer(r"(?i)(?:\bADO\s*|AB#)(\d+)\b", text or ""):
        if int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def questions(questions_text, wid=None, ticked=True, tagged_only=False):
    """questions.md lines, without the box: the ticked (or open) ones that hold for `wid` (tagged `(ADO <wid>)`,
    or untagged unless `tagged_only`); every ticked (or open) one when `wid` is None."""
    out = []
    for ln in (questions_text or "").splitlines():
        m = re.match(r"\s*[-*]\s*\[([ xX])\]\s*(.+)", ln)
        if not m or (m.group(1) != " ") != ticked:
            continue
        tags = re.findall(r"\(ADO\s*(\d+)\)", m.group(2))
        if wid is None or (str(int(wid)) in tags) or (not tags and not tagged_only):
            out.append(m.group(2).strip())
    return out


def item_plan(design_text):
    """The "## Work item plan" of a design: (found, {id: {title, starts, stops, in, out, needs, gives, decisions}})."""
    found, level, plan, cur, key = False, 0, {}, None, None
    for ln in (design_text or "").splitlines():
        h = re.match(r"(#{1,6})\s+(.*)", ln)
        if h:
            if not found:
                if PLAN_HEADING.match(ln):
                    found, level = True, len(h.group(1))
                continue
            if len(h.group(1)) <= level:
                break  # the next part of the design
            ids = ids_in(h.group(2))
            cur, key = (ids[0] if ids else None), None
            if cur is not None:
                plan.setdefault(cur, {"title": h.group(2).strip(), **{k: [] for k, _ in PARTS[:7]}})
            continue
        if not found or cur is None:
            continue
        top = re.match(r"[-*]\s+([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)", ln)
        sub = re.match(r"\s{2,}[-*]\s+(.*)", ln)
        if top and top.group(1).strip().lower() in KEYS:
            key = KEYS[top.group(1).strip().lower()]
            if top.group(2).strip():
                plan[cur][key].append(top.group(2).strip())
        elif sub and key:
            plan[cur][key].append(sub.group(1).strip())
        elif ln.strip() and key and plan[cur][key] and ln.startswith((" ", "\t")):
            plan[cur][key][-1] += " " + ln.strip()
    return found, plan


def edges(plan):
    """(predecessor, successor) pairs the plan orders: X's `Needs: ADO Y` is Y before X; `Gives: ADO Z` is X before Z."""
    out = set()
    for wid, e in plan.items():
        for line in e["needs"]:
            out |= {(y, wid) for y in ids_in(line) if y != wid}
        for line in e["gives"]:
            out |= {(wid, z) for z in ids_in(line) if z != wid}
    return sorted(out)


def cycle(pairs):
    """One loop in the order, as [a, b, ..., a], or None."""
    nxt = {}
    for a, b in pairs:
        nxt.setdefault(a, []).append(b)
    state = {}

    def walk(n, path):
        state[n] = 1
        for m in nxt.get(n, []):
            if state.get(m) == 1:
                return path[path.index(m):] + [m]
            if not state.get(m):
                got = walk(m, path + [m])
                if got:
                    return got
        state[n] = 2
        return None
    for n in sorted(nxt):
        if not state.get(n):
            got = walk(n, [n])
            if got:
                return got
    return None


def plan_problems(design_text, items, wid, done_states):
    """What stops a Feature's or Epic's design from being agreed: no work item plan; an open item directly under it
    with no entry; an entry for an item not under it; an entry without where it starts, where it stops and what is in
    scope; something out of scope that says neither who builds it nor "not planned"; an order that names no item, an
    item not under it, or goes round in a loop."""
    found, plan = item_plan(design_text)
    if not found:
        return ["design.md has no \"## Work item plan\": an entry per item under it, with where its work starts and "
                "stops, in and out of scope, what it needs and gives (see the Design stage, step 6)"]
    out, mine = [], set(under(items, wid))
    missing = [c for c in open_children(items, wid, done_states) if c not in plan]
    if missing:
        out.append("the work item plan has no entry for " + ", ".join(f"ADO {c}" for c in missing))
    for i, e in sorted(plan.items()):
        if i not in mine:
            out.append(f"the work item plan has an entry for ADO {i}, which is not under {wid}")
            continue
        lack = [t for k, t in (("starts", "Starts"), ("stops", "Stops"), ("in", "In scope")) if not e[k]]
        if lack:
            out.append(f"ADO {i}'s entry has no {', no '.join(lack)}")
        for line in e["out"]:
            if not ids_in(line) and "not planned" not in line.lower():
                out.append(f"ADO {i}'s out of scope \"{line[:60]}\" names neither the item that builds it (ADO <id>) "
                           "nor \"not planned\"")
        for k, word in (("needs", "Needs"), ("gives", "Gives")):
            for line in e[k]:
                named = ids_in(line)
                if not named:
                    out.append(f"ADO {i}'s {word} \"{line[:60]}\" names no work item (ADO <id>)")
                bad = [n for n in named if n not in mine]
                if bad:
                    out.append(f"ADO {i}'s {word} names " + ", ".join(f"ADO {n}" for n in bad) + f", not under {wid}")
    loop = cycle(edges(plan))
    if loop:
        out.append("the work item plan orders a loop: " + " before ".join(f"ADO {n}" for n in loop))
    return out


def plan_targets(design_text, items, wid, done_states):
    """Who gets a block: the item itself, then each open item the plan has an entry for."""
    low = {s.lower() for s in done_states} | {"removed"}
    _, plan = item_plan(design_text)
    return [int(wid)] + [i for i in sorted(plan) if str(i) in items
                         and (items[str(i)].get("state") or "").lower() not in low and not items[str(i)].get("removed")]


def block_md(src, target, design_text, questions_text, agreed_at):
    """The block for `target` from `src` ({id, type, title}), as markdown: only what that item needs to do its work.
    The block for `src` itself carries the whole design."""
    sid, tid = int(src["id"]), int(target)
    lines = [f"**sdd plan: {src['type']} ADO {sid} for ADO {tid}, agreed {(agreed_at or '')[:10]}**", ""]
    if tid == sid:
        lines += [f"The agreed design of {src['type']} ADO {sid}: {src.get('title') or ''}. Each item under it carries "
                  "its own part in its Implementation Plan.", "", f"### {dict(PARTS)['design']}", "",
                  (design_text or "").strip(), ""]
        settled, still = questions(questions_text), questions(questions_text, ticked=False)
    else:
        _, plan = item_plan(design_text)
        e = plan.get(tid) or {k: [] for k, _ in PARTS[:7]}
        needs, gives = list(e["needs"]), list(e["gives"])
        def about(other, ln):  # another entry's line about this item, as this item's own line would say it
            rest = re.sub(r"(?i)(?:\bADO\s*|AB#)" + str(tid) + r"\b", "", ln).strip(" :-")
            rest = rest[1:-1].strip() if rest.startswith("(") and rest.endswith(")") else rest
            return f"ADO {other} ({rest})" if rest else f"ADO {other}"
        for other, oe in sorted(plan.items()):  # what the other entries say about this one
            if other == tid:
                continue
            needs += [about(other, ln) for ln in oe["gives"] if tid in ids_in(ln) and other not in
                      [y for n in e["needs"] for y in ids_in(n)]]
            gives += [about(other, ln) for ln in oe["needs"] if tid in ids_in(ln) and other not in
                      [z for g in e["gives"] for z in ids_in(g)]]
        lines += [f"Part of {src['type']} ADO {sid}: {src.get('title') or ''}. Build only what is in scope here: what is "
                  f"out of scope is another work item's, and the whole design is in ADO {sid}'s Implementation Plan.", ""]
        for k, title in PARTS[:7]:
            vals = {"needs": needs, "gives": gives}.get(k, e[k])
            lines += [f"### {title}", ""] + ([f"- {v}" for v in vals] or ["- (none)"]) + [""]
        settled = questions(questions_text, tid, ticked=True, tagged_only=True)
        still = questions(questions_text, tid, ticked=False, tagged_only=True)
    lines += [f"### {dict(PARTS)['settled']}", ""] + ([f"- {q}" for q in settled] or ["- (none)"]) + [""]
    lines += [f"### {dict(PARTS)['open']}", ""] + ([f"- {q}" for q in still] or ["- (none)"]) + [""]
    lines += [f"end of sdd plan from ADO {sid}"]
    return "\n".join(lines).strip() + "\n"


def _inline(s):
    s = html_escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_html(md):
    """The little markdown a design uses, as the HTML an ADO rich-text field takes. The block's own parts are <h3>;
    the design's headings become <h4>, so a block read back finds its parts."""
    out, lst, fence, code = [], False, False, []
    for ln in (md or "").splitlines():
        if ln.strip().startswith("```"):
            if fence:
                out.append("<pre>" + html_escape("\n".join(code)) + "</pre>")
                code = []
            elif lst:
                out.append("</ul>")
                lst = False
            fence = not fence
            continue
        if fence:
            code.append(ln)
            continue
        m = re.match(r"\s*(?:[-*+]|\d+[.)])\s+(.*)", ln)
        if m:
            if not lst:
                out.append("<ul>")
                lst = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        if lst:
            out.append("</ul>")
            lst = False
        h = re.match(r"(#{1,6})\s+(.*)", ln)
        if h:
            tag = "h3" if len(h.group(1)) == 3 and h.group(2) in TITLES else "h4"
            out.append(f"<{tag}>{_inline(h.group(2))}</{tag}>")
        elif ln.strip():
            out.append(f"<div>{_inline(ln.strip())}</div>")
    if fence:
        out.append("<pre>" + html_escape("\n".join(code)) + "</pre>")
    if lst:
        out.append("</ul>")
    return "\n".join(out)


def html_to_md(text):
    """A rich-text field's HTML back as plain markdown: a block's parts as `### `, the design's headings as `#### `."""
    s = text or ""
    s = re.sub(r"(?is)<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + m.group(1) + "\n```\n", s)
    s = re.sub(r"(?is)<h3[^>]*>(.*?)</h3>", r"\n### \1\n", s)
    s = re.sub(r"(?is)<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n#### \1\n", s)
    s = re.sub(r"(?is)<li[^>]*>", "\n- ", s)
    s = re.sub(r"(?is)<code[^>]*>(.*?)</code>", r"`\1`", s)
    s = re.sub(r"(?is)<b[^>]*>(.*?)</b>|<strong[^>]*>(.*?)</strong>", lambda m: "**" + (m.group(1) or m.group(2) or "") + "**", s)
    s = re.sub(r"(?is)<br\s*/?>|</(div|p|li|ul|ol)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'") \
        .replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def _end(sid):
    return f"end of sdd plan from ADO {int(sid)}"


def merge_block(field_html, sid, block_html):
    """The field with the block from `sid` put in: in place of the one there, else after what the field holds.
    Everything else in the field (other blocks, a person's own text) stays as it is."""
    field_html = field_html or ""
    m = re.search(r"sdd plan:\s*[A-Za-z][\w ]*?\s+ADO\s+" + str(int(sid)) + r"\s+for\s+ADO\s+\d+", field_html)
    end = field_html.find(_end(sid), m.end()) if m else -1
    if not m or end < 0:
        return (field_html.rstrip() + "\n" if field_html.strip() else "") + block_html
    start = field_html.rfind("<div", 0, m.start())
    start = start if start >= 0 else m.start()
    close = field_html.find("</div>", end)
    stop = close + len("</div>") if close >= 0 else end + len(_end(sid))
    return field_html[:start] + block_html + field_html[stop:]


def read_blocks(field_html):
    """The sdd plan blocks in an Implementation Plan field: [{head: (type, source id, for id, date), md}]."""
    out, cur = [], None
    for ln in html_to_md(field_html).splitlines():
        m = _HEAD.search(ln.replace("**", ""))
        if m:
            cur = {"head": (m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4) or ""), "lines": [ln]}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
            if ln.strip() == _end(cur["head"][1]):
                cur = None
    return [{"head": b["head"], "md": "\n".join(b["lines"]).strip() + "\n"} for b in out]


def block_parts(md):
    """A block read back, by part: {starts, stops, in, out, needs, gives, decisions, settled, open: [lines]}.
    A part's title may come back as a heading or, if the field dropped the heading, in bold."""
    part, out = None, {k: [] for k, _ in PARTS}
    for ln in (md or "").splitlines():
        t = ln.lstrip("#* ").rstrip("* ")
        if ln.startswith(("#", "**")) and t in TITLES:
            part = TITLES[t]
        elif part and ln.startswith("#"):
            part = None
        elif part and part != "design" and ln.startswith("- ") and ln[2:].strip() != "(none)":
            out[part].append(ln[2:].strip())
    return out


def pick_plans(chain, found):
    """The blocks that hold for chain[0]: from each item above it, the one meant for the nearest item of the chain
    (the item itself, then its parent, ...). chain: [wid, parent, grandparent, ...]. found: [{head, ...}]
    -> {source id: that block}, nearest source first."""
    pos = {int(c): n for n, c in enumerate(chain)}
    best = {}
    for b in found:
        _, src, for_id, _ = b["head"]
        if src not in pos or src == chain[0] or for_id not in pos or pos[for_id] > pos[src]:
            continue
        if src not in best or pos[for_id] < pos[best[src]["head"][2]]:
            best[src] = b
    return dict(sorted(best.items(), key=lambda kv: pos[kv[0]]))
