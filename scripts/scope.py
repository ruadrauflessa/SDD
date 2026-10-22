"""The feature or epic around a work item, for the spec and bug flows: the designs agreed above an item (so its
own work starts from them and does not ask again what they settled), and the items a feature or epic built as one
piece of work covers (so the flow claims, links and hands over each of them).

Pure functions of metrics.json's items (spec.py writes it on every sync) and of file texts; env.py does the I/O.

    an agreed design   {specFolder}/design-agreed.json, written by env.py when "Design agreed" passes on any spec item,
                       taken away when the gate is revoked
    members            workitem.json "members": the items under a Feature or Epic that a whole build covers,
                       picked by the user (env.py members --set)
    a design brief     an ADO comment on a Feature or Epic and on each open item under it (env.py brief): the agreed
                       design, carried to the board so another developer's workspace starts from it too
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


# --- the design brief: a feature's or epic's agreed design, carried to the items under it as an ADO comment ---------
#
# Another developer's workspace has none of this one's spec files; the board is what both see. So when "Design agreed"
# passes on a Feature or Epic, env.py brief posts one comment on the item itself (the whole design) and one on each
# open item under it (what the design decides for that item, what holds for all of them, what is settled, what is
# still open). env.py upstream on the other side reads them back. The first line marks a brief and says where from:
#
#     sdd design brief: Feature ADO 900 for ADO 901 · agreed 2026-10-22

BRIEF_TAG = "sdd design brief"
DECIDES, WHOLE, SETTLED, STILL_OPEN = "What the design decides for", "What holds for all of it", \
    "Settled: do not ask again", "Still open for"
MAX_BRIEF = 100000  # characters of HTML; past this the brief points to the one on the feature or epic itself
_HEAD = re.compile(r"sdd design brief:\s*([A-Za-z][\w ]*?)\s+ADO\s+(\d+)\s+for\s+ADO\s+(\d+)(?:\s*·\s*agreed\s+([\d-]+))?", re.I)


def questions(questions_text, wid=None, ticked=True):
    """questions.md lines, without the box: the ticked (or open) ones that hold for `wid` (untagged, or tagged
    `(ADO <wid>)`); every ticked (or open) one when `wid` is None."""
    out = []
    for ln in (questions_text or "").splitlines():
        m = re.match(r"\s*[-*]\s*\[([ xX])\]\s*(.+)", ln)
        if not m or (m.group(1) != " ") != ticked:
            continue
        tags = re.findall(r"\(ADO\s*(\d+)\)", m.group(2))
        if wid is None or not tags or str(int(wid)) in tags:
            out.append(m.group(2).strip())
    return out


def sections(design_text):
    """design.md as [(heading line or "", [blocks])]; a block is a paragraph, a list item or a fenced code block."""
    out, blocks, cur, fence, heading = [], [], [], False, ""

    def flush():
        if cur:
            blocks.append("\n".join(cur))
            cur.clear()
    for ln in (design_text or "").splitlines():
        if ln.strip().startswith("```"):
            cur.append(ln)
            fence = not fence
            if not fence:
                flush()
            continue
        if fence:
            cur.append(ln)
            continue
        if re.match(r"#{1,6}\s", ln):
            flush()
            if heading or blocks:
                out.append((heading, list(blocks)))
            heading, blocks = ln.strip(), []
        elif not ln.strip():
            flush()
        elif re.match(r"\s*([-*+]|\d+[.)])\s", ln) and not ln.startswith((" ", "\t")):
            flush()
            cur.append(ln)
        else:
            cur.append(ln)
    flush()
    if heading or blocks:
        out.append((heading, blocks))
    return out


def brief_targets(items, wid, design_text, done_states):
    """Who gets a brief: the open items directly under `wid`, and the open items further down its design names."""
    low = {s.lower() for s in done_states} | {"removed"}
    live = [i for i in under(items, wid) if (items[str(i)].get("state") or "").lower() not in low
            and not items[str(i)].get("removed") and not items[str(i)].get("missing")]
    kids = set(direct_children(items, wid))
    return [i for i in live if i in kids or mentions(design_text, i)]


def brief_md(src, target, design_text, questions_text, agreed_at, others=()):
    """The brief for `target` from `src` ({id, type, title}), as markdown. `others`: the other targets, so the
    blocks that name only them stay out of this one. A brief for `src` itself carries the whole design."""
    sid, tid = int(src["id"]), int(target)
    head = f"**{BRIEF_TAG}**: {src['type']} ADO {sid} for ADO {tid} · agreed {(agreed_at or '')[:10]}"
    lines = [head, "", f"{src['type']} ADO {sid}: {src.get('title') or ''}. Its design is agreed; the work on "
             f"ADO {tid} starts from it. Where the work departs from it, say so in its own design.", ""]
    if tid == sid:
        lines += [f"### {DECIDES} ADO {tid}", "", (design_text or "").strip(), ""]
    else:
        own, whole = [], []
        for heading, blocks in sections(design_text):
            if mentions(heading, tid):
                own += [heading] + blocks
                continue
            if any(mentions(heading, o) for o in others if o != tid):
                continue  # a part about another item
            mine = [b for b in blocks if mentions(b, tid)]
            common = [b for b in blocks if not any(mentions(b, o) for o in set(others) | {tid})]
            if mine:
                own += ([heading] if heading else []) + mine
            if common:
                whole += ([heading] if heading else []) + common
        lines += [f"### {DECIDES} ADO {tid}", ""] + (own or ["Nothing names this item; what holds for all of it "
                                                              "applies."]) + [""]
        lines += [f"### {WHOLE}", ""] + (whole or ["(nothing apart from the above)"]) + [""]
    settled = questions(questions_text, None if tid == sid else tid, ticked=True)
    still = questions(questions_text, None if tid == sid else tid, ticked=False)
    lines += [f"### {SETTLED}", ""] + ([f"- {q}" for q in settled] or ["(none)"]) + [""]
    lines += [f"### {STILL_OPEN} ADO {tid}", ""] + ([f"- {q}" for q in still] or ["(none)"])
    return "\n".join(lines).strip() + "\n"


def _inline(s):
    s = html_escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_html(md):
    """The little markdown a design uses, as the HTML an ADO comment takes. The brief's own parts are <h3>; the
    design's headings become <h4>, so a brief read back finds its parts."""
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
            tag = "h3" if len(h.group(1)) == 3 and h.group(2).startswith((DECIDES, WHOLE, SETTLED, STILL_OPEN)) else "h4"
            out.append(f"<{tag}>{_inline(h.group(2))}</{tag}>")
        elif ln.strip():
            out.append(f"<div>{_inline(ln.strip())}</div>")
    if fence:
        out.append("<pre>" + html_escape("\n".join(code)) + "</pre>")
    if lst:
        out.append("</ul>")
    return "\n".join(out)


