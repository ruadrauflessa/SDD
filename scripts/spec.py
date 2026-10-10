"""Spec mirror and index: ADO work items -> {specRoot}/**/{id}-{TYPE}-{slug}/requirements.md + {specRoot}/.index/spec.db

Deterministic: the same ADO state always produces the same files and index. No LLM, no tokens.

    sync --id N          N, everything under it, its parents, and 1 hop of links out of that tree
    sync                 refresh every synced item and every scope root (picks up new children)
    sync --all           every spec type in every project in sdd.json, all states
    embed                (re)embed changed items with Ollama; sync runs this for you
    query links   --id N [--hops 2]      linked items, both directions
    query overlap --id N                 items sharing this one's key terms, rarest terms weigh most
    query term    TEXT                   items naming a term
    query search  TEXT                   full-text search (SQLite FTS5, BM25)
    query similar --id N | --text T      meaning search (Ollama embeddings)
    query show    --id N                 one item's index row and folder
    impact --id N [--hops 2]             all of the above for N, written to its folder as impact.json
    impact --all [--scope N]             every item (or everything under N): impact.json each, plus one
                                         deduplicated pair list and a token estimate in impact-all.json

Writes to ADO (rev-tested, retried on a conflict; adowrite.py; exit 3 = stop and ask the user):
    claim    --id N [--id M ...] [--reopen] [--take]
                                                 assign to you, Active, Dev In Progress; never someone's work in progress
    handover --id N [--tag T] [--root-cause-details-file F --resolution-file F] [--root-cause V]
                                                 Resolved + Dev Completed: the hand-over to QA
    sprint   --id N [--id M ...] [--team T]      move to the current sprint
    comment  --id N --file F                     post an HTML comment (refuses a `#<id>` mention)
    (--dry-run on any of them prints the patch and writes nothing)

Which item to take next (nextpick.py; read-only, from the index — sync the scope first):
    next       --scope N --version V [--email E] [--json]
                                    the items under epic/feature N tagged V, ranked: bugs and issues
                                    first, then by dev priority; plus what needs a judgement first
    next-judge --scope N --id M (--blocked yes|no | --complexity 1-5) --reason TEXT
                                    record the agent's judgement; it holds while its evidence holds

Only the files sync writes are touched: requirements.md. design.md, tasks.md, questions.md and
impact.* in a spec folder are never overwritten, and move with the folder on a reparent.
"""
import argparse
import array
import hashlib
import html
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import adowrite
import nextpick
from sddlib import die, get_items, load_config, org_url, require_root, slug, wiql

SYNCED_BY = "sdd-spec-sync@1"
TEXT_FIELDS = [("System.Description", "Description"),
               ("Microsoft.VSTS.Common.AcceptanceCriteria", "Acceptance criteria"),
               ("Microsoft.VSTS.TCM.ReproSteps", "Repro steps")]
MATERIAL = ["System.WorkItemType", "System.Title"] + [f for f, _ in TEXT_FIELDS]
HIER_FWD = "System.LinkTypes.Hierarchy-Forward"
# Planning fields: what a person (or the next-item skill) weighs to pick work. Incidental — a change
# never blocks a flow. Process templates name some differently: each takes the first field present.
PLANNING = {
    "board": ["Custom.BoardColumnTitle"],                       # the team's real workflow column
    "priority": ["Microsoft.VSTS.Common.Priority"],
    "severity": ["Microsoft.VSTS.Common.Severity"],
    "rank": ["Microsoft.VSTS.Common.StackRank", "Microsoft.VSTS.Common.BacklogPriority"],  # backlog order
    "effort": ["Microsoft.VSTS.Scheduling.StoryPoints", "Microsoft.VSTS.Scheduling.Effort",
               "Microsoft.VSTS.Scheduling.Size", "Microsoft.VSTS.Scheduling.OriginalEstimate"],
    "target": ["Microsoft.VSTS.Scheduling.TargetDate", "Microsoft.VSTS.Scheduling.DueDate"],
    "blocked": ["Microsoft.VSTS.CMMI.Blocked"],
    "created": ["System.CreatedDate"],
}
PLANNING_LABELS = [("board", "Board column"), ("priority", "Priority"), ("severity", "Severity"),
                   ("effort", "Effort"), ("target", "Target date"), ("blocked", "Blocked")]


