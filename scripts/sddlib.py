"""Shared helpers for the sdd scripts: workspace config, ADO REST, git, work item folders.

Every script finds the workspace by walking up from the current directory to the first
folder holding .claude/sdd.json. Run `env.py init` once per workspace to create it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
CONFIG_REL = Path(".claude") / "sdd.json"

DEFAULTS = {
    "specRoot": "docs/spec",
    "worktreeRoot": ".claude/worktrees",
    "repoDirs": [],  # empty = discover from .gitmodules plus any child/grandchild folder holding .git
    "ado": {"org": "", "projects": []},
    "specTypes": ["Epic", "Feature", "User Story", "Tech Story", "Change Request",
                  "Product Backlog Item", "Bug", "Issue"],
    "branchTemplate": "dev/{developer}/{version}/{type}/{id}-{slug}",
    "doneStates": ["Resolved", "Closed", "Done"],  # ADO states that mean the flow's close-out ran
    "embeddings": {"provider": "ollama", "url": "http://localhost:11434", "model": "nomic-embed-text"},
}

TYPE_SEGMENT = {
    "User Story": "story", "Product Backlog Item": "story", "Change Request": "story",
    "Feature": "feature", "Epic": "feature",
    "Bug": "bug", "Issue": "bug",
    "Tech Story": "tech", "Task": "tech",
}
BUG_TYPES = {"Bug", "Issue"}


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- workspace / config

def find_root(start=None):
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / CONFIG_REL).is_file():
            return d
    return None


def require_root():
    root = find_root()
    if not root:
        die(f"no {CONFIG_REL} found above {os.getcwd()}. Run: python env.py init  (from the workspace root)")
    return root


def load_config(root):
    cfg = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    merged = {**DEFAULTS, **cfg}
    merged["ado"] = {**DEFAULTS["ado"], **cfg.get("ado", {})}
    merged["embeddings"] = {**DEFAULTS["embeddings"], **cfg.get("embeddings", {})}
    return merged


def slug(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = s[:limit].strip("-")
    return s or "untitled"


# ---------------------------------------------------------------- git

def git(args, cwd, check=True, capture=True):
    r = subprocess.run(["git", *args], cwd=str(cwd), text=True, encoding="utf-8",
                       capture_output=capture)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed in {cwd}:\n{(r.stderr or r.stdout or '').strip()}")
    return (r.stdout or "").strip() if capture else ""


def parse_remote(url):
    """Azure DevOps remote -> (org, project, repo). Handles https, ssh and visualstudio.com forms."""
    url = (url or "").strip()
    for pat in (r"dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+?)(?:\.git)?/?$",
                r"ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/([^/]+?)(?:\.git)?/?$",
                r"//([^./@]+)\.visualstudio\.com/(?:DefaultCollection/)?([^/]+)/_git/([^/]+?)(?:\.git)?/?$"):
        m = re.search(pat, url)
        if m:
            return tuple(urllib.request.unquote(x) for x in m.groups())
    return None


def discover_repos(root, cfg):
    """{name: Path} for every repo in the workspace. Name is the folder name."""
    dirs = []
    if cfg.get("repoDirs"):
        dirs = [root / d for d in cfg["repoDirs"]]
    else:
        gm = root / ".gitmodules"
        if gm.is_file():
            dirs += [root / m for m in re.findall(r"^\s*path\s*=\s*(.+?)\s*$", gm.read_text(), re.M)]
        for child in root.iterdir():
            if child.name.startswith(".") or not child.is_dir():
                continue
            dirs.append(child)
            dirs += [g for g in child.iterdir() if g.is_dir() and not g.name.startswith(".")]
    wt_root = (root / cfg["worktreeRoot"]).resolve()
    repos = {}
    for d in dirs:
        d = d.resolve()
        if (d / ".git").exists() and wt_root not in d.parents and d != root:
            repos.setdefault(d.name, d)
    return repos


def ensure_ignored(repo_dir, rel, is_dir=True):
    """Make sure `rel` is ignored in repo_dir; add it to .git/info/exclude (machine-local) if not."""
    if not (repo_dir / ".git").exists():
        return
    probe = rel.rstrip("/") + ("/x" if is_dir else "")
    if subprocess.run(["git", "check-ignore", "-q", probe], cwd=str(repo_dir)).returncode == 0:
        return
    common = Path(git(["rev-parse", "--git-common-dir"], repo_dir))
    if not common.is_absolute():
        common = repo_dir / common
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as f:
        f.write(f"\n{rel.rstrip('/')}{'/' if is_dir else ''}\n")
    print(f"added {rel.rstrip('/')}{'/' if is_dir else ''} to {exclude}")


def developer():
    email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
    name = email.split("@")[0] if email else (os.environ.get("USERNAME") or os.environ.get("USER") or "")
    return slug(name) if name else die("cannot work out the developer name; set git config user.email")


# ---------------------------------------------------------------- ADO REST

_token = None


def token():
    global _token
    if _token:
        return _token
    az = shutil.which("az") or shutil.which("az.cmd")
    if not az:
        die("Azure CLI (az) not found. Install it and run: az login")
    r = subprocess.run([az, "account", "get-access-token", "--resource", ADO_RESOURCE,
                        "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        die("could not get an ADO token from az. Run: az login\n" + r.stderr.strip())
    _token = r.stdout.strip()
    return _token


def ado(method, url, body=None, content_type="application/json"):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token()}", "Content-Type": content_type,
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"ADO {method} {url} -> HTTP {e.code}: {detail}") from None


def org_url(cfg):
    org = cfg["ado"]["org"] or die("ado.org is empty in .claude/sdd.json")
    return f"https://dev.azure.com/{urllib.request.quote(org)}"


def get_items(cfg, ids, fields=None, relations=False):
    """Batch read, 200 ids per call. Missing (deleted) ids are simply absent from the result."""
    out, ids = [], sorted(set(int(i) for i in ids))
    for i in range(0, len(ids), 200):
        body = {"ids": ids[i:i + 200], "errorPolicy": "omit"}
        if relations:
            body["$expand"] = "relations"
        elif fields:
            body["fields"] = fields
        r = ado("POST", f"{org_url(cfg)}/_apis/wit/workitemsbatch?api-version=7.1", body)
        out += [w for w in (r or {}).get("value", []) if w]
    return out


def wiql(cfg, query, project=None):
    base = org_url(cfg) + (f"/{urllib.request.quote(project)}" if project else "")
    r = ado("POST", f"{base}/_apis/wit/wiql?$top=20000&api-version=7.1", {"query": query})
    if "workItemRelations" in r:
        return r["workItemRelations"]
    return [w["id"] for w in r.get("workItems", [])]


# ---------------------------------------------------------------- work item folders

def wt_root(root, cfg):
    return (root / cfg["worktreeRoot"]).resolve()


def find_env(root, cfg, wid):
    """The .claude/worktrees/{id}-{slug} folder for a work item, or None."""
    base = wt_root(root, cfg)
    if not base.is_dir():
        return None
    hits = [d for d in base.iterdir() if d.is_dir() and re.match(rf"^{int(wid)}-", d.name)
            and (d / "workitem.json").is_file()]
    return hits[0] if hits else None


def read_env(env_dir):
    return json.loads((env_dir / "workitem.json").read_text(encoding="utf-8"))


def write_env(env_dir, data):
    (env_dir / "workitem.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
