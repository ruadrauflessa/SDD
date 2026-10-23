#!/usr/bin/env python3
"""devops: the mechanics of the devops skills, so the agent reads a short summary instead of raw git and
ADO output. Every outward write (a PR, a wiki page) goes through a plan the user approved.

    status [--json]                          what the /devops pane shows (reads files only)
    versions [--json]                        team/* versions the repos know (no fetch)
    approve --token T                        record the user's Yes (the pane; the agent may not run it)

    release scan --version V [--no-fetch] [--no-ado] [--repos a,b]
    release open --version V                 create / refresh the approved release PRs, verify links
    release show --version V [--items]       the summary again, or the planned PRs as JSON

    sync chain [--from V] [--to V]           the per-repo version chain and its waves
    sync scan --source S --destination D [--repos a,b] [--prior-source P --prior-destination Q]
    sync start --repo R --source S --destination D --user U [--recreate]
    sync verify --repo R                     the four checks after the user resolved the conflicts
    sync finish --repo R [--note TEXT]       commit, check, push the sync branch
    sync techstory --project P (--create | --id N [--no-check --title T])
    sync plan --source S --destination D     PRs for the clean repos and the pushed sync branches
    sync open --source S --destination D     create the approved sync PRs, keep only the tech story linked
    sync show --source S --destination D     the planned sync PRs as JSON (the MCP fallback)
    sync record --source S --destination D --repo R --pr N   a sync PR made with the MCP tools
    sync report --source S --destination D
    sync restore [--status]                  the snapshot's Restore (or Status), for the pane

    notes collect [--org O] [--project P] [--pr N ...] [--commit SHA --repo R] [--top 50]
    notes ingest --file F                    the MCP fallback: data saved by the agent
    notes detect --run ID [--migrations] [--skills]
    notes render --run ID [--scope S --priority M --env E] [--texts F]   (a re-render keeps the last choices)
    notes publish --run ID
    notes release --version V --env E [--scope S] [--priority M] [--migrations] [--skills]
                                             the pane's one press: notes from the version's release PRs
    notes text --run ID --id N               a bug's one-line fix summary, from stdin; renders again

    pipelines [--version V] [--json]         the newest build of each pipeline on the version's team and release branches
    deployments [--json]                     what each environment (QA, UAT, STAGE, PROD) runs now
    doctor [--json]                          what devops needs (tools, sign-in, access, the wiki) and how to fix what is missing


    reviews list [--all] [--json]            PRs waiting on you (or every active one) in the workspace's projects
    reviews show --project P --id N [--json] one PR: policies, votes, work items, files, threads, may you vote
    reviews pack --project P --id N          the quick review's prompt and the lines a finding may name (the pane)
    reviews save --key K                     the quick review's findings, from stdin (the pane)
    reviews post --project P --id N          the person's comments, from stdin (the pane; the agent may not run it)
    reviews vote --project P --id N --vote approve|suggest|wait|reject|reset   (the pane; the agent may not run it)

Exit 0 = done, 1 = something blocks (conflicts, lint, a failed check), 2 = refused or an error.
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import devopslib as L  # noqa: E402
import notes as N  # noqa: E402
import pipelines as PI  # noqa: E402
import prs as P  # noqa: E402
import reviews as R  # noqa: E402

PLUGIN = HERE.parent
SCAN_RELEASE = PLUGIN / "skills" / "release-prep" / "scripts" / "Scan-ReleasePrep.ps1"
SYNC_DIR = PLUGIN / "skills" / "sync-team-branches" / "scripts"
WI_FIELDS = ["System.Id", "System.Title", "System.WorkItemType", "System.State", "System.Parent", "System.Tags",
             "System.AssignedTo", "System.AreaPath", "System.TeamProject", "Microsoft.VSTS.Common.Priority"]
WI_PATTERNS = [re.compile(p, re.I) for p in (r"AB#(\d{3,7})", r"ADO[\s:#-]*(\d{3,7})", r"#(\d{3,7})",
                                             r"(?:fix|fixes|fixed|bug|issue|resolve|resolves|resolved)[\s:#-]+(\d{3,7})")]


def out(*lines):
    for ln in lines:
        print(ln)


def ctx(a):
    root = L.find_root(getattr(a, "root", None))
    return root, L.load_config(root)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def candidates(subject):
    ids = set()
    for rx in WI_PATTERNS:
        ids.update(int(m) for m in rx.findall(subject or ""))
    return sorted(ids)


def org_project(root, cfg, org=None, project=None):
    """The ADO org and project: given, else the most common among the repos' origins."""
    if org and project:
        return org, project
    seen = collections.Counter()
    for d in L.discover_repos(root, cfg).values():
        c = L.repo_coords(d)
        if c:
            seen[(c[0], c[1])] += 1
    if not seen:
        raise L.Refused("no Azure DevOps origin found in the workspace repos: pass --org and --project")
    (o, p), _ = seen.most_common(1)[0]
    return org or o, project or p


def item_view(org, w):
    f = w.get("fields", {})
    who = f.get("System.AssignedTo")
    name = who.get("displayName") if isinstance(who, dict) else (re.sub(r"\s*<[^>]+>", "", who) if who else "")
    proj = f.get("System.TeamProject", "")
    return {"id": int(w["id"]), "type": f.get("System.WorkItemType", ""), "title": f.get("System.Title", ""),
            "state": f.get("System.State", ""), "parent": f.get("System.Parent"),
            "tags": [t.strip() for t in (f.get("System.Tags") or "").split(";") if t.strip()],
            "assignee": name or "", "priority": f.get("Microsoft.VSTS.Common.Priority"), "project": proj,
            "area": f.get("System.AreaPath", ""), "url": L.web_item_url(org, proj, w["id"])}


def short(text, n=70):
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[:n - 1] + "…"


# ================================================================ status, versions, approve

def cmd_versions(a):
    root, cfg = ctx(a)
    vs = L.local_versions(root, cfg)
    if a.json:
        print(json.dumps(vs))
        return 0
    if not vs:
        out(f"No {cfg['branchPrefix']}* branches known locally. Fetch first, or check branchPrefix in .claude/devops.json.")
        return 0
    for v, rs in vs.items():
        out(f"{v}  ({len(rs)} repo{'s' if len(rs) != 1 else ''})")
    return 0


def cmd_approve(a):
    root, _ = ctx(a)
    L.approve(root, a.token, a.via)
    out(f"Plan {a.token} approved.")
    return 0


def item_line(kind, it):
    """One plain line per planned write, for the pane's approve panel."""
    if kind == "notes":
        return f"Publish {it['path']} to the {it['project']} wiki"
    if it.get("op") == "update":
        what = [x for x in ["new description" if it.get("description") else "", f"link {', '.join(map(str, it.get('linkWorkItems') or []))}" if it.get("linkWorkItems") else ""] if x]
        return f"Refresh PR {it['prId']} {it['repo']}: {', '.join(what)}"
    links = ", ".join(f"ADO {i}" for i in it.get("workItems") or []) or "no work items"
    return f"Open {'sync ' if kind == 'sync-prs' else ''}PR {it['repo']}: {it['source']} → {it['target']} · links {links}"


def plan_view(root, p):
    ok = L.approval(root, p["token"])
    return {"token": p["token"], "kind": p.get("kind"), "summary": p.get("summary", ""), "created": p.get("created", 0),
            "items": len(p.get("items", [])), "approved": bool(ok), "approvedAt": ok and ok.get("at"),
            "done": bool(p.get("done")), "ref": p.get("ref"),
            "lines": [item_line(p.get("kind"), it) for it in p.get("items", [])]}


def reviews_summary(root):
    """From the last `reviews list` (the pane reads ADO for it on a press): how many PRs wait on the user."""
    d = L.read_json(L.state_dir(root, "reviews", "list.json"))
    if not d:
        return None
    rows = d.get("rows", [])
    return {"generated": d.get("generated", 0), "waiting": sum(1 for r in rows if r.get("waiting")), "active": len(rows)}