def planning(f):
    """{column: value} of the planning fields, '' where the item has none of the field's names."""
    out = {}
    for col, names in PLANNING.items():
        v = next((f[n] for n in names if f.get(n) not in (None, "")), "")
        out[col] = v if isinstance(v, (int, float)) else str(v)
    return out


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(v):
    t = str(v or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(x.rstrip() for x in t.split("\n")).strip()


def h8(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- context

class Ctx:
    def __init__(self):
        self.root = require_root()
        self.cfg = load_config(self.root)
        self.spec = (self.root / self.cfg["specRoot"]).resolve()
        (self.spec / ".index").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.spec / ".index" / "spec.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, project TEXT, type TEXT, title TEXT,
            state TEXT, area TEXT, iteration TEXT, tags TEXT, assigned TEXT, parent INTEGER,
            rev INTEGER, hash TEXT, fhash TEXT, path TEXT, removed INTEGER DEFAULT 0,
            missing INTEGER DEFAULT 0, changed TEXT, synced_at TEXT, body TEXT, other TEXT);
        CREATE TABLE IF NOT EXISTS links(src INTEGER, dst INTEGER, rel TEXT);
        CREATE INDEX IF NOT EXISTS links_src ON links(src);
        CREATE INDEX IF NOT EXISTS links_dst ON links(dst);
        CREATE TABLE IF NOT EXISTS terms(id INTEGER, term TEXT, kind TEXT);
        CREATE INDEX IF NOT EXISTS terms_term ON terms(term);
        CREATE INDEX IF NOT EXISTS terms_id ON terms(id);
        CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(id UNINDEXED, title, body);
        CREATE TABLE IF NOT EXISTS emb(id INTEGER PRIMARY KEY, hash TEXT, model TEXT, vec BLOB);
        CREATE TABLE IF NOT EXISTS scopes(root TEXT PRIMARY KEY, synced_at TEXT);
        """)
        # columns added after an index was first built: add them in place; the next sync fills them
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(items)")}
        for col in ["assigned_email", *PLANNING]:
            if col not in have:
                self.db.execute(f"ALTER TABLE items ADD COLUMN {col}")
        self.db.commit()

    def item(self, wid):
        return self.db.execute("SELECT * FROM items WHERE id=?", (wid,)).fetchone()


# ---------------------------------------------------------------- HTML -> Markdown

class _Strip(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "ul", "ol", "table"}

    def __init__(self):
        super().__init__()
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")
        if tag in ("s", "del", "strike"):  # descoped criteria must stay visibly struck out
            self.out.append("~~")

    def handle_endtag(self, tag):
        if tag in ("s", "del", "strike"):
            self.out.append("~~")

    def handle_data(self, d):
        self.out.append(d)


def tidy(md):
    """Drop the hard-break backslashes ADO's <br> soup turns into; each line is its own paragraph anyway."""
    md = re.sub(r"\\(\*\*|__)?[ \t]*$", r"\1", md, flags=re.M)
    return norm(re.sub(r"\n{3,}", "\n\n", md))


def to_markdown(fragments):
    """Convert many HTML fragments in one pandoc call. Falls back to tag stripping without pandoc."""
    if not fragments:
        return []
    exe = shutil.which("pandoc")
    if exe:
        joined = "".join(f"<p>SDDSPLIT{i:06d}</p>\n{frag}\n" for i, frag in enumerate(fragments))
        # native_divs/spans off: ADO wraps everything in <div>, which gfm would keep as raw HTML
        r = subprocess.run([exe, "-f", "html-native_divs-native_spans", "-t", "gfm", "--wrap=none"], input=joined,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            parts = re.split(r"^SDDSPLIT\d{6}\s*$", r.stdout, flags=re.M)[1:]
            if len(parts) == len(fragments):
                return [tidy(p) for p in parts]
        print("warning: pandoc failed; using plain text conversion", file=sys.stderr)
    out = []
    for frag in fragments:
        p = _Strip()
        p.feed(frag or "")
        out.append(norm(re.sub(r"\n{3,}", "\n\n", html.unescape("".join(p.out)))))
    return out


# ---------------------------------------------------------------- terms

TERM_RULES = [
    ("code", re.compile(r"`([^`\n]{2,60})`")),
    ("route", re.compile(r"(?<![\w/])(/(?:api|v\d)[\w{}\-./]*|/[a-z][\w-]*(?:/[\w{}\-.]+){1,})")),
    ("table", re.compile(r"\b((?:dbo|agent|[a-z]{2,12})\.[A-Z]\w{2,})\b")),
    ("ident", re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b")),
    ("code_id", re.compile(r"\b([A-Z]{1,4}\d{3,})\b")),
    ("snake", re.compile(r"\b([a-z]+(?:_[a-z0-9]+){1,})\b")),
]


def extract_terms(text):
    text = re.sub(r"\\([\\_*`\[\]()#.!-])", r"\1", text or "")  # undo Markdown escapes: Document\_Id
    seen = {}
    for kind, rx in TERM_RULES:
        for m in rx.finditer(text or ""):
            t = m.group(1).strip().strip(".,;:\\").lower()
            if len(t) >= 3 and t not in seen:
                seen[t] = kind
    return seen


# ---------------------------------------------------------------- ADO fetch

def rels_of(w):
    out = []
    for r in w.get("relations") or []:
        m = re.search(r"/workItems/(\d+)$", r.get("url", ""), re.I)
        if m:
            name = (r.get("attributes") or {}).get("name") or r["rel"].split(".")[-1]
            out.append((r["rel"], name, int(m.group(1))))
    return out


def parent_of(w):
    for rel, _, dst in rels_of(w):
        if rel == "System.LinkTypes.Hierarchy-Reverse":
            return dst
    return None


def subtree(ctx, wid, project):
    q = (f"SELECT [System.Id] FROM WorkItemLinks WHERE ([Source].[System.Id] = {int(wid)}) "
         f"AND ([System.Links.LinkType] = '{HIER_FWD}') MODE (Recursive)")
    rows = wiql(ctx.cfg, q, project)
    return {r["target"]["id"] for r in rows if r.get("target")}


def fetch(ctx, ids, cache):
    need = [i for i in ids if i not in cache]
    for w in get_items(ctx.cfg, need, relations=True):
        cache[w["id"]] = w
    return [cache[i] for i in ids if i in cache]


# ---------------------------------------------------------------- sync

def cmd_sync(a):
    ctx = Ctx()
    types = set(ctx.cfg["specTypes"])
    cache, wanted, scopes = {}, set(), []
    all_projects = ctx.cfg["ado"]["projects"] if a.all else [] if a.id else [
        r["root"][4:] for r in ctx.db.execute("SELECT root FROM scopes WHERE root LIKE 'all:%'")]
    if all_projects:
        for p in all_projects:
            tl = ", ".join(f"'{t}'" for t in sorted(types))
            ids = wiql(ctx.cfg, f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{p}' "
                                f"AND [System.WorkItemType] IN ({tl})", p)
            print(f"{p}: {len(ids)} items")
            wanted |= set(ids)
            scopes.append(f"all:{p}")
    if not a.all:
        roots = [a.id] if a.id else [int(r["root"]) for r in ctx.db.execute(
            "SELECT root FROM scopes WHERE root NOT LIKE 'all:%'")]
        if not a.id:
            wanted |= {r["id"] for r in ctx.db.execute("SELECT id FROM items")}
            if not roots and not wanted:
                die("nothing synced yet. Run: spec.py sync --id <epic or feature id>")
        for rid in roots:
            got = fetch(ctx, [rid], cache)
            if not got:
                print(f"warning: scope root {rid} not found (deleted or no access)")
                continue
            wanted |= {rid} | subtree(ctx, rid, got[0]["fields"]["System.TeamProject"])
            p = parent_of(got[0])
            while p and p not in wanted:  # ancestors, so the folder tree has its top
                wanted.add(p)
                up = fetch(ctx, [p], cache)
                p = parent_of(up[0]) if up else None
            scopes.append(str(rid))

    items = [w for w in fetch(ctx, sorted(wanted), cache)
             if w["fields"]["System.WorkItemType"] in types or w["id"] == a.id]
    # one hop out of the tree: linked items the scope does not already hold
    hop = {dst for w in items for _, _, dst in rels_of(w)} - {w["id"] for w in items}
    items += [w for w in fetch(ctx, sorted(hop), cache) if w["fields"]["System.WorkItemType"] in types]
    got_ids = {w["id"] for w in items}
    missing = sorted(i for i in wanted if i not in cache)
    print(f"fetched {len(items)} items ({len(hop & got_ids)} by one-hop links), {len(missing)} missing")

    # links to non-spec items (test cases, tasks, release schedules) are counted, never followed
    # every link target's type must be known, or a hop item's own test cases would count as spec
    # links in this run and not in the last one — a false MATERIAL
    kinds = {i: w["fields"]["System.WorkItemType"] for i, w in cache.items()}
    unknown = {dst for w in items for _, _, dst in rels_of(w)} - set(kinds)
    kinds.update({w["id"]: w["fields"]["System.WorkItemType"]
                  for w in get_items(ctx.cfg, unknown, fields=["System.Id", "System.WorkItemType"])})
    other = {i: t for i, t in kinds.items() if t not in types}
    report, pending = write_items(ctx, items, other)
    for i in missing:
        if ctx.item(i):
            ctx.db.execute("UPDATE items SET missing=1 WHERE id=?", (i,))
            report["missing"].append(i)
    for s in scopes:
        ctx.db.execute("INSERT OR REPLACE INTO scopes VALUES(?,?)", (s, now()))
    ctx.db.commit()
    place_folders(ctx, pending)

    for k in ("new", "material", "incidental", "unchanged", "missing"):
        print(f"{k:<11} {len(report[k])}")
    for wid, fields in report["material_detail"]:
        r = ctx.item(wid)
        print(f"  MATERIAL {wid} {r['type']} — {r['title']}: {', '.join(fields)}")
    for wid in report["missing"]:
        print(f"  MISSING  {wid}: deleted in ADO, moved to a project you cannot read, or no access")
    if not a.no_embed:
        embed(ctx)


def write_items(ctx, items, other=None):
    other = other or {}
    report = {k: [] for k in ("new", "material", "incidental", "unchanged", "missing")}
    report["material_detail"], pending = [], {}
    frags = [w["fields"].get(f) or "" for w in items for f, _ in TEXT_FIELDS]
    md = to_markdown(frags)
    titles = {w["id"]: w["fields"]["System.Title"] for w in items}
    for n, w in enumerate(items):
        f = w["fields"]
        rev = w.get("rev", f.get("System.Rev"))  # the batch API puts rev at the top level
        texts = md[n * len(TEXT_FIELDS):(n + 1) * len(TEXT_FIELDS)]
        every = sorted(rels_of(w), key=lambda x: (x[1], x[2]))
        rels = [r for r in every if r[2] not in other]
        extra = {}
        for _, name, dst in every:
            if dst in other:
                extra[f"{name} {other[dst]}"] = extra.get(f"{name} {other[dst]}", 0) + 1
        rel_lines = [f"rel:{name}:{dst}" for _, name, dst in rels]
        fh = {m: h8(norm(f.get(m))) for m in MATERIAL}
        fh["relations"] = h8("\n".join(rel_lines))
        full = h8("\n".join(f"{m}={norm(f.get(m))}" for m in MATERIAL) + "\n" + "\n".join(rel_lines))
        body = "\n\n".join(f"## {label}\n\n{t}" for (_, label), t in zip(TEXT_FIELDS, texts) if t)
        old = ctx.item(w["id"])
        if not old:
            report["new"].append(w["id"])
        elif old["hash"] != full:
            report["material"].append(w["id"])
            was = json.loads(old["fhash"] or "{}")
            report["material_detail"].append((w["id"], [k.split(".")[-1] for k, v in fh.items() if was.get(k) != v]))
        elif old["rev"] != rev:
            report["incidental"].append(w["id"])
        else:
            report["unchanged"].append(w["id"])
        who = f.get("System.AssignedTo")
        assigned = who.get("displayName", "") if isinstance(who, dict) else str(who or "")
        m = re.search(r"<([^>]+)>", assigned)
        email = (who.get("uniqueName", "") if isinstance(who, dict) else m.group(1) if m
                 else assigned if "@" in assigned else "").lower()
        row = dict(id=w["id"], project=f["System.TeamProject"], type=f["System.WorkItemType"],
                   title=f["System.Title"], state=f["System.State"], area=f.get("System.AreaPath", ""),
                   iteration=f.get("System.IterationPath", ""), tags=f.get("System.Tags", ""),
                   assigned=assigned, parent=parent_of(w), rev=rev, hash=full,
                   fhash=json.dumps(fh, sort_keys=True), path=old["path"] if old else None,
                   removed=int(f["System.State"] == "Removed"), missing=0,
                   changed=f.get("System.ChangedDate", ""), synced_at=now(), body=body,
                   other=json.dumps(extra, sort_keys=True), assigned_email=email, **planning(f))
        ctx.db.execute(f"INSERT OR REPLACE INTO items({','.join(row)}) VALUES({','.join('?' * len(row))})",
                       list(row.values()))
        ctx.db.execute("DELETE FROM links WHERE src=?", (w["id"],))
        ctx.db.executemany("INSERT INTO links VALUES(?,?,?)", [(w["id"], dst, name) for _, name, dst in rels])
        ctx.db.execute("DELETE FROM terms WHERE id=?", (w["id"],))
        ctx.db.executemany("INSERT INTO terms VALUES(?,?,?)",
                           [(w["id"], t, k) for t, k in extract_terms(f["System.Title"] + "\n" + body).items()])
        ctx.db.execute("DELETE FROM fts WHERE id=?", (w["id"],))
        ctx.db.execute("INSERT INTO fts VALUES(?,?,?)", (w["id"], f["System.Title"], body))
        row["_links"] = [(name, dst, titles.get(dst) or (ctx.item(dst)["title"] if ctx.item(dst) else ""))
                         for _, name, dst in rels]
        row["_org"] = ctx.cfg["ado"]["org"]
        pending[w["id"]] = row
    return report, pending


def render(row):
    links = "\n".join(f"  - {name} {dst}" for name, dst, _ in row["_links"])
    link_list = "\n".join(f"- {name}: {dst} — {t}" for name, dst, t in row["_links"]) or "- none"
    extra = json.loads(row["other"])
    if extra:
        link_list += "\n\nNot specs, counted only: " + ", ".join(f"{n} × {k}" for k, n in sorted(extra.items()))
    url = f"https://dev.azure.com/{row['_org']}/{row['project']}/_workitems/edit/{row['id']}"
    meta = [("Type", row["type"]), ("State", row["state"]), ("Project", row["project"]),
            ("Area", row["area"]), ("Iteration", row["iteration"]), ("Tags", row["tags"]),
            ("Assigned to", row["assigned"])] + [(label, row.get(col)) for col, label in PLANNING_LABELS]
    table = "\n".join(f"| {k} | {v} |" for k, v in meta if v not in (None, ""))
    return (f"---\nid: {row['id']}\ntype: {row['type']}\nproject: {row['project']}\nstate: {row['state']}\n"
            f"parent: {row['parent'] or ''}\nfields_hash: {row['hash']}\nsynced_by: {SYNCED_BY}\n"
            f"links:\n{links or '  []'}\n---\n\n"
            f"<!-- Mirrored from Azure DevOps by sdd-spec-sync. Do not edit: the next sync overwrites it.\n"
            f"     Put open questions in questions.md in this folder. -->\n\n"
            f"# {row['id']} — {row['title']}\n\n[Open in ADO]({url})\n\n| Field | Value |\n| --- | --- |\n{table}\n\n"
            f"{row['body'] or '_No description, acceptance criteria or repro steps in ADO._'}\n\n"
            f"## Links\n\n{link_list}\n")


def scan_folders(spec):
    out = {}
    for d in spec.rglob("*"):
        m = re.match(r"^(\d+)-", d.name)
        if m and d.is_dir() and ".index" not in d.parts:
            out.setdefault(int(m.group(1)), d)
    return out


# Uppercase, so it can never be confused with the (always lowercase) slug after it.
TYPE_CODES = {"Epic": "EPIC", "Feature": "FEAT", "User Story": "US", "Tech Story": "TS",
              "Change Request": "CR", "Product Backlog Item": "PBI", "Bug": "BUG", "Issue": "ISSUE"}


def folder_name(wid, typ, title, current=None):
    """{id}-{TYPE}-{slug}. An existing folder keeps its slug (cosmetic, survives a retitle) but always
    carries the current type code, so a retype or an old {id}-{slug} folder is renamed in place."""
    code = TYPE_CODES.get(typ) or re.sub(r"[^A-Z0-9]", "", (typ or "ITEM").upper()) or "ITEM"
    rest = current.split("-", 1)[1] if current and "-" in current else slug(title)
    rest = re.sub(r"^[A-Z][A-Z0-9]*-", "", rest)  # drop an old type code; slugs are lowercase so this is safe
    return f"{wid}-{code}-{rest or 'untitled'}"


def place_folders(ctx, pending):
    """Folder tree follows the ADO parent chain; names are {id}-{TYPE}-{slug}. Folders move with a
    reparent, are renamed when the type changes, and keep their slug through a retitle."""
    rows = {r["id"]: r for r in ctx.db.execute("SELECT id, parent, title, type FROM items")}
    parents = {i: r["parent"] for i, r in rows.items()}

    def chain(i):
        out, seen = [], set()
        while i in parents and i not in seen:
            seen.add(i)
            out.insert(0, i)
            i = parents[i]
        return out

    have = scan_folders(ctx.spec)
    todo = set(pending) | {anc for w in pending for anc in chain(w)}  # ancestors get renamed too
    moved = 0
    for wid in sorted(todo, key=lambda i: len(chain(i))):
        desired = ctx.spec
        for anc in chain(wid):
            cur_name = have[anc].name if anc in have else None
            desired = desired / folder_name(anc, rows[anc]["type"], rows[anc]["title"], cur_name)
        cur = have.get(wid)
        if cur and cur.resolve() != desired.resolve():
            desired.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(cur), str(desired))
            moved += 1
            have = scan_folders(ctx.spec)
        desired.mkdir(parents=True, exist_ok=True)
        have[wid] = desired
        if wid in pending:
            target = desired / "requirements.md"
            text = render(pending[wid])
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                target.write_text(text, encoding="utf-8", newline="\n")
    # a moved or renamed parent moves its children too, so refresh every recorded path
    for wid, d in scan_folders(ctx.spec).items():
        ctx.db.execute("UPDATE items SET path=? WHERE id=?", (d.relative_to(ctx.spec).as_posix(), wid))
    ctx.db.commit()
    if moved:
        print(f"moved       {moved} folders (reparented, retyped or renamed to {{id}}-{{TYPE}}-{{slug}})")

# ---------------------------------------------------------------- embeddings

def ollama(ctx, path, body=None):
    url = ctx.cfg["embeddings"]["url"].rstrip("/") + path
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def ollama_ready(ctx):
    model = ctx.cfg["embeddings"]["model"]
    try:
        names = [m["name"] for m in ollama(ctx, "/api/tags").get("models", [])]
    except (urllib.error.URLError, OSError):
        print("warning: Ollama is not running; meaning search skipped. Word search still works.")
        return None
    if not any(n.split(":")[0] == model.split(":")[0] for n in names):
        print(f"warning: Ollama model {model} not pulled; meaning search skipped. Run: ollama pull {model}")
        return None
    return model


def embed_texts(ctx, model, texts):
    return ollama(ctx, "/api/embed", {"model": model, "input": texts})["embeddings"]


def embed(ctx):
    model = ollama_ready(ctx)
    if not model:
        return
    todo = ctx.db.execute("""SELECT i.id, i.title, i.body, i.hash FROM items i LEFT JOIN emb e ON e.id=i.id
                             WHERE e.id IS NULL OR e.hash<>i.hash OR e.model<>?""", (model,)).fetchall()
    for n in range(0, len(todo), 16):
        batch = todo[n:n + 16]
        vecs = embed_texts(ctx, model, [f"search_document: {r['title']}\n{(r['body'] or '')[:6000]}" for r in batch])
        ctx.db.executemany("INSERT OR REPLACE INTO emb VALUES(?,?,?,?)",
                           [(r["id"], r["hash"], model, array.array("f", v).tobytes()) for r, v in zip(batch, vecs)])
        ctx.db.commit()
    print(f"embedded    {len(todo)} items ({model})")


def cmd_embed(a):
    embed(Ctx())


def similar(ctx, vec, skip=None, top=15):
    # ponytail: brute-force cosine over every vector; fine to ~50k specs, use sqlite-vec beyond that
    def unit(v):
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
    q = unit(vec)
    scored = []
    for r in ctx.db.execute("SELECT id, vec FROM emb"):
        if r["id"] == skip:
            continue
        v = unit(array.array("f", r["vec"]))
        scored.append((round(sum(a * b for a, b in zip(q, v)), 3), r["id"]))
    return sorted(scored, reverse=True)[:top]


# ---------------------------------------------------------------- queries

def links(ctx, wid, hops):
    seen, frontier, out = {wid}, [wid], []
    for depth in range(1, hops + 1):
        nxt = []
        for cur in frontier:
            rows = ctx.db.execute("SELECT dst AS other, rel FROM links WHERE src=? UNION "
                                  "SELECT src AS other, rel || ' (reverse)' FROM links WHERE dst=?", (cur, cur))
            for r in rows:
                if r["other"] not in seen:
                    seen.add(r["other"])
                    nxt.append(r["other"])
                    out.append({"id": r["other"], "hops": depth, "via": cur, "rel": r["rel"]})
        frontier = nxt
    return out


def overlap(ctx, wid, top=20):
    total = ctx.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] or 1
    mine = [r["term"] for r in ctx.db.execute("SELECT term FROM terms WHERE id=?", (wid,))]
    scores = {}
    for t in mine:
        rows = ctx.db.execute("SELECT id FROM terms WHERE term=? AND id<>?", (t, wid)).fetchall()
        if not rows or len(rows) > max(10, total * 0.2):  # a term on a fifth of all specs says nothing
            continue
        w = math.log(total / (len(rows) + 1)) + 1
        for r in rows:
            s = scores.setdefault(r["id"], [0.0, []])
            s[0] += w
            s[1].append(t)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1][0])[:top]
    return [{"id": i, "score": round(s, 2), "terms": ts[:8]} for i, (s, ts) in ranked]


