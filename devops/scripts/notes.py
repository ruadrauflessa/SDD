"""Release notes: pick the release, pick the work items, write the repository file and the wiki page.

Pure functions of the data `devops.py notes collect` gathers (or the agent saves from the MCP tools), so
the format never drifts between runs and is tested without ADO. The layout is the one in
skills/release-notes/assets/release-notes-template.md.

    data = {"org", "project", "prs": [{"id", "repo", "project", "title", "source", "target", "created", "url"}],
            "workItems": {"<id>": {"id", "type", "title", "state", "parent", "tags", "assignee", "priority",
                                   "project", "url", "area"}},
            "prWorkItems": {"<pr id>": [ids]},
            "migrations": {"<pr id>": [{"path", "kind"}]}, "skills": {"<pr id>": [{"path", "change", "name"}]},
            "gaps": ["..."]}
"""
import re
import urllib.parse
from datetime import datetime, timezone

SCOPES = {
    "bugs": ("Only bugs", "only-bugs"),
    "all": ("All tasks/items", ""),
    "tasks": ("Only tasks", "only-tasks"),
    "stories": ("Only stories", "only-stories"),
    "features": ("Only features", "only-features"),
}
PRIORITY_MODES = {
    "none": "Do not divide or order by priority",
    "order": "Order by priority only",
    "sections": "Divide into priority sections only",
    "both": "Divide into priority sections and order by priority",
}
ENVS = {"QA": "7C3AED", "UAT": "2563EB", "STAGE": "D97706", "PROD": "DC2626"}
SECTIONS = [("Bug", "Delivered Bug Fixes"), ("Story", "Delivered User Stories"), ("Task", "Delivered Tasks"),
            ("Other", "Other Items"), ("Feature", "Features"), ("Epic", "Epics")]
PRIO_WORD = {1: ("critical", "D92D20"), 2: ("high", "DC6803"), 3: ("medium", "CA8A04"), 4: ("low", "6B7280")}
SCOPE_SECTIONS = {"bugs": {"Bug"}, "tasks": {"Task"}, "stories": {"Story"}, "features": {"Feature"},
                  "all": {"Bug", "Story", "Task", "Other", "Feature", "Epic"}}


def kind_of(wtype):
    t = (wtype or "").lower()
    if t == "bug":
        return "Bug"
    if t in ("user story", "product backlog item"):
        return "Story"
    if t == "task":
        return "Task"
    if t == "feature":
        return "Feature"
    if t == "epic":
        return "Epic"
    return "Other"


def parse_time(s):
    """ADO's creationDate (2026-08-21T10:00:00.123Z) as a naive UTC datetime; unreadable is the epoch."""
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return datetime(1970, 1, 1)


def newest_cluster(prs, gap_hours=2):
    """The newest group of PRs: sorted by creation, newest first, a gap over `gap_hours` starts a new one."""
    ordered = sorted(prs, key=lambda p: parse_time(p.get("created")), reverse=True)
    out = []
    for p in ordered:
        if out and (parse_time(out[-1].get("created")) - parse_time(p.get("created"))).total_seconds() > gap_hours * 3600:
            break
        out.append(p)
    return out


def release_prs(prs):
    return [p for p in prs if (p.get("target") or "").lower().startswith("release/")]


def version_of(prs):
    vs = sorted({(p.get("target") or "").split("/", 1)[-1] for p in prs if p.get("target")})
    return " + ".join(vs) if vs else "unknown"


def ancestors(items, wid):
    out, seen = [], set()
    cur = items.get(str(wid), {}).get("parent")
    while cur and str(cur) in items and cur not in seen:
        seen.add(cur)
        out.append(int(cur))
        cur = items[str(cur)].get("parent")
    return out


def selected(data, scope, pr_ids=None):
    """The work items the notes list for this scope, each once."""
    items = data.get("workItems", {})
    prw = data.get("prWorkItems", {})
    direct = []
    for pid, ids in prw.items():
        if pr_ids is None or int(pid) in pr_ids:
            direct += [int(i) for i in ids if str(i) in items]
    pool = list(dict.fromkeys(direct))
    if scope != "tasks":
        for d in list(pool):
            pool += ancestors(items, d)
    pool = list(dict.fromkeys(pool))
    keep = SCOPE_SECTIONS[scope]
    return [items[str(i)] for i in pool if kind_of(items[str(i)].get("type")) in keep]


def prio(item):
    p = item.get("priority")
    try:
        return int(p)
    except (TypeError, ValueError):
        return None


def arrange(items, mode):
    """[(subheading or None, items)] for one section, per the priority presentation."""
    by_title = sorted(items, key=lambda i: (i.get("title") or "").lower())
    if mode in ("order", "both"):
        by_title = sorted(by_title, key=lambda i: (prio(i) is None, prio(i) or 0))
    if mode not in ("sections", "both"):
        return [(None, by_title)]
    groups = {}
    for i in (by_title if mode == "both" else items):
        groups.setdefault(prio(i), []).append(i)
    keys = sorted([k for k in groups if k is not None]) + ([None] if None in groups else [])
    if mode == "sections":
        keys = list(groups)
    return [(f"Priority {k}" if k is not None else "Unspecified Priority", groups[k]) for k in keys]