def cmd_status(a):
    root, cfg = ctx(a)
    rel = []
    for f in sorted(L.state_dir(root, "release").glob("*.json")) if L.state_dir(root, "release").is_dir() else []:
        if f.name.endswith(".scan.json"):
            continue
        r = L.read_json(f) or {}
        r.pop("items", None)
        rel.append(r)
    rel.sort(key=lambda r: r.get("generated", 0), reverse=True)
    sd = L.state_dir(root, "sync")
    scans = []
    if sd.is_dir():
        for f in sorted(sd.glob("scan-*.json")):
            s = L.read_json(f) or {}
            scans.append({"file": f.name, "source": s.get("source"), "destination": s.get("destination"),
                          "generated": int(f.stat().st_mtime),
                          "repos": [{k: r.get(k) for k in ("Repo", "Status", "Ahead", "Behind", "Dirty", "ConflictCount", "Conflicts", "Detail")}
                                    for r in as_list(s.get("repos"))],
                          "prs": L.read_json(sd / f.name.replace("scan-", "prs-"), [])})
    scans.sort(key=lambda s: s["generated"], reverse=True)
    manifest = L.read_json(root / "temp" / "sync-repo-state.json")
    chain = L.read_json(sd / "chain.json")
    reports = []
    for d in (root / "documents" / "sync-reports", root / "temp"):
        if d.is_dir():
            reports += [str(p) for p in d.glob("sync-*-to-*.md")]
    notes_dir = root / cfg["notesDir"]
    files = sorted(notes_dir.glob("release-notes-*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if notes_dir.is_dir() else []
    runs = []
    nd = L.state_dir(root, "notes")
    if nd.is_dir():
        for d in sorted(nd.iterdir(), reverse=True):
            m = L.read_json(d / "meta.json")
            if m:
                m["approved"] = bool(m.get("token") and L.approval(root, m["token"]))
                runs.append(m)
    data = {
        "root": str(root), "generated": int(time.time()),
        "config": {"reposDir": cfg["reposDir"], "sourcePattern": cfg["sourcePattern"], "targetPattern": cfg["targetPattern"],
                   "branchPrefix": cfg["branchPrefix"], "guard": cfg["guard"]},
        "release": rel,
        "sync": {"chain": chain and {"versions": chain.get("versions"), "waves": chain.get("waves"),
                                     "repoLockedVersions": chain.get("repoLockedVersions")},
                 "scans": scans, "active": L.read_json(sd / "active.json", {}), "snapshot": manifest,
                 "techStories": L.read_json(sd / "techstory.json", {}), "reports": sorted(reports, reverse=True)[:10]},
        "notes": {"files": [{"path": str(p), "name": p.name, "at": int(p.stat().st_mtime)} for p in files[:10]], "runs": runs[:10]},
        "plans": sorted([plan_view(root, p) for p in L.plans(root)], key=lambda p: p["created"], reverse=True)[:20],
        "guard": {"recent": L.read_jsonl(L.state_dir(root, "guard.jsonl"))[-20:][::-1]},
        "reviews": reviews_summary(root),
        "pipelines": L.read_json(L.state_dir(root, "pipelines.json")),
        "deployments": L.read_json(L.state_dir(root, "deployments.json")),
        "doctor": L.read_json(L.state_dir(root, "doctor.json")),
    }
    if a.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0
    out(f"Workspace {root}")
    for r in rel[:3]:
        c = collections.Counter(x["status"] for x in r.get("repos", []))
        out(f"release {r['version']}: " + ", ".join(f"{n} {k}" for k, n in c.items()) + f" · plan {r.get('token') or 'none'}")
    for p in data["plans"][:5]:
        out(f"plan {p['token']} {p['kind']}: {p['summary']} · {'approved' if p['approved'] else 'waiting for approval'}")
    return 0


# ================================================================ release prep

def release_rows(scan):
    return [r for r in as_list(scan.get("Repos")) if isinstance(r, dict)]


def cmd_release_scan(a):
    root, cfg = ctx(a)
    v = a.version
    scan_path = L.state_dir(root, "release", f"{v}.scan.json")
    args = ["-Version", v, "-JsonPath", str(scan_path), "-Root", str(root), "-ReposDir", cfg["reposDir"],
            "-SourcePattern", cfg["sourcePattern"], "-TargetPattern", cfg["targetPattern"]]
    if a.repos:
        args += ["-Repos", a.repos]
    if a.no_fetch:
        args.append("-NoFetch")
    if scan_path.exists():
        scan_path.unlink()
    rc, so, se = L.run_ps(SCAN_RELEASE, args, root)
    scan = L.read_json(scan_path)
    if not scan:
        L.die(f"the scan wrote nothing (exit {rc}): {(se or so).strip()[-600:]}")
    rows = release_rows(scan)
    for r in rows:  # the scan's own commit list carries no ids yet
        for c in as_list(r.get("Commits")):
            c["Candidates"] = candidates(c.get("Subject"))
        r["Commits"] = as_list(r.get("Commits"))
        r["Conflicts"] = as_list(r.get("Conflicts"))
        r["MigrationFiles"] = as_list(r.get("MigrationFiles"))
        r["WorkItemCandidates"] = as_list(r.get("WorkItemCandidates"))
        if r.get("Status") == "Ready" and r.get("SourceBranch"):
            r["SourceSha"] = L.git(["rev-parse", f"refs/remotes/origin/{r['SourceBranch']}"], r["Path"], check=False)

    plan = {"version": v, "source": scan.get("Source"), "target": scan.get("Target"), "generated": int(time.time()),
            "root": str(root), "fetched": not a.no_fetch, "ado": False, "adoError": None, "pending": [], "existing": [],
            "workItems": {}, "dropped": [], "token": None, "items": [], "results": []}
    if not a.no_ado:
        try:
            enrich_release(plan, rows)
            plan["ado"] = True
        except (L.Refused, RuntimeError) as e:
            plan["adoError"] = str(e)
    plan["repos"] = [repo_view(r) for r in rows]
    items = release_items(plan, rows)
    if items:
        n_new = sum(1 for i in items if i["op"] == "create")
        n_upd = len(items) - n_new
        summary = " and ".join(x for x in [f"Open {n_new} release PR{'s' if n_new != 1 else ''}" if n_new else "",
                                            f"refresh {n_upd} open one{'s' if n_upd != 1 else ''}" if n_upd else ""] if x)
        plan["token"] = L.save_plan(root, "release-prs", items, summary, {"ref": f"release {v}"})
        plan["summary"] = summary
    plan["items"] = items
    L.write_json(L.state_dir(root, "release", f"{v}.json"), plan)
    print_release(root, plan)
    blocking = any(r["status"] in ("Conflicts", "FetchFailed", "MergeError") for r in plan["repos"])
    return 1 if blocking else 0


def repo_view(r):
    return {"repo": r.get("Repo"), "status": r.get("Status"), "source": r.get("SourceBranch"), "target": r.get("TargetBranch"),
            "ahead": r.get("Ahead", 0), "behind": r.get("Behind", 0), "files": r.get("FilesChanged", 0),
            "insertions": r.get("Insertions", 0), "deletions": r.get("Deletions", 0),
            "migrations": [{"path": m.get("Path"), "kind": m.get("Kind")} for m in r["MigrationFiles"]],
            "workItems": r.get("WorkItems", []), "candidates": r["WorkItemCandidates"],
            "loose": [{"sha": c.get("Short"), "subject": c.get("Subject")} for c in r["Commits"] if not c.get("WorkItems")],
            "conflicts": r["Conflicts"], "detail": r.get("Detail", ""), "branchesUrl": r.get("BranchesUrl"),
            "missingSource": bool(r.get("MissingSourceBranch")), "missingTarget": bool(r.get("MissingTargetBranch")),
            "project": r.get("AdoProject"), "org": r.get("AdoOrg"), "adoRepo": r.get("AdoRepo"), "pr": r.get("OpenPr"),
            "sourceSha": r.get("SourceSha")}


def enrich_release(plan, rows):
    """Phases 2-4 in one pass: PRs still headed into the source, release PRs already open, the work items."""
    by_proj = collections.defaultdict(list)
    for r in rows:
        if r.get("AdoOrg") and r.get("AdoProject"):
            by_proj[(r["AdoOrg"], r["AdoProject"])].append(r)
    if not by_proj:
        raise L.Refused("no repo has an Azure DevOps origin")
    found = {}
    for (org, proj), rs in by_proj.items():
        ado = L.Ado(org)
        name_of = {(r.get("AdoRepo") or r["Repo"]).lower(): r for r in rs}
        sources = {r["SourceBranch"] for r in rs if r.get("SourceBranch")} | {plan["source"]}
        targets = {r["TargetBranch"] for r in rs if r.get("TargetBranch")} | {plan["target"]}
        seen = set()
        for s in sorted(sources):
            for pr in ado.pull_requests(proj, target=s):
                if pr["pullRequestId"] in seen:
                    continue
                seen.add(pr["pullRequestId"])
                r = name_of.get(pr["repository"]["name"].lower())
                case = "ready" if r and r.get("Status") == "Ready" else ("uptodate" if r and r.get("Status") == "UpToDate" else "other")
                plan["pending"].append({"id": pr["pullRequestId"], "repo": pr["repository"]["name"], "project": proj,
                                        "title": pr.get("title", ""), "source": pr["sourceRefName"][11:], "case": case,
                                        "url": L.web_pr_url(org, proj, pr["repository"]["name"], pr["pullRequestId"])})
        for t in sorted(targets):
            for pr in ado.pull_requests(proj, target=t):
                r = name_of.get(pr["repository"]["name"].lower())
                if not r or (pr["sourceRefName"][11:]).lower() != (r.get("SourceBranch") or "").lower():
                    continue
                linked = ado.pr_work_items(proj, pr["repository"]["name"], pr["pullRequestId"])
                r["OpenPr"] = {"id": pr["pullRequestId"], "description": pr.get("description", ""), "linked": linked,
                               "url": L.web_pr_url(org, proj, pr["repository"]["name"], pr["pullRequestId"]),
                               "source": pr["sourceRefName"][11:], "target": pr["targetRefName"][11:]}
        ids = sorted({i for r in rs for i in r["WorkItemCandidates"]})
        if ids:
            for w in ado.work_items(ids, WI_FIELDS):
                found[int(w["id"])] = item_view(org, w)
    plan["workItems"] = {str(k): v for k, v in found.items()}
    for r in rows:
        r["WorkItems"] = [i for i in r["WorkItemCandidates"] if i in found]
        for c in r["Commits"]:
            c["WorkItems"] = [i for i in c["Candidates"] if i in found]
    plan["dropped"] = sorted({i for r in rows for i in r["WorkItemCandidates"]} - set(found))


def release_items(plan, rows):
    items = []
    wis = plan["workItems"]
    if not plan["ado"]:
        # no ADO read: the candidates stand unchecked (the MCP fallback checks them; the guard allows a subset)
        for r in rows:
            r["WorkItems"] = r["WorkItemCandidates"]
            for c in r["Commits"]:
                c["WorkItems"] = c["Candidates"]
            for i in r["WorkItems"]:
                subj = next((c.get("Subject", "") for c in r["Commits"] if i in c["Candidates"]), "")
                wis.setdefault(str(i), {"title": subj or "(title not read)", "type": "?", "state": "?",
                                        "url": L.web_item_url(r.get("AdoOrg") or "", r.get("AdoProject") or "", i)})
    for r in rows:
        if r.get("Status") != "Ready":
            continue
        body = P.release_body(r, wis, lambda i: wis[str(i)]["url"])
        base = {"project": r["AdoProject"], "org": r["AdoOrg"], "repo": r.get("AdoRepo") or r["Repo"], "local": r["Repo"], "path": r["Path"],
                "source": r["SourceBranch"], "target": r["TargetBranch"], "sourceSha": r.get("SourceSha")}
        pr = r.get("OpenPr")
        if not plan["ado"] and not (r.get("AdoOrg") and r.get("AdoProject")):
            continue
        if not pr:
            items.append(dict(base, op="create", title=P.release_title(r["SourceBranch"], r["TargetBranch"]),
                              description=body, workItems=r["WorkItems"]))
            continue
        missing = [i for i in r["WorkItems"] if i not in pr["linked"]]
        changed = L.digest(pr["description"]) != L.digest(body)
        if missing or changed:
            items.append(dict(base, op="update", prId=pr["id"], description=body if changed else None, linkWorkItems=missing))
    return items


def print_release(root, plan):
    rs = plan["repos"]
    by = collections.defaultdict(list)
    for r in rs:
        by[r["status"]].append(r)
    out(f"Release {plan['version']}: {plan['source']} -> {plan['target']} · {len(rs)} repos · "
        + ("fetched" if plan["fetched"] else "NOT fetched (--no-fetch): rescan before opening anything"))
    for r in by.get("Ready", []):
        wi = ", ".join(f"ADO {i}" for i in r["workItems"]) or "no work items"
        pr = f" · open PR {r['pr']['id']}" if r.get("pr") else ""
        out(f"  READY      {r['repo']}: {r['source']} -> {r['target']} · {r['ahead']} commits, {r['files']} files "
            f"(+{r['insertions']} -{r['deletions']}) · {wi}{pr}" + (f" · behind {r['behind']} (normal)" if r["behind"] else ""))
        for m in r["migrations"]:
            out(f"             MIGRATION {m['kind']}: {m['path']}")
        for c in r["loose"]:
            out(f"             no work item: {c['sha']} {short(c['subject'], 60)}")
    for r in by.get("Conflicts", []):
        out(f"  CONFLICTS  {r['repo']}: {len(r['conflicts'])} paths: {', '.join(r['conflicts'][:5])} -> stop; the user decides")
    up = by.get("UpToDate", [])
    if up:
        out("  UP TO DATE " + ", ".join(r["repo"] for r in up))
    for r in by.get("Skipped", []):
        if r["missingTarget"] and not r["missingSource"]:
            out(f"  MISSING RELEASE BRANCH {r['repo']}: the user creates {plan['target']} from {r['source'] or plan['source']} at {r['branchesUrl']}")
        else:
            out(f"  SKIPPED    {r['repo']}: {r['detail']}")
    for s in ("FetchFailed", "MergeError", "Unknown"):
        for r in by.get(s, []):
            out(f"  {s.upper()} {r['repo']}: {short(r['detail'], 160)}")
    if not plan["ado"]:
        out(f"ADO not read: {plan['adoError'] or 'skipped (--no-ado)'}. Pending PRs, open PRs and work items are NOT "
            "checked: follow the MCP fallback (references/mcp-fallback.md, release-prep).")
    if not plan["ado"]:
        pass
    elif plan["pending"]:
        out(f"PRs still headed into {plan['source']}:")
        for p in plan["pending"]:
            why = {"ready": "rides this release only if it merges before the release PR completes",
                   "uptodate": "repo was up to date: it needs a release PR this run did not raise once it merges",
                   "other": "repo not in this release"}[p["case"]]
            out(f"  PR {p['id']} {p['repo']} \"{short(p['title'], 60)}\": {why}")
    else:
        out(f"No PRs headed into {plan['source']}.")
    if plan["dropped"]:
        out("Not work items (dropped): " + ", ".join(str(i) for i in plan["dropped"]))
    for i, w in plan["workItems"].items():
        out(f"  ADO {i} {w['type']} [{w['state']}] {short(w['title'], 70)}")
    if plan["token"]:
        for it in plan["items"]:
            if it["op"] == "create":
                out(f"  WILL OPEN  {it['repo']}: {it['source']} -> {it['target']} linking {', '.join(map(str, it['workItems'])) or 'nothing'}")
            else:
                what = [x for x in ["description" if it["description"] else "", f"link {it['linkWorkItems']}" if it["linkWorkItems"] else ""] if x]
                out(f"  WILL REFRESH PR {it['prId']} {it['repo']}: {', '.join(what)}")
        out(f"Plan {plan['token']}. Show this to the user, then ask with AskUserQuestion: "
            f"\"{L.approval_question(root, plan['token'])}\" options \"Yes, go ahead\" / \"No\". "
            f"After a Yes: devops.py release open --version {plan['version']}")
    else:
        out("Nothing to open or refresh.")


def cmd_release_show(a):
    root, _ = ctx(a)
    plan = L.read_json(L.state_dir(root, "release", f"{a.version}.json")) or L.die(f"no scan of {a.version}: run release scan")
    if a.items:
        print(json.dumps(plan.get("items", []), indent=2, ensure_ascii=False))
        return 0
    print_release(root, plan)
    return 0


def cmd_release_open(a):
    root, _ = ctx(a)
    path = L.state_dir(root, "release", f"{a.version}.json")
    plan = L.read_json(path) or L.die(f"no scan of {a.version}: run release scan")
    if not plan.get("token"):
        L.die("the scan planned nothing to open")
    if L.plan_token("release-prs", plan["items"]) != plan["token"]:
        raise L.Refused(f"{path.name} changed after the plan was made: scan again and ask again")
    L.require_approval(root, plan["token"])
    if not plan.get("fetched"):
        raise L.Refused("the scan ran with --no-fetch: scan again (fetching) and approve again")
    repos = {r["repo"]: r for r in plan["repos"]}
    results, bad = [], 0
    for it in plan["items"]:
        local = Path(it["path"])
        now = L.git(["ls-remote", "origin", f"refs/heads/{it['source']}"], local, check=False).split()
        if it.get("sourceSha") and (not now or now[0] != it["sourceSha"]):
            results.append({"repo": it["repo"], "error": f"{it['source']} moved since the scan: scan again and approve again"})
            bad += 1
            continue
        try:
            results.append(open_release_item(it, plan))
        except (RuntimeError, L.Refused) as e:
            results.append({"repo": it["repo"], "error": str(e)})
            bad += 1
    plan["results"] = results
    L.write_json(path, plan)
    p = L.load_plan(root, plan["token"])
    if p:
        p["done"] = int(time.time())
        L.write_json(L.state_dir(root, "plans", f"{plan['token']}.json"), p)
    for r in results:
        if r.get("error"):
            out(f"  FAILED {r['repo']}: {r['error']}")
        else:
            miss = f" · could not link {r['missing']}" if r["missing"] else ""
            out(f"  {r['action'].upper()} PR {r['prId']} {r['repo']}: {r['url']}{miss}")
    mig = [m["path"] for r in repos.values() if r["status"] == "Ready" for m in r["migrations"]]
    ok = [r for r in results if not r.get("error")]
    if ok:
        out("Hand-off to release-notes: PRs " + ", ".join(f"{r['prId']} ({r['project']})" for r in ok)
            + f"; work items {', '.join(sorted({str(i) for r in ok for i in r['linked']}))}; "
            + (f"migration files found: {', '.join(mig)}" if mig else "no migration files found"))
    return 1 if bad else 0


def open_release_item(it, plan):
    ado = L.Ado(it["org"])
    proj, repo = it["project"], it["repo"]
    if it["op"] == "create":
        dup = [x for x in ado.pull_requests(proj, target=it["target"], repo=repo)
               if x["sourceRefName"][11:] == it["source"]]
        if dup:
            pr_id, action = dup[0]["pullRequestId"], "found"
        else:
            problems = L.lint_outbound(it["description"], "pr")
            if problems:
                raise L.Refused("; ".join(problems))
            pr = ado.create_pr(proj, repo, it["source"], it["target"], it["title"], it["description"], it["workItems"])
            pr_id, action = pr["pullRequestId"], "opened"
        want = it["workItems"]
    else:
        pr_id, action = it["prId"], "refreshed"
        if it.get("description"):
            problems = L.lint_outbound(it["description"], "pr")
            if problems:
                raise L.Refused("; ".join(problems))
            ado.update_pr(proj, repo, pr_id, {"description": it["description"]})
        want = next((r["workItems"] for r in plan["repos"] if r["repo"] == it["local"]), [])
    linked = ado.pr_work_items(proj, repo, pr_id)
    missing = [i for i in want if i not in linked]
    if missing:
        meta = ado.repository(proj, repo)
        for i in missing:
            ado.patch_item(i, L.link_pr_ops(meta["project"]["id"], meta["id"], pr_id))
        linked = ado.pr_work_items(proj, repo, pr_id)
    return {"repo": repo, "project": proj, "prId": pr_id, "action": action, "url": L.web_pr_url(it["org"], proj, repo, pr_id),
            "linked": linked, "missing": [i for i in want if i not in linked]}


# ================================================================ sync team branches

def norm_branch(name, prefix):
    if name.startswith("refs/heads/"):
        return name[11:]
    return name if "/" in name else f"{prefix}{name}"


def bare(name, prefix):
    b = norm_branch(name, prefix)
    return b[len(prefix):] if prefix and b.lower().startswith(prefix.lower()) else b.replace("/", "-")


def scan_file(root, cfg, s, d):
    key = f"{norm_branch(s, cfg['branchPrefix'])}-to-{norm_branch(d, cfg['branchPrefix'])}".replace("/", "_")
    return L.state_dir(root, "sync", f"scan-{key}.json"), L.state_dir(root, "sync", f"prs-{key}.json")


def ps_common(a, root, cfg):
    args = ["-Root", str(root), "-ReposDir", cfg["reposDir"], "-BranchPrefix", cfg["branchPrefix"]]
    if getattr(a, "repos", None):
        args += ["-Repos", a.repos]
    if getattr(a, "skip_lock_check", False):
        args.append("-SkipLockCheck")
    return args


def cmd_sync_chain(a):
    root, cfg = ctx(a)
    path = L.state_dir(root, "sync", "chain.json")
    args = ps_common(a, root, cfg) + ["-JsonPath", str(path)]
    if a.from_version:
        args += ["-FromVersion", a.from_version]
    if a.to_version:
        args += ["-ToVersion", a.to_version]
    if path.exists():
        path.unlink()
    rc, so, se = L.run_ps(SYNC_DIR / "Get-TeamVersionChain.ps1", args, root)
    c = L.read_json(path) or L.die(f"the chain discovery wrote nothing (exit {rc}): {(se or so).strip()[-600:]}")
    vs = as_list(c.get("versions"))
    out(f"Versions, lowest first: {' -> '.join(vs) or 'none'}")
    waves = as_list(c.get("waves"))
    if not waves:
        out("No repo has two versions in scope: nothing to chain-sync.")
    for w in waves:
        out(f"Wave -> {w['Destination']}")
        for g in as_list(w.get("Groups")):
            prior = f"after {g['PriorSource']} -> {g['PriorDestination']} landed" if g.get("PriorSource") else "first hop"
            flags = f" --prior-source {g['PriorSource']} --prior-destination {g['PriorDestination']}" if g.get("PriorSource") else ""
            out(f"  {g['Source']} -> {w['Destination']}  [{', '.join(as_list(g['Repos']))}]  {prior}")
            out(f"    scan: devops.py sync scan --source {g['Source']} --destination {w['Destination']} --repos {','.join(as_list(g['Repos']))}{flags}")
    locked = c.get("repoLockedVersions") or {}
    if locked:
        out("Locked (left out): " + "; ".join(f"{r}: {', '.join(as_list(v))}" for r, v in locked.items()))
    out("Show the wave plan and ask the user to confirm it before the first scan.")
    return 0


def cmd_sync_scan(a):
    root, cfg = ctx(a)
    path, _ = scan_file(root, cfg, a.source, a.destination)
    args = ["-Source", a.source, "-Destination", a.destination, "-JsonPath", str(path)] + ps_common(a, root, cfg)
    if bool(a.prior_source) != bool(a.prior_destination):
        L.die("--prior-source and --prior-destination go together")
    if a.prior_source:
        args += ["-PriorSource", a.prior_source, "-PriorDestination", a.prior_destination]
    if path.exists():
        path.unlink()
    rc, so, se = L.run_ps(SYNC_DIR / "Scan-TeamBranchSync.ps1", args, root)
    s = L.read_json(path) or L.die(f"the scan wrote nothing (exit {rc}): {(se or so).strip()[-600:]}")
    rows = as_list(s.get("repos"))
    out(f"Sync {s['source']} -> {s['destination']} · {len(rows)} repos")
    word = {"Clean": "PR direct", "FastForward": "PR direct", "Conflicts": "local merge, the user resolves",
            "UpToDate": "nothing to do", "Skipped": "not applicable", "PendingPriorHop": "waits: its prior hop has not landed",
            "Locked": "locked in ADO: left out", "FetchFailed": "investigate", "MergeError": "investigate"}
    for r in rows:
        extra = f" · {r.get('Ahead')} commits" if r["Status"] in ("Clean", "FastForward", "Conflicts") else ""
        dirty = " · has uncommitted work" if r.get("Dirty") and r["Status"] == "Conflicts" else ""
        out(f"  {r['Status']:<15} {r['Repo']}{extra}{dirty}: {word.get(r['Status'], '')} · {short(r.get('Detail'), 90)}")
        for c in as_list(r.get("Conflicts")):
            out(f"      conflict: {c}")
    act = [r for r in rows if r["Status"] in ("Clean", "FastForward", "Conflicts")]
    conf = [r["Repo"] for r in rows if r["Status"] == "Conflicts"]
    if act:
        out("Next: settle the team-sync work item per ADO project (ask the user: auto-create, or one they have), then "
            f"devops.py sync techstory. Conflicted repos: snapshot ({', '.join(conf)}) then sync start." if conf else
            "Next: settle the team-sync work item per ADO project (ask the user: auto-create, or one they have), "
            f"then devops.py sync plan --source {a.source} --destination {a.destination}.")
    return 0


def active_path(root):
    return L.state_dir(root, "sync", "active.json")


def repo_dir(root, cfg, name):
    repos = L.discover_repos(root, cfg)
    hit = next((d for n, d in repos.items() if n.lower() == name.lower()), None)
    if not hit:
        raise L.Refused(f"no repo {name} under {root / cfg['reposDir']}")
    return hit


def cmd_sync_start(a):
    root, cfg = ctx(a)
    d = repo_dir(root, cfg, a.repo)
    pre = cfg["branchPrefix"]
    src, dst = norm_branch(a.source, pre), norm_branch(a.destination, pre)
    if L.merge_in_progress(d):
        raise L.Refused(f"{a.repo} already has a merge in progress: the user finishes or aborts it first")
    manifest = L.read_json(root / "temp" / "sync-repo-state.json") or {}
    snap = any(e.get("Repo", "").lower() == a.repo.lower() for e in as_list(manifest.get("entries")))
    dirty = L.dirty_files(d)
    if dirty:
        raise L.Refused(f"{a.repo} has {len(dirty)} uncommitted entries. Snapshot it first: pwsh -File "
                        f"{SYNC_DIR / 'Invoke-RepoStateSnapshot.ps1'} -Action Save -Repos {a.repo}")
    if not snap:
        out(f"note: {a.repo} has no snapshot entry; its branch is not recorded for the restore. "
            "Run the snapshot Save first if the user wants to return to their branch.")
    L.git(["fetch", "--prune", "--quiet", "origin"], d)
    heads = L.remote_heads(d)
    src_x, dst_x = L.exact_branch(heads, src), L.exact_branch(heads, dst)
    if not (src_x and dst_x):
        raise L.Refused(f"origin lacks {src if not src_x else dst}")
    branch = f"sync/{a.user}/{bare(src, pre)}_to_{bare(dst, pre)}"
    exists = L.git(["branch", "--list", branch], d, check=False)
    if exists and not a.recreate:
        raise L.Refused(f"{branch} already exists in {a.repo}. Ask the user: reuse it (switch to it yourself) or "
                        "recreate it (run again with --recreate).")
    if exists:
        L.git(["branch", "-D", branch], d)
    L.git(["switch", "-c", branch, "--no-track", f"origin/{dst_x}"], d)
    rc, so, se = L.git_rc(["merge", "--no-ff", "--no-edit", f"origin/{src_x}"], d)
    conflicts = [x for x in L.git(["diff", "--name-only", "--diff-filter=U"], d, check=False).splitlines() if x]
    state = "conflict" if conflicts else ("ready" if rc == 0 else "error")
    act = L.read_json(active_path(root), {})
    act[a.repo] = {"repo": a.repo, "path": str(d), "branch": branch, "source": src_x, "destination": dst_x,
                   "state": state, "conflicts": conflicts, "startedAt": int(time.time()), "user": a.user}
    L.write_json(active_path(root), act)
    if state == "error":
        raise L.Refused(f"git merge failed without conflicts: {(se or so).strip()[:300]}")
    if conflicts:
        out(f"{a.repo}: on {branch} (from origin/{dst_x}, no upstream). Merging origin/{src_x} stopped on {len(conflicts)} conflicts:")
        for c in conflicts:
            ours = L.git(["log", "-1", "--format=%h %s", f"origin/{dst_x}", "--", c], d, check=False)
            theirs = L.git(["log", "-1", "--format=%h %s", f"origin/{src_x}", "--", c], d, check=False)
            out(f"  {c}\n     {dst_x}: {short(ours, 80) or '-'}\n     {src_x}: {short(theirs, 80) or '-'}")
        out("Hand these to the user. They resolve every hunk; you do not edit these files (the guard refuses). "
            f"When they say done: devops.py sync verify --repo {a.repo}")
        return 1
    out(f"{a.repo}: merged cleanly on {branch}. Next: devops.py sync finish --repo {a.repo}")
    return 0


MARKER = re.compile(rb"^(<{7}|={7}|>{7}|\|{7})( |\r?$)", re.M)
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist"}


def verify_repo(d):
    """The four checks after a hand resolution: unmerged entries, whitespace errors, markers, status."""
    res = []
    unmerged = L.git(["ls-files", "-u"], d, check=False)
    res.append(("no unmerged entries (git ls-files -u)", not unmerged, unmerged[:400]))
    # cr-at-eol: in a CRLF repo the CR ends the line, it is not trailing whitespace
    rc, so, se = L.git_rc(["-c", "core.whitespace=cr-at-eol", "diff", "--check"], d)
    rc2, so2, _ = L.git_rc(["-c", "core.whitespace=cr-at-eol", "diff", "--cached", "--check"], d)
    res.append(("no whitespace errors or markers (git diff --check)", rc == 0 and rc2 == 0, (so + so2)[:400]))
    hits = []
    files = L.git(["ls-files", "-co", "--exclude-standard"], d, check=False).splitlines()
    for f in files:
        if any(part in SKIP_DIRS for part in Path(f).parts):
            continue
        p = Path(d) / f
        try:
            if p.stat().st_size > 5_000_000:
                continue
            blob = p.read_bytes()
        except OSError:
            continue
        if b"\0" in blob[:8000]:
            continue
        for m in MARKER.finditer(blob):
            line = blob.count(b"\n", 0, m.start()) + 1
            hits.append(f"{f}:{line}")
    res.append(("no conflict markers in any file (CRLF-safe scan)", not hits, ", ".join(hits[:10])))
    status = L.git(["status", "--short"], d, check=False)
    res.append(("status read", True, status[:400]))
    return res


def cmd_sync_verify(a):
    root, cfg = ctx(a)
    d = repo_dir(root, cfg, a.repo)
    res = verify_repo(d)
    ok = all(r[1] for r in res)
    for name, passed, detail in res:
        out(f"  {'PASS' if passed else 'FAIL'} {name}" + (f": {detail}" if detail and (not passed or name == 'status read') else ""))
    out(f"{a.repo}: resolution complete. Next: devops.py sync finish --repo {a.repo}" if ok else
        f"{a.repo}: NOT resolved. Tell the user what failed and hand back; do not fix it yourself.")
    return 0 if ok else 1


def cmd_sync_finish(a):
    root, cfg = ctx(a)
    d = repo_dir(root, cfg, a.repo)
    act = L.read_json(active_path(root), {})
    e = act.get(a.repo) or next((v for k, v in act.items() if k.lower() == a.repo.lower()), None)
    if not e:
        raise L.Refused(f"no sync in progress for {a.repo}: start one with devops.py sync start")
    cur = L.git(["rev-parse", "--abbrev-ref", "HEAD"], d)
    if cur != e["branch"]:
        raise L.Refused(f"{a.repo} is on {cur}, not {e['branch']}")
    res = verify_repo(d)
    if not all(r[1] for r in res):
        raise L.Refused("the resolution is not complete: " + "; ".join(f"{n}: {x}" for n, ok, x in res if not ok))
    if L.merge_in_progress(d):
        L.git(["commit", "--no-edit"], d)
    if L.dirty_files(d):
        raise L.Refused(f"{a.repo} has uncommitted changes after the merge commit: the user decides what they are")
    if L.git_rc(["merge-base", "--is-ancestor", f"origin/{e['source']}", "HEAD"], d)[0] != 0:
        raise L.Refused(f"origin/{e['source']} is not in {e['branch']}: the merge did not land")
    if not e["branch"].startswith("sync/"):
        raise L.Refused("only a sync/* branch is pushed by this command")
    L.git(["push", "-u", "origin", e["branch"]], d)
    e.update(state="pushed", pushedAt=int(time.time()), note=a.note or e.get("note"))
    act[e["repo"]] = e
    L.write_json(active_path(root), act)
    out(f"{a.repo}: {e['branch']} pushed. Next: devops.py sync plan --source {e['source']} --destination {e['destination']}")
    return 0


def techstory_cache(root):
    return L.state_dir(root, "sync", "techstory.json")


def cmd_sync_techstory(a):
    root, cfg = ctx(a)
    org, _ = org_project(root, cfg, a.org, a.project)
    ado = L.Ado(org)
    cache = L.read_json(techstory_cache(root), {})
    if a.no_check and not a.id:
        L.die("--no-check goes with --id")
    today = datetime.now().strftime("%Y-%m-%d")
    if a.id and a.no_check:  # the MCP fallback: the agent read the item and its project with the MCP tools
        cache[a.project] = {"id": int(a.id), "day": today, "title": a.title or f"ADO {a.id}",
                            "url": L.web_item_url(org, a.project, a.id), "created": False}
    elif a.id:
        w = ado.work_items([a.id], ["System.TeamProject", "System.Title", "System.WorkItemType"])
        if not w:
            raise L.Refused(f"work item {a.id} does not exist: ask the user for a valid one")
        proj = w[0]["fields"].get("System.TeamProject", "")
        if proj.lower() != a.project.lower():
            raise L.Refused(f"work item {a.id} is in {proj}, not {a.project}: ask the user for one in {a.project}")
        cache[a.project] = {"id": int(a.id), "day": today, "title": w[0]["fields"].get("System.Title"),
                            "url": L.web_item_url(org, proj, a.id), "created": False}
    else:
        c = cache.get(a.project)
        if c and c.get("day") == today:
            out(f"{a.project}: reusing ADO {c['id']} ({c['title']})")
            return 0
        feat = ado.wiql(a.project, f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project AND "
                                   f"[System.WorkItemType] = 'Feature' AND [System.Title] CONTAINS 'Branch Synchronization'")
        if feat:
            fid = feat[0]
        else:
            fid = ado.create_item(a.project, "Feature", [{"op": "add", "path": "/fields/System.Title", "value": cfg["syncFeatureTitle"]}])["id"]
        title = f"sync team branches ({datetime.now().strftime('%Y/%m/%d')})"
        ops = [{"op": "add", "path": "/fields/System.Title", "value": title},
               {"op": "add", "path": "/relations/-", "value": {"rel": "System.LinkTypes.Hierarchy-Reverse",
                                                             "url": f"{ado.base}/_apis/wit/workItems/{fid}"}}]
        wid = ado.create_item(a.project, cfg["syncWorkItemType"], ops)["id"]
        cache[a.project] = {"id": int(wid), "day": today, "title": title, "url": L.web_item_url(org, a.project, wid),
                            "created": True, "feature": fid}
    L.write_json(techstory_cache(root), cache)
    c = cache[a.project]
    out(f"{a.project}: team-sync work item ADO {c['id']} ({c['title']}) {c['url']}")
    return 0


def cmd_sync_plan(a):
    root, cfg = ctx(a)
    spath, _ = scan_file(root, cfg, a.source, a.destination)
    scan = L.read_json(spath) or L.die("no scan for that hop: run sync scan first")
    act = L.read_json(active_path(root), {})
    cache = L.read_json(techstory_cache(root), {})
    items, waiting, need_story = [], [], set()
    for r in as_list(scan.get("repos")):
        if r["Status"] not in ("Clean", "FastForward", "Conflicts"):
            continue
        d = Path(r["Path"])
        coords = L.repo_coords(d)
        if not coords:
            waiting.append(f"{r['Repo']}: origin is not Azure DevOps")
            continue
        org, proj, adorepo = coords
        story = cache.get(proj)
        if not story:
            need_story.add(proj)
            continue
        heads = L.remote_heads(d)
        src = L.exact_branch(heads, scan["source"])
        dst = L.exact_branch(heads, scan["destination"])
        if not (src and dst):
            waiting.append(f"{r['Repo']}: origin lacks {scan['source'] if not src else scan['destination']}")
            continue
        head_from, note, conflicted = src, None, False
        if r["Status"] == "Conflicts":
            e = act.get(r["Repo"])
            if not e or e.get("state") != "pushed":
                waiting.append(f"{r['Repo']}: conflicts not resolved and pushed yet (sync start / verify / finish)")
                continue
            head_from, note, conflicted = e["branch"], e.get("note"), True
        log = L.git(["log", "--no-merges", "--format=%h%x1f%s", f"origin/{dst}..origin/{src}"], d, check=False)
        commits = [tuple(x.split("\x1f", 1)) for x in log.splitlines() if "\x1f" in x]
        body = P.sync_body(src, dst, commits, conflicted, head_from if conflicted else None, note)
        problems = L.lint_outbound(body, "sync-pr")
        if problems:
            waiting.append(f"{r['Repo']}: " + "; ".join(problems))
            continue
        items.append({"op": "create", "org": org, "project": proj, "repo": adorepo, "local": r["Repo"], "source": head_from,
                      "target": dst, "title": P.sync_title(src, dst), "description": body, "workItems": [story["id"]],
                      "syncBranch": head_from if conflicted else None, "note": note,
                      "techStoryId": story["id"], "techStoryUrl": story["url"]})
    for w in waiting:
        out(f"  WAITING {w}")
    if need_story:
        out("No team-sync work item yet for: " + ", ".join(sorted(need_story)) + ". Ask the user: auto-create, or one they "
            "have? Then devops.py sync techstory --project <P> --create | --id <N>, and plan again.")
    if not items:
        out("Nothing to raise yet.")
        return 1 if (need_story or waiting) else 0
    summary = f"Open {len(items)} sync PR{'s' if len(items) != 1 else ''} {scan['source']} -> {scan['destination']}"
    token = L.save_plan(root, "sync-prs", items, summary, {"ref": f"sync {scan['source']} -> {scan['destination']}"})
    for it in items:
        out(f"  WILL OPEN {it['repo']}: {it['source']} -> {it['target']} · links only ADO {it['techStoryId']}")
    out(f"Plan {token}. Show this to the user, then ask with AskUserQuestion: \"{L.approval_question(root, token)}\" "
        f"options \"Yes, go ahead\" / \"No\". After a Yes: devops.py sync open --source {a.source} --destination {a.destination}")
    return 0


def cmd_sync_open(a):
    root, cfg = ctx(a)
    spath, ppath = scan_file(root, cfg, a.source, a.destination)
    scan = L.read_json(spath) or L.die("no scan for that hop")
    plan = latest_sync_plan(root, scan) or L.die("no sync plan for that hop: run sync plan")
    if L.plan_token("sync-prs", plan["items"]) != plan["token"]:
        raise L.Refused("the plan file changed after it was made: plan again and ask again")
    L.require_approval(root, plan["token"])
    results = L.read_json(ppath, [])
    done = {r["repo"] for r in results if r.get("prId")}
    bad = 0
    for it in plan["items"]:
        if it["local"] in done:
            continue
        try:
            ado = L.Ado(it["org"])
            dup = [x for x in ado.pull_requests(it["project"], target=it["target"], repo=it["repo"])
                   if x["sourceRefName"][11:] == it["source"]]
            pr_id = dup[0]["pullRequestId"] if dup else ado.create_pr(
                it["project"], it["repo"], it["source"], it["target"], it["title"], it["description"], it["workItems"])["pullRequestId"]
            meta = ado.repository(it["project"], it["repo"])
            linked = ado.pr_work_items(it["project"], it["repo"], pr_id)
            removed = []
            for wid in linked:
                if wid == it["techStoryId"]:
                    continue
                w = ado.work_items([wid], relations=True)
                ops = L.unlink_pr_ops(w[0], meta["project"]["id"], meta["id"], pr_id) if w else []
                if ops:
                    ado.patch_item(wid, ops)
                    removed.append(wid)
            if it["techStoryId"] not in linked:
                ado.patch_item(it["techStoryId"], L.link_pr_ops(meta["project"]["id"], meta["id"], pr_id))
            url = L.web_pr_url(it["org"], it["project"], it["repo"], pr_id)
            results.append({"repo": it["local"], "prId": pr_id, "prUrl": url, "syncBranch": it.get("syncBranch"),
                            "note": it.get("note") or "", "techStoryId": it["techStoryId"], "techStoryUrl": it["techStoryUrl"]})
            out(f"  PR {pr_id} {it['repo']}: {url}" + (f" · unlinked {removed}" if removed else ""))
        except (RuntimeError, L.Refused) as e:
            bad += 1
            out(f"  FAILED {it['repo']}: {e}")
    L.write_json(ppath, results)
    plan["done"] = int(time.time())
    L.write_json(L.state_dir(root, "plans", f"{plan['token']}.json"), plan)
    out(f"Next, once every PR of the hop is raised: restore the snapshot, then devops.py sync report --source {a.source} --destination {a.destination}")
    return 1 if bad else 0


def latest_sync_plan(root, scan):
    mine = [p for p in L.plans(root) if p.get("kind") == "sync-prs" and p.get("ref") == f"sync {scan['source']} -> {scan['destination']}"]
    return max(mine, key=lambda p: p["created"]) if mine else None


def cmd_sync_show(a):
    root, cfg = ctx(a)
    spath, _ = scan_file(root, cfg, a.source, a.destination)
    scan = L.read_json(spath) or L.die("no scan for that hop")
    plan = latest_sync_plan(root, scan) or L.die("no sync plan for that hop: run sync plan")
    print(json.dumps({"token": plan["token"], "approved": bool(L.approval(root, plan["token"])), "items": plan["items"]},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_sync_record(a):
    """The MCP fallback: note a sync PR made with the MCP tools, so the report and the guard know it."""
    root, cfg = ctx(a)
    spath, ppath = scan_file(root, cfg, a.source, a.destination)
    scan = L.read_json(spath) or L.die("no scan for that hop")
    plan = latest_sync_plan(root, scan) or L.die("no sync plan for that hop")
    it = next((i for i in plan["items"] if i["local"].lower() == a.repo.lower() or i["repo"].lower() == a.repo.lower()), None)
    if not it:
        L.die(f"{a.repo} is not in the sync plan")
    results = [r for r in L.read_json(ppath, []) if r["repo"] != it["local"]]
    results.append({"repo": it["local"], "prId": a.pr, "prUrl": a.url or L.web_pr_url(it["org"], it["project"], it["repo"], a.pr),
                    "syncBranch": it.get("syncBranch"), "note": it.get("note") or "", "techStoryId": it["techStoryId"],
                    "techStoryUrl": it["techStoryUrl"]})
    L.write_json(ppath, results)
    out(f"Recorded PR {a.pr} for {it['local']}.")
    return 0


def cmd_sync_restore(a):
    """The snapshot's Restore (or Status), for the pane: back to each recorded branch, stash re-applied by SHA."""
    root, cfg = ctx(a)
    args = ["-Action", "Status" if a.status else "Restore", "-Root", str(root), "-ReposDir", cfg["reposDir"]]
    rc, so, se = L.run_ps(SYNC_DIR / "Invoke-RepoStateSnapshot.ps1", args, root)
    text = (so + se).strip()
    out("\n".join(ln for ln in text.splitlines() if ln.strip())[-1500:])
    return 0 if rc == 0 and "not restored" not in text else 1


def cmd_sync_report(a):
    root, cfg = ctx(a)
    spath, ppath = scan_file(root, cfg, a.source, a.destination)
    if not spath.exists():
        L.die("no scan for that hop")
    if not ppath.exists():
        L.write_json(ppath, [])
    rc, so, se = L.run_ps(SYNC_DIR / "New-SyncReport.ps1", ["-ScanJson", str(spath), "-PrResultsJson", str(ppath)], root)
    if rc != 0:
        L.die(f"the report failed: {(se or so).strip()[-600:]}")
    m = re.search(r"Sync report written to:\s*\n\s*(.+)", so)
    out(f"Report: {m.group(1).strip() if m else so.strip()[-300:]}")
    if "WARNING" in so:
        out(next(ln for ln in so.splitlines() if "WARNING" in ln).strip())
    out("Give the user the path. Do not post it anywhere: sharing is theirs to do.")
    return 0


# ================================================================ release notes

def run_dir(root, run):
    d = L.state_dir(root, "notes", run)
    if not d.is_dir():
        raise L.Refused(f"no notes run {run} in {L.state_dir(root, 'notes')}")
    return d


def pr_view(org, proj, pr):
    repo = pr["repository"]["name"]
    return {"id": pr["pullRequestId"], "repo": repo, "project": pr["repository"].get("project", {}).get("name", proj),
            "title": pr.get("title", ""), "source": pr["sourceRefName"][11:], "target": pr["targetRefName"][11:],
            "created": pr.get("creationDate", ""), "status": pr.get("status", ""), "url": L.web_pr_url(org, proj, repo, pr["pullRequestId"])}


def cmd_notes_collect(a):
    root, cfg = ctx(a)
    org, proj = org_project(root, cfg, a.org, a.project)
    ado = L.Ado(org)
    if a.pr:
        prs = [pr_view(org, proj, ado.pull_request(proj, i)) for i in a.pr]
        how = "the PRs you named"
    elif a.commit:
        if not a.repo:
            L.die("--commit needs --repo")
        hits = ado.prs_by_commit(proj, a.repo, a.commit)
        if not hits:
            raise L.Refused(f"no PR in ADO holds commit {a.commit} in {a.repo}")
        prs = [pr_view(org, proj, ado.pull_request(proj, h["pullRequestId"])) for h in hits]
        how = f"the PR of commit {a.commit[:10]}"
    else:
        listed = [pr_view(org, proj, x) for x in ado.pull_requests(proj, status="active", top=a.top)]
        rel = N.release_prs(listed)
        prs = N.newest_cluster(rel, cfg["clusterGapHours"])
        how = f"{len(rel)} active PRs into release/*, newest group of {len(prs)}"
    if not prs:
        raise L.Refused("no active PR into release/* in ADO. Check the project, the branch names, or the PR status.")
    run = save_run(root, cfg, ado, org, proj, prs, how)
    out(f"Next: devops.py notes detect --run {run} (if opted in), then notes render --run {run} ...")
    return 0


def new_run_id(root):
    run = datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while L.state_dir(root, "notes", run if n == 1 else f"{run}-{n}").exists():  # two projects in one second
        n += 1
    return run if n == 1 else f"{run}-{n}"


def save_run(root, cfg, ado, org, proj, prs, how, release=None):
    """Reads the PRs' work items up to Epic, and what each environment runs now, into a new notes run."""
    pw, ids = {}, set()
    for p in prs:
        pw[str(p["id"])] = ado.pr_work_items(p["project"], p["repo"], p["id"])
        ids.update(pw[str(p["id"])])
    items = {}
    todo = set(ids)
    for _ in range(8):  # up through Feature and Epic
        if not todo:
            break
        got = [item_view(org, w) for w in ado.work_items(sorted(todo), WI_FIELDS)]
        for g in got:
            items[str(g["id"])] = g
        todo = {int(g["parent"]) for g in got if g.get("parent") and str(g["parent"]) not in items}
    deployed, _ = read_deployments(cfg, org, proj, ado)  # so the notes name the last deploy; best effort
    run = new_run_id(root)
    data = {"org": org, "project": proj, "generated": int(time.time()), "how": how, "prs": prs, "workItems": items,
            "prWorkItems": pw, "migrations": {}, "skills": {}, "gaps": [], "deployed": deployed}
    L.write_json(L.state_dir(root, "notes", run, "data.json"), data)
    meta = {"run": run, "stage": "collected", "project": proj, "prs": [p["id"] for p in prs], "generated": int(time.time())}
    if release:
        meta["release"] = release
    L.write_json(L.state_dir(root, "notes", run, "meta.json"), meta)
    out(f"Run {run}: {how}.")
    for p in prs:
        out(f"  PR {p['id']} {p['repo']}: {p['source']} -> {p['target']} \"{short(p['title'], 60)}\" · {len(pw[str(p['id'])])} work items")
    out(f"{len(items)} work items with parents.")
    return run


def cmd_notes_ingest(a):
    root, _ = ctx(a)
    data = L.read_json(a.file)
    need = ("org", "project", "prs", "workItems", "prWorkItems")
    if not isinstance(data, dict) or any(k not in data for k in need):
        L.die(f"{a.file} needs the keys {', '.join(need)} (see the release-notes skill, MCP fallback)")
    data.setdefault("migrations", {})
    data.setdefault("skills", {})
    data.setdefault("gaps", [])
    run = datetime.now().strftime("%Y%m%d-%H%M%S")
    L.write_json(L.state_dir(root, "notes", run, "data.json"), data)
    L.write_json(L.state_dir(root, "notes", run, "meta.json"), {"run": run, "stage": "collected", "project": data["project"],
                                                                "prs": [p["id"] for p in data["prs"]], "generated": int(time.time())})
    out(f"Run {run}: {len(data['prs'])} PRs, {len(data['workItems'])} work items.")
    return 0


def migration_kind(path):
    if path.lower().endswith(".sql"):
        return "SQL Script"
    if re.search(r"(^|/)Migrations/.*\.cs$", path, re.I) or re.search(r"(^|/)\d{14}_.*\.cs$", path):
        return "EF Core Migration"
    return None


def skill_file(path):
    parts = path.split("/")
    return path.lower().endswith(".md") and any(p.lower() in ("skill", "skills") for p in parts[:-1])


def front_matter_name(text):
    lines = (text or "").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return None
    block = lines[1:end]
    name = next((ln.split(":", 1)[1].strip().strip("'\"") for ln in block if ln.startswith("name:")), None)
    has_desc = any(ln.startswith("description:") for ln in block)
    return name if (name and has_desc) else None


def cmd_notes_detect(a):
    root, cfg = ctx(a)
    detect(root, cfg, a.run, a.migrations, a.skills)
    return 0


def detect(root, cfg, run, migrations, skills):
    d = run_dir(root, run)
    data = L.read_json(d / "data.json")
    repos = L.discover_repos(root, cfg)
    for extra in ("All Code Repositories",):
        if (root / extra).is_dir():
            repos.update({x.name: x for x in (root / extra).iterdir() if x.is_dir() and L.is_repo(x)})
    byname = {n.lower(): p for n, p in repos.items()}
    for p in repos.values():
        c = L.repo_coords(p)
        if c:
            byname.setdefault(c[2].lower(), p)
    for pr in data["prs"]:
        clone = byname.get(pr["repo"].lower())
        key = str(pr["id"])
        if not clone:
            data["gaps"].append(f"PR {pr['id']} {pr['repo']}: no local clone; detection skipped")
            continue
        rc, _, se = L.git_rc(["fetch", "--quiet", "origin", pr["source"], pr["target"]], clone)
        rc2, diff, se2 = L.git_rc(["diff", "--name-status", f"origin/{pr['target']}...origin/{pr['source']}"], clone)
        if rc2 != 0:
            data["gaps"].append(f"PR {pr['id']} {pr['repo']}: diff failed ({(se2 or se).strip()[:120]})")
            continue
        mig, skl = [], []
        for ln in diff.splitlines():
            bits = ln.split("\t")
            st, path = bits[0], bits[-1]
            if st.startswith("D"):
                continue
            if migrations and migration_kind(path):
                mig.append({"path": path, "kind": migration_kind(path)})
            if skills and skill_file(path):
                name = front_matter_name(L.git(["show", f"origin/{pr['source']}:{path}"], clone, check=False))
                if name:
                    skl.append({"path": path, "change": "Added" if st.startswith("A") else "Modified", "name": name})
        if migrations:
            data["migrations"][key] = mig
        if skills:
            data["skills"][key] = skl
    L.write_json(d / "data.json", data)
    out(f"Migration files: {sum(len(v) for v in data['migrations'].values())} · skill files: {sum(len(v) for v in data['skills'].values())}")
    for g in data["gaps"]:
        out(f"  gap: {g}")


def cmd_notes_render(a):
    root, cfg = ctx(a)
    return render(root, cfg, a.run, a.scope, a.priority, a.env, a.texts)


def render(root, cfg, run, scope=None, priority=None, env=None, texts_path=None):
    """Writes the file and the wiki page of a run, and plans the page. Choices left out are the last render's."""
    d = run_dir(root, run)
    data = L.read_json(d / "data.json")
    last = (L.read_json(d / "meta.json", {}) or {}).get("facts") or {}
    scope, priority, env = scope or last.get("scope"), priority or last.get("mode"), env or last.get("env")
    if not (scope and priority and env):
        raise L.Refused("the first render needs --scope, --priority and --env")
    texts = L.read_json(texts_path, {}) if texts_path else (L.read_json(d / "texts.json", {}) or {})
    if texts_path:
        L.write_json(d / "texts.json", texts)
    since = PI.last_deploy(data.get("deployed"), data["project"], env)
    file_md, wiki_md, facts = N.build(data, scope, priority, env, texts, since=since)
    problems = L.lint_outbound(file_md, "wiki", env) + L.lint_outbound(wiki_md, "wiki", env)
    if problems:
        for p in sorted(set(problems)):
            out(f"  BLOCKED: {p}")
        out("Fix the texts (or the work item data) and render again. Nothing was written.")
        return 1
    nd = root / cfg["notesDir"]
    nd.mkdir(parents=True, exist_ok=True)
    meta = L.read_json(d / "meta.json", {})
    old = meta.get("file")
    if old and Path(old).exists() and meta.get("stage") == "rendered":
        fname = Path(old).name  # a re-render of this run rewrites its own file, never another day's
    else:
        fname = N.slug_file(facts["day"].replace("-", ""), scope, [p.name for p in nd.glob("release-notes-*.md")])
    (nd / fname).write_text(file_md, encoding="utf-8")
    (d / "wiki.md").write_text(wiki_md, encoding="utf-8")
    link = L.wiki_git_path(facts["wikiPath"])
    line = N.index_line(facts, link, [p for p in data["prs"] if p["id"] in facts["prs"]])
    item = {"op": "wiki", "org": data["org"], "project": data["project"], "path": facts["wikiPath"],
            "digest": L.digest(wiki_md), "indexEntry": f"[Release {facts['version']} [{facts['env']}] - {facts['day']}]("}
    token = L.save_plan(root, "notes", [item], f"Publish the {facts['env']} release notes for {facts['version']} to the {data['project']} wiki",
                        {"ref": f"notes {run}"})
    meta.update({"stage": "rendered", "file": str(nd / fname), "wikiFile": str(d / "wiki.md"), "token": token, "facts": facts,
                 "indexLine": line, "title": f"Release {facts['version']} — {facts['env']}",
                 "needText": [{"id": i, "title": data["workItems"].get(str(i), {}).get("title", "")} for i in facts["needText"]]})
    L.write_json(d / "meta.json", meta)
    out(f"File: {nd / fname}")
    out(f"Wiki page (not published): {facts['wikiPath']} · {facts['items']} work items · {len(facts['prs'])} PR{'s' if len(facts['prs']) != 1 else ''}")
    if facts["needText"]:
        out(f"No one-line fix summary yet for bugs {facts['needText']}: write {{\"<id>\": \"<sentence>\"}} to a file and render again with --texts.")
    if facts["unassigned"]:
        out(f"Unassigned: {facts['unassigned']}")
    out(f"Plan {token}. Show the user the file path, then ask with AskUserQuestion: \"{L.approval_question(root, token)}\" "
        f"options \"Yes, go ahead\" / \"No\". After a Yes: devops.py notes publish --run {run}")
    return 0


def cmd_notes_release(a):
    """The pane's one press after the release PRs: per project, collect from those PRs, detect, render."""
    root, cfg = ctx(a)
    plan = L.read_json(L.state_dir(root, "release", f"{a.version}.json")) or L.die(f"no scan of {a.version}: run release scan")
    orgs = {r["project"]: r["org"] for r in plan.get("repos", []) if r.get("project") and r.get("org")}
    groups = collections.defaultdict(set)
    for r in plan.get("results", []):
        if r.get("prId") and not r.get("error") and r.get("project") in orgs:
            groups[(orgs[r["project"]], r["project"])].add(int(r["prId"]))
    for r in plan.get("repos", []):
        if (r.get("pr") or {}).get("id") and r.get("project") in orgs:
            groups[(orgs[r["project"]], r["project"])].add(int(r["pr"]["id"]))
    if not groups:
        raise L.Refused(f"release {a.version} has no release PR yet: open them first (approve the plan, then open the PRs)")
    worst = 0
    for (org, proj), ids in sorted(groups.items()):
        ado = L.Ado(org)
        prs = [pr_view(org, proj, ado.pull_request(proj, i)) for i in sorted(ids)]
        run = save_run(root, cfg, ado, org, proj, prs, f"the release PRs of {a.version}", release=a.version)
        if a.migrations or a.skills:
            detect(root, cfg, run, a.migrations, a.skills)
        worst = max(worst, render(root, cfg, run, a.scope, a.priority, a.env))
    return worst


def cmd_notes_text(a):
    """A bug's one-line fix summary, typed in the pane (stdin); empty takes it out. Renders the run again."""
    root, cfg = ctx(a)
    d = run_dir(root, a.run)
    texts = L.read_json(d / "texts.json", {}) or {}
    line = " ".join(sys.stdin.read().split())
    if line:
        texts[str(a.id)] = line
    else:
        texts.pop(str(a.id), None)
    L.write_json(d / "texts.json", texts)
    return render(root, cfg, a.run)


def cmd_notes_publish(a):
    root, _ = ctx(a)
    d = run_dir(root, a.run)
    meta = L.read_json(d / "meta.json") or L.die("render first")
    if meta.get("stage") not in ("rendered", "published"):
        L.die("render first")
    L.require_approval(root, meta["token"])
    plan = L.load_plan(root, meta["token"])
    item = plan["items"][0]
    wiki_md = (d / "wiki.md").read_text(encoding="utf-8")
    if L.digest(wiki_md) != item["digest"]:
        raise L.Refused("wiki.md changed after it was approved: render again and ask again")
    problems = L.lint_outbound(wiki_md, "wiki", meta["facts"]["env"])
    if problems:
        raise L.Refused("; ".join(problems))
    ado = L.Ado(item["org"])
    wikis = ado.wikis(item["project"])
    if not wikis:
        raise L.Refused(f"{item['project']} has no project wiki. The user creates it once (Overview > Wiki > Create project wiki); "
                        "the file is delivered either way.")
    wiki = next((w for w in wikis if w.get("type") == "projectWiki"), wikis[0])
    _, etag = ado.wiki_page(item["project"], wiki["id"], item["path"])
    res = ado.put_wiki_page(item["project"], wiki["id"], item["path"], wiki_md, etag)
    link = (res or {}).get("gitItemPath", "").rsplit(".md", 1)[0] or L.wiki_git_path(item["path"])
    line = re.sub(r"\]\([^)]*\)", f"]({link})", meta["indexLine"], count=1)
    page, etag2 = ado.wiki_page(item["project"], wiki["id"], "/Release Notes")
    index = N.index_page((page or {}).get("content"), line, item["project"])
    res2 = ado.put_wiki_page(item["project"], wiki["id"], "/Release Notes", index, etag2)
    meta.update(stage="published", publishedAt=int(time.time()), url=(res or {}).get("remoteUrl"), indexUrl=(res2 or {}).get("remoteUrl"),
                wiki=wiki.get("name"))
    L.write_json(d / "meta.json", meta)
    plan["done"] = int(time.time())
    L.write_json(L.state_dir(root, "plans", f"{meta['token']}.json"), plan)
    out(f"Published {item['path']} to {wiki.get('name')}: {meta['url']}")
    out(f"Index /Release Notes updated: {meta['indexUrl']}")
    return 0


# ================================================================ pipelines, deployments, setup (read only)

def default_version(root, cfg):
    """The version of the newest release scan, else the newest team version the repos know."""
    d = L.state_dir(root, "release")
    scans = [L.read_json(f) or {} for f in d.glob("*.json") if not f.name.endswith(".scan.json")] if d.is_dir() else []
    if scans:
        return max(scans, key=lambda r: r.get("generated", 0)).get("version")
    vs = list(L.local_versions(root, cfg))
    return vs[-1] if vs else None


def release_branches(root, cfg, version):
    """A version's team and release branches: the patterns, and each repo's own spelling from the last scan."""
    names = {cfg["sourcePattern"].format(version), cfg["targetPattern"].format(version)}
    for r in (L.read_json(L.state_dir(root, "release", f"{version}.json")) or {}).get("repos", []):
        names.update(x for x in (r.get("source"), r.get("target")) if x)
    return sorted(names, key=lambda n: (n.lower(), n))


def cmd_pipelines(a):
    root, cfg = ctx(a)
    v = a.version or default_version(root, cfg)
    if not v:
        raise L.Refused("no version: pass --version, or scan a release first")
    branches = release_branches(root, cfg, v)
    rows, errors = [], []
    for (org, proj), clones in sorted(workspace_projects(root, cfg).items()):
        ado = L.Ado(org)
        try:
            names = {r["id"].lower(): r["name"] for r in ado.repositories(proj)}  # a build may name its repo by id only
            seen, builds = set(), []
            for b in branches:
                for x in ado.builds(proj, branch=b):
                    repo = x.get("repository") or {}
                    name = repo.get("name") or names.get((repo.get("id") or "").lower(), "")
                    if x["id"] not in seen and name.lower() in clones:
                        seen.add(x["id"])
                        builds.append(dict(x, repository=dict(repo, name=name)))
            for b in PI.latest_builds(builds):
                failing = PI.failing_step(ado.build_timeline(proj, b["id"])) if b.get("result") in PI.FAILED else None
                rows.append(PI.build_row(org, proj, b, failing))
        except (L.Refused, RuntimeError) as e:
            errors.append(f"{proj}: {short(str(e), 300)}")
    rows.sort(key=lambda r: (r["repo"].lower(), r["branch"].lower(), r["pipeline"].lower()))
    data = {"generated": int(time.time()), "version": v, "branches": branches, "rows": rows, "errors": errors}
    L.write_json(L.state_dir(root, "pipelines.json"), data)
    if a.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0
    c = PI.pipeline_counts(rows)
    out(f"Pipelines on {', '.join(branches)}: {c['failed']} failed, {c['running']} running, {c['passed']} passed")
    for r in sorted(rows, key=lambda r: PI.build_word(r) not in ("failed", "partly failed")):
        w = PI.build_word(r)
        why = f" · step \"{r['failing']['step']}\": {short(r['failing']['message'], 120)}" if r.get("failing") else ""
        out(f"  {w.upper():13} {r['repo']} · {r['pipeline']} · {r['branch']} · {r['number']}{why}  {r['url']}")
    for e in errors:
        out(f"  could not read {e}")
    if not rows and not errors:
        out("  No builds on these branches.")
    return 2 if errors and not rows else 0


def read_deployments(cfg, org, proj, ado=None):
    """(rows, errors) of one project: its YAML environments and its classic release stages."""
    ado = ado or L.Ado(org)
    aliases = cfg["deployments"]["environments"]
    pats = [cfg["targetPattern"], cfg["sourcePattern"]]
    rows, errors = [], []
    try:
        envs = ado.environments(proj)
        recs = {e["id"]: ado.environment_records(proj, e["id"]) for e in envs}
        ids = sorted({int((r.get("owner") or {}).get("id") or 0) for rs in recs.values() for r in rs
                      if r.get("result") in ("succeeded", "succeededWithIssues")} - {0})
        builds = {}
        names = {r["id"].lower(): r["name"] for r in ado.repositories(proj)} if ids else {}
        for i in range(0, len(ids), 100):
            for b in ado.builds(proj, ids=ids[i:i + 100]):
                repo = b.get("repository") or {}
                builds[int(b["id"])] = dict(b, repository=dict(repo, name=repo.get("name") or names.get((repo.get("id") or "").lower(), "")))
        for e in envs:
            rows += PI.yaml_rows(org, proj, e, recs[e["id"]], builds, aliases, pats)
    except (L.Refused, RuntimeError) as e:
        errors.append(f"{proj} environments: {short(str(e), 300)}")
    try:
        rows += PI.classic_rows(org, proj, ado.release_deployments(proj), aliases, pats)
    except (L.Refused, RuntimeError) as e:
        errors.append(f"{proj} classic releases: {short(str(e), 300)}")
    return rows, errors


def cmd_deployments(a):
    root, cfg = ctx(a)
    rows, errors = [], []
    for (org, proj) in sorted(workspace_projects(root, cfg)):
        r, e = read_deployments(cfg, org, proj)
        rows += r
        errors += e
    order = {e: i for i, e in enumerate(PI.ENV_ORDER)}
    rows.sort(key=lambda r: (order.get(r["env"], 9), r["envName"].lower(), r["pipeline"].lower()))
    data = {"generated": int(time.time()), "rows": rows, "errors": errors}
    L.write_json(L.state_dir(root, "deployments.json"), data)
    if a.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0
    out("Deployed now:" if rows else "No deployments found (YAML environments or classic release stages).")
    for r in rows:
        ver = r["version"] or r["branch"] or "?"
        out(f"  {(r['env'] or r['envName'])[:12]:12} {r['pipeline']} → {r['repo'] or r['project']} {ver}"
            f"{' (build ' + r['build'] + ')' if r['build'] else ''} · {r['at'][:10]}")
    for e in errors:
        out(f"  could not read {e}")
    return 2 if errors and not rows else 0


def doctor_checks(root, cfg):
    C = PI.check
    rows = [C("Python", "ok", sys.version.split()[0])]
    rows.append(C("git", "ok", L.git(["--version"], root, check=False)) if shutil.which("git")
                else C("git", "fail", "git not found", "Install Git (https://git-scm.com), then open a new terminal."))
    ps = shutil.which("pwsh") or shutil.which("pwsh.exe")
    rows.append(C("PowerShell 7", "ok", ps) if ps else C("PowerShell 7", "fail", "pwsh not found: the release and sync scans need it",
                                                         "Install it: winget install Microsoft.PowerShell (or https://aka.ms/powershell)."))
    cp = root / L.CONFIG
    if not cp.is_file():
        rows.append(C("Config", "ok", f"no {L.CONFIG}: the defaults apply"))
    else:
        try:
            raw = json.loads(cp.read_text(encoding="utf-8-sig"))
            odd = sorted(set(raw if isinstance(raw, dict) else {}) - set(L.DEFAULTS))
            rows.append(C("Config", "warn", f"{L.CONFIG}: unknown keys {', '.join(odd)}", "Check their spelling against the README's config table.")
                        if odd else C("Config", "ok", f"{L.CONFIG} read"))
        except ValueError as e:
            rows.append(C("Config", "fail", f"{L.CONFIG} is not valid JSON ({e})", "Fix the file; until then the defaults apply."))
    repos = L.discover_repos(root, cfg)
    coords = {n: L.repo_coords(d) for n, d in repos.items()}
    with_ado = sorted(n for n, c in coords.items() if c)
    if not repos:
        rows.append(C("Repos", "fail", f"no git repos under {cfg['reposDir']}/", "Run devops from the workspace root, or set reposDir in .claude/devops.json."))
    elif not with_ado:
        rows.append(C("Repos", "fail", f"{len(repos)} repos, none with an Azure DevOps origin", "Clone the repos from Azure DevOps."))
    else:
        rows.append(C("Repos", "ok", f"{len(with_ado)} with an Azure DevOps origin"))
        other = sorted(set(repos) - set(with_ado))
        if other:
            rows.append(C("Repos", "warn", f"no Azure DevOps origin, so devops skips them: {', '.join(other)}"))
    vs = L.local_versions(root, cfg)
    rows.append(C("Team branches", "ok", f"{len(vs)} version{'s' if len(vs) != 1 else ''} known, newest {list(vs)[-1]}") if vs else
                C("Team branches", "warn", f"no origin/{cfg['branchPrefix']}* branch known in the repos", "Fetch the repos, or check branchPrefix in .claude/devops.json."))
    rows.append(C("Guard", "ok", "on") if cfg["guard"]["enabled"] else C("Guard", "warn", "off", "Set guard.enabled to true in .claude/devops.json."))
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT") or os.environ.get("DEVOPS_ADO_PAT")
    az = shutil.which("az") or shutil.which("az.cmd")
    if pat:
        rows.append(C("Sign-in", "ok", "a PAT in AZURE_DEVOPS_EXT_PAT"))
    elif not az and not os.environ.get("DEVOPS_FAKE_ADO"):
        rows.append(C("Sign-in", "fail", "the Azure CLI (az) is not installed and no PAT is set",
                      "Install it (winget install Microsoft.AzureCLI), then run az login."))
    if az:
        r = subprocess.run([az, "extension", "show", "--name", "azure-devops", "-o", "none"], capture_output=True, text=True)
        rows.append(C("az devops", "ok", "the azure-devops extension is installed") if r.returncode == 0 else
                    C("az devops", "warn", "the azure-devops extension is missing: the sync scan cannot check branch locks",
                      "az extension add --name azure-devops"))
    signed = {}
    for org in sorted({c[0] for c in coords.values() if c}):
        try:
            me = L.Ado(org).me()
            signed[org] = True
            rows.append(C(f"ADO {org}", "ok", f"signed in as {me['name'] or me['id']}"))
        except (L.Refused, RuntimeError) as e:
            signed[org] = False
            fix = getattr(e, "fix", "")
            rows.append(C(f"ADO {org}", "fail", short(str(e), 240),
                          f"Run {fix} in a terminal, then check again." if fix else "Run az login (or set AZURE_DEVOPS_EXT_PAT), then check again."))
    for (org, proj), clones in (sorted(workspace_projects(root, cfg).items()) if with_ado else []):
        if not signed.get(org):
            continue
        ado = L.Ado(org)
        try:
            listed = {r["name"].lower(): r for r in ado.repositories(proj)}
        except (L.Refused, RuntimeError) as e:
            rows.append(C(f"{proj}: repos", "fail", short(str(e), 200), "Ask a project admin for access to the project."))
            continue
        gone = sorted(n for n in clones if n not in listed)
        if gone:
            rows.append(C(f"{proj}: repos", "warn", f"not in Azure DevOps (renamed or deleted?): {', '.join(gone)}"))
        known = [listed[n] for n in sorted(clones) if n in listed]
        if known:
            pid = known[0]["project"]["id"]
            tokens = [f"repoV2/{pid}/{r['id']}" for r in known]
            try:
                got = {b: ado.has_permission(PI.GIT_NAMESPACE, b, tokens) for b in (PI.PR_CONTRIBUTE, PI.CONTRIBUTE, PI.CREATE_BRANCH)}
                lacking = {r["name"]: PI.missing_bits({b: (v[i] if i < len(v) else True) for b, v in got.items()}) for i, r in enumerate(known)}
                lacking = {k: v for k, v in lacking.items() if v}
                if not lacking:
                    rows.append(C(f"{proj}: access", "ok", f"{len(known)} repos: push, create branches, pull requests"))
                for name, miss in sorted(lacking.items()):
                    rows.append(C(f"{proj}: {name}", "fail" if "contribute to pull requests" in miss else "warn", "you cannot " + ", ".join(miss),
                                  "Ask a project admin for Contribute, Create branch and Contribute to pull requests on this repo."))
            except (L.Refused, RuntimeError) as e:
                rows.append(C(f"{proj}: access", "warn", f"could not check permissions: {short(str(e), 160)}"))
        try:
            wiki = next((w for w in ado.wikis(proj) if w.get("type") == "projectWiki"), None)
            if not wiki:
                rows.append(C(f"{proj}: wiki", "warn", "no project wiki: release notes stay a file", "Create it once: Overview > Wiki > Create project wiki."))
            else:
                tok = f"repoV2/{wiki.get('projectId') or (known[0]['project']['id'] if known else '')}/{wiki.get('repositoryId')}"
                can = ado.has_permission(PI.GIT_NAMESPACE, PI.CONTRIBUTE, [tok])
                rows.append(C(f"{proj}: wiki", "ok", f"{wiki.get('name')}: you can write it") if (can or [True])[0] else
                            C(f"{proj}: wiki", "fail", f"{wiki.get('name')}: you cannot write it", "Ask a project admin for Contribute on the wiki."))
        except (L.Refused, RuntimeError) as e:
            rows.append(C(f"{proj}: wiki", "warn", f"could not read the wikis: {short(str(e), 160)}"))
        try:
            ado.builds(proj, top=1)
            rows.append(C(f"{proj}: pipelines", "ok", "builds can be read"))
        except (L.Refused, RuntimeError) as e:
            rows.append(C(f"{proj}: pipelines", "warn", f"cannot read builds: the Pipelines tab stays empty ({short(str(e), 120)})",
                          "Ask for View builds on the project's pipelines."))
    return rows


def cmd_doctor(a):
    root, cfg = ctx(a)
    rows = doctor_checks(root, cfg)
    data = {"generated": int(time.time()), "root": str(root), "rows": rows}
    L.write_json(L.state_dir(root, "doctor.json"), data)
    if a.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        for r in rows:
            out(f"{r['state'].upper():4} {r['name']}: {r['detail']}" + (f"\n     fix: {r['fix']}" if r["fix"] and r["state"] != "ok" else ""))
        bad = [r for r in rows if r["state"] == "fail"]
        out(f"{len(bad)} problem{'s' if len(bad) != 1 else ''}, {sum(1 for r in rows if r['state'] == 'warn')} warnings.")
    return 1 if any(r["state"] == "fail" for r in rows) else 0


# ================================================================ PR reviews (the /devops pane's Reviews tab)

def workspace_projects(root, cfg):
    """{(org, project): {ado repo name, lower: local clone}} for the ADO projects the workspace repos live in."""
    out = {}
    for d in L.discover_repos(root, cfg).values():
        c = L.repo_coords(d)
        if c:
            out.setdefault((c[0], c[1]), {})[c[2].lower()] = d
    if not out:
        raise L.Refused("no Azure DevOps origin in the workspace repos: the Reviews tab lists the PRs of their projects")
    return out


def project_org(root, cfg, project):
    hit = [o for (o, p) in workspace_projects(root, cfg) if p.lower() == project.lower()]
    if not hit:
        raise L.Refused(f"{project} is not a project of the workspace repos")
    return hit[0]


def my_groups(ado, me, reviewer_ids):
    """The ids, among these reviewer groups, of the ones the user is in (two identity reads)."""
    if not reviewer_ids or not me.get("id"):
        return set()
    mine = ado.identities([me["id"]], "ExpandedUp")
    member_of = {d.lower() for d in ((mine[0].get("memberOf") or []) if mine else [])}
    groups = ado.identities(sorted(reviewer_ids))
    return {g["id"].lower() for g in groups if (g.get("descriptor") or "").lower() in member_of}


def cmd_reviews_list(a):
    root, cfg = ctx(a)
    rows, who = [], {}
    for (org, proj) in sorted(workspace_projects(root, cfg)):
        ado = L.Ado(org)
        if org not in who:
            who[org] = ado.me()
        me = who[org]
        prs_ = ado.pull_requests(proj, status="active")
        groups = {r["id"] for pr in prs_ for r in pr.get("reviewers") or [] if r.get("isContainer")}
        mine = my_groups(ado, me, groups)
        for pr in prs_:
            rows.append(R.pr_row(org, proj, pr, me.get("id"), mine,
                                 L.web_pr_url(org, proj, pr["repository"]["name"], pr["pullRequestId"])))
    rows.sort(key=lambda r: (not r["waiting"], r["created"]))
    data = {"generated": int(time.time()), "me": ", ".join(sorted({m.get("name", "") for m in who.values()})), "rows": rows}
    L.write_json(L.state_dir(root, "reviews", "list.json"), data)
    shown = rows if a.all else [r for r in rows if r["waiting"]]
    if a.json:
        print(json.dumps(dict(data, rows=shown), ensure_ascii=False))
        return 0
    out(f"{len(shown)} PR{'s' if len(shown) != 1 else ''} {'active' if a.all else 'waiting on you'} ({len(rows)} active in "
        f"{len(workspace_projects(root, cfg))} project{'s' if len(workspace_projects(root, cfg)) != 1 else ''})")
    for r in shown:
        out(f"  PR {r['id']} {r['repo']}: {short(r['title'], 60)} · {r['author']} · {r['role'] or 'not a reviewer'} · {R.vote_word(r['myVote'])}")
    return 0


def pr_detail(root, cfg, project, pr_id):
    org = project_org(root, cfg, project)
    ado = L.Ado(org)
    me = ado.me()
    pr = ado.pull_request(project, pr_id)
    repo = pr["repository"]["name"]
    its = ado.pr_iterations(project, repo, pr_id)
    it = its[-1] if its else {}
    changes = ado.pr_changes(project, repo, pr_id, it["id"]) if it else []
    files = [{"path": (c.get("item") or {}).get("path", "").lstrip("/"), "change": c.get("changeType", "")}
             for c in changes if not (c.get("item") or {}).get("isFolder")]
    ids = ado.pr_work_items(project, repo, pr_id)
    wis = [{"id": int(w["id"]), "type": w["fields"].get("System.WorkItemType", ""), "title": w["fields"].get("System.Title", ""),
            "state": w["fields"].get("System.State", ""),
            "criteria": R.strip_html(w["fields"].get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))[:1500]}
           for w in (ado.work_items(ids, ["System.Title", "System.WorkItemType", "System.State",
                                          "Microsoft.VSTS.Common.AcceptanceCriteria"]) if ids else [])]
    policies = R.policy_rows(ado.policy_evaluations(project, pr["repository"]["project"]["id"], pr_id))
    groups = {r["id"] for r in pr.get("reviewers") or [] if r.get("isContainer")}
    row = R.pr_row(org, project, pr, me.get("id"), my_groups(ado, me, groups), L.web_pr_url(org, project, repo, pr_id))
    ok, why = R.can_vote(pr, me.get("id"), policies)
    key = R.key_of(org, project, pr_id, it.get("id", 0))
    return dict(row, description=pr.get("description", ""), iteration=it.get("id", 0),
                commits={"source": (it.get("sourceRefCommit") or {}).get("commitId"),
                         "common": (it.get("commonRefCommit") or {}).get("commitId")},
                files=files, workItems=wis, threads=R.thread_rows(ado.pr_threads(project, repo, pr_id)),
                policies=[{k: v for k, v in p.items() if k != "settings"} for p in policies],
                canVote=ok, voteNote=why, me=me.get("name", ""), key=key,
                review=L.read_json(L.state_dir(root, "reviews", f"{key}.json")))


def cmd_reviews_show(a):
    root, cfg = ctx(a)
    d = pr_detail(root, cfg, a.project, a.id)
    if a.json:
        print(json.dumps(d, ensure_ascii=False))
        return 0
    out(f"PR {d['id']} {d['repo']}: {d['title']} · {d['author']} · {d['source']} -> {d['target']}")
    out("  policies: " + (", ".join(f"{p['name']} {p['status']}" for p in d["policies"]) or "none"))
    out("  votes: " + (", ".join(f"{v['name']} {R.vote_word(v['vote'])}" for v in d["votes"]) or "none"))
    out(f"  you: {d['role'] or 'not a reviewer'}, {R.vote_word(d['myVote'])}" + ("" if d["canVote"] else f" · may not vote: {d['voteNote']}"))
    wis = ", ".join("ADO %s" % w["id"] for w in d["workItems"]) or "none"
    out(f"  {len(d['files'])} files · {len(d['threads'])} threads · work items {wis}")
    return 0


def pr_diff(root, cfg, d):
    """The PR's diff (common base -> source of the latest iteration): from the local clone when it has the
    commits, else from ADO's file contents."""
    clone = workspace_projects(root, cfg).get((d["org"], d["project"]), {}).get(d["repo"].lower())
    src, base = d["commits"]["source"], d["commits"]["common"]
    if clone and src and base:
        L.git_rc(["fetch", "--quiet", "origin", d["source"], d["target"]], clone)
        if all(L.git_rc(["cat-file", "-e", f"{c}^{{commit}}"], clone)[0] == 0 for c in (src, base)):
            return L.git(["diff", "-U3", "--no-color", "--no-ext-diff", base, src], clone, check=False)
    ado = L.Ado(d["org"])
    parts = []
    for f in d["files"][:80]:
        old = None if f["change"].startswith("add") else ado.file_at(d["project"], d["repo"], "/" + f["path"], base)
        new = None if f["change"].startswith("delete") else ado.file_at(d["project"], d["repo"], "/" + f["path"], src)
        parts.append(R.unified(f["path"], old, new))
    return "\n".join(parts)


def cmd_reviews_pack(a):
    """What the pane's quick review sends to the model, and the lines a finding may name."""
    root, cfg = ctx(a)
    d = pr_detail(root, cfg, a.project, a.id)
    rc = cfg["reviews"]
    bundle, lines, cut = R.number_diff(pr_diff(root, cfg, d), int(rc["maxDiffChars"]))
    print(json.dumps({"key": d["key"], "iteration": d["iteration"], "system": R.SYSTEM % int(rc["maxFindings"]),
                      "prompt": R.prompt(d, bundle, cut), "lines": lines, "truncated": cut, "model": rc["model"],
                      "maxTokens": int(rc["maxTokens"]), "maxFindings": int(rc["maxFindings"])}, ensure_ascii=False))
    return 0


def cmd_reviews_save(a):
    """The quick review's findings for one PR iteration (stdin JSON), so reopening the PR shows them again."""
    root, _ = ctx(a)
    if not re.fullmatch(r"[\w.-]+", a.key):
        L.die("bad key")
    data = json.loads(sys.stdin.read() or "{}")
    data["at"] = int(time.time())
    L.write_json(L.state_dir(root, "reviews", f"{a.key}.json"), data)
    out(f"Saved {len(data.get('findings', []))} findings.")
    return 0


def cmd_reviews_post(a):
    """Posts the person's comments (stdin JSON {"iteration": n, "drafts": [...]}) under their own name."""
    root, cfg = ctx(a)
    org = project_org(root, cfg, a.project)
    data = json.loads(sys.stdin.read() or "{}")
    drafts = [x for x in data.get("drafts", []) if str(x.get("text", "")).strip()]
    if not drafts:
        L.die("nothing to post")
    bad = []
    for i, x in enumerate(drafts, 1):
        problems = L.lint_outbound(x["text"] + "\n" + str(x.get("suggestion") or ""), "pr")
        bad += [f"comment {i}: {p}" for p in problems if "4000" not in p]
    if bad:
        raise L.Refused("nothing was posted: " + "; ".join(bad))
    ado = L.Ado(org)
    pr = ado.pull_request(a.project, a.id)
    repo = pr["repository"]["name"]
    its = ado.pr_iterations(a.project, repo, a.id)
    iteration = its[-1]["id"] if its else None
    tracking = {}
    if iteration and any(x.get("file") for x in drafts):
        tracking = {(c.get("item") or {}).get("path", "").lstrip("/"): c.get("changeTrackingId")
                    for c in ado.pr_changes(a.project, repo, a.id, iteration)}
    if data.get("iteration") and iteration and int(data["iteration"]) != int(iteration):
        raise L.Refused(f"PR {a.id} has a new push (iteration {iteration}, the review read {data['iteration']}): "
                        "its line numbers may have moved. Open the PR again and review the new code. Nothing was posted.")
    done = 0
    for x in drafts:
        if x.get("reply"):
            ado.post_reply(a.project, repo, a.id, x["reply"], x["text"].strip())
        else:
            ado.post_thread(a.project, repo, a.id, R.thread_body(x, iteration, tracking))
        done += 1
    out(f"Posted {done} comment{'s' if done != 1 else ''} on PR {a.id}.")
    return 0


def cmd_reviews_vote(a):
    """The person's vote on a PR, under their own name; refused where the PR's policy does not count it."""
    root, cfg = ctx(a)
    org = project_org(root, cfg, a.project)
    ado = L.Ado(org)
    me = ado.me()
    pr = ado.pull_request(a.project, a.id)
    if a.vote != "reset":
        policies = R.policy_rows(ado.policy_evaluations(a.project, pr["repository"]["project"]["id"], a.id))
        ok, why = R.can_vote(pr, me.get("id"), policies)
        if not ok:
            raise L.Refused(why)
    ado.vote(a.project, pr["repository"]["name"], a.id, me["id"], R.VOTES[a.vote])
    out(f"Voted on PR {a.id}: {R.vote_word(R.VOTES[a.vote])}.")
    return 0


# ================================================================ main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="devops.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("versions")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_versions)
    s = sub.add_parser("approve")
    s.add_argument("--token", required=True)
    s.add_argument("--via", default="pane")
    s.set_defaults(fn=cmd_approve)

    rel = sub.add_parser("release").add_subparsers(dest="sub", required=True)
    s = rel.add_parser("scan")
    s.add_argument("--version", required=True)
    s.add_argument("--repos")
    s.add_argument("--no-fetch", action="store_true")
    s.add_argument("--no-ado", action="store_true")
    s.set_defaults(fn=cmd_release_scan)
    s = rel.add_parser("open")
    s.add_argument("--version", required=True)
    s.set_defaults(fn=cmd_release_open)
    s = rel.add_parser("show")
    s.add_argument("--version", required=True)
    s.add_argument("--items", action="store_true", help="the planned PRs as JSON (for the MCP fallback)")
    s.set_defaults(fn=cmd_release_show)

    sy = sub.add_parser("sync").add_subparsers(dest="sub", required=True)
    s = sy.add_parser("chain")
    s.add_argument("--from", dest="from_version")
    s.add_argument("--to", dest="to_version")
    s.add_argument("--repos")
    s.add_argument("--skip-lock-check", action="store_true")
    s.set_defaults(fn=cmd_sync_chain)
    s = sy.add_parser("scan")
    s.add_argument("--source", required=True)
    s.add_argument("--destination", required=True)
    s.add_argument("--repos")
    s.add_argument("--prior-source")
    s.add_argument("--prior-destination")
    s.add_argument("--skip-lock-check", action="store_true")
    s.set_defaults(fn=cmd_sync_scan)
    s = sy.add_parser("start")
    for f in ("--repo", "--source", "--destination", "--user"):
        s.add_argument(f, required=True)
    s.add_argument("--recreate", action="store_true")
    s.set_defaults(fn=cmd_sync_start)
    s = sy.add_parser("verify")
    s.add_argument("--repo", required=True)
    s.set_defaults(fn=cmd_sync_verify)
    s = sy.add_parser("finish")
    s.add_argument("--repo", required=True)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_sync_finish)
    s = sy.add_parser("techstory")
    s.add_argument("--project", required=True)
    s.add_argument("--org")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--id", type=int)
    s.add_argument("--no-check", action="store_true", help="with --id: you checked it with the MCP tools")
    s.add_argument("--title")
    s.set_defaults(fn=cmd_sync_techstory)
    s = sy.add_parser("restore")
    s.add_argument("--status", action="store_true")
    s.set_defaults(fn=cmd_sync_restore)
    s = sy.add_parser("record")
    for f in ("--source", "--destination", "--repo"):
        s.add_argument(f, required=True)
    s.add_argument("--pr", type=int, required=True)
    s.add_argument("--url")
    s.set_defaults(fn=cmd_sync_record)
    for name, fn in (("plan", cmd_sync_plan), ("open", cmd_sync_open), ("report", cmd_sync_report), ("show", cmd_sync_show)):
        s = sy.add_parser(name)
        s.add_argument("--source", required=True)
        s.add_argument("--destination", required=True)
        s.set_defaults(fn=fn)

    no = sub.add_parser("notes").add_subparsers(dest="sub", required=True)
    s = no.add_parser("collect")
    s.add_argument("--org")
    s.add_argument("--project")
    s.add_argument("--pr", type=int, action="append")
    s.add_argument("--commit")
    s.add_argument("--repo")
    s.add_argument("--top", type=int, default=50)
    s.set_defaults(fn=cmd_notes_collect)
    s = no.add_parser("ingest")
    s.add_argument("--file", required=True)
    s.set_defaults(fn=cmd_notes_ingest)
    s = no.add_parser("detect")
    s.add_argument("--run", required=True)
    s.add_argument("--migrations", action="store_true")
    s.add_argument("--skills", action="store_true")
    s.set_defaults(fn=cmd_notes_detect)
    s = no.add_parser("render")
    s.add_argument("--run", required=True)
    s.add_argument("--scope", choices=sorted(N.SCOPES))
    s.add_argument("--priority", choices=sorted(N.PRIORITY_MODES))
    s.add_argument("--env", choices=sorted(N.ENVS))
    s.add_argument("--texts")
    s.set_defaults(fn=cmd_notes_render)
    s = no.add_parser("publish")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_notes_publish)
    s = no.add_parser("release")
    s.add_argument("--version", required=True)
    s.add_argument("--env", required=True, choices=sorted(N.ENVS))
    s.add_argument("--scope", default="all", choices=sorted(N.SCOPES))
    s.add_argument("--priority", default="none", choices=sorted(N.PRIORITY_MODES))
    s.add_argument("--migrations", action="store_true")
    s.add_argument("--skills", action="store_true")
    s.set_defaults(fn=cmd_notes_release)
    s = no.add_parser("text")
    s.add_argument("--run", required=True)
    s.add_argument("--id", type=int, required=True)
    s.set_defaults(fn=cmd_notes_text)

    s = sub.add_parser("pipelines")
    s.add_argument("--version")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_pipelines)
    s = sub.add_parser("deployments")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_deployments)
    s = sub.add_parser("doctor")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    rv = sub.add_parser("reviews").add_subparsers(dest="sub", required=True)
    s = rv.add_parser("list")
    s.add_argument("--all", action="store_true", help="every active PR, not only those waiting on you")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_reviews_list)
    for name, fn in (("show", cmd_reviews_show), ("pack", cmd_reviews_pack), ("post", cmd_reviews_post)):
        s = rv.add_parser(name)
        s.add_argument("--project", required=True)
        s.add_argument("--id", type=int, required=True)
        if name == "show":
            s.add_argument("--json", action="store_true")
        s.set_defaults(fn=fn)
    s = rv.add_parser("save")
    s.add_argument("--key", required=True)
    s.set_defaults(fn=cmd_reviews_save)
    s = rv.add_parser("vote")
    s.add_argument("--project", required=True)
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--vote", required=True, choices=sorted(R.VOTES))
    s.set_defaults(fn=cmd_reviews_vote)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except L.Refused as e:
        print(f"devops: refused: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"devops: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