def describe(ctx, wid):
    r = ctx.item(wid)
    if not r:
        return {"id": wid, "synced": False}
    return {"id": wid, "type": r["type"], "state": r["state"], "title": r["title"], "project": r["project"],
            "board": r["board"] or "", "priority": r["priority"], "assigned": r["assigned"] or "",
            "removed": bool(r["removed"]), "missing": bool(r["missing"]), "path": r["path"]}


def line(d, extra=""):
    if not d.get("synced", True):
        return f"{d['id']:<7} (not synced) {extra}"
    flag = " [REMOVED]" if d["removed"] else " [MISSING]" if d["missing"] else ""
    return f"{d['id']:<7} {d['type']:<15} {d['state']:<10} {d['title'][:70]}{flag} {extra}".rstrip()


def cmd_query(a):
    ctx = Ctx()
    if a.what in ("links", "overlap", "similar", "show") and not (a.id or a.text):
        die(f"query {a.what} needs --id")
    if a.id and not ctx.item(a.id) and a.what != "similar":
        die(f"{a.id} is not synced. Run: spec.py sync --id {a.id}")
    res = []
    if a.what == "links":
        res = [{**describe(ctx, x["id"]), **x} for x in links(ctx, a.id, a.hops)]
        rows = [line(r, f"hop {r['hops']} {r['rel']} of {r['via']}") for r in res]
    elif a.what == "overlap":
        res = [{**describe(ctx, x["id"]), **x} for x in overlap(ctx, a.id)]
        rows = [line(r, f"score {r['score']}: {', '.join(r['terms'])}") for r in res]
    elif a.what == "term":
        ids = [r["id"] for r in ctx.db.execute("SELECT DISTINCT id FROM terms WHERE term=?", (a.text.lower(),))]
        res = [describe(ctx, i) for i in ids]
        rows = [line(r) for r in res]
    elif a.what == "search":
        q = " ".join(f'"{w}"' for w in re.findall(r"\w+", a.text))
        found = ctx.db.execute("SELECT id, bm25(fts) AS s FROM fts WHERE fts MATCH ? ORDER BY s LIMIT 20", (q,))
        res = [{**describe(ctx, int(r["id"])), "score": round(-r["s"], 2)} for r in found]
        rows = [line(r, f"score {r['score']}") for r in res]
    elif a.what == "similar":
        model = ollama_ready(ctx) or die("meaning search needs Ollama with the embeddings model")
        if a.id:
            row = ctx.db.execute("SELECT vec FROM emb WHERE id=?", (a.id,)).fetchone() or die(f"{a.id} has no embedding; run spec.py embed")
            vec = array.array("f", row["vec"])
        else:
            vec = embed_texts(ctx, model, [f"search_query: {a.text}"])[0]
        res = [{**describe(ctx, i), "score": s} for s, i in similar(ctx, vec, a.id)]
        rows = [line(r, f"cosine {r['score']}") for r in res]
    else:
        res = [dict(ctx.item(a.id))]
        res[0].pop("body", None)
        res[0]["folder"] = str(ctx.spec / res[0]["path"])
        rows = [json.dumps(res[0], indent=2)]
    print(json.dumps(res, indent=2) if a.json else ("\n".join(rows) or "no results"))


