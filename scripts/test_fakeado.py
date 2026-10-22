"""Self-check for the offline ADO stand-in (fakeado.py) driving the real commands.

    python scripts/test_fakeado.py      (temp folders only)
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

WORLD = {
    "currentIteration": "Proj\\2026\\Sprint 20",
    "items": {
        "500": {"rev": 4, "fields": {"System.WorkItemType": "Change Request", "System.TeamProject": "Proj",
                                     "System.Title": "Export rounds totals", "System.State": "Active",
                                     "System.Description": "<div>FR1: totals are rounded to whole rand.</div>"},
                "relations": [{"rel": "System.LinkTypes.Related", "url": "https://x/_apis/wit/workItems/501"}]},
        "502": {"rev": 1, "fields": {"System.WorkItemType": "User Story", "System.TeamProject": "Proj",
                                     "System.Title": "Show cents on the export", "System.State": "New"}},
        "501": {"rev": 7, "fields": {"System.WorkItemType": "Bug", "System.TeamProject": "Proj",
                                     "System.Title": "Export drops cents", "System.State": "New",
                                     "Custom.BoardColumnTitle": "New", "Microsoft.VSTS.Common.Priority": 1,
                                     "Microsoft.VSTS.Common.Severity": "2 - High",
                                     "Microsoft.VSTS.Scheduling.StoryPoints": 3,
                                     "Microsoft.VSTS.Scheduling.TargetDate": "2026-10-20T00:00:00Z",
                                     "System.CreatedDate": "2026-09-01T08:00:00Z",
                                     "Microsoft.VSTS.TCM.ReproSteps": "<div>Export shows 12 not 12.40</div>"},
                "relations": [{"rel": "System.LinkTypes.Related", "url": "https://x/_apis/wit/workItems/500"}]},
    },
}


def child(wid, typ, title, state="New", tags="1.1.0", rels=(), **fields):
    """A work item under feature 600 for the next-item scenario."""
    f = {"System.WorkItemType": typ, "System.TeamProject": "Proj", "System.Title": title, "System.State": state,
         "System.Tags": tags, **fields}
    rel = [{"rel": "System.LinkTypes.Hierarchy-Reverse", "url": "https://x/_apis/wit/workItems/600"}, *rels]
    return str(wid), {"rev": 1, "fields": f, "relations": rel}


P, S, SP = "Microsoft.VSTS.Common.Priority", "Microsoft.VSTS.Common.Severity", "Microsoft.VSTS.Scheduling.StoryPoints"
FEATURE = dict([
    ("600", {"rev": 1, "fields": {"System.WorkItemType": "Feature", "System.TeamProject": "Proj",
                                  "System.Title": "Invoice export v2", "System.State": "Active", "System.Tags": "1.1.0"}}),
    child(601, "Bug", "Totals lose cents", **{P: 2, S: "2 - High"}),
    child(602, "Bug", "Export crashes on empty invoice", "Active", **{P: 1, S: "1 - Critical", "System.AssignedTo":
          {"displayName": "Ann", "uniqueName": "ann@x.co"}, "Custom.BoardColumnTitle": "Dev In Progress"}),
    child(603, "User Story", "Export in CSV", **{P: 1, SP: 8, "System.AssignedTo": {"displayName": "Bob", "uniqueName": "bob@x.co"}}),
    child(604, "User Story", "Export in PDF", tags="1.0.0", **{P: 1}),
    child(605, "User Story", "CSV column picker", rels=[{"rel": "System.LinkTypes.Dependency-Reverse",
          "url": "https://x/_apis/wit/workItems/603", "attributes": {"name": "Predecessor"}}], **{P: 2, SP: 2}),
    child(606, "Change Request", "Show currency symbol", **{P: 2, "System.Description":
          "<div>This depends on ADO 601 being fixed first, since both change the totals.</div>"}),
    child(607, "Bug", "Old rounding bug", "Resolved", **{P: 1, S: "1 - Critical"}),
    child(608, "Bug", "Typo in header", **{P: 3, S: "3 - Medium", SP: 1, "Microsoft.VSTS.CMMI.Blocked": "Yes"}),
])


def run(root, script, *args, check=True):
    r = subprocess.run([PY, str(HERE / script), *args], cwd=str(root), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{script} {args} -> {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        (root / ".claude" / "sdd.json").write_text(json.dumps(
            {"specRoot": "docs/spec", "ado": {"org": "Org", "projects": ["Proj"]}}))
        world = root / "world.json"
        world.write_text(json.dumps({**WORLD, "items": {**WORLD["items"], **FEATURE}}))
        os.environ["SDD_FAKE_ADO"] = str(world)
        cfg = root / "gitconfig"
        cfg.write_text("[user]\n\temail = dev@x.co\n\tname = Dev\n")
        os.environ["GIT_CONFIG_GLOBAL"] = str(cfg)

        # an index built before the planning fields existed gets their columns in place
        idx = root / "docs" / "spec" / ".index"
        idx.mkdir(parents=True)
        import sqlite3
        old = sqlite3.connect(idx / "spec.db")
        old.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, project TEXT, type TEXT, title TEXT, state TEXT, "
                    "area TEXT, iteration TEXT, tags TEXT, assigned TEXT, parent INTEGER, rev INTEGER, hash TEXT, "
                    "fhash TEXT, path TEXT, removed INTEGER DEFAULT 0, missing INTEGER DEFAULT 0, changed TEXT, "
                    "synced_at TEXT, body TEXT, other TEXT)")
        old.commit()
        old.close()

        run(root, "spec.py", "sync", "--id", "501", "--no-embed")
        req = next((root / "docs" / "spec").rglob("501-*/requirements.md")).read_text(encoding="utf-8")
        assert "Export drops cents" in req and "12.40" in req, req
        assert any((root / "docs" / "spec").rglob("500-*/requirements.md")), "the linked CR was not mirrored"
        show = json.loads(run(root, "spec.py", "query", "show", "--id", "501", "--json").stdout)
        assert show and "Bug" in json.dumps(show), show
        row = show[0]
        assert (row["board"], row["priority"], row["severity"], row["effort"]) == ("New", 1, "2 - High", 3), row
        assert row["target"].startswith("2026-10-20") and row["created"].startswith("2026-09-01"), row
        assert row["assigned_email"] == "" and row["blocked"] == "", row
        for cell in ("| Board column | New |", "| Priority | 1 |", "| Severity | 2 - High |", "| Effort | 3 |"):
            assert cell in req, (cell, req)
        assert "| Blocked |" not in req                                   # absent fields stay out of the table

        out = run(root, "spec.py", "claim", "--id", "501").stdout
        assert "claimed" in out, out
        w = json.loads(world.read_text())
        f = w["items"]["501"]["fields"]
        assert f["System.AssignedTo"] == "dev@x.co" and f["System.State"] == "Active"
        assert f["Custom.BoardColumnTitle"] == "Dev In Progress" and w["items"]["501"]["rev"] == 8
        assert w["writes"][0]["ops"][0] == {"op": "test", "path": "/rev", "value": 7}
        row = json.loads(run(root, "spec.py", "query", "show", "--id", "501", "--json").stdout)[0]
        assert (row["board"], row["state"], row["assigned_email"]) == ("Dev In Progress", "Active", "dev@x.co"), row

        w["items"]["500"]["fields"]["System.AssignedTo"] = {"displayName": "Ann", "uniqueName": "ann@x.co"}
        world.write_text(json.dumps(w))
        r = run(root, "spec.py", "claim", "--id", "500", check=False)
        assert r.returncode == 3 and "Ann" in r.stdout, r.stdout

        run(root, "spec.py", "sprint", "--id", "501")
        assert json.loads(world.read_text())["items"]["501"]["fields"]["System.IterationPath"] == "Proj\\2026\\Sprint 20"

        (root / "rc.html").write_text("<div>The export cut the cents.</div>")
        (root / "res.html").write_text("<div>See #500 for the rule.</div>")
        r = run(root, "spec.py", "handover", "--id", "501", "--root-cause-details-file", "rc.html",
                "--resolution-file", "res.html", check=False)
        assert r.returncode == 3 and "ADO 500" in r.stdout, r.stdout
        (root / "res.html").write_text("<div>The export keeps the cents now.</div>")
        run(root, "spec.py", "handover", "--id", "501", "--root-cause-details-file", "rc.html",
            "--resolution-file", "res.html")
        f = json.loads(world.read_text())["items"]["501"]["fields"]
        assert f["System.State"] == "Resolved" and f["Custom.BoardColumnTitle"] == "Dev Completed"

        (root / "c.html").write_text("<div>PR is up. Check the export shows 12.40.</div>")
        run(root, "spec.py", "comment", "--id", "501", "--file", "c.html")
        kinds = [x["method"] for x in json.loads(world.read_text()).get("writes", [])]
        assert kinds == ["PATCH", "PATCH", "PATCH", "COMMENT"], kinds

        # the spec flow's path: asked at the start; no stage after Specify runs until it is chosen
        run(root, "env.py", "progress", "--id", "502", "--flow", "spec", "--phase", "Specify", "--status", "done",
            "--passed", "Claimed")
        r = run(root, "env.py", "can", "--id", "502", "--op", "phase", "--flow", "spec", "--phase", "Open Questions",
                check=False)
        assert r.returncode == 3 and "no path chosen" in r.stdout, r.stdout
        r = run(root, "env.py", "path", "--id", "502", "--set", "short", check=False)
        assert r.returncode != 0 and "--confirmed" in r.stderr, r.stderr
        run(root, "env.py", "path", "--id", "502", "--set", "short", "--confirmed", "short path please")
        r = run(root, "env.py", "can", "--id", "502", "--op", "phase", "--flow", "spec", "--phase", "Open Questions")
        assert "allowed" in r.stdout and "modes/open-questions.md" in r.stdout.replace("\\", "/"), r.stdout
        rec = json.loads(next((root / ".claude" / "worktrees").glob("502-*/workitem.json")).read_text())
        assert rec["path"] == "short" and rec["pathChosen"]["confirmed"] == "short path please"
        rec["stages"]["Decompose"] = {"at": "t", "status": "worked"}
        next((root / ".claude" / "worktrees").glob("502-*/workitem.json")).write_text(json.dumps(rec))
        r = run(root, "env.py", "path", "--id", "502", "--set", "short", "--confirmed", "again", check=False)
        assert r.returncode != 0 and "too late" in r.stderr, r.stderr
        run(root, "env.py", "path", "--id", "502", "--set", "full", "--confirmed", "back to full")
        r = run(root, "env.py", "path", "--id", "502", "--set", "design", "--confirmed", "design it", check=False)
        assert r.returncode != 0 and "for Feature and Epic only; 502 is a User Story" in r.stderr, r.stderr
        assert json.loads(run(root, "env.py", "type", "--id", "600").stdout)["ask"] == ["next", "design", "full", "short"]
        assert "ask" not in json.loads(run(root, "env.py", "type", "--id", "603").stdout)    # a story goes straight on
        # a feature on the design-only path: no claim, the flow ends after Design, done needs no close-out in ADO
        can = lambda wid, phase, **kw: run(root, "env.py", "can", "--id", wid, "--op", "phase", "--flow", "spec", "--phase", phase, **kw)
        run(root, "env.py", "progress", "--id", "600", "--flow", "spec", "--phase", "Specify", "--status", "done")
        r = can("600", "Requirements", check=False)
        assert r.returncode == 3 and "(full / short / design)" in r.stdout and "needs 'Claimed'" in r.stdout, r.stdout
        run(root, "env.py", "path", "--id", "600", "--set", "design", "--confirmed", "design it, the stories come later")
        assert "allowed" in can("600", "Requirements").stdout                              # no claim needed
        run(root, "env.py", "progress", "--id", "600", "--flow", "spec", "--phase", "Requirements", "--status", "done",
            "--passed", "Requirements agreed")
        assert "allowed" in can("600", "Design").stdout
        run(root, "env.py", "progress", "--id", "600", "--flow", "spec", "--phase", "Design", "--status", "done")
        rec = json.loads(next((root / ".claude" / "worktrees").glob("600-*/workitem.json")).read_text())
        assert {k: v["status"] for k, v in rec["stages"].items() if k in ("Decompose", "Implement", "Verify", "Review")} == \
            dict.fromkeys(("Decompose", "Implement", "Verify", "Review"), "skipped"), rec["stages"]
        assert rec["stages"]["Review"]["confirmed"] == "design path: design it, the stories come later"
        r = can("600", "Decompose", check=False)
        assert r.returncode == 3 and "the flow ends after Design" in r.stdout and "/sdd next 600" in r.stdout, r.stdout
        r = run(root, "env.py", "path", "--id", "600", "--set", "full", "--confirmed", "build it after all", check=False)
        assert r.returncode != 0 and "too late to leave the design path" in r.stderr, r.stderr
        r = run(root, "env.py", "can", "--id", "600", "--op", "done", check=False)
        assert r.returncode == 0 and "allowed" in r.stdout, r.stdout                         # ADO 600 stays Active: fine
        # the next item under feature 600 for version 1.1.0
        run(root, "spec.py", "sync", "--id", "600", "--no-embed")
        mpath = root / "docs" / "spec" / ".index" / "metrics.json"
        m = json.loads(mpath.read_text())
        it = m["items"]
        assert [b["id"] for b in it["605"]["blockers"]] == [603] and it["603"]["blocking"] == [605]
        assert [b["id"] for b in it["606"]["blockers"]] == [601] and it["601"]["blocking"] == [606]
        assert it["605"]["ancestors"] == [{"id": 600, "type": "Feature", "title": "Invoice export v2"}]
        assert it["600"]["children"] == {"total": 8, "open": 7, "done": 1, "inProgress": 1, "bugsOpen": 3}, it["600"]["children"]
        assert it["602"]["inProgress"] and it["607"]["done"] and it["601"]["versions"] == ["1.1.0"]
        assert it["603"]["complexity"] == 5 and it["601"]["complexity"] is None
        assert {c["kind"] for c in m["changes"]} == {"new"} and len(m["changes"]) == 9
        nxt = lambda: json.loads(run(root, "spec.py", "next", "--scope", "600", "--version", "1.1.0", "--json").stdout)
        res = nxt()
        why = {r["id"]: r["why"] for r in res["unavailable"]}
        assert set(why) == {602, 604, 607}, why
        assert "Ann is working on it" in why[602] and "tagged 1.0.0" in why[604] and why[607] == "Resolved"
        assert {r["id"]: r["ask"] for r in res["needs"]} == {601: ["complexity"], 606: ["blocked", "complexity"]}, res["needs"]
        (b605,) = res["blocked"]                                    # a predecessor not done blocks: no judgement asked
        assert b605["id"] == 605 and b605["reason"] == "waits on ADO 603 (New): its predecessor", b605
        ev = next(r for r in res["needs"] if r["id"] == 606)["evidence"]
        assert ev[0]["id"] == 601 and ev[0]["kind"] == "named in the text" and "depends on ADO 601" in ev[0]["text"]
        assert [r["id"] for r in res["ranked"]] == [608, 603]       # bugs first; ADO's Blocked=Yes on 608 ignored
        assert "--take" in res["ranked"][1]["note"]                # on Bob's name, not started
        assert res["ranked"][1]["unblocks"] == [605]
        judge = lambda *a: run(root, "spec.py", "next-judge", "--scope", "600", *a)
        judge("--id", "601", "--complexity", "3", "--reason", "one formatter and its tests")
        judge("--id", "606", "--blocked", "no", "--complexity", "2", "--reason",
              "the symbol is added after formatting; 601's fix does not change that path")
        res = nxt()
        assert [r["id"] for r in res["ranked"]] == [601, 608, 603, 606], res["ranked"]
        dev = {r["id"]: r["devPriority"] for r in res["ranked"]}
        assert dev == {601: 63.3, 608: 26.7, 603: 85.0, 606: 53.3}, dev   # 50/30/20, complex first
        assert [r["id"] for r in res["blocked"]] == [605] and not res["needs"]
        text = run(root, "spec.py", "next", "--scope", "600", "--version", "1.1.0").stdout
        assert "Ready, best first" in text and "Blocked:" in text and "Ann is working on it" in text, text
        # 603 is done: 605 is free
        w = json.loads(world.read_text())
        w["items"]["603"]["fields"]["System.State"] = "Closed"
        w["items"]["603"]["rev"] += 1                                  # ADO bumps rev on every change
        world.write_text(json.dumps(w))
        run(root, "spec.py", "sync", "--id", "600", "--no-embed")
        res = nxt()
        assert 605 in [r["id"] for r in res["ranked"]] and not res["blocked"], res
        m = json.loads(mpath.read_text())
        ch = {c["id"]: c for c in m["changes"]}
        assert set(ch) == {603} and ch[603]["kind"] == "incidental", m["changes"]   # only what moved
        assert ch[603]["diff"] == {"state": ["New", "Closed"]}, ch[603]
        assert m["items"]["605"]["blockers"] == [] and m["items"]["603"]["lastChange"]["diff"]["state"][1] == "Closed"
        assert m["items"]["601"]["lastChange"]["kind"] == "new"                    # carried from the sync before
        # a requirement change: material, with what it likely affects
        w = json.loads(world.read_text())
        w["items"]["606"]["fields"]["System.Title"] = "Show the currency symbol on totals"
        w["items"]["606"]["rev"] += 1
        world.write_text(json.dumps(w))
        run(root, "spec.py", "sync", "--id", "600", "--no-embed")
        c606 = next(c for c in json.loads(mpath.read_text())["changes"] if c["id"] == 606)
        assert c606["kind"] == "material" and c606["fields"] == ["Title"], c606
        assert c606["diff"]["title"] == ["Show currency symbol", "Show the currency symbol on totals"]
        assert 600 in [x["id"] for x in c606["affects"]], c606["affects"]           # its feature, by link
        before = json.loads(mpath.read_text())
        run(root, "spec.py", "metrics")
        assert json.loads(mpath.read_text())["changes"] == before["changes"]       # a rebuild keeps them
        run(root, "spec.py", "sync", "--id", "600", "--no-embed")                  # nothing new in ADO
        after = json.loads(mpath.read_text())
        assert after["changes"] == before["changes"] and after["changesAt"] == before["changesAt"]
        assert after["sync"]["at"] >= before["sync"]["at"]
        # taking an item: never someone's work in progress; one on another name only with --take
        w = json.loads(world.read_text())
        w["items"]["603"]["fields"]["System.State"] = "New"
        world.write_text(json.dumps(w))
        r = run(root, "spec.py", "claim", "--id", "603", check=False)
        assert r.returncode == 3 and "--take" in r.stdout, r.stdout
        run(root, "spec.py", "claim", "--id", "603", "--take")
        f = json.loads(world.read_text())["items"]["603"]["fields"]
        assert f["System.AssignedTo"] == "dev@x.co" and f["Custom.BoardColumnTitle"] == "Dev In Progress"
        r = run(root, "spec.py", "claim", "--id", "602", "--take", check=False)
        assert r.returncode == 3 and "working on it" in r.stdout, r.stdout

        # next syncs its scope first; --no-sync ranks from the last sync; a failed sync stops it
        w = json.loads(world.read_text())
        w["items"]["608"]["fields"][P] = 1
        w["items"]["608"]["rev"] += 1
        world.write_text(json.dumps(w))
        prio = lambda *extra: {r["id"]: r["priority"] for r in json.loads(run(
            root, "spec.py", "next", "--scope", "600", "--version", "1.1.0", "--json", *extra).stdout)["ranked"]}
        assert prio("--no-sync")[608] == 3                       # the mirror still has the old priority
        assert prio()[608] == 1                                  # the default synced first (and --json stays clean)
        os.environ["SDD_FAKE_ADO"] = str(root / "no-such-world.json")
        r = run(root, "spec.py", "next", "--scope", "600", "--version", "1.1.0", check=False)
        assert r.returncode != 0 and "Ready" not in r.stdout, r.stdout
        os.environ["SDD_FAKE_ADO"] = str(world)

        # an Ai Agent Request: the report names its items and the work left; route sends it once
        w = json.loads(world.read_text())
        w["items"]["700"] = {"rev": 1, "fields": {
            "System.WorkItemType": "Ai Agent Request", "System.TeamProject": "Proj", "System.State": "New",
            "System.Title": "Hand-over: export rounding", "System.AreaPath": "Proj\\Export",
            "System.IterationPath": "Proj\\2026\\Sprint 20",
            "System.Description": "<div>Fixed the rounding for Bug 601. The PDF part of ADO 604 is done.</div>"
                                  "<div>Work still to be done: the PDF export drops the cents.</div>"},
            "comments": [{"text": "<div>Tests for 9999 are not yet written: ADO 9999.</div>",
                          "createdBy": {"displayName": "Agent A"}}]}
        world.write_text(json.dumps(w))
        assert json.loads(run(root, "env.py", "type", "--id", "700").stdout)["flow"] == "request"
        r = run(root, "spec.py", "request", "--id", "700", check=False)
        assert r.returncode != 0 and "spec.py sync --id 700" in r.stderr, r.stderr      # mirror it first
        run(root, "spec.py", "sync", "--id", "700", "--no-embed")
        rep = json.loads(run(root, "spec.py", "request", "--id", "700", "--json").stdout)
        refs = {x["id"]: x for x in rep["references"]}
        assert list(refs) == [601, 604, 9999], refs
        assert refs[601]["fits"] == ["bug"] and refs[601]["open"] and refs[604]["fits"] == ["spec"]
        assert not refs[9999]["found"]
        assert rep["workLeft"] == ["Work still to be done: the PDF export drops the cents.",
                                   "Tests for 9999 are not yet written: ADO 9999."], rep["workLeft"]
        md = (root / rep["request"]).read_text(encoding="utf-8")
        assert "Fixed the rounding" in md and "Agent A" in md, md
        r = run(root, "spec.py", "route", "--id", "700", "--flow", "spec", "--to", "601", check=False)
        assert r.returncode == 3 and "runs the bug flow" in r.stdout, r.stdout
        r = run(root, "spec.py", "route", "--id", "700", "--flow", "spec", "--to", "607", check=False)
        assert r.returncode == 3 and "not open" in r.stdout, r.stdout
        (root / "air.html").write_text("<div>The PDF export drops the cents. See #601.</div>")
        r = run(root, "spec.py", "route", "--id", "700", "--flow", "bug", "--title", "PDF export drops the cents",
                "--text-file", "air.html", check=False)
        assert r.returncode == 3 and "ADO 601" in r.stdout, r.stdout                   # no mention, ever
        (root / "air.html").write_text("<div>The PDF export drops the cents. See ADO 601.</div>")
        run(root, "spec.py", "route", "--id", "700", "--flow", "bug", "--title", "PDF export drops the cents",
            "--text-file", "air.html", "--parent", "600", "--related", "601")
        w = json.loads(world.read_text())
        new = max(int(k) for k in w["items"])
        f = w["items"][str(new)]["fields"]
        assert f["System.WorkItemType"] == "Bug" and "ADO 601" in f["Microsoft.VSTS.TCM.ReproSteps"], f
        assert f["System.AreaPath"] == "Proj\\Export" and f["System.IterationPath"] == "Proj\\2026\\Sprint 20"
        rels = {(x["rel"].split(".")[-1], x["url"].split("/")[-1]) for x in w["items"][str(new)]["relations"]}
        assert rels == {("Related", "700"), ("Hierarchy-Reverse", "600"), ("Related", "601")}, rels
        assert {k: v for k, v in w["writes"][-1].items() if k != "commentId"} == {"method": "COMMENT", "id": 700, "text": w["writes"][-1]["text"]}
        assert f"ADO {new} (Bug" in w["writes"][-1]["text"]
        r = run(root, "spec.py", "route", "--id", "700", "--flow", "bug", "--to", "601", check=False)
        assert r.returncode == 3 and f"ADO {new}" in r.stdout, r.stdout                # once only
        assert f"/sdd bug {new}" in run(root, "spec.py", "request", "--id", "700").stdout
        # an open item the work belongs to: linked to the request, nothing created
        w["items"]["710"] = dict(w["items"]["700"], rev=1, comments=[])
        world.write_text(json.dumps(w))
        run(root, "spec.py", "sync", "--id", "710", "--no-embed")
        run(root, "spec.py", "route", "--id", "710", "--flow", "bug", "--to", "601")
        w = json.loads(world.read_text())
        assert max(int(k) for k in w["items"]) == 710 and w["items"][str(new)]["fields"]["System.WorkItemType"] == "Bug"
        assert w["writes"][-2]["method"] == "PATCH" and w["writes"][-2]["id"] == 601
        assert w["writes"][-2]["ops"][0]["op"] == "test"                                # rev-tested link
        assert any(x["url"].endswith("/710") for x in w["items"]["601"]["relations"])

        view = json.loads(run(root, "env.py", "view", "--json", "--id", "502").stdout)
        assert {i["id"]: i.get("path") for i in view["items"]}[502] == "full", view["items"]
        assert view["flows"]["spec"]["paths"]["short"]["label"].startswith("Short")   # the view reads the paths
        # a story is never offered the design-only path
        run(root, "env.py", "progress", "--id", "604", "--flow", "spec", "--phase", "Specify", "--status", "done", "--passed", "Claimed")
        r = run(root, "env.py", "can", "--id", "604", "--op", "phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert r.returncode == 3 and "(full / short)" in r.stdout, r.stdout
    tags_like_ado()
    progress_flow()
    feature_flow()
    print("ok")


def feature_flow():
    """A feature built as one piece of work: the items under it, the user's pick, the refusals; and a story under an
    epic whose design is agreed: the design above it, and the questions it already answered."""
    def under(wid, parent, typ, title, state="New", **fields):
        f = {"System.WorkItemType": typ, "System.TeamProject": "Proj", "System.Title": title, "System.State": state, **fields}
        rel = [{"rel": "System.LinkTypes.Hierarchy-Reverse", "url": f"https://x/_apis/wit/workItems/{parent}"}] if parent else []
        return str(wid), {"rev": 1, "fields": f, "relations": rel}
    bob = {"displayName": "Bob", "uniqueName": "bob@x.co"}
    items = dict([
        under(890, None, "Epic", "Billing"),
        under(900, 890, "Feature", "Invoice export v3", "Active"),
        under(901, 900, "User Story", "CSV export"),
        under(902, 900, "User Story", "PDF export", "Active", **{"System.AssignedTo": bob, "Custom.BoardColumnTitle": "Dev In Progress"}),
        under(903, 900, "User Story", "Old export", "Closed"),
        under(904, 901, "Bug", "CSV loses cents"),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        (root / ".claude" / "sdd.json").write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "Org", "projects": ["Proj"]}}))
        world = root / "world.json"
        world.write_text(json.dumps({"items": items}))
        os.environ["SDD_FAKE_ADO"] = str(world)
        cfg = root / "gitconfig"
        cfg.write_text("[user]\n\temail = dev@x.co\n\tname = Dev\n")
        os.environ["GIT_CONFIG_GLOBAL"] = str(cfg)
        r = run(root, "env.py", "members", "--id", "900", check=False)
        assert r.returncode != 0 and "spec.py sync --id 900" in r.stderr, r.stderr          # nothing synced yet
        run(root, "spec.py", "sync", "--id", "890", "--no-embed")
        r = run(root, "env.py", "members", "--id", "901", check=False)
        assert r.returncode != 0 and "for a Feature or Epic" in r.stderr, r.stderr
        out = run(root, "env.py", "members", "--id", "900").stdout
        assert "ADO 902 User Story: PDF export [Active] · Bob is working on it" in out and "ADO 903 User Story: Old export [Closed] · done" in out, out
        assert "Free to build: 901, 904." in out, out
        # built as one piece of work: no stage after Specify until the user picked the items it covers
        run(root, "env.py", "progress", "--id", "900", "--flow", "spec", "--phase", "Specify", "--status", "done")
        run(root, "env.py", "path", "--id", "900", "--set", "full", "--confirmed", "build the whole feature")
        can = lambda *a, **kw: run(root, "env.py", "can", "--id", "900", "--op", *a, **kw)
        r = can("phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert r.returncode == 3 and "record the items under it this build covers" in r.stdout, r.stdout
        r = run(root, "env.py", "members", "--id", "900", "--set", "901", check=False)
        assert r.returncode != 0 and "--confirmed" in r.stderr
        r = run(root, "env.py", "members", "--id", "900", "--set", "901,902", "--confirmed", "both", check=False)
        assert r.returncode != 0 and "someone else is working on ADO 902 (Bob)" in r.stderr, r.stderr
        r = run(root, "env.py", "members", "--id", "900", "--set", "901,999", "--confirmed", "x", check=False)
        assert r.returncode != 0 and "not work under 900: 999" in r.stderr, r.stderr
        out = run(root, "env.py", "members", "--id", "900", "--set", "904,901", "--confirmed", "the CSV story and its bug").stdout
        assert "spec.py claim --id 900 --id 901 --id 904" in out, out
        rec = json.loads(next((root / ".claude" / "worktrees").glob("900-*/workitem.json")).read_text())
        assert rec["members"] == [901, 904] and rec["membersChosen"]["confirmed"] == "the CSV story and its bug"
        r = can("phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert "record the items" not in r.stdout and "needs 'Claimed'" in r.stdout, r.stdout     # the claim is next
        assert "* ADO 901" in run(root, "env.py", "members", "--id", "900").stdout
        r = can("done", check=False)
        assert r.returncode == 3 and "ADO 901, covered by this build, is still New" in r.stdout, r.stdout
        # Decompose cannot pass "Tasks written" while a picked item has no task naming it
        prog = lambda *a, **kw: run(root, "env.py", "progress", "--id", "900", "--flow", "spec", *a, **kw)
        for st in ("Requirements", "Design"):
            prog("--phase", st, "--status", "skipped", "--confirmed", "test: straight to the task list")
        feat = next((root / "docs" / "spec").glob("890-*/900-*"))
        (feat / "tasks.md").write_text("1. CSV columns (ADO 901)\n")
        r = prog("--phase", "Decompose", "--status", "done", "--passed", "Tasks written", check=False)
        assert r.returncode != 0 and "tasks.md does not name ADO 904" in r.stderr, r.stderr
        (feat / "tasks.md").write_text("1. CSV columns (ADO 901)\n2. Keep the cents (ADO 904)\n")
        prog("--phase", "Decompose", "--status", "done", "--passed", "Tasks written")
        # the epic's design is agreed: the items below start from it, and keep what it already answered
        epic = next((root / "docs" / "spec").glob("890-*"))
        (epic / "design.md").write_text("# Billing design\n")
        (epic / "questions.md").write_text("- [x] Q1: Which currency? (context: all exports) Answer: ZAR\n"
                                           "- [x] Q2 (ADO 901): CSV delimiter? Answer: semicolon\n"
                                           "- [x] Q3 (ADO 902): PDF paper size? Answer: A4\n- [ ] Q4: Open still\n")
        assert json.loads(run(root, "env.py", "upstream", "--id", "901", "--json").stdout) == []      # not agreed yet
        (epic / "design-agreed.json").write_text(json.dumps({"id": 890, "type": "Epic", "at": "2026-10-22T08:00:00Z"}))
        (up,) = json.loads(run(root, "env.py", "upstream", "--id", "901", "--json").stdout)
        assert (up["id"], up["type"]) == (890, "Epic") and up["design"].endswith("design.md"), up
        assert up["answered"] == ["Q1: Which currency? (context: all exports) Answer: ZAR", "Q2 (ADO 901): CSV delimiter? Answer: semicolon"], up
        out = run(root, "env.py", "upstream", "--id", "901").stdout
        assert "Epic ADO 890 Billing: design agreed 2026-10-22" in out and "settled: Q2 (ADO 901)" in out, out
        assert "open: Q4: Open still" in out, out
        r = can("phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert "Epic ADO 890's design is agreed: start from" in r.stdout and "(1 settled question(s) hold for this item" in r.stdout, r.stdout

        # the feature's agreed design goes up to the board: each item's part into its Implementation Plan, the order
        # as predecessor links; a story's flow (anyone's) reads its part back from there
        PLAN = "Custom.ImplementationPlan"
        w = json.loads(world.read_text())
        w["items"]["902"]["fields"][PLAN] = "<div>Bob's own notes</div>"
        world.write_text(json.dumps(w))
        wi = next((root / ".claude" / "worktrees").glob("900-*/workitem.json"))
        rec = json.loads(wi.read_text())
        agreed = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rec["gates"]["Design agreed"] = agreed       # agreed in this workspace, with no design-agreed.json: as if elsewhere
        wi.write_text(json.dumps(rec))
        (feat / "design.md").write_text("# Export design (Epic ADO 890)\n\n## Approach\nOne exporter for all formats.\n")
        (feat / "questions.md").write_text("- [x] Q1: Rounding? Answer: half up\n- [x] Q2: Header row? (ADO 901) Answer: yes\n"
                                           "- [x] Q3: Fonts? (ADO 902) Answer: Arial\n- [ ] Q4: Quote text cells? (ADO 901)\n")
        r = can("phase", "--flow", "spec", "--phase", "Implement", check=False)
        assert "is not on the board yet" in r.stdout and "env.py plan --id 900" in r.stdout, r.stdout
        r = run(root, "env.py", "plan", "--id", "900", check=False)
        assert r.returncode != 0 and 'no "## Work item plan"' in r.stderr, r.stderr
        plan_md = ("\n## Work item plan\n\n### ADO 901 CSV export\n- Starts: the exporter interface ADO 902 builds\n"
                   "- Stops: a CSV file the user downloads\n- In scope: the CSV writer\n- Out of scope: PDF output (ADO 902)\n"
                   "- Out of scope: scheduled exports (not planned)\n- Decision: amounts in cents\n\n"
                   "### ADO 902 PDF export\n- Starts: nothing; it goes first\n- Stops: the exporter interface and PDF output\n"
                   "- In scope: the exporter interface\n- Gives: ADO 901 (the exporter interface)\n")
        (feat / "design.md").write_text((feat / "design.md").read_text() + plan_md.replace("- Stops: a CSV", "- Stop it: a CSV"))
        r = run(root, "env.py", "plan", "--id", "900", check=False)
        assert r.returncode != 0 and "ADO 901's entry has no Stops" in r.stderr, r.stderr
        (feat / "design.md").write_text("# Export design (Epic ADO 890)\n\n## Approach\nOne exporter for all formats.\n" + plan_md)
        out = run(root, "env.py", "plan", "--id", "900").stdout
        assert "field of 3 item(s)" in out and "ADO 903" not in out, out           # itself, 901 and 902; 903 is closed
        assert "ADO 902 before ADO 901 (a predecessor link on ADO 901)" in out, out
        p901 = (feat / "plans" / "901.md").read_text()
        assert "sdd plan: Feature ADO 900 for ADO 901" in p901 and "the CSV writer" in p901 and "PDF output (ADO 902)" in p901, p901
        assert "ADO 902 (its plan gives ADO 901 (the exporter interface))" in p901, p901      # 902's Gives, seen from 901
        assert "the exporter interface and PDF output" not in p901 and "Arial" not in p901, p901     # 902's own part stays off
        assert "Q2: Header row?" in p901 and "Q4: Quote text cells?" in p901 and "Rounding" not in p901, p901
        assert "One exporter for all formats" in (feat / "plans" / "900.md").read_text()      # the feature: the whole design
        assert not json.loads(world.read_text()).get("writes")
        r = run(root, "env.py", "plan", "--id", "900", "--post", check=False)
        assert r.returncode != 0 and "--confirmed" in r.stderr, r.stderr
        out = run(root, "env.py", "plan", "--id", "900", "--post", "--confirmed", "yes, put it on the board").stdout
        assert out.count("plan written") == 3 and "ADO 901: plan written, 1 predecessor link(s) added" in out, out
        w = json.loads(world.read_text())
        f = {k: w["items"][k]["fields"].get(PLAN, "") for k in ("900", "901", "902")}
        assert "One exporter for all formats" in f["900"] and "<h3>In scope</h3>" in f["901"], f
        assert "One exporter" not in f["901"] and f["902"].startswith("<div>Bob's own notes</div>"), f
        assert {"rel": "System.LinkTypes.Dependency-Reverse", "url": "https://dev.azure.com/Org/_apis/wit/workItems/902",
                "attributes": {"comment": "sdd plan of ADO 900"}} in w["items"]["901"]["relations"]
        assert not [x for x in w["writes"] if x["method"] == "COMMENT"]                    # nothing in the discussion
        r = can("phase", "--flow", "spec", "--phase", "Implement", check=False)
        assert "not on the board" not in r.stdout, r.stdout
        n = len(json.loads(world.read_text())["writes"])
        out = run(root, "env.py", "plan", "--id", "900", "--post", "--confirmed", "again").stdout
        assert out.count("plan unchanged") == 3 and len(json.loads(world.read_text())["writes"]) == n, out
        (feat / "design.md").write_text((feat / "design.md").read_text().replace("amounts in cents", "amounts in rands"))
        out = run(root, "env.py", "plan", "--id", "900", "--post", "--confirmed", "post the change").stdout
        assert out.count("plan written") == 2 and "ADO 902: plan unchanged" in out and "link" not in out, out   # 901's part only
        f902 = json.loads(world.read_text())["items"]["902"]["fields"][PLAN]
        assert f902.count("sdd plan: Feature ADO 900") == 1 and "Bob's own notes" in f902, f902
        # story 901, in any workspace: its flow reads the board before Requirements, then starts from its part
        sprog = lambda *a, **kw: run(root, "env.py", "progress", "--id", "901", "--flow", "spec", *a, **kw)
        sprog("--phase", "Specify", "--status", "done")
        story = next((root / "docs" / "spec").glob("890-*/900-*/901-*"))
        (story / "upstream.json").write_text(json.dumps({"fetched": "2026-01-02T00:00:00Z", "plans": []}))  # read long ago
        r = run(root, "env.py", "can", "--id", "901", "--op", "phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert "read the board for a design agreed above 901 first (last read 2026-01-02" in r.stdout, r.stdout
        ups = json.loads(run(root, "env.py", "upstream", "--id", "901", "--json").stdout)
        assert [(u["id"], u["source"]) for u in ups] == [(900, "ado"), (890, "local")], ups
        p = ups[0]["plan"]
        assert p["in"] == ["the CSV writer"] and p["out"] == ["PDF output (ADO 902)", "scheduled exports (not planned)"], p
        assert p["needs"] == ["ADO 902 (its plan gives ADO 901 (the exporter interface))"] and p["decisions"] == ["amounts in rands"], p
        assert ups[0]["answered"] == ["Q2: Header row? (ADO 901) Answer: yes"] and ups[0]["open"] == ["Q4: Quote text cells? (ADO 901)"]
        out = run(root, "env.py", "upstream", "--id", "901", "--cached").stdout
        assert "out of scope: PDF output (ADO 902)" in out and "where the work starts: the exporter interface" in out, out
        r = run(root, "env.py", "can", "--id", "901", "--op", "phase", "--flow", "spec", "--phase", "Requirements", check=False)
        assert "read the board" not in r.stdout and "Feature ADO 900's design is agreed: start from" in r.stdout, r.stdout
        assert "1 settled question(s) hold for this item: do not ask them again; 1 left open for it" in r.stdout, r.stdout
        # bug 904 under 901 has no plan of its own: its story's holds
        (b,) = [u for u in json.loads(run(root, "env.py", "upstream", "--id", "904", "--json").stdout) if u["id"] == 900]
        assert b["for"] == 901 and b["source"] == "ado", b
        # /sdd next reads the order: 901 waits on 902
        run(root, "spec.py", "sync", "--id", "890", "--no-embed")
        m = json.loads((root / "docs" / "spec" / ".index" / "metrics.json").read_text())
        assert [x["id"] for x in m["items"]["901"]["blockers"]] == [902] and m["items"]["902"]["blocking"] == [901], m["items"]["901"]

        # the board around the work: a claim makes the feature and epic above it Active; closing off the last item
        # under a feature resolves it, and the epic above when that was its last
        w = json.loads(world.read_text())
        w["items"]["900"]["fields"]["System.State"] = "New"
        world.write_text(json.dumps(w))
        out = run(root, "spec.py", "claim", "--id", "904").stdout                       # a bug under a story under 900
        assert "900: made active" in out and "890: made active" in out and "901:" not in out, out
        out = run(root, "spec.py", "claim", "--id", "901").stdout
        assert "made active" not in out, out                                             # both are Active by now
        w = json.loads(world.read_text())
        assert w["items"]["890"]["fields"]["System.State"] == "Active" and w["items"]["901"]["fields"]["System.State"] == "Active"
        out = run(root, "spec.py", "handover", "--id", "904").stdout                    # a bug under a story: never the story
        assert "901: resolved" not in out and json.loads(world.read_text())["items"]["901"]["fields"]["System.State"] == "Active", out
        out = run(root, "spec.py", "handover", "--id", "901").stdout
        assert "resolved: its last item" not in out, out                                # 902 is still Active
        w = json.loads(world.read_text())
        w["items"]["902"]["fields"]["System.State"] = "Closed"
        world.write_text(json.dumps(w))
        out = run(root, "spec.py", "handover", "--id", "901", "--dry-run").stdout
        assert "900: would be resolved" in out and "890: would be resolved" in out, out
        assert json.loads(world.read_text())["items"]["900"]["fields"]["System.State"] == "Active"
        out = run(root, "spec.py", "handover", "--id", "901").stdout
        assert "900: resolved: its last item is closed off" in out and "890: resolved" in out, out
        w = json.loads(world.read_text())
        assert w["items"]["900"]["fields"]["System.State"] == w["items"]["890"]["fields"]["System.State"] == "Resolved"


def progress_flow():
    """/sdd-progress's numbers: an epic's features and stories by count, points and criteria, bugs apart, the
    rules per project, and what a partly synced epic says."""
    def under(wid, parent, typ, title, state="New", **fields):
        f = {"System.WorkItemType": typ, "System.TeamProject": "Proj", "System.Title": title, "System.State": state, **fields}
        rel = [{"rel": "System.LinkTypes.Hierarchy-Reverse", "url": f"https://x/_apis/wit/workItems/{parent}"}] if parent else []
        return str(wid), {"rev": 1, "fields": f, "relations": rel}
    AC = "Microsoft.VSTS.Common.AcceptanceCriteria"
    items = dict([
        under(800, None, "Epic", "Invoice platform", "Active"),
        under(810, 800, "Feature", "Export", "Active"),
        under(811, 810, "User Story", "CSV", "Closed", **{SP: 3, AC: "<div><b>Acceptance Criteria 1 - Totals</b><br>Given a total</div>"
              "<div><b>Acceptance Criteria 2 - Cents</b></div><div><strike><b>Acceptance Criteria 3 - Old</b></strike></div>"}),
        under(812, 810, "User Story", "PDF", "Active", **{SP: 5, AC: "<ul><li>Given a, when b, then c</li><li>Given d</li><li>Given e</li></ul>",
              "Custom.BoardColumnTitle": "Dev Completed"}),
        under(813, 810, "User Story", "XLSX", **{"Custom.Stage": "Ready", "Custom.BoardColumnTitle": "New"}),
        under(820, 800, "Feature", "Import"),
        under(830, 800, "User Story", "Audit column", "Closed", **{SP: 2}),
        under(840, 811, "Bug", "CSV drops cents", "Active", **{S: "2 - High"}),
        under(841, 800, "Issue", "Slow export", "Closed"),
        under(850, 810, "User Story", "Dropped idea", "Removed"),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        cfgp = root / ".claude" / "sdd.json"
        cfgp.write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "Org", "projects": ["Proj"]}}))
        world = root / "world.json"
        world.write_text(json.dumps({"items": items}))
        os.environ["SDD_FAKE_ADO"] = str(world)
        run(root, "spec.py", "sync", "--id", "810", "--no-embed")          # a feature: its epic comes as a parent
        data = json.loads(run(root, "spec.py", "progress", "--json").stdout)
        (epic,) = data["tops"]
        assert epic["id"] == 800 and epic["partial"], epic                    # 820, 830, 841 are not synced
        run(root, "spec.py", "sync", "--id", "800", "--no-embed")
        idx = root / "docs" / "spec" / ".index"
        old = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
        (idx / "progress-history.jsonl").write_text(json.dumps({"day": old, "pct": {"800": {"count": 20.0, "points": 50.0, "criteria": 0.0}}}) + "\n")
        data = json.loads(run(root, "spec.py", "progress", "--json").stdout)
        (epic,) = data["tops"]
        assert not epic["partial"]
        m = epic["measures"]
        assert m["count"] == {"total": 5, "done": 2, "active": 1, "todo": 2, "missing": 0}, m["count"]   # 850 removed: out
        assert m["points"] == {"total": 10, "done": 5, "active": 5, "todo": 0, "missing": 2}, m["points"]
        assert m["criteria"] == {"total": 8, "done": 3, "active": 3, "todo": 2, "missing": 3}, m["criteria"]
        assert [k["id"] for k in epic["kids"]] == [810, 820, 830]
        f810 = epic["kids"][0]
        assert [k["id"] for k in f810["kids"]] == [811, 812, 813] and f810["kids"][0]["withdrawn"] == 1
        assert f810["kids"][1]["units"] == {"count": 1, "points": 5.0, "criteria": 3}
        d = epic["defects"]
        assert (d["total"], d["done"], d["active"], d["high"]) == (2, 1, 1, 1), d
        assert f810["defects"]["total"] == 1 and f810["defects"]["items"][0]["id"] == 840
        assert epic["url"] == "https://dev.azure.com/Org/Proj/_workitems/edit/800"
        assert data["trend"]["800"]["count"] == {"delta": 20.0, "since": old}, data["trend"]
        hist = [json.loads(x) for x in (idx / "progress-history.jsonl").read_text().splitlines()]
        assert [h["day"] for h in hist][0] == old and len(hist) == 2
        states = {x["state"]: x["rule"] for x in data["projects"]["Proj"]["states"]}
        assert states == {"Active": "active", "Closed": "done", "New": "todo", "Removed": "ignored"}, states
        assert "40.0% of 5 items done" in run(root, "spec.py", "progress").stdout
        crit = json.loads(run(root, "spec.py", "criteria", "--id", "811", "--json").stdout)       # a story opened on the page
        assert [(c["text"], c["withdrawn"]) for c in crit["criteria"]] == [("Acceptance Criteria 1 - Totals Given a total", False),
            ("Acceptance Criteria 2 - Cents", False), ("Acceptance Criteria 3 - Old", True)], crit
        assert json.loads(run(root, "spec.py", "criteria", "--id", "813", "--json").stdout)["criteria"] == []
        assert "no acceptance criteria in ADO" in run(root, "spec.py", "criteria", "--id", "813").stdout
        r = run(root, "spec.py", "criteria", "--id", "99999", check=False)
        assert r.returncode != 0 and "spec.py sync --id 99999" in r.stderr, r.stderr
        # a project's own rules: Active counts as not started, points first
        r = run(root, "spec.py", "progress-rules", "--project", "Proj", "--done", "Closed", "--todo", "Closed,New", check=False)
        assert r.returncode != 0 and "both done and todo" in r.stderr and "Nothing was written" in r.stderr, r.stderr
        run(root, "spec.py", "progress-rules", "--project", "Proj", "--measure", "points", "--done", "Closed",
            "--todo", "New,Active", "--ignore", "Removed")
        got = json.loads(cfgp.read_text())
        assert got["progress"]["projects"]["Proj"] == {"measure": "points", "done": ["Closed"], "todo": ["New", "Active"], "ignore": ["Removed"]}
        assert got["ado"] == {"org": "Org", "projects": ["Proj"]}                       # nothing else changed
        data = json.loads((idx / "progress.json").read_text())                          # written again at once
        assert data["projects"]["Proj"]["rules"]["measure"] == "points"
        assert data["tops"][0]["measures"]["count"]["todo"] == 3
        # rules on any field: the board column, and a custom field together with the state; the first match wins
        fields = {f["field"]: [v["value"] for v in f["values"]] for f in data["projects"]["Proj"]["fields"]}
        assert list(fields)[:2] == ["System.State", "Custom.BoardColumnTitle"], list(fields)
        assert fields["Custom.BoardColumnTitle"] == ["Dev Completed", "New"], fields     # as often, then by name
        assert fields["Custom.Stage"] == ["Ready"] and "System.Title" not in fields and "System.CreatedDate" not in fields
        rules = [{"field": "Custom.BoardColumnTitle", "values": ["dev completed"], "as": "done"},
                 {"field": "System.State", "values": ["New"], "and": {"Custom.Stage": ["Ready"]}, "as": "active"}]
        r = run(root, "spec.py", "progress-rules", "--project", "Proj", "--done", "", "--todo", "New",
                "--rules-json", json.dumps([{"field": "Custom.Stage", "values": [], "as": "done"}]), check=False)
        assert r.returncode != 0 and "rule 1 needs a field" in r.stderr and "state or rule must count as done" in r.stderr, r.stderr
        run(root, "spec.py", "progress-rules", "--project", "Proj", "--done", "Closed", "--todo", "New", "--ignore", "Removed",
            "--rules-json", json.dumps(rules))
        assert json.loads(cfgp.read_text())["progress"]["projects"]["Proj"]["rules"] == rules
        data = json.loads((idx / "progress.json").read_text())
        assert data["tops"][0]["measures"]["count"] == {"total": 5, "done": 3, "active": 1, "todo": 1, "missing": 0}, data["tops"][0]["measures"]["count"]
        kids = {k["id"]: k["status"] for k in data["tops"][0]["kids"][0]["kids"]}
        assert kids == {811: "done", 812: "done", 813: "active"}, kids
        run(root, "spec.py", "progress-rules", "--project", "Proj", "--reset")
        assert json.loads(cfgp.read_text())["progress"]["projects"] == {}
        cfgp.write_text("{broken")
        r = run(root, "spec.py", "progress-rules", "--project", "Proj", "--done", "Closed", check=False)
        assert r.returncode != 0 and cfgp.read_text() == "{broken"


def tags_like_ado():
    """ADO merges an add into System.Tags and only a replace sets the whole list (Work Items - Update: "Add a tag" and
    "Update a tag"). The fake must do the same, or a test passes a tag removal that ADO would ignore."""
    import fakeado
    with tempfile.TemporaryDirectory() as tmp:
        world = Path(tmp) / "w.json"
        world.write_text(json.dumps({"items": {"1": {"rev": 1, "fields": {"System.Tags": "Tag0; Tag1"}}}}))
        old = os.environ.get(fakeado.ENV)
        os.environ[fakeado.ENV] = str(world)
        try:
            def patch(op, value):
                fakeado.request("PATCH", "https://x/p/_apis/wit/workitems/1", [{"op": op, "path": "/fields/System.Tags", "value": value}])
                return json.loads(world.read_text())["items"]["1"]["fields"]["System.Tags"]
            assert patch("add", "tag1; Tag2") == "Tag0; Tag1; Tag2"        # merged, case aside: nothing taken off
            assert patch("add", "Tag0") == "Tag0; Tag1; Tag2"
            assert patch("replace", "Tag1; Tag2") == "Tag1; Tag2"          # the whole list: Tag0 is gone
            assert patch("replace", "") == ""
        finally:
            if old is None:
                os.environ.pop(fakeado.ENV, None)
            else:
                os.environ[fakeado.ENV] = old


if __name__ == "__main__":
    main()
