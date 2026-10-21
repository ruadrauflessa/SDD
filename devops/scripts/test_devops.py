"""Self-check for the devops scripts: the pure functions, then the real commands on git repos in temp folders
against the offline ADO (DEVOPS_FAKE_ADO).

    python devops/scripts/test_devops.py      (needs git; the scan commands also need pwsh)
"""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import devops  # noqa: E402
import devopslib as L  # noqa: E402
import notes as N  # noqa: E402
import prs as P  # noqa: E402

HAVE_PWSH = bool(shutil.which("pwsh") or shutil.which("pwsh.exe"))


def _force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


@contextlib.contextmanager
def scratch():
    """A temp folder that is really removed afterwards (git's read-only objects included), even on Windows."""
    here = os.getcwd()
    d = tempfile.mkdtemp(prefix="devops-test-")
    try:
        yield Path(d)
    finally:
        os.chdir(here)
        os.environ.pop("DEVOPS_FAKE_ADO", None)
        for wait in (0, 0.2, 1, 3):
            time.sleep(wait)
            try:
                shutil.rmtree(d, onerror=_force)
                break
            except OSError:
                continue
        assert not os.path.exists(d), f"could not remove {d}"


def sh(args, cwd, check=True):
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def run(root, *args):
    """devops.py in-process: (exit code, stdout + stderr)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = devops.main(["--root", str(root), *args])
        except SystemExit as e:
            code = e.code
    return code, buf.getvalue()


# ---------------------------------------------------------------- pure functions

def check_lint():
    assert L.lint_outbound("Fixes ADO 12345 and [#123](u)", "pr") == []
    assert any("mention" in p for p in L.lint_outbound("Fixes #12345", "pr"))
    assert any("AB-123" in p for p in L.lint_outbound("Fix AB#123", "sync-pr"))
    assert L.lint_outbound("Fix AB#123", "pr") == []  # a release PR may name AB#
    assert any("password" in p for p in L.lint_outbound("Server=x;Password=hunter22", "wiki"))
    assert any("placeholder" in p for p in L.lint_outbound("# Release {version}", "wiki"))
    assert any("path on this computer" in p for p in L.lint_outbound(r"see C:\Users\ann\x.txt", "wiki"))
    assert any("4000" in p for p in L.lint_outbound("x" * 4001, "pr"))
    assert any("environment" in p for p in L.lint_outbound("# Release 1.0\n", "wiki", "PROD"))
    assert any("PAT" in p for p in L.lint_outbound("token " + "a" * 52, "wiki"))
    assert L.lint_outbound("# Release 1.0 — PROD\nsha " + "a1b2c3d4" * 5, "wiki", "PROD") == []


def check_helpers():
    assert P.sanitize("Fix AB#123 and #4567, not ADO 89") == "Fix AB-123 and AB-4567, not ADO 89"
    assert [v for v in sorted(["1.10.0", "1.2.0", "1.2.0-rc1", "0.9"], key=L.version_key)] == ["0.9", "1.2.0", "1.2.0-rc1", "1.10.0"]
    pats = L.DEFAULTS["guard"]["protectedBranches"]
    assert L.branch_matches("Team/1.1.0", pats) and L.branch_matches("refs/heads/main", pats)
    assert not L.branch_matches("sync/ann/1.1.0_to_1.2.0", pats) and not L.branch_matches("dev/ann/x", pats)
    assert L.parse_remote("https://ann@dev.azure.com/Org/My%20Proj/_git/Repo") == ("Org", "My Proj", "Repo")
    assert L.parse_remote("git@ssh.dev.azure.com:v3/Org/Proj/Repo") == ("Org", "Proj", "Repo")
    assert L.parse_remote("https://org.visualstudio.com/Proj/_git/Repo.git") == ("org", "Proj", "Repo")
    assert L.wiki_git_path("/Release Notes/Release 1.0.2 [QA] - 2026-07-17") == "/Release-Notes/Release-1.0.2-%5BQA%5D-%2D-2026%2D07%2D17"
    assert L.digest("a \r\nb\n") == L.digest("a\nb")
    assert devops.candidates("Fix 12345: login, AB#777, ADO 888 and #999") == [777, 888, 999, 12345]
    row = {"SourceBranch": "Team/1", "TargetBranch": "Release/1", "Ahead": 40, "FilesChanged": 3, "Insertions": 1, "Deletions": 2,
           "WorkItems": [5], "MigrationFiles": [], "Commits": [{"Short": f"{i:07x}", "Subject": "x" * 120, "WorkItems": []} for i in range(60)]}
    body = P.release_body(row, {"5": {"title": "Fix #9 thing"}}, lambda i: f"https://w/{i}")
    assert len(body) <= 4000 and "more line(s) left out" in body and "AB-9" in body and "[ADO 5](https://w/5)" in body
    sb = P.sync_body("team/1.1.0", "team/1.2.0", [("abc1234", "Fix AB#1 login #22")])
    assert "AB-1" in sb and "AB-22" in sb and not L.lint_outbound(sb, "sync-pr")


def notes_data():
    items = {
        "1": {"id": 1, "type": "Epic", "title": "Platform", "parent": None, "tags": [], "assignee": "", "priority": 2, "url": "https://w/1"},
        "2": {"id": 2, "type": "Feature", "title": "Login", "parent": 1, "tags": [], "assignee": "Ann", "priority": None, "url": "https://w/2"},
        "3": {"id": 3, "type": "Bug", "title": "Crash on save", "parent": 2, "tags": ["UAT", "Regression"], "assignee": "Bo Li-Smith",
              "priority": 1, "area": "Proj\\Gateway", "url": "https://w/3"},
        "4": {"id": 4, "type": "Task", "title": "Wire it", "parent": 3, "tags": [], "assignee": "Cy", "priority": 3, "url": "https://w/4"},
        "5": {"id": 5, "type": "Bug", "title": "Typo", "parent": None, "tags": [], "assignee": "", "priority": None, "url": "https://w/5"},
    }
    prs = [{"id": 70, "repo": "Gateway", "project": "Proj", "title": "Merge team into release", "source": "team/1.0.2",
            "target": "release/1.0.2", "created": "2026-07-17T10:00:00Z", "url": "https://pr/70"}]
    return {"org": "Org", "project": "Proj", "prs": prs, "workItems": items, "prWorkItems": {"70": [4, 5]},
            "migrations": {"70": [{"path": "Migrations/20260101_X.cs", "kind": "EF Core Migration"}]}, "skills": {}, "gaps": []}


def check_notes():
    prs = [{"id": i, "created": c, "target": "release/1"} for i, c in
           [(1, "2026-07-17T10:00:00Z"), (2, "2026-07-17T09:00:00.5Z"), (3, "2026-07-17T05:00:00Z"), (4, "2026-07-17T10:30:00Z")]]
    assert [p["id"] for p in N.newest_cluster(prs, 2)] == [4, 1, 2]
    assert N.release_prs([{"target": "release/x"}, {"target": "main"}, {"target": "Release/y"}]) == [{"target": "release/x"}, {"target": "Release/y"}]
    data = notes_data()
    assert sorted(i["id"] for i in N.selected(data, "all")) == [1, 2, 3, 4, 5]
    assert sorted(i["id"] for i in N.selected(data, "bugs")) == [3, 5]   # a task's parent bug counts
    assert [i["id"] for i in N.selected(data, "tasks")] == [4]
    assert [i["id"] for i in N.selected(data, "features")] == [2]
    groups = N.arrange([data["workItems"]["5"], data["workItems"]["3"]], "both")
    assert [g[0] for g in groups] == ["Priority 1", "Unspecified Priority"]
    assert N.slug_file("20260717", "bugs", ["release-notes-20260717-only-bugs-1.md", "release-notes-20260717-1.md"]) == "release-notes-20260717-only-bugs-2.md"
    assert N.slug_file("20260717", "all", ["release-notes-20260717-only-bugs-1.md"]) == "release-notes-20260717-1.md"
    f, w, facts = N.build(data, "all", "none", "UAT", {"3": "Saving no longer crashes."}, now=datetime(2026, 7, 17, 12))
    assert f.startswith("# Release 1.0.2 — UAT\n") and "- Environment: UAT" in f
    assert "[3](https://w/3) - Gateway - Saving no longer crashes. (Priority 1) — Handled by Bo Li-Smith — Tags: UAT, Regression" in f
    assert "[5](https://w/5) - General - Typo — Handled by Unassigned" in f and "Tags:" not in f.split("[5](")[1].split("\n")[0]
    assert "## Database Migration Changes" in f and "## Skill Documentation Changes" not in f
    assert w.startswith("# Release 1.0.2 — UAT — 2026-07-17")
    assert "#### [#3](https://w/3) Gateway — Crash on save" in w
    assert "Handled_by-Bo_Li--Smith-2B6CB0" in w and "Environment-UAT-2563EB" in w and "Generated-2026--07--17" in w
    assert facts["wikiPath"] == "/Release Notes/Release 1.0.2 [UAT] - 2026-07-17" and facts["needText"] == [5]
    assert w.index("## Delivered Bug Fixes") < w.index("## Features") < w.index("## Epics")
    assert not L.lint_outbound(w, "wiki", "UAT") and not L.lint_outbound(f, "wiki", "UAT")
    line = N.index_line(facts, "/Release-Notes/x", data["prs"])
    page = N.index_page(None, line, "Proj")
    assert page.startswith("# Release Notes") and line in page
    older = "- [Release 1.0.1 [QA] - 2026-07-01](/Release-Notes/y) — **QA** — Only bugs"
    page2 = N.index_page(page.replace(line, older) + "\n## Notes\n\nkeep me\n", line, "Proj")
    assert page2.index(line) < page2.index(older) and "keep me" in page2
    assert N.index_page(page2, line, "Proj").count("/Release-Notes/x)") == 1


# ---------------------------------------------------------------- a workspace with origins

def make_ws(t):
    ws, origins = t / "ws", t / "origins"
    (ws / "projects").mkdir(parents=True)
    origins.mkdir()
    sh(["git", "init", "-q"], ws)
    return ws, origins


def make_repo(ws, origins, name, project="Proj"):
    origin = origins / f"{name}.git"
    sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)], origins)
    repo = ws / "projects" / name
    sh(["git", "clone", "-q", str(origin), str(repo)], ws)
    for k, v in (("user.email", "t@example.com"), ("user.name", "Tester"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        sh(["git", "config", k, v], repo)
    url = f"https://dev.azure.com/Org/{project}/_git/{name}"
    sh(["git", "config", "remote.origin.url", url], repo)
    sh(["git", "config", f"url.{origin.as_posix()}.insteadOf", url], repo)
    (repo / "a.txt").write_text("base\n")
    sh(["git", "add", "."], repo)
    sh(["git", "commit", "-qm", "base"], repo)
    sh(["git", "push", "-q", "origin", "HEAD:main"], repo)
    return repo


def commit(repo, name, text, msg):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    sh(["git", "add", "."], repo)
    sh(["git", "commit", "-qm", msg], repo)


def branch(repo, name, start="main"):
    sh(["git", "switch", "-q", "-c", name, start], repo)
    sh(["git", "push", "-q", "origin", f"HEAD:{name}"], repo)


def world(t, extra=None):
    repos = {f"Proj/{n}": {"id": f"r-{n}", "name": n, "project": {"id": "p-1", "name": "Proj"}} for n in ("Gateway", "UserStore", "Docs")}
    w = {"repositories": repos, "pullRequests": [], "items": {}, "wikis": {"Proj": [{"id": "w1", "name": "Proj.wiki", "type": "projectWiki"}]},
         "pages": {}, "writes": []}
    w.update(extra or {})
    p = t / "world.json"
    p.write_text(json.dumps(w))
    os.environ["DEVOPS_FAKE_ADO"] = str(p)
    return p


def item(i, typ, title, parent=None, project="Proj", **f):
    fields = {"System.WorkItemType": typ, "System.Title": title, "System.State": "Resolved", "System.TeamProject": project, **f}
    if parent:
        fields["System.Parent"] = parent
    return {"rev": 1, "fields": fields, "relations": []}


def release_ws(t):
    ws, origins = make_ws(t)
    gw = make_repo(ws, origins, "Gateway")
    branch(gw, "Release/1.1.0")
    branch(gw, "Team/1.1.0")
    commit(gw, "src/login.cs", "fixed\n", "Fix 12345 login crash")
    commit(gw, "Migrations/20260101120000_AddX.cs", "m\n", "Add migration AB#12346")
    commit(gw, "deps.txt", "2\n", "bump deps")
    sh(["git", "push", "-q", "origin", "HEAD:Team/1.1.0"], gw)
    us = make_repo(ws, origins, "UserStore")
    branch(us, "release/1.1.0")
    commit(us, "a.txt", "release side\n", "hotfix on release")
    sh(["git", "push", "-q", "origin", "HEAD:release/1.1.0"], us)
    branch(us, "team/1.1.0")
    commit(us, "a.txt", "team side\n", "team change #55555")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.1.0"], us)
    docs = make_repo(ws, origins, "Docs")
    branch(docs, "team/1.1.0")
    commit(docs, "d.md", "d\n", "docs")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.1.0"], docs)
    return ws, gw


def check_release(t):
    ws, gw = release_ws(t)
    pending = {"pullRequestId": 77, "repository": {"id": "r-Gateway", "name": "Gateway", "project": {"id": "p-1", "name": "Proj"}},
               "sourceRefName": "refs/heads/dev/ann/fix", "targetRefName": "refs/heads/Team/1.1.0", "title": "Late fix",
               "status": "active", "creationDate": "2026-10-20T10:00:00Z", "workItems": []}
    wp = world(t, {"items": {"12345": item(12345, "Bug", "Login crash"), "12346": item(12346, "Task", "Add X")},
                   "pullRequests": [pending], "branches": {"Proj/Gateway": ["main", "Team/1.1.0", "Release/1.1.0"]}})
    code, text = run(ws, "release", "scan", "--version", "1.1.0")
    assert code == 1, text  # UserStore conflicts
    assert "READY      Gateway: Team/1.1.0 -> Release/1.1.0 · 3 commits" in text, text
    assert "MIGRATION EF Core Migration: Migrations/20260101120000_AddX.cs" in text
    assert "no work item: " in text and "bump deps" in text
    assert "CONFLICTS  UserStore" in text and "MISSING RELEASE BRANCH Docs" in text
    assert "PR 77 Gateway \"Late fix\": rides this release only if it merges" in text
    assert "Not work items (dropped): 55555" in text
    plan = L.read_json(L.state_dir(ws, "release", "1.1.0.json"))
    tok = plan["token"]
    assert tok and plan["items"][0]["source"] == "Team/1.1.0" and plan["items"][0]["workItems"] == [12345, 12346]
    assert "ADO 12345" in plan["items"][0]["description"] and not L.lint_outbound(plan["items"][0]["description"], "pr")
    # no approval, no PR
    code, text = run(ws, "release", "open", "--version", "1.1.0")
    assert code == 2 and "not approved" in text and f"(plan {tok})" in text
    assert not [w for w in json.loads(wp.read_text())["writes"] if w["op"] == "create-pr"]
    # approved, but someone pushed since the scan: refused
    L.approve(ws, tok, "test")
    commit(gw, "late.txt", "l\n", "late commit")
    sh(["git", "push", "-q", "origin", "HEAD:Team/1.1.0"], gw)
    code, text = run(ws, "release", "open", "--version", "1.1.0")
    assert code == 1 and "moved since the scan" in text, text
    # scan again, the plan changes, so the old approval does not cover it
    code, text = run(ws, "release", "scan", "--version", "1.1.0")
    tok2 = L.read_json(L.state_dir(ws, "release", "1.1.0.json"))["token"]
    assert tok2 != tok and not L.approval(ws, tok2)
    L.approve(ws, tok2, "test")
    w = json.loads(wp.read_text())
    w["dropLinks"] = ["12346"]  # ADO drops a cross-project id on create: the read-back links it
    wp.write_text(json.dumps(w))
    code, text = run(ws, "release", "open", "--version", "1.1.0")
    assert code == 0, text
    assert "OPENED PR 101 Gateway" in text and "could not link" not in text
    assert "Hand-off to release-notes: PRs 101 (Proj)" in text and "Migrations/20260101120000_AddX.cs" in text
    w = json.loads(wp.read_text())
    create = next(x for x in w["writes"] if x["op"] == "create-pr")
    assert create["body"]["sourceRefName"] == "refs/heads/Team/1.1.0" and create["body"]["targetRefName"] == "refs/heads/Release/1.1.0"
    assert sorted(w["pullRequests"][-1]["workItems"]) == [12345, 12346]
    # refresh: a later commit with a new work item updates the description and links it
    w["items"]["12347"] = item(12347, "Bug", "Late bug")
    wp.write_text(json.dumps(w))
    commit(gw, "late2.txt", "l\n", "Fix 12347 late")
    sh(["git", "push", "-q", "origin", "HEAD:Team/1.1.0"], gw)
    code, text = run(ws, "release", "scan", "--version", "1.1.0")
    assert "WILL REFRESH PR 101 Gateway: description, link [12347]" in text, text
    L.approve(ws, L.read_json(L.state_dir(ws, "release", "1.1.0.json"))["token"], "test")
    code, text = run(ws, "release", "open", "--version", "1.1.0")
    assert code == 0 and "REFRESHED PR 101" in text, text
    w = json.loads(wp.read_text())
    assert 12347 in w["pullRequests"][-1]["workItems"] and "ADO 12347" in w["pullRequests"][-1]["description"]
    code, text = run(ws, "status", "--json")
    st = json.loads(text)
    assert st["release"][0]["version"] == "1.1.0" and st["plans"][0]["approved"]
    # no ADO: the plan still holds the PR, its work items unchecked candidates, for the MCP fallback
    code, text = run(ws, "release", "scan", "--version", "1.1.0", "--no-ado", "--no-fetch")
    assert "ADO not read" in text and "No PRs headed into" not in text and "WILL OPEN  Gateway" in text, text
    code, text = run(ws, "release", "show", "--version", "1.1.0", "--items")
    items = json.loads(text)
    assert items[0]["source"] == "Team/1.1.0" and set(items[0]["workItems"]) >= {12345, 12346, 12347}


def sync_ws(t):
    ws, origins = make_ws(t)
    a = make_repo(ws, origins, "Gateway")
    branch(a, "team/1.1.0")
    branch(a, "team/1.2.0")
    sh(["git", "switch", "-q", "team/1.1.0"], a)
    commit(a, "fix.txt", "f\n", "Fix AB#4471 login #4472")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.1.0"], a)
    b = make_repo(ws, origins, "UserStore")
    branch(b, "team/1.1.0")
    commit(b, "a.txt", "old side\n", "old change AB#6000")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.1.0"], b)
    sh(["git", "switch", "-q", "main"], b)
    branch(b, "team/1.2.0")
    commit(b, "a.txt", "new side\r\nline2\r\n", "new change")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.2.0"], b)
    sh(["git", "switch", "-q", "main"], b)
    return ws, a, b


def check_sync(t):
    ws, a, b = sync_ws(t)
    wp = world(t, {"items": {"4471": item(4471, "Bug", "Old"), "6000": item(6000, "Bug", "Old 2")}, "autoLink": [4471]})
    code, text = run(ws, "sync", "chain")
    assert code == 0 and "1.1.0 -> 1.2.0  [Gateway, UserStore]  first hop" in text, text
    code, text = run(ws, "sync", "scan", "--source", "1.1.0", "--destination", "1.2.0")
    assert "FastForward     Gateway" in text and "Conflicts       UserStore" in text and "conflict: a.txt" in text, text
    code, text = run(ws, "sync", "plan", "--source", "1.1.0", "--destination", "1.2.0")
    assert code == 1 and "No team-sync work item yet for: Proj" in text, text
    code, text = run(ws, "sync", "techstory", "--project", "Proj", "--create")
    assert code == 0 and "sync team branches (" in text, text
    sid = L.read_json(L.state_dir(ws, "sync", "techstory.json"))["Proj"]["id"]
    code, text = run(ws, "sync", "techstory", "--project", "Proj", "--create")
    assert "reusing" in text  # one per project per day
    # the conflicted repo: a dirty tree is refused, then the merge stops for the user
    (b / "scratch.txt").write_text("mine")
    code, text = run(ws, "sync", "start", "--repo", "UserStore", "--source", "1.1.0", "--destination", "1.2.0", "--user", "ann")
    assert code == 2 and "Snapshot it first" in text, text
    (b / "scratch.txt").unlink()
    code, text = run(ws, "sync", "start", "--repo", "UserStore", "--source", "1.1.0", "--destination", "1.2.0", "--user", "ann")
    assert code == 1 and "sync/ann/1.1.0_to_1.2.0" in text and "a.txt" in text, text
    assert sh(["git", "config", "--get", "branch.sync/ann/1.1.0_to_1.2.0.merge"], b, check=False) == ""  # --no-track
    assert L.read_json(L.state_dir(ws, "sync", "active.json"))["UserStore"]["state"] == "conflict"
    code, text = run(ws, "sync", "verify", "--repo", "UserStore")
    assert code == 1 and "FAIL no unmerged entries" in text
    # a CRLF file whose markers are still there fails the marker scan even once git add marked it resolved
    (b / "a.txt").write_bytes(b"<<<<<<< HEAD\r\nnew side\r\n=======\r\nold side\r\n>>>>>>> x\r\n")
    sh(["git", "add", "a.txt"], b)
    code, text = run(ws, "sync", "verify", "--repo", "UserStore")
    assert code == 1 and "FAIL no conflict markers" in text and "a.txt:1" in text, text
    (b / "a.txt").write_bytes(b"new side\r\nold side\r\n")
    sh(["git", "add", "a.txt"], b)
    code, text = run(ws, "sync", "verify", "--repo", "UserStore")
    assert code == 0, text
    code, text = run(ws, "sync", "finish", "--repo", "UserStore", "--note", "kept both lines")
    assert code == 0 and "pushed" in text, text
    assert "sync/ann/1.1.0_to_1.2.0" in sh(["git", "ls-remote", "--heads", "origin"], b)
    assert "refs/heads/team/1.2.0" in sh(["git", "ls-remote", "--heads", "origin"], b)
    code, text = run(ws, "sync", "plan", "--source", "1.1.0", "--destination", "1.2.0")
    assert code == 0 and f"links only ADO {sid}" in text and "sync/ann/1.1.0_to_1.2.0 -> team/1.2.0" in text, text
    tok = [p for p in L.plans(ws) if p["kind"] == "sync-prs"][0]["token"]
    for it in L.load_plan(ws, tok)["items"]:
        assert "AB#" not in it["description"] and "#4472" not in it["description"] and it["workItems"] == [sid]
    code, text = run(ws, "sync", "open", "--source", "1.1.0", "--destination", "1.2.0")
    assert code == 2 and "not approved" in text
    L.approve(ws, tok, "test")
    code, text = run(ws, "sync", "open", "--source", "1.1.0", "--destination", "1.2.0")
    assert code == 0 and "unlinked [4471]" in text, text
    w = json.loads(wp.read_text())
    assert all(pr["workItems"] == [sid] for pr in w["pullRequests"]), w["pullRequests"]
    res = L.read_json(L.state_dir(ws, "sync", "prs-team_1.1.0-to-team_1.2.0.json"))
    assert {r["repo"] for r in res} == {"Gateway", "UserStore"} and any(r["note"] == "kept both lines" for r in res)
    code, text = run(ws, "sync", "report", "--source", "1.1.0", "--destination", "1.2.0")
    assert code == 0, text
    report = Path(text.split("Report: ")[1].splitlines()[0].strip())
    md = report.read_text(encoding="utf-8")
    assert "kept both lines" in md and "Incomplete" not in md
    report.unlink()


def check_notes_flow(t):
    ws, origins = make_ws(t)
    gw = make_repo(ws, origins, "Gateway")
    branch(gw, "release/1.0.2")
    branch(gw, "team/1.0.2")
    commit(gw, "docs/skills/tariff.md", "---\nname: tariff-search\ndescription: x\n---\nbody\n", "skill")
    commit(gw, "docs/skills/README.md", "# not a skill\n", "readme")
    commit(gw, "SQL Scripts/add.sql", "select 1;\n", "sql")
    sh(["git", "push", "-q", "origin", "HEAD:team/1.0.2"], gw)
    repo = {"id": "r-Gateway", "name": "Gateway", "project": {"id": "p-1", "name": "Proj"}}
    prs_ = [{"pullRequestId": 70, "repository": repo, "sourceRefName": "refs/heads/team/1.0.2", "targetRefName": "refs/heads/release/1.0.2",
             "title": "Merge team/1.0.2 into release/1.0.2", "status": "active", "creationDate": "2026-07-17T10:00:00Z", "workItems": [3]},
            {"pullRequestId": 60, "repository": repo, "sourceRefName": "refs/heads/team/1.0.1", "targetRefName": "refs/heads/release/1.0.1",
             "title": "older", "status": "active", "creationDate": "2026-07-10T10:00:00Z", "workItems": []},
            {"pullRequestId": 80, "repository": repo, "sourceRefName": "refs/heads/dev/x", "targetRefName": "refs/heads/main",
             "title": "not a release", "status": "active", "creationDate": "2026-07-17T10:30:00Z", "workItems": []}]
    items = {"3": item(3, "Bug", "Crash", parent=2, **{"System.Tags": "UAT; Regression", "Microsoft.VSTS.Common.Priority": 1,
                                                      "System.AssignedTo": {"displayName": "Ann Lee"}, "System.AreaPath": "Proj\\Gateway"}),
             "2": item(2, "Feature", "Login", parent=1), "1": item(1, "Epic", "Platform")}
    wp = world(t, {"pullRequests": prs_, "items": items,
                   "pages": {"Proj/w1//Release Notes": {"content": "# Release Notes\n\nIntro.\n\n## Releases\n\n- [Release 1.0.1 [QA] - 2026-07-10](/Release-Notes/old) — **QA** — Only bugs\n", "etag": "\"4\""}}})
    code, text = run(ws, "notes", "collect")
    assert code == 0 and "newest group of 1" in text and "PR 70" in text and "PR 80" not in text, text
    run_id = text.split("Run ")[1].split(":")[0]
    code, text = run(ws, "notes", "detect", "--run", run_id, "--migrations", "--skills")
    assert "Migration files: 1 · skill files: 1" in text, text
    code, text = run(ws, "notes", "render", "--run", run_id, "--scope", "all", "--priority", "both", "--env", "PROD")
    assert code == 0 and "No one-line fix summary yet for bugs [3]" in text, text
    tf = t / "texts.json"
    tf.write_text(json.dumps({"3": "Saving no longer crashes."}))
    code, text = run(ws, "notes", "render", "--run", run_id, "--scope", "all", "--priority", "both", "--env", "PROD", "--texts", str(tf))
    assert code == 0 and "No one-line" not in text, text
    files = sorted((ws / "documents" / "release-notes").glob("*.md"))
    assert len(files) == 1 and files[0].name.endswith("-1.md"), files  # a re-render keeps its own file
    md = files[0].read_text(encoding="utf-8")
    assert "# Release 1.0.2 — PROD" in md and "skill `tariff-search`" in md and "README" not in md and "SQL Script: `SQL Scripts/add.sql`" in md
    meta = L.read_json(L.state_dir(ws, "notes", run_id, "meta.json"))
    code, text = run(ws, "notes", "publish", "--run", run_id)
    assert code == 2 and "not approved" in text
    L.approve(ws, meta["token"], "test")
    # a hand edit after the approval is refused
    wiki = L.state_dir(ws, "notes", run_id, "wiki.md")
    good = wiki.read_text(encoding="utf-8")
    wiki.write_text(good + "\nextra\n", encoding="utf-8")
    code, text = run(ws, "notes", "publish", "--run", run_id)
    assert code == 2 and "changed after it was approved" in text
    wiki.write_text(good, encoding="utf-8")
    code, text = run(ws, "notes", "publish", "--run", run_id)
    assert code == 0 and "Published /Release Notes/Release 1.0.2 [PROD]" in text, text
    w = json.loads(wp.read_text())
    idx = w["pages"]["Proj/w1//Release Notes"]["content"]
    assert idx.index("[Release 1.0.2 [PROD]") < idx.index("[Release 1.0.1 [QA]") and "%5BPROD%5D" in idx
    assert any(k.startswith("Proj/w1//Release Notes/Release 1.0.2 [PROD]") for k in w["pages"])
    # no wiki: refused with what the user does
    w["wikis"] = {}
    wp.write_text(json.dumps(w))
    code, text = run(ws, "notes", "publish", "--run", run_id)
    assert code == 2 and "Create project wiki" in text


def check_env(t):
    ws, origins = make_ws(t)
    gw = make_repo(ws, origins, "Gateway")
    wt = ws / ".claude" / "worktrees" / "80459-close-icon" / "src" / "Gateway"
    sh(["git", "worktree", "add", "-q", "-b", "dev/x/80459", str(wt), "origin/main"], gw)
    commit(wt, "src/x.cs", "x\n", "Fix")
    (ws / ".claude" / "worktrees" / "80459-close-icon" / "workitem.json").write_text(json.dumps({"repos": [{"name": "Gateway", "base": "main"}]}))
    (ws / "scripts").mkdir()
    (ws / "scripts" / "run-stack.ps1").write_text("param(\n  [string[]]$Only,\n  [string]$Worktree,\n  [switch]$Status,\n  [switch]$Stop\n)\nWrite-Host 'mainapi   Main API   7097   UP   (pid 1)  worktree: 80459-close-icon'\n")
    code, text = run(ws, "env", "find", "--id", "80459")
    assert code == 0 and "Gateway (sdd)" in text and "src/x.cs" in text and "Only, Status, Stop, Worktree" in text, text
    assert ".claude/scripts is NOT ignored" in text
    if HAVE_PWSH:
        code, text = run(ws, "env", "gate", "--id", "80459")
        assert code == 0 and "Gate D: PASS" in text, text
        (ws / "scripts" / "run-stack.ps1").write_text("param([switch]$Status)\nWrite-Host 'mainapi   Main API   7097   UP   (pid 1)'\n")
        code, text = run(ws, "env", "gate", "--id", "80459")
        assert code == 1 and "NO TAG for Gateway" in text, text
    sh(["git", "worktree", "remove", "--force", str(wt)], gw)


def main():
    check_lint()
    check_helpers()
    check_notes()
    print("pure functions: ok")
    for name, fn in (("release", check_release), ("sync", check_sync), ("notes", check_notes_flow), ("env", check_env)):
        if name in ("release", "sync") and not HAVE_PWSH:
            print(f"{name}: skipped (no pwsh)")
            continue
        with scratch() as t:
            fn(t)
        print(f"{name}: ok")
    print("all ok")


if __name__ == "__main__":
    main()