# ---------------------------------------------------------------- impact

def build_impact(ctx, wid, hops, sims=None):
    """Candidates for one item. `sims` = precomputed [(cosine, id)] (the --all path), else computed."""
    me = ctx.item(wid)
    cands = {}

    def add(i, signal):
        cands.setdefault(i, {**describe(ctx, i), "signals": []})["signals"].append(signal)

    for x in links(ctx, wid, hops):
        add(x["id"], {"kind": "link", "hops": x["hops"], "rel": x["rel"], "via": x["via"]})
    for x in overlap(ctx, wid):
        add(x["id"], {"kind": "terms", "score": x["score"], "terms": x["terms"]})
    if sims is None and ollama_ready(ctx):
        row = ctx.db.execute("SELECT vec FROM emb WHERE id=?", (wid,)).fetchone()
        sims = similar(ctx, array.array("f", row["vec"]), wid) if row else None
    for s, i in sims or []:
        add(i, {"kind": "meaning", "cosine": s})
    scopes = [dict(r) for r in ctx.db.execute("SELECT * FROM scopes ORDER BY root")]
    ordered = sorted(cands.values(), key=lambda c: (not c.get("synced", True), -len(c["signals"])))
    out = {"target": describe(ctx, wid), "target_other_links": json.loads(me["other"] or "{}"),
           "generated_at": now(), "scopes": scopes, "meaning_search": sims is not None,
           "item_count": ctx.db.execute("SELECT COUNT(*) FROM items").fetchone()[0],
           "candidates": [c for c in ordered if c.get("synced", True) and not c["removed"]],
           "removed": [c for c in ordered if c.get("synced", True) and c["removed"]],
           "unsynced_links": [c["id"] for c in ordered if not c.get("synced", True)]}
    (ctx.spec / me["path"] / "impact.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def cmd_impact(a):
    ctx = Ctx()
    if a.all:
        return impact_all(ctx, a)
    ctx.item(a.id) or die(f"{a.id} is not synced. Run: spec.py sync --id {a.id}")
    out = build_impact(ctx, a.id, a.hops)
    scopes = out["scopes"]
    print(f"target  {line(out['target'])}")
    if out["target_other_links"]:
        print("        non-spec links: " + ", ".join(f"{n} × {k}" for k, n in out["target_other_links"].items()))
    print(f"scopes  {', '.join(s['root'] + ' @ ' + s['synced_at'] for s in scopes)}  ({out['item_count']} items)")
    if not out["meaning_search"]:
        print("meaning search: off (Ollama or model missing, or item not embedded)")
    for c in out["candidates"]:
        sig = "; ".join(f"{s['kind']}:{s.get('rel') or s.get('score') or s.get('cosine')}" for s in c["signals"])
        print("  " + line(c, sig))
    if out["removed"]:
        print(f"removed items with signals: {', '.join(str(c['id']) for c in out['removed'])}")
    if out["unsynced_links"]:
        print(f"linked but NOT synced (outside every scope): {', '.join(map(str, out['unsynced_links']))}")
    print(f"wrote {ctx.spec / ctx.item(a.id)['path'] / 'impact.json'}")


# Rough cost model for the agent half of a full-spec run. Deliberately a floor, not a forecast:
# every turn re-sends the growing context, so real usage is usually several times this.
TOKENS_PER_PAIR = 500     # judging one pair and writing its line
CHARS_PER_TOKEN = 4


def pair_strength(sig):
    return (sig.get("link_hops") == 1 or len(sig["kinds"]) >= 2
            or sig.get("terms", 0) >= 10 or sig.get("cosine", 0) >= 0.80)


def impact_all(ctx, a):
    """Candidate pairs for every item (or every item under --scope), deduplicated: A-B is judged once."""
    rows = {r["id"]: r for r in ctx.db.execute("SELECT id, parent, path, title, type FROM items "
                                               "WHERE removed=0 AND missing=0")}
    if a.scope:
        rows.get(a.scope) or die(f"{a.scope} is not synced")
        kids = {}
        for i, r in rows.items():
            kids.setdefault(r["parent"], []).append(i)
        keep, stack = set(), [a.scope]
        while stack:
            i = stack.pop()
            if i not in keep:
                keep.add(i)
                stack += kids.get(i, [])
        rows = {i: r for i, r in rows.items() if i in keep}
    ids = sorted(rows)
    sims = {}
    if ollama_ready(ctx):
        import numpy as np  # ponytail: full n×n matrix; fine to ~20k specs, chunk it beyond that
        vecs = {r["id"]: array.array("f", r["vec"]) for r in ctx.db.execute("SELECT id, vec FROM emb")}
        have = [i for i in ids if i in vecs]
        allids = sorted(vecs)
        if have:
            m = np.array([vecs[i] for i in allids], dtype=np.float32)
            m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
            pos = {i: n for n, i in enumerate(allids)}
            scores = m[[pos[i] for i in have]] @ m.T
            for row_n, i in enumerate(have):
                order = np.argsort(-scores[row_n])
                sims[i] = [(round(float(scores[row_n][j]), 3), allids[j]) for j in order if allids[j] != i][:15]
    pairs = {}
    for n, wid in enumerate(ids, 1):
        out = build_impact(ctx, wid, a.hops, sims.get(wid, []) if sims else None)
        for c in out["candidates"]:
            if c["id"] not in rows:          # outside the scope: the per-item impact.json still lists it
                continue
            key = (min(wid, c["id"]), max(wid, c["id"]))
            sig = pairs.setdefault(key, {"kinds": set()})
            for s in c["signals"]:
                sig["kinds"].add(s["kind"])
                if s["kind"] == "link":
                    sig["link_hops"] = min(sig.get("link_hops", 9), s["hops"])
                    sig.setdefault("rel", s["rel"])
                elif s["kind"] == "terms":
                    sig["terms"] = max(sig.get("terms", 0), s["score"])
                    sig["shared_terms"] = s["terms"]
                else:
                    sig["cosine"] = max(sig.get("cosine", 0), s["cosine"])
        if n % 100 == 0:
            print(f"  scanned {n}/{len(ids)}")

    def size(i):
        f = ctx.spec / rows[i]["path"] / "requirements.md"
        return f.stat().st_size if f.is_file() else 0

    def estimate(sel):
        files = {i for k in sel for i in k}
        return sum(size(i) for i in files) // CHARS_PER_TOKEN + len(sel) * TOKENS_PER_PAIR, len(files)

    listed = []
    for (x, y), sig in pairs.items():
        listed.append({"a": x, "b": y, "a_title": rows[x]["title"], "b_title": rows[y]["title"],
                       "a_path": rows[x]["path"], "b_path": rows[y]["path"],
                       "strong": pair_strength(sig), "kinds": sorted(sig["kinds"]),
                       **{k: v for k, v in sig.items() if k != "kinds"}})
    listed.sort(key=lambda p: (not p["strong"], -len(p["kinds"]), -(p.get("cosine") or 0)))
    strong = [(p["a"], p["b"]) for p in listed if p["strong"]]
    est_all, files_all = estimate(list(pairs))
    est_strong, files_strong = estimate(strong)
    summary = {"generated_at": now(), "scope": a.scope, "items": len(ids), "meaning_search": bool(sims),
               "pairs": len(listed), "strong_pairs": len(strong),
               "estimate": {"all": {"tokens_min": est_all, "files": files_all},
                            "strong": {"tokens_min": est_strong, "files": files_strong},
                            "model": f"{TOKENS_PER_PAIR} tokens/pair + requirements.md size/{CHARS_PER_TOKEN}; "
                                     "a floor — context re-reads usually multiply it"},
               "pair_list": listed}
    dest = (ctx.spec / rows[a.scope]["path"] if a.scope else ctx.spec / ".index") / "impact-all.json"
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"items   {len(ids)}{' under ' + str(a.scope) if a.scope else ''}   meaning search: {'on' if sims else 'off'}")
    print(f"pairs   {len(listed)} candidate pairs, {len(strong)} strong")
    print(f"cost    all pairs:    at least ~{est_all:,} tokens ({files_all} spec files)")
    print(f"        strong pairs: at least ~{est_strong:,} tokens ({files_strong} spec files)")
    print("        (a floor: each agent turn re-sends its growing context, so real use is often 3-5x this)")
    print(f"wrote {dest}")