def html_to_md(text):
    """An ADO comment's HTML back as plain markdown: the brief's parts as `### `, the design's headings as `#### `."""
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
        .replace("&nbsp;", " ").replace("&middot;", "·").replace("&#183;", "·").replace("&amp;", "&")
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def brief_head(text):
    """(source type, source id, for id, agreed date) of a brief, or None for any other comment."""
    m = _HEAD.search(html_to_md(text)[:600].replace("**", ""))
    return (m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4) or "") if m else None


def brief_parts(md):
    """The settled and the still-open questions of a brief read back: (settled, still_open)."""
    part, settled, still = None, [], []
    for ln in (md or "").splitlines():
        t = ln.lstrip("#* ").rstrip("* ")  # a part's title, as a heading or (if ADO dropped the heading) in bold
        if ln.startswith(("#", "**")) and t.startswith((DECIDES, WHOLE, SETTLED, STILL_OPEN)):
            part = SETTLED if t.startswith(SETTLED) else STILL_OPEN if t.startswith(STILL_OPEN) else None
        elif part and ln.startswith("#"):
            part = None
        elif part and ln.startswith("- "):
            (settled if part == SETTLED else still).append(ln[2:].strip())
    return settled, still


def pick_briefs(chain, found):
    """The briefs that hold for chain[0]: from each item above it, the one meant for the nearest item of the chain
    (the item itself, then its parent, ...). chain: [wid, parent, grandparent, ...]. found: [{head, md, ...}]
    -> {source id: that brief}, nearest source first."""
    pos = {int(c): n for n, c in enumerate(chain)}
    best = {}
    for b in found:
        _, src, for_id, _ = b["head"]
        if src not in pos or src == chain[0] or for_id not in pos or pos[for_id] > pos[src]:
            continue
        if src not in best or pos[for_id] < pos[best[src]["head"][2]]:
            best[src] = b
    return dict(sorted(best.items(), key=lambda kv: pos[kv[0]]))
