"""Shared helpers of the devops plugin: the workspace, its config, git, the ADO REST client, plans and
approvals, and the outbound lint every PR and wiki page passes.

Standard library only; runs on Python 3.9 and on Windows. Nothing here asks a person anything: the
skills ask, the scripts do the mechanics, the hooks refuse what breaks a rule.

State lives in `<root>/.claude/devops/`:

    plans/<token>.json   a plan of outward writes (PRs, wiki pages); the token is its content's hash
    approvals.jsonl      one line per approved plan: the person's Yes (the question hook or the pane)
    guard.jsonl          one line per refusal of a guard hook
    release/<v>.json     the release-prep plan for version v
    sync/...             the sync chain, scans, PR results, the sync in progress, the tech story cache
    notes/<id>/...       one release-notes run: data.json, wiki.md, meta.json
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6c55d0b"
CONFIG = ".claude/devops.json"
STATE = ".claude/devops"

DEFAULTS = {
    "reposDir": "projects",
    "sourcePattern": "team/{0}",
    "targetPattern": "release/{0}",
    "branchPrefix": "team/",
    "notesDir": "documents/release-notes",
    "clusterGapHours": 2,
    "syncFeatureTitle": "Branch Synchronizations",
    "syncWorkItemType": "Tech Story",
    "guard": {
        "enabled": True,
        "protectedBranches": ["main", "master", "develop", "release/*", "team/*"],
        "forcePush": False,
        "protectWorkingTree": True,
        "requireApproval": True,
        "approvalHours": 24,
    },
}


class Refused(Exception):
    """A rule says no. The message says why and what to do instead."""


def die(msg, code=2):
    print(f"devops: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- workspace and config

def find_root(start=None, repos_dir=None):
    """The workspace root: the nearest folder holding .claude/devops.json, else one holding the repos
    folder or a .gitmodules, else the start folder."""
    here = Path(start or os.getcwd()).resolve()
    chain = [here, *here.parents]
    for d in chain:
        if (d / CONFIG).is_file():
            return d
    name = repos_dir if repos_dir is not None else DEFAULTS["reposDir"]
    for d in chain:
        if (name and (d / name).is_dir()) or (d / ".gitmodules").is_file():
            return d
    return here


def merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


def load_config(root):
    p = Path(root) / CONFIG
    try:
        raw = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        raw = {}
    return merge(DEFAULTS, raw if isinstance(raw, dict) else {})


def state_dir(root, *parts):
    d = Path(root) / STATE
    for p in parts:
        d = d / p
    return d


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for x in lines:
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def is_repo(p):
    return (Path(p) / ".git").exists()


def discover_repos(root, cfg):
    """{name: path} of the workspace's repos: the repos folder's children, else the root itself, else
    the root's children. A submodule (.git is a file) and a plain clone both count."""
    root = Path(root)
    name = cfg.get("reposDir")
    if name and (root / name).is_dir():
        found = {d.name: d for d in sorted((root / name).iterdir()) if d.is_dir() and is_repo(d)}
        if found:
            return found
    if is_repo(root):
        return {root.name: root}
    return {d.name: d for d in sorted(root.iterdir()) if d.is_dir() and is_repo(d)}


# ---------------------------------------------------------------- git