# ---------------------------------------------------------------- next

def _next_state(ctx):
    rows = {r["id"]: dict(r) for r in ctx.db.execute("SELECT * FROM items")}
    links = {}
    for r in ctx.db.execute("SELECT src, dst, rel FROM links"):
        links.setdefault(r["src"], []).append((r["rel"], r["dst"]))
    path = ctx.spec / ".index" / "next.json"
    judged = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return rows, links, path, judged


def cmd_next(a):
    ctx = Ctx()
    if not ctx.item(a.scope):
        die(f"{a.scope} is not synced. Run: spec.py sync --id {a.scope}")
    me = a.email or adowrite.my_email() or die("no email: set git config user.email, or pass --email")
    rows, links, _, judged = _next_state(ctx)
    res = nextpick.plan(rows, links, a.scope, a.version, me, ctx.cfg["next"], ctx.cfg["doneStates"], judged)
    if a.json:
        print(json.dumps(res, indent=2))
        return
    s = rows[a.scope]
    print(f"Next under {a.scope} {s['type']} — {s['title']}, version {a.version}, for {me}\n")
    w = ctx.cfg["next"]["weights"]
    print(f"Ready, best first (bugs and issues first; dev priority = priority {w['priority']} / severity "
          f"{w['severity']} / complexity {w['complexity']}, {ctx.cfg['next']['complexity']}):")
    for n, r in enumerate(res["ranked"], 1):
        print(f"  {n:>2}. {r['id']:<7} {r['type']:<15} dev {r['devPriority']:>5}  P{r['priority'] or '-'} "
              f"S{r['severity'] or '-'} C{r['complexity']} ({r['complexitySource']})  {r['title'][:60]}  [{r['note']}]")
        if r.get("notBlocked"):
            print(f"      not blocked: {r['notBlocked']}")
    if not res["ranked"]:
        print("  none")
    if res["needs"]:
        print("\nNeeds a judgement first (spec.py next-judge):")
        for r in res["needs"]:
            print(f"  {r['id']:<7} {r['type']:<15} {r['title'][:60]}")
            if "blocked" in r["ask"]:
                for e in r["evidence"]:
                    print(f"      blocked? {e['kind']}: {e['id']} {e['title'][:50]} ({e['state']}"
                          f"{', ' + e['board'] if e['board'] else ''}){'  …' + e['text'] + '…' if e['text'] else ''}")
            if "complexity" in r["ask"]:
                print("      complexity? no effort in ADO: estimate 1-5 from the requirement and the code")
    if res["blocked"]:
        print("\nBlocked:")
        for r in res["blocked"]:
            print(f"  {r['id']:<7} {r['type']:<15} {r['title'][:60]}\n      {r['reason']}")
    if res["unavailable"]:
        print("\nNot available:")
        for r in res["unavailable"]:
            print(f"  {r['id']:<7} {r['type']:<15} {r['title'][:50]} — {r['why']}")


