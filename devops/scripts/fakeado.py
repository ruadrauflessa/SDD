"""An offline stand-in for the Azure DevOps REST calls devops.py makes, for tests.

Set DEVOPS_FAKE_ADO to a JSON "world" file and every devopslib.Ado call answers from it (no `az` login).
Writes change the world and are logged under "writes", so a test reads back what was sent. Only the
endpoints the scripts use are served; any other call is an error, so a new call cannot slip through.

    {
      "repositories": {"Proj/Repo": {"id": "r1", "name": "Repo", "project": {"id": "p1", "name": "Proj"}}},
      "pullRequests": [{"pullRequestId": 7, "repository": {...}, "sourceRefName": "refs/heads/team/1.1.0",
                        "targetRefName": "refs/heads/release/1.1.0", "title": "...", "description": "...",
                        "status": "active", "creationDate": "2026-08-21T10:00:00Z", "workItems": [101],
                        "createdBy": {"displayName": "Ann"}}],
      "items": {"101": {"rev": 1, "fields": {"System.Title": "...", ...}, "relations": []}},
      "wikis": {"Proj": [{"id": "w1", "name": "Proj.wiki", "type": "projectWiki"}]},
      "pages": {"Proj/Proj.wiki//Release Notes": {"content": "...", "etag": "\\"1\\""}},
      "writes": []
    }
"""
import json
import os
import re
import urllib.parse
from pathlib import Path

ENV = "DEVOPS_FAKE_ADO"


def active():
    return bool(os.environ.get(ENV))


def _load():
    p = Path(os.environ[ENV])
    return p, json.loads(p.read_text(encoding="utf-8"))


