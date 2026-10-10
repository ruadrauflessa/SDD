"""Self-check for the offline ADO stand-in (fakeado.py) driving the real commands.

    python scripts/test_fakeado.py      (temp folders only)
"""
import json
import os
import subprocess
import sys
import tempfile
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
        world.write_text(json.dumps(WORLD))
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
        kinds = [x["method"] for x in json.loads(world.read_text())["writes"]]
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
        assert "allowed" in r.stdout and "modes/open-questions.md" in r.stdout, r.stdout
        rec = json.loads(next((root / ".claude" / "worktrees").glob("502-*/workitem.json")).read_text())
        assert rec["path"] == "short" and rec["pathChosen"]["confirmed"] == "short path please"
        rec["stages"]["Decompose"] = {"at": "t", "status": "worked"}
        next((root / ".claude" / "worktrees").glob("502-*/workitem.json")).write_text(json.dumps(rec))
        r = run(root, "env.py", "path", "--id", "502", "--set", "short", "--confirmed", "again", check=False)
        assert r.returncode != 0 and "too late" in r.stderr, r.stderr
        run(root, "env.py", "path", "--id", "502", "--set", "full", "--confirmed", "back to full")
        view = json.loads(run(root, "env.py", "view", "--json", "--id", "502").stdout)
        assert {i["id"]: i.get("path") for i in view["items"]}[502] == "full", view["items"]
        assert view["flows"]["spec"]["paths"]["short"]["label"].startswith("Short")   # the view reads the paths
    print("ok")


if __name__ == "__main__":
    main()