def cmd_next_judge(a):
    ctx = Ctx()
    rows, links, path, judged = _next_state(ctx)
    r = rows.get(a.id) or die(f"{a.id} is not synced. Run: spec.py sync --id {a.scope}")
    if not (a.reason or "").strip():
        die("a judgement needs --reason: what you read that decided it")
    j = judged.setdefault(str(a.id), {})
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if a.blocked:
        evs = nextpick.evidence(r, links.get(a.id, []), rows, ctx.cfg["doneStates"])
        if not evs:
            die(f"{a.id} has no blocking evidence to judge: nothing to record")
        j["blocked"] = {"value": a.blocked == "yes", "reason": a.reason.strip(), "key": nextpick.evidence_key(evs),
                        "on": [e["id"] for e in evs], "at": at}
    if a.complexity:
        j["complexity"] = {"value": a.complexity, "reason": a.reason.strip(), "hash": r["hash"], "at": at}
    path.write_text(json.dumps(judged, indent=2) + "\n", encoding="utf-8")
    print(f"{a.id}: " + ", ".join(x for x in (f"blocked={a.blocked}" if a.blocked else "",
                                            f"complexity={a.complexity}" if a.complexity else "") if x))


# ---------------------------------------------------------------- writes

def _refresh(ids):
    """Re-sync what was written, so the mirror and index show it."""
    for wid in ids:
        try:
            cmd_sync(argparse.Namespace(id=wid, all=False, no_embed=True))
        except (RuntimeError, OSError, SystemExit) as e:
            print(f"warning: the write landed, but re-syncing {wid} failed ({e}). Run: spec.py sync --id {wid}")