def slug_file(day, scope, existing):
    """release-notes-yyyyMMdd[-<scope-slug>]-N.md, N the next free counter for that day and scope."""
    slug = SCOPES[scope][1]
    stem = f"release-notes-{day}" + (f"-{slug}" if slug else "")
    rx = re.compile(re.escape(stem) + r"-(\d+)\.md$")
    used = [int(m.group(1)) for m in (rx.match(n) for n in existing) if m]
    return f"{stem}-{max(used + [0]) + 1}.md"


def badge_text(s):
    s = str(s).replace("-", "--").replace("_", "__").replace(" ", "_")
    return urllib.parse.quote(s, safe="_-.")


def badge(alt, label, message, color):
    if message is None:
        return f"![{alt}](https://img.shields.io/badge/{badge_text(label)}-{color}?style=flat-square)"
    return f"![{alt}](https://img.shields.io/badge/{badge_text(label)}-{badge_text(message)}-{color}?style=flat-square)"


def prio_badge(item):
    p = prio(item)
    if p is None:
        return badge("Priority", "Priority", "unspecified", "6B7280")
    word, color = PRIO_WORD.get(p, ("low", "6B7280"))
    return badge(f"Priority {p}", f"Priority {p}", word, color)


def assignee(item):
    return item.get("assignee") or "Unassigned"


def area(item):
    a = item.get("area") or ""
    return a.replace("/", "\\").split("\\")[-1] if a else ""


def file_line(item, text):
    k = kind_of(item.get("type"))
    head = f"[{item['id']}]({item.get('url', '')})"
    if k == "Bug":
        bits = [head, area(item) or "General", text or item.get("title", "")]
        line = " - ".join(bits) + (f" (Priority {prio(item)})" if prio(item) is not None else "")
    else:
        line = f"{head} - {item.get('title', '')}"
    line += f" — Handled by {assignee(item)}"
    if item.get("tags"):
        line += " — Tags: " + ", ".join(item["tags"])
    return f"- {line}"


def wiki_card(item, text):
    k = kind_of(item.get("type"))
    a = area(item)
    title = f"{a} — {item.get('title', '')}" if (k == "Bug" and a) else item.get("title", "")
    row = [prio_badge(item)]
    tags = " ".join(badge("Tag", t, None, "6B7280") for t in item.get("tags") or [])
    out = [f"#### [#{item['id']}]({item.get('url', '')}) {title}", ""]
    out.append(" &nbsp; ".join(x for x in [row[0], tags, badge("Handled by", "Handled by", assignee(item), "2B6CB0")] if x))
    if text and k not in ("Feature", "Epic"):
        out += ["", text]
    out.append("")
    return out


def since_text(since):
    """`1.0.1 (build 20261001.4, 2026-10-01)`: what the environment ran before this release, or ''."""
    if not since:
        return ""
    what = since.get("version") or since.get("branch") or since.get("build") or "?"
    bits = [f"build {since['build']}" if since.get("build") and since.get("version") else "", (since.get("at") or "")[:10]]
    bits = [b for b in bits if b]
    return what + (f" ({', '.join(bits)})" if bits else "")