def git(args, cwd, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip() if check else (r.stdout.strip() if r.returncode == 0 else "")


def git_rc(args, cwd):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def remote_heads(repo):
    """The branch names on origin, with the server's own casing."""
    out = git(["ls-remote", "--heads", "origin"], repo, check=False)
    return [ln.split("refs/heads/", 1)[1].strip() for ln in out.splitlines() if "refs/heads/" in ln]


def exact_branch(heads, wanted):
    """The server's spelling of `wanted` (case-insensitive match), or None."""
    w = wanted.lower()
    return next((h for h in heads if h.lower() == w), None)


ADO_URL = [
    re.compile(r"dev\.azure\.com/(?P<org>[^/]+)/(?P<proj>[^/]+)/_git/(?P<repo>[^/?#]+?)(?:\.git)?/?$"),
    re.compile(r"ssh\.dev\.azure\.com:v3/(?P<org>[^/]+)/(?P<proj>[^/]+)/(?P<repo>[^/?#]+?)(?:\.git)?$"),
    re.compile(r"(?P<org>[^/.@]+)\.visualstudio\.com/(?:DefaultCollection/)?(?P<proj>[^/]+)/_git/(?P<repo>[^/?#]+?)(?:\.git)?/?$"),
]


def parse_remote(url):
    """(org, project, repo) of an Azure DevOps origin URL, or None."""
    for rx in ADO_URL:
        m = rx.search((url or "").strip())
        if m:
            q = urllib.parse.unquote
            return q(m.group("org")), q(m.group("proj")), q(m.group("repo"))
    return None


def repo_coords(repo):
    """The configured origin URL, not `remote get-url`: that one applies insteadOf rewrites."""
    return parse_remote(git(["config", "--get", "remote.origin.url"], repo, check=False))


def merge_in_progress(repo):
    gd = git(["rev-parse", "--absolute-git-dir"], repo, check=False)
    return bool(gd) and (Path(gd) / "MERGE_HEAD").exists()


def dirty_files(repo):
    return [x for x in git(["status", "--porcelain"], repo, check=False).splitlines() if x.strip()]


# ---------------------------------------------------------------- versions

def version_key(v):
    """Numeric, not lexical: 1.2.0 before 1.10.0. A suffix (1.1.0-rc1) sorts after its plain version."""
    parts = re.split(r"[.\-]", v)
    nums = []
    for p in parts:
        nums.append((0, int(p), "") if p.isdigit() else (1, 0, p))
    return nums


def local_versions(root, cfg, prefix=None):
    """{version: [repos]} for every origin/<prefix><version> branch the repos already know (no fetch)."""
    prefix = cfg["branchPrefix"] if prefix is None else prefix
    out = {}
    for name, d in discover_repos(root, cfg).items():
        refs = git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/"], d, check=False)
        for r in refs.splitlines():
            b = r[len("origin/"):] if r.startswith("origin/") else r
            if b.lower().startswith(prefix.lower()) and len(b) > len(prefix):
                out.setdefault(b[len(prefix):], []).append(name)
    return {v: sorted(set(rs)) for v, rs in sorted(out.items(), key=lambda kv: version_key(kv[0]))}


# ---------------------------------------------------------------- PowerShell

def pwsh():
    exe = shutil.which("pwsh") or shutil.which("pwsh.exe")
    if not exe:
        die("PowerShell 7 (pwsh) not found. Install it from https://aka.ms/powershell; the scan scripts need it.")
    return exe


def run_ps(script, args, cwd):
    """Runs a skill's .ps1 and returns (exit code, stdout, stderr)."""
    for i, a in enumerate(args[:-1]):  # the scripts do not all make the folder of their JSON output
        if a in ("-JsonPath", "-OutputPath"):
            Path(args[i + 1]).parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, NO_COLOR="1", TERM="dumb")
    r = subprocess.run([pwsh(), "-NoProfile", "-NonInteractive", "-File", str(script), *args], env=env,
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------- ADO REST

class Ado:
    """Azure DevOps REST with an `az` token (or a PAT in AZURE_DEVOPS_EXT_PAT). DEVOPS_FAKE_ADO names an
    offline world file instead (tests)."""

    def __init__(self, org):
        self.org = org
        self.base = f"https://dev.azure.com/{urllib.parse.quote(org)}"
        self._auth = None

    def auth(self):
        if self._auth:
            return self._auth
        if os.environ.get("DEVOPS_ADO_ANONYMOUS"):  # a public project: reads need no sign-in
            return None
        pat = os.environ.get("AZURE_DEVOPS_EXT_PAT") or os.environ.get("DEVOPS_ADO_PAT")
        if pat:
            self._auth = "Basic " + base64.b64encode(f":{pat}".encode()).decode()
            return self._auth
        az = shutil.which("az") or shutil.which("az.cmd")
        if not az:
            raise Refused("Azure CLI (az) not found and no PAT in AZURE_DEVOPS_EXT_PAT. Run `az login`, "
                          "or use the Azure DevOps MCP tools as the skill's fallback says.")
        r = subprocess.run([az, "account", "get-access-token", "--resource", ADO_RESOURCE, "--query",
                            "accessToken", "-o", "tsv"], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            raise Refused("could not get an ADO token from az. Run: az login")
        self._auth = "Bearer " + r.stdout.strip()
        return self._auth

    def url(self, api, project=None, **query):
        q = {"api-version": "7.1", **{k: v for k, v in query.items() if v is not None}}
        proj = f"/{urllib.parse.quote(project)}" if project else ""
        return f"{self.base}{proj}/_apis/{api}?{urllib.parse.urlencode(q, safe='$/')}"

    def call(self, method, url, body=None, content_type="application/json", headers=None, want_headers=False):
        import fakeado  # only answers when DEVOPS_FAKE_ADO is set
        if fakeado.active():
            data, hdrs = fakeado.request(method, url, body, headers or {})
            return (data, hdrs) if want_headers else data
        raw = None if body is None else json.dumps(body).encode("utf-8")
        h = {"Content-Type": content_type, "Accept": "application/json"}
        auth = self.auth()
        if auth:
            h["Authorization"] = auth
        h.update(headers or {})
        req = urllib.request.Request(url, data=raw, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read()
                data = json.loads(text) if text else None
                return (data, dict(resp.headers)) if want_headers else data
        except urllib.error.HTTPError as e:
            if e.code == 404 and want_headers:
                return None, {}
            detail = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"ADO {method} {url.split('?')[0]} -> HTTP {e.code}: {detail}") from None

    # -- git
    def repository(self, project, repo):
        return self.call("GET", self.url(f"git/repositories/{urllib.parse.quote(repo)}", project))

    def pull_requests(self, project, target=None, source=None, status="active", repo=None, top=100):
        path = f"git/repositories/{urllib.parse.quote(repo)}/pullrequests" if repo else "git/pullrequests"
        q = {"searchCriteria.status": status, "$top": top}
        if target:
            q["searchCriteria.targetRefName"] = "refs/heads/" + target
        if source:
            q["searchCriteria.sourceRefName"] = "refs/heads/" + source
        out, skip = [], 0
        while True:
            page = (self.call("GET", self.url(path, project, **q, **{"$skip": skip})) or {}).get("value", [])
            out += page
            if len(page) < top:
                return out
            skip += top

    def pull_request(self, project, pr_id):
        return self.call("GET", self.url(f"git/pullrequests/{int(pr_id)}", project))

    def create_pr(self, project, repo, source, target, title, description, work_items=(), draft=False):
        body = {"sourceRefName": "refs/heads/" + source, "targetRefName": "refs/heads/" + target,
                "title": title, "description": description, "isDraft": bool(draft),
                "workItemRefs": [{"id": str(i)} for i in work_items]}
        return self.call("POST", self.url(f"git/repositories/{urllib.parse.quote(repo)}/pullrequests", project), body)

    def update_pr(self, project, repo, pr_id, fields):
        return self.call("PATCH", self.url(f"git/repositories/{urllib.parse.quote(repo)}/pullrequests/{int(pr_id)}", project), fields)

    def pr_work_items(self, project, repo, pr_id):
        r = self.call("GET", self.url(f"git/repositories/{urllib.parse.quote(repo)}/pullrequests/{int(pr_id)}/workitems", project))
        return sorted(int(x["id"]) for x in (r or {}).get("value", []))

    def prs_by_commit(self, project, repo, sha):
        """The PRs a commit belongs to: one it introduced, or the PR's own merge commit (ADO answers the two
        query types apart; a branch commit alone can match neither, a merge commit only the second)."""
        out, seen = [], set()
        for typ in ("commit", "lastMergeCommit"):
            body = {"queries": [{"type": typ, "items": [sha]}]}
            r = self.call("POST", self.url(f"git/repositories/{urllib.parse.quote(repo)}/pullrequestquery", project), body)
            for prs in (((r or {}).get("results") or [{}])[0]).values():
                for pr in prs:
                    if pr["pullRequestId"] not in seen:
                        seen.add(pr["pullRequestId"])
                        out.append(pr)
        return out

    # -- work items
    def work_items(self, ids, fields=None, relations=False):
        out, ids = [], sorted(set(int(i) for i in ids))
        for i in range(0, len(ids), 200):
            body = {"ids": ids[i:i + 200], "errorPolicy": "omit"}
            if relations:
                body["$expand"] = "relations"
            elif fields:
                body["fields"] = fields
            r = self.call("POST", self.url("wit/workitemsbatch"), body)
            out += [w for w in (r or {}).get("value", []) if w]
        return out

    def patch_item(self, wid, ops):
        return self.call("PATCH", self.url(f"wit/workitems/{int(wid)}"), ops, "application/json-patch+json")

    def create_item(self, project, wtype, ops):
        return self.call("POST", self.url(f"wit/workitems/${urllib.parse.quote(wtype)}", project), ops,
                         "application/json-patch+json")

    def wiql(self, project, query):
        r = self.call("POST", self.url("wit/wiql", project), {"query": query})
        return [w["id"] for w in (r or {}).get("workItems", [])]

    # -- wiki
    def wikis(self, project):
        return (self.call("GET", self.url("wiki/wikis", project)) or {}).get("value", [])

    def wiki_page(self, project, wiki, path):
        data, hdrs = self.call("GET", self.url(f"wiki/wikis/{urllib.parse.quote(wiki)}/pages", project, path=path,
                                               includeContent="true"), want_headers=True)
        etag = next((v for k, v in (hdrs or {}).items() if k.lower() == "etag"), None)
        return data, etag

    def put_wiki_page(self, project, wiki, path, content, etag=None):
        h = {"If-Match": etag} if etag else {}
        return self.call("PUT", self.url(f"wiki/wikis/{urllib.parse.quote(wiki)}/pages", project, path=path),
                         {"content": content}, headers=h)


def pr_link_url(project_id, repo_id, pr_id):
    return f"vstfs:///Git/PullRequestId/{project_id}%2F{repo_id}%2F{pr_id}"


def link_pr_ops(project_id, repo_id, pr_id):
    return [{"op": "add", "path": "/relations/-", "value": {
        "rel": "ArtifactLink", "url": pr_link_url(project_id, repo_id, pr_id),
        "attributes": {"name": "Pull Request"}}}]


def unlink_pr_ops(item, project_id, repo_id, pr_id):
    """JSON Patch that removes this PR's link from a work item read with relations; [] when it has none."""
    want = pr_link_url(project_id, repo_id, pr_id).lower()
    for i, rel in enumerate(item.get("relations") or []):
        if (rel.get("url") or "").lower() == want:
            return [{"op": "test", "path": "/rev", "value": item.get("rev")},
                    {"op": "remove", "path": f"/relations/{i}"}]
    return []


def wiki_git_path(page_path):
    """The wiki's git path of a page: a literal `-` is %2D, a space is `-`, brackets are %5B/%5D.
    `/Release Notes/Release 1.0.2 [QA] - 2026-07-17` -> `/Release-Notes/Release-1.0.2-%5BQA%5D-%2D-2026%2D07%2D17`."""
    segs = []
    for s in page_path.strip("/").split("/"):
        s = s.replace("-", "%2D").replace(" ", "-").replace("[", "%5B").replace("]", "%5D")
        segs.append(s)
    return "/" + "/".join(segs)


def web_pr_url(org, project, repo, pr_id):
    q = urllib.parse.quote
    return f"https://dev.azure.com/{q(org)}/{q(project)}/_git/{q(repo)}/pullrequest/{pr_id}"


def web_item_url(org, project, wid):
    q = urllib.parse.quote
    return f"https://dev.azure.com/{q(org)}/{q(project)}/_workitems/edit/{wid}"


def branches_url(org, project, repo):
    q = urllib.parse.quote
    return f"https://dev.azure.com/{q(org)}/{q(project)}/_git/{q(repo)}/branches"


# ---------------------------------------------------------------- plans and approvals

def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(text):
    """Hash of a text with line endings and trailing spaces evened out, so a CRLF copy matches."""
    norm = "\n".join(ln.rstrip() for ln in (text or "").replace("\r\n", "\n").split("\n")).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def plan_token(kind, items):
    return hashlib.sha256(canonical({"kind": kind, "items": items}).encode("utf-8")).hexdigest()[:10]


def save_plan(root, kind, items, summary, extra=None):
    """Writes the plan and returns its token. The same content gives the same token, so an approval
    holds only for exactly what was shown."""
    token = plan_token(kind, items)
    write_json(state_dir(root, "plans", f"{token}.json"),
               {"token": token, "kind": kind, "created": int(time.time()), "summary": summary,
                "items": items, **(extra or {})})
    return token


def load_plan(root, token):
    return read_json(state_dir(root, "plans", f"{token}.json"))


def plans(root):
    d = state_dir(root, "plans")
    if not d.is_dir():
        return []
    out = [read_json(p) for p in sorted(d.glob("*.json"))]
    return [p for p in out if isinstance(p, dict) and p.get("token")]


def approve(root, token, via, who=None):
    if not load_plan(root, token):
        raise Refused(f"no plan {token} in {state_dir(root, 'plans')}")
    append_jsonl(state_dir(root, "approvals.jsonl"),
                 {"token": token, "at": int(time.time()), "via": via, "who": who or os.environ.get("USERNAME") or os.environ.get("USER") or ""})


def approval(root, token, hours=None):
    """The newest approval of the token still in its window, or None."""
    cfg = load_config(root)
    window = (hours if hours is not None else cfg["guard"]["approvalHours"]) * 3600
    now = time.time()
    rows = [r for r in read_jsonl(state_dir(root, "approvals.jsonl")) if r.get("token") == token]
    rows = [r for r in rows if now - r.get("at", 0) <= window]
    return rows[-1] if rows else None


def require_approval(root, token):
    cfg = load_config(root)
    if not cfg["guard"]["requireApproval"]:
        return
    if not approval(root, token):
        raise Refused(f"plan {token} is not approved. Show the plan to the user and ask with AskUserQuestion: "
                      f"\"{approval_question(root, token)}\" with the options \"Yes, go ahead\" and \"No\". "
                      "Their Yes is recorded by the devops hook; or they press Approve in the /devops pane. A yes typed in the "
                      "chat does not count: ask with AskUserQuestion (or point them to the pane) even if they already said yes.")


def approval_question(root, token):
    p = load_plan(root, token) or {}
    return f"{p.get('summary') or 'Go ahead with this plan'}? (plan {token})"


def approved_items(root, kind):
    """Every item of an approved, in-window plan of this kind."""
    out = []
    for p in plans(root):
        if p.get("kind") == kind and approval(root, p["token"]):
            out += [dict(i, _token=p["token"]) for i in p.get("items", [])]
    return out


# ---------------------------------------------------------------- outbound lint

SECRETS = [
    ("a password or key assignment", re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|accountkey|sharedaccesskey|client[_-]?secret)\s*[=:]\s*[^\s;,'\"]{4,}")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*")),
    ("a JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    ("an Azure DevOps PAT", re.compile(r"(?<![A-Za-z0-9])[a-z2-7]{52}(?![A-Za-z0-9])")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("an AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a connection string", re.compile(r"(?i)(server|data source)=[^;\n]+;[^\n]*(password|pwd)=")),
]
PLACEHOLDER = re.compile(r"\{(org|project|repo|version|environment|env_color|prId|workItemId|assignee|tags?\d*|area|"
                         r"title|scope|short headline|fix summary|presentation mode|pr title|n|yyyy-MM-dd|yyyy|MM|dd)\}")
LOCAL_PATH = re.compile(r"(?i)\b[a-z]:\\users\\[^\\\s]+|(?<![\w.])/(?:home|Users)/[^/\s]+/")
MENTION = re.compile(r"(?<![\w&/\[#-])#\d{3,}\b")
AB_MENTION = re.compile(r"\bAB#\d+")
PR_LIMIT = 4000


def lint_outbound(text, kind, env=None):
    """Problems that stop a text from leaving the machine. kind: 'pr', 'sync-pr', 'wiki', or 'any' (secrets only)."""
    text = text or ""
    out = []
    for what, rx in SECRETS:
        if rx.search(text):
            out.append(f"it holds what looks like {what}")
    if kind == "any":  # a text devops did not write: only what must never leave
        return out
    m = PLACEHOLDER.search(text)
    if m:
        out.append(f"a template placeholder is left in: {m.group(0)}")
    m = LOCAL_PATH.search(text)
    if m:
        out.append(f"it names a path on this computer: {m.group(0)}")
    if kind in ("pr", "sync-pr"):
        m = MENTION.search(text)
        if m:
            out.append(f"`{m.group(0)}` is an ADO mention (it posts onto that work item); write `ADO {m.group(0)[1:]}`")
        if len(text) > PR_LIMIT:
            out.append(f"it is {len(text)} characters; ADO takes at most {PR_LIMIT} in a PR description")
    if kind == "sync-pr":
        m = AB_MENTION.search(text)
        if m:
            out.append(f"`{m.group(0)}` links an old work item to a sync PR; write `AB-{m.group(0)[3:]}`")
    if kind == "wiki" and env:
        first = next((ln for ln in text.splitlines() if ln.startswith("# ")), "")
        if env not in first:
            out.append(f"the page title does not name the environment {env}")
    return out


# ---------------------------------------------------------------- guard log

def guard_log(root, rule, detail):
    try:
        append_jsonl(state_dir(root, "guard.jsonl"), {"at": int(time.time()), "rule": rule, "detail": detail[:400]})
    except OSError:
        pass


def devops_pr(source, target, patterns):
    """A PR devops plans: from a protected or sync/* branch into a protected one (team -> release, team -> team).
    A developer's own branch into team/x is not one: the sdd flow and the person raise those."""
    s = re.sub(r"^refs/heads/", "", source or "")
    return bool(s) and branch_matches(target, patterns) and (branch_matches(s, patterns) or s.lower().startswith("sync/"))


def branch_matches(name, patterns):
    """Case-insensitive glob match of a branch name against the protected patterns."""
    import fnmatch
    n = (name or "").lower()
    if n.startswith("refs/heads/"):
        n = n[len("refs/heads/"):]
    return any(fnmatch.fnmatchcase(n, p.lower()) for p in patterns)