def _write_each(a, ids, plan, label):
    """Apply one decision per item, report each, re-sync the written ones. Exit 3 if any was refused."""
    cfg = load_config(require_root())
    written, refused = [], []
    for wid in ids:
        try:
            w, ops = adowrite.write(cfg, wid, plan, dry_run=a.dry_run)
        except (adowrite.Refused, adowrite.Conflict) as e:
            refused.append(wid)
            print(f"{wid}: not {label}: {e}")
            continue
        fields = ", ".join(f"{o['path'].split('/')[-1]}={o['value']}" for o in ops
                           if len(str(o["value"])) < 80) or "nothing to change"
        if a.dry_run:
            print(f"{wid}: would write {json.dumps([{'op': 'test', 'path': '/rev', 'value': w['rev']}] + ops)}")
        else:
            print(f"{wid}: {label} ({fields})")
            if ops:
                written.append(wid)
    if written:
        _refresh(written)
    if refused:
        sys.exit(3)


def cmd_claim(a):
    me = a.email or adowrite.my_email() or die("no email: set git config user.email, or pass --email")
    busy = load_config(require_root())["next"]["inProgress"]
    _write_each(a, a.id, lambda f: adowrite.claim_ops(f, me, reopen=a.reopen, take=a.take,
                                                     busy=(busy["states"], busy["boards"])), "claimed")