def build(data, scope, mode, env, texts=None, now=None, pr_ids=None, since=None):
    """(file markdown, wiki markdown, facts) for one release build. since: the environment's last deployment
    (pipelines.last_deploy), named in both so readers know what these notes come after."""
    texts = {str(k): v for k, v in (texts or {}).items()}
    now = now or datetime.now(timezone.utc).astimezone()
    day = now.strftime("%Y-%m-%d")
    prs = [p for p in data.get("prs", []) if pr_ids is None or p["id"] in pr_ids]
    version = version_of(prs)
    scope_label = SCOPES[scope][0]
    items = selected(data, scope, {p["id"] for p in prs})
    by_section = {}
    for i in items:
        by_section.setdefault(kind_of(i.get("type")), []).append(i)
    branches = sorted({p.get("target") for p in prs if p.get("target")})
    branch = branches[0] if len(branches) == 1 else ", ".join(branches)
    repos = sorted({p["repo"] for p in prs})
    mig = {str(k): v for k, v in (data.get("migrations") or {}).items() if v}
    skl = {str(k): v for k, v in (data.get("skills") or {}).items() if v}
    pr_link = lambda p: f"[{p['id']}]({p.get('url', '')})"

    f = [f"# Release {version} — {env}", "", f"- Environment: {env}", f"- Generated: {day}",
         f"- Release branch: `{branch}`", f"- Scope: {scope_label}", f"- Priority presentation: {PRIORITY_MODES[mode]}"]
    if since:
        f.append(f"- Last deployed to {env}: {since_text(since)}")
    f.append("")
    f += ["## Repositories", ""] + [f"- {r}" for r in repos] + [""]
    f += ["## Included Pull Requests", ""] + [f"- {pr_link(p)} - {p['repo']} - {p['title']}" for p in prs] + [""]
    if mig:
        f += ["## Database Migration Changes", ""]
        for p in prs:
            if str(p["id"]) in mig:
                f.append(f"- {pr_link(p)} - {p['repo']}")
                f += [f"  - {m['kind']}: `{m['path']}`" for m in mig[str(p["id"])]]
        f.append("")
    if skl:
        f += ["## Skill Documentation Changes", ""]
        for p in prs:
            if str(p["id"]) in skl:
                f.append(f"- {pr_link(p)} - {p['repo']}")
                f += [f"  - {s['change']}: `{s['path']}` — skill `{s['name']}`" for s in skl[str(p["id"])]]
        f.append("")

    color = ENVS.get(env, "6B7280")
    w = [f"# Release {version} — {env} — {day}", "",
         " ".join([badge("Release", "Release", version, "2B6CB0"), badge("Environment", "Environment", env, color),
                   badge("Generated", "Generated", day, "6B7280"), badge("Scope", "Scope", scope_label, "2B6CB0"),
                   badge("Branch", "branch", branch, "475467")]), ""]
    if since:
        w.append(f"> **Last deployed to {env}:** {since_text(since)}  ")
    for p in prs:
        w.append(f"> **Pull request:** {pr_link(p)} — {p['repo']} — {p['title']}  ")
    w += ["", "---", ""]
    if mig:
        w += ["## Database Migration Changes", ""]
        for p in prs:
            if str(p["id"]) in mig:
                w.append(f"- {pr_link(p)} - {p['repo']}")
                w += [f"  - {m['kind']}: `{m['path']}`" for m in mig[str(p["id"])]]
        w.append("")
    if skl:
        w += ["## Skill Documentation Changes", ""]
        for p in prs:
            if str(p["id"]) in skl:
                w.append(f"- {pr_link(p)} - {p['repo']}")
                w += [f"  - {s['change']}: `{s['path']}` — skill `{s['name']}`" for s in skl[str(p["id"])]]
        w.append("")

    for key, heading in SECTIONS:
        sec = by_section.get(key)
        if not sec:
            continue
        f += [f"## {heading}", ""]
        w += [f"## {heading}", ""]
        for sub, group in arrange(sec, mode):
            if sub:
                f += [f"### {sub}", ""]
                w += [f"### {sub}", ""]
            f += [file_line(i, texts.get(str(i["id"]))) for i in group]
            f.append("")
            for i in group:
                w += wiki_card(i, texts.get(str(i["id"])))
    w += ["---", "", "_Sourced from Azure DevOps pull requests " + ", ".join(pr_link(p) for p in prs)
          + " and their linked work items._", ""]
    facts = {"version": version, "env": env, "day": day, "scope": scope, "mode": mode, "repos": repos,
             "prs": [p["id"] for p in prs], "items": len(items),
             "unassigned": [i["id"] for i in items if not i.get("assignee")],
             "needText": [i["id"] for i in items if kind_of(i.get("type")) == "Bug" and str(i["id"]) not in texts],
             "migrations": sum(len(v) for v in mig.values()), "skills": sum(len(v) for v in skl.values()),
             "wikiPath": f"/Release Notes/Release {version} [{env}] - {day}",
             "since": {"version": since.get("version"), "build": since.get("build"), "at": since.get("at")} if since else None}
    return "\n".join(f).rstrip() + "\n", "\n".join(w).rstrip() + "\n", facts


INDEX_HEAD = "## Releases"


def index_line(facts, link, prs):
    scope = SCOPES[facts["scope"]][0]
    pr_bits = ", ".join(f"[{p['id']}]({p.get('url', '')})" for p in prs)
    return (f"- [Release {facts['version']} [{facts['env']}] - {facts['day']}]({link}) — **{facts['env']}** — {scope}"
            + (f" (PR {pr_bits})" if pr_bits else ""))


def index_page(existing, line, project):
    """The `/Release Notes` page with `line` first in its Releases list. A line for the same page is replaced."""
    target = re.search(r"\]\(([^)]+)\)", line).group(1)
    if not existing or INDEX_HEAD not in existing:
        intro = (f"# Release Notes\n\nRelease notes for the {project} platform, one page per release build. Pages are "
                 "named `Release <version> [<environment>] - <yyyy-MM-dd>` so several builds of one version, or one "
                 "version in different environments, can sit side by side.\n\n")
        return intro + INDEX_HEAD + "\n\n" + line + "\n"
    head, _, tail = existing.partition(INDEX_HEAD)
    rows = tail.strip("\n").split("\n")
    cut = next((i for i, ln in enumerate(rows) if ln.startswith("#")), len(rows))
    listed = [ln for ln in rows[:cut] if ln.strip() and f"]({target})" not in ln]
    rest = "\n".join(rows[cut:]).strip("\n")
    return head + INDEX_HEAD + "\n\n" + "\n".join([line] + listed) + "\n" + ("\n" + rest + "\n" if rest else "")