def _save(p, world):
    p.write_text(json.dumps(world, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _repo(world, project, name):
    repos = world.setdefault("repositories", {})
    for key, r in repos.items():
        p, n = key.split("/", 1)
        if p.lower() == project.lower() and (n.lower() == name.lower() or r.get("id") == name):
            return r
    raise RuntimeError(f"fake ADO: no repository {project}/{name}")


def _pr_view(pr):
    return {k: v for k, v in pr.items() if k != "workItems"}


def request(method, url, body, headers):
    p, world = _load()
    parts = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parts.query))
    path = urllib.parse.unquote(parts.path)
    m = re.match(r"^/(?P<org>[^/]+)(?:/(?P<proj>[^/]+))?/_apis/(?P<rest>.+)$", path)
    if not m:
        raise RuntimeError(f"fake ADO: cannot read {url}")
    proj, rest = m.group("proj"), m.group("rest")
    prs = world.setdefault("pullRequests", [])
    items = world.setdefault("items", {})
    writes = world.setdefault("writes", [])

    def done(data, hdrs=None, save=False):
        if save:
            _save(p, world)
        return data, hdrs or {}

    # -- repositories and pull requests
    mm = re.match(r"^git/repositories/([^/]+)$", rest)
    if mm and method == "GET":
        return done(_repo(world, proj, mm.group(1)))
    mm = re.match(r"^git/(?:repositories/([^/]+)/)?pullrequests$", rest)
    if mm and method == "GET":
        out = [pr for pr in prs if pr["repository"]["project"]["name"].lower() == proj.lower()]
        if mm.group(1):
            r = _repo(world, proj, mm.group(1))
            out = [pr for pr in out if pr["repository"]["id"] == r["id"]]
        st = q.get("searchCriteria.status", "active")
        if st != "all":
            out = [pr for pr in out if pr.get("status", "active") == st]
        for key, field in (("searchCriteria.targetRefName", "targetRefName"), ("searchCriteria.sourceRefName", "sourceRefName")):
            if key in q:
                out = [pr for pr in out if pr[field] == q[key]]  # ADO matches the ref exactly
        skip, top = int(q.get("$skip", 0)), int(q.get("$top", 100))
        return done({"value": [_pr_view(x) for x in out[skip:skip + top]]})
    mm = re.match(r"^git/repositories/([^/]+)/pullrequests$", rest)
    if mm and method == "POST":
        r = _repo(world, proj, mm.group(1))
        heads = world.get("branches", {}).get(f"{proj}/{r['name']}")
        for ref in (body["sourceRefName"], body["targetRefName"]):
            if heads is not None and ref[len("refs/heads/"):] not in heads:
                raise RuntimeError("ADO POST -> HTTP 400: TF401398: The pull request cannot be activated because "
                                   "the source and/or the target branch no longer exists")
        new_id = max([x["pullRequestId"] for x in prs] + [100]) + 1
        pr = {"pullRequestId": new_id, "repository": r, "sourceRefName": body["sourceRefName"],
              "targetRefName": body["targetRefName"], "title": body["title"], "description": body.get("description", ""),
              "status": "active", "isDraft": body.get("isDraft", False), "creationDate": "2026-10-21T10:00:00Z",
              "workItems": [int(w["id"]) for w in body.get("workItemRefs", [])
                            if str(w["id"]) not in world.get("dropLinks", [])]}
        pr["workItems"] += [int(x) for x in world.get("autoLink", [])]  # ADO's own link from a commit message
        from devopslib import pr_link_url
        for wid in pr["workItems"]:  # as in ADO, a link is a relation on the work item
            it = items.get(str(wid))
            if it is not None:
                it.setdefault("relations", []).append({"rel": "ArtifactLink", "attributes": {"name": "Pull Request"},
                                                       "url": pr_link_url(r["project"]["id"], r["id"], new_id)})
        prs.append(pr)
        writes.append({"op": "create-pr", "project": proj, "repo": r["name"], "body": body, "id": new_id})
        return done(_pr_view(pr), save=True)
    mm = re.match(r"^git/(?:repositories/([^/]+)/)?pullrequests/(\d+)$", rest)
    if mm:
        pr = next((x for x in prs if x["pullRequestId"] == int(mm.group(2))), None)
        if not pr:
            raise RuntimeError(f"ADO -> HTTP 404: no pull request {mm.group(2)}")
        if method == "GET":
            return done(_pr_view(pr))
        if method == "PATCH":
            pr.update(body)
            writes.append({"op": "update-pr", "id": pr["pullRequestId"], "body": body})
            return done(_pr_view(pr), save=True)
    mm = re.match(r"^git/repositories/([^/]+)/pullrequests/(\d+)/workitems$", rest)
    if mm and method == "GET":
        pr = next(x for x in prs if x["pullRequestId"] == int(mm.group(2)))
        return done({"value": [{"id": str(i)} for i in pr.get("workItems", [])]})
    mm = re.match(r"^git/repositories/([^/]+)/pullrequestquery$", rest)
    if mm and method == "POST":
        typ, sha = body["queries"][0]["type"], body["queries"][0]["items"][0]
        field = {"commit": "commits", "lastMergeCommit": "lastMergeCommit"}[typ]  # as ADO: two separate questions
        hits = [_pr_view(x) for x in prs if sha in (x.get(field) or [])
                or (field == "lastMergeCommit" and (x.get(field) or {}).get("commitId") == sha)]
        return done({"results": [{sha: hits}]})

    # -- work items
    if rest == "wit/workitemsbatch" and method == "POST":
        out = []
        for i in body["ids"]:
            it = items.get(str(i))
            if it:
                w = {"id": int(i), "rev": it.get("rev", 1), "fields": it.get("fields", {})}
                if body.get("$expand") == "relations":
                    w["relations"] = it.get("relations", [])
                out.append(w)
        return done({"value": out})
    mm = re.match(r"^wit/workitems/(\d+)$", rest)
    if mm and method == "PATCH":
        it = items[mm.group(1)]
        for op in body:
            if op["op"] == "test" and op["path"] == "/rev" and op["value"] != it.get("rev", 1):
                raise RuntimeError("ADO PATCH -> HTTP 412: rev mismatch")
        for op in body:
            if op["path"] == "/relations/-" and op["op"] == "add":
                it.setdefault("relations", []).append(op["value"])
                link = op["value"]["url"]
                pid = int(link.rsplit("%2F", 1)[1])
                pr = next((x for x in prs if x["pullRequestId"] == pid), None)
                if pr is not None and int(mm.group(1)) not in pr.setdefault("workItems", []):
                    pr["workItems"].append(int(mm.group(1)))
            elif op["op"] == "remove" and op["path"].startswith("/relations/"):
                rel = it["relations"].pop(int(op["path"].rsplit("/", 1)[1]))
                pid = int(rel["url"].rsplit("%2F", 1)[1])
                pr = next((x for x in prs if x["pullRequestId"] == pid), None)
                if pr is not None and int(mm.group(1)) in pr.get("workItems", []):
                    pr["workItems"].remove(int(mm.group(1)))
            elif op["op"] == "add" and op["path"].startswith("/fields/"):
                it.setdefault("fields", {})[op["path"][len("/fields/"):]] = op["value"]
        it["rev"] = it.get("rev", 1) + 1
        writes.append({"op": "patch-item", "id": int(mm.group(1)), "body": body})
        return done({"id": int(mm.group(1)), "rev": it["rev"]}, save=True)
    mm = re.match(r"^wit/workitems/\$(.+)$", rest)
    if mm and method == "POST":
        new_id = max([int(k) for k in items] + [9000]) + 1
        fields = {"System.WorkItemType": mm.group(1), "System.TeamProject": proj}
        rels = []
        for op in body:
            if op["path"].startswith("/fields/"):
                fields[op["path"][len("/fields/"):]] = op["value"]
            elif op["path"] == "/relations/-":
                rels.append(op["value"])
        items[str(new_id)] = {"rev": 1, "fields": fields, "relations": rels}
        writes.append({"op": "create-item", "type": mm.group(1), "id": new_id, "fields": fields})
        return done({"id": new_id, "rev": 1, "fields": fields}, save=True)
    if rest == "wit/wiql" and method == "POST":
        query = body["query"]
        typ = re.search(r"\[System\.WorkItemType\]\s*=\s*'([^']+)'", query)
        title = re.search(r"\[System\.Title\]\s*(?:=|CONTAINS)\s*'([^']+)'", query)
        hits = [int(k) for k, it in items.items()
                if (not typ or it["fields"].get("System.WorkItemType") == typ.group(1))
                and (not title or title.group(1).lower() in it["fields"].get("System.Title", "").lower())
                and it["fields"].get("System.TeamProject", proj).lower() == proj.lower()]
        return done({"workItems": [{"id": i} for i in sorted(hits)]})

    # -- wiki
    if rest == "wiki/wikis" and method == "GET":
        return done({"value": world.get("wikis", {}).get(proj, [])})
    mm = re.match(r"^wiki/wikis/([^/]+)/pages$", rest)
    if mm:
        key = f"{proj}/{mm.group(1)}/{q.get('path', '')}"
        pages = world.setdefault("pages", {})
        if method == "GET":
            page = pages.get(key)
            if not page:
                return None, {}
            return done({"path": q.get("path"), "content": page["content"]}, {"ETag": page["etag"]})
        if method == "PUT":
            page = pages.get(key)
            if page and headers.get("If-Match") != page["etag"]:
                raise RuntimeError("ADO PUT -> HTTP 412: the page changed (etag)")
            if not page and headers.get("If-Match"):
                raise RuntimeError("ADO PUT -> HTTP 404: no such page")
            n = int(page["etag"].strip('"')) + 1 if page else 1
            pages[key] = {"content": body["content"], "etag": f'"{n}"'}
            from devopslib import wiki_git_path
            git_path = wiki_git_path(q["path"]) + ".md"
            writes.append({"op": "put-page", "project": proj, "wiki": mm.group(1), "path": q["path"]})
            return done({"path": q["path"], "gitItemPath": git_path,
                         "remoteUrl": f"https://dev.azure.com/org/{proj}/_wiki/wikis/{mm.group(1)}?pagePath={urllib.parse.quote(q['path'])}"},
                        {"ETag": pages[key]["etag"]}, save=True)
    raise RuntimeError(f"fake ADO: {method} {rest} is not served")