def cmd_handover(a):
    text = lambda p: Path(p).read_text(encoding="utf-8") if p else None
    rcd, res = text(a.root_cause_details_file), text(a.resolution_file)
    _write_each(a, [a.id], lambda f: adowrite.handover_ops(f, a.tag, rcd, res, a.root_cause), "handed over to QA")


def cmd_sprint(a):
    cfg = load_config(require_root())
    paths = {}

    def plan(fields):
        project = fields[adowrite.PROJECT]
        if project not in paths:
            paths[project] = adowrite.current_iteration(cfg, project, a.team)
        return adowrite.iteration_ops(fields, paths[project])
    _write_each(a, a.id, plan, "in the current sprint")


def cmd_comment(a):
    cfg = load_config(require_root())
    body = Path(a.file).read_text(encoding="utf-8")
    try:
        project = adowrite.read(cfg, a.id)["fields"][adowrite.PROJECT]
        if a.dry_run:
            adowrite.refuse_mentions(body, "the comment")
            print(f"{a.id}: would post a comment of {len(body)} characters to {project}")
            return
        r = adowrite.comment(cfg, project, a.id, body)
    except (adowrite.Refused, adowrite.Conflict) as e:
        print(f"{a.id}: comment not posted: {e}")
        sys.exit(3)
    print(f"{a.id}: comment {(r or {}).get('id', '')} posted")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sync")
    s.add_argument("--id", type=int)
    s.add_argument("--all", action="store_true")
    s.add_argument("--no-embed", action="store_true")
    sp.add_parser("embed")
    s = sp.add_parser("query")
    s.add_argument("what", choices=["links", "overlap", "term", "search", "similar", "show"])
    s.add_argument("text", nargs="?")
    s.add_argument("--id", type=int)
    s.add_argument("--hops", type=int, default=2)
    s.add_argument("--json", action="store_true")
    s = sp.add_parser("impact")
    s.add_argument("--id", type=int)
    s.add_argument("--all", action="store_true", help="every synced item: deduplicated candidate pairs + a token estimate")
    s.add_argument("--scope", type=int, help="with --all: only items under this epic/feature/story")
    s.add_argument("--hops", type=int, default=2)
    s = sp.add_parser("claim", help="assign to you, Active, Dev In Progress (rev-tested)")
    s.add_argument("--id", type=int, action="append", required=True, help="repeat for a batch: claim every one")
    s.add_argument("--email", help="default: git config user.email")
    s.add_argument("--reopen", action="store_true", help="the item is Resolved/Closed and the user said to claim it anyway")
    s.add_argument("--take", action="store_true",
                   help="the item is on someone else's name but not started, and the user chose to take it")
    s.add_argument("--dry-run", action="store_true")
    s = sp.add_parser("handover", help="Resolved + Dev Completed, the hand-over to QA (rev-tested)")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--tag", help="append this tag (the spec flow's team/{version} segment)")
    s.add_argument("--root-cause-details-file", help="HTML for Custom.RootCauseDetails (required for an Issue)")
    s.add_argument("--resolution-file", help="HTML for Microsoft.VSTS.Common.Resolution (required for an Issue)")
    s.add_argument("--root-cause", help="the Microsoft.VSTS.CMMI.RootCause picklist value, when it is clear")
    s.add_argument("--dry-run", action="store_true")
    s = sp.add_parser("sprint", help="move to the current sprint (rev-tested)")
    s.add_argument("--id", type=int, action="append", required=True, help="repeat: every item the PR covers")
    s.add_argument("--team", help="default: '<project> Team'")
    s.add_argument("--dry-run", action="store_true")
    s = sp.add_parser("comment", help="post an HTML comment on a work item")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--file", required=True, help="the comment, as HTML")
    s.add_argument("--dry-run", action="store_true")
    s = sp.add_parser("next", help="which item under an epic or feature to take next")
    s.add_argument("--scope", type=int, required=True, help="the epic or feature the dev is assigned")
    s.add_argument("--version", required=True, help="the team branch version the items are tagged with")
    s.add_argument("--email", help="default: git config user.email")
    s.add_argument("--json", action="store_true")
    s = sp.add_parser("next-judge", help="record whether an item is blocked, or its estimated complexity")
    s.add_argument("--scope", type=int, required=True)
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--blocked", choices=["yes", "no"])
    s.add_argument("--complexity", type=int, choices=[1, 2, 3, 4, 5])
    s.add_argument("--reason", required=True)
    a = ap.parse_args()
    if a.cmd == "next-judge" and not (a.blocked or a.complexity):
        die("next-judge needs --blocked yes|no, --complexity 1-5, or both")
    if a.cmd == "impact" and bool(a.all) == bool(a.id):
        die("impact needs --id N, or --all [--scope N]")
    if a.cmd == "impact" and a.scope and not a.all:
        die("--scope only works with --all")
    if a.cmd == "sync" and a.all and a.id:
        die("use --id or --all, not both")
    if a.cmd == "query" and a.what in ("term", "search") and not a.text:
        die(f"query {a.what} needs TEXT")
    if a.cmd == "query" and a.what == "similar" and not a.id:
        a.text = a.text or die("query similar needs --id or TEXT")
    {"sync": cmd_sync, "embed": cmd_embed, "query": cmd_query, "impact": cmd_impact, "claim": cmd_claim,
     "handover": cmd_handover, "sprint": cmd_sprint, "comment": cmd_comment, "next": cmd_next,
     "next-judge": cmd_next_judge}[a.cmd](a)


if __name__ == "__main__":
    main()
