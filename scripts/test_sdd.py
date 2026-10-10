"""Offline self-check: python test_sdd.py  (no ADO, no Ollama, temp folder only)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import env
import spec
import sddlib
from sddlib import parse_remote, renumber_bug_phases, slug


def wi(i, title, parent=None, rels=(), desc="", typ="User Story", rev=1, state="Active"):
    r = [{"rel": "System.LinkTypes.Hierarchy-Reverse", "url": f"https://x/_apis/wit/workItems/{parent}",
          "attributes": {"name": "Parent"}}] if parent else []
    r += [{"rel": "System.LinkTypes.Related", "url": f"https://x/_apis/wit/workItems/{d}",
           "attributes": {"name": "Related"}} for d in rels]
    return {"id": i, "relations": r, "fields": {
        "System.TeamProject": "P", "System.WorkItemType": typ, "System.Title": title,
        "System.State": state, "System.Rev": rev, "System.Description": desc}}


def main():
    assert parse_remote("https://Org@dev.azure.com/Org/My.Proj/_git/Repo_1") == ("Org", "My.Proj", "Repo_1")
    assert parse_remote("git@ssh.dev.azure.com:v3/Org/Proj/Repo") == ("Org", "Proj", "Repo")
    assert slug("Help Materials: AI Knowledge!") == "help-materials-ai-knowledge"
    v = env.verdict
    assert v(None, None, []) == "not started in sdd"
    assert v(None, {"progress": {"status": "waiting", "gate": "Approval", "phase": "P5"}}, []) == "waiting on you: Approval"
    merged = [{"pr_live": {"status": "completed"}}]
    assert v(None, {"progress": {"status": "active", "phase": "P10"}}, merged).startswith("PRs merged")
    assert v(None, {"progress": {"status": "done"}, "removed": "x"}, []) == "completed — folder cleaned up"
    assert v(None, {"progress": {"status": "abandoned"}, "removed": "x"}, []) == "abandoned"
    # reopen: back to a done stage, or to the current one while it waits; later recorded gates fall
    item = {"id": 5, "flow": "spec", "gates": {"Claimed": "t", "Requirements agreed": "t", "Design agreed": "t", "Ready to PR": "t"},
            "progress": {"flow": "spec", "phase": "Verify", "status": "waiting"}}
    ok, why, revoke = env.reopen_plan(item, "Design")
    assert ok and revoke == ["Design agreed", "Ready to PR"], (why, revoke)
    assert env.reopen_plan(item, "Specify")[2] == ["Requirements agreed", "Design agreed", "Ready to PR"]
    assert env.reopen_plan(item, "Verify")[:2] == (True, [])
    working = {**item, "progress": {"flow": "spec", "phase": "Verify", "status": "active"}}
    assert not env.reopen_plan(working, "Verify")[0] and env.reopen_plan(working, "Design")[0]
    early = {**item, "progress": {"flow": "spec", "phase": "Design", "status": "waiting"}}
    assert "has not started" in env.reopen_plan(early, "Implement")[1][0]
    assert not env.reopen_plan({**item, "progress": {**item["progress"], "status": "done"}}, "Design")[0]
    bug = {"id": 6, "flow": "bug", "gates": {"Claimed": "t", "Approval": "t", "Red test": "t"},
           "progress": {"flow": "bug", "phase": "Phase 8 — Apply fix", "status": "blocked"}}
    assert env.reopen_plan(bug, "Phase 5")[2] == ["Approval", "Red test"]
    assert not env.reopen_plan(bug, "Phase 8")[0]
    # review stages: wait on the PR once it is raised; a rejected PR goes back to the reworkTo stage
    assert env.PHASE_NEEDS["spec"]["Review"] == ["PR raised"] and env.PHASE_NEEDS["bug"]["Phase 15"] == ["PR raised"]
    assert env.phase_key("bug", "Phase 15 — PR review") == "Phase 15"
    # a record from the old bug numbering (Phase 0 … Phase 13, with 9a) reads in the new one
    old = {"stages": {f"Phase {n}": {"status": "done"} for n in ("0", "1", "5", "9", "9a", "10", "13")},
           "progress": {"flow": "bug", "phase": "Phase 9a — Manual verification", "status": "waiting",
                        "note": "Phase 9a is where we stopped"},
           "history": [{"phase": "Phase 0"}, {"phase": "Phase 12 — Record learnings"}]}
    got = renumber_bug_phases(json.loads(json.dumps(old)))
    assert list(got["stages"]) == ["Phase 1", "Phase 2", "Phase 6", "Phase 10", "Phase 11", "Phase 12", "Phase 15"], got
    assert got["progress"]["phase"] == "Phase 11 — Manual verification"
    assert got["progress"]["note"] == "Phase 9a is where we stopped"          # free text is left as written
    assert [h["phase"] for h in got["history"]] == ["Phase 1", "Phase 14 — Record learnings"]
    new = {"stages": {"Phase 1": {}, "Phase 6": {}}, "progress": {"flow": "bug", "phase": "Phase 6"}, "history": []}
    assert renumber_bug_phases(json.loads(json.dumps(new))) == new           # the new numbering is left alone
    spec_rec = {"stages": {"Design": {}}, "progress": {"flow": "spec", "phase": "Design"}}
    assert renumber_bug_phases(dict(spec_rec)) == spec_rec
    assert env.phase_key("bug", "Phase 9a") is None and env.phase_key("bug", "Phase 0") is None
    review = {"id": 7, "flow": "spec", "gates": {"Requirements agreed": "t", "Design agreed": "t", "Ready to PR": "t"},
              "progress": {"flow": "spec", "phase": "Review", "status": "waiting"}}
    assert env.reopen_plan(review, "Implement")[2] == ["Ready to PR"]
    passed = {**review, "gates": {**review["gates"], "PR approved": "t"}}
    assert env.reopen_plan(passed, "Implement")[2] == ["Ready to PR", "PR approved"]
    bugrev = {"id": 8, "flow": "bug", "gates": {"Approval": "t", "Red test": "t", "Verified": "t", "Manual verification": "t"},
              "progress": {"flow": "bug", "phase": "Phase 15", "status": "waiting"}}
    assert env.reopen_plan(bugrev, "Phase 8")[2] == ["Verified", "Manual verification"]
    assert {s["key"]: s.get("reworkTo") for s in env.FLOWS["flows"]["spec"]["stages"]}["Review"] == "Implement"
    # a waiting gate needs an .html sdd-visual ref, or --no-visual with a reason
    import argparse, contextlib, io

    def gate_error(refs, no_visual=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                env.cmd_progress(argparse.Namespace(status="waiting", ref=refs, no_visual=no_visual, id=0))
            except BaseException:  # past the checks it needs a real workspace; only the message matters
                pass
        return err.getvalue()
    assert "sdd:visual" in gate_error(["design.md"])
    assert "sdd:visual" not in gate_error(["design.md", "visuals/design.html"])
    assert "sdd:visual" not in gate_error([r"C:\x\visuals\bug.html"])
    assert "sdd:visual" not in gate_error(["design.md"], no_visual="plain choice")
    terms = spec.extract_terms("Call `GET /api/chat/{id}` on ChatSession, write dbo.CaseAssignedUser, E200801")
    for t in ("get /api/chat/{id}", "chatsession", "dbo.caseassigneduser", "e200801"):
        assert t in terms, (t, terms)
    assert spec.to_markdown(["<p>a <b>b</b></p>", "", "<ul><li>x</li></ul>"])[2].startswith("- x")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        (root / ".claude" / "sdd.json").write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "Org"}}))
        os.chdir(root)
        ctx = spec.Ctx()
        items = [wi(1, "Epic One", typ="Epic"), wi(2, "Feature Two", 1, typ="Feature"),
                 wi(3, "Story Three", 2, rels=[4], desc="<p>Uses <code>ChatSession</code></p>"),
                 wi(4, "Story Four", 2, desc="<p>Also ChatSession here</p>")]
        tested = {"rel": "Microsoft.VSTS.Common.TestedBy-Forward",
                  "url": "https://x/_apis/wit/workItems/9", "attributes": {"name": "Tested By"}}

        def with_test(w):
            w["relations"].append(tested)
            return w
        items[2] = with_test(items[2])
        rep, pend = spec.write_items(ctx, items, {9: "Test Case"})
        spec.place_folders(ctx, pend)
        assert sorted(rep["new"]) == [1, 2, 3, 4]
        assert 9 not in {x["id"] for x in spec.links(ctx, 3, 2)}  # non-spec links are never followed
        req = root / "docs/spec/1-EPIC-epic-one/2-FEAT-feature-two/3-US-story-three/requirements.md"
        assert req.is_file(), list((root / "docs/spec").rglob("*"))
        assert "1 × Tested By Test Case" in req.read_text(encoding="utf-8")
        (req.parent / "design.md").write_text("mine")
        first = req.read_text()

        # same ADO state -> identical file; incidental rev bump -> incidental, not material
        rep, pend = spec.write_items(ctx, [with_test(wi(3, "Story Three", 2, rels=[4], rev=2,
                                              desc="<p>Uses <code>ChatSession</code></p>"))], {9: "Test Case"})
        spec.place_folders(ctx, pend)
        assert rep["incidental"] == [3] and req.read_text() == first

        # retitle + reparent to the epic -> material, folder keeps its name, moves, design.md survives
        rep, pend = spec.write_items(ctx, [with_test(wi(3, "Story Renamed", 1, rels=[4], rev=3, desc="<p>Uses <code>ChatSession</code></p>"))], {9: "Test Case"})
        spec.place_folders(ctx, pend)
        moved = root / "docs/spec/1-EPIC-epic-one/3-US-story-three"
        assert rep["material"] == [3] and (moved / "design.md").read_text() == "mine"

        # retype: a story promoted to a tech story is renamed in place, slug kept
        rep, pend = spec.write_items(ctx, [with_test(wi(3, "Story Renamed", 1, rels=[4], rev=4, typ="Tech Story", desc="<p>Uses <code>ChatSession</code></p>"))], {9: "Test Case"})
        spec.place_folders(ctx, pend)
        assert (root / "docs/spec/1-EPIC-epic-one/3-TS-story-three/design.md").read_text() == "mine"
        # an old-style {id}-{slug} folder is renamed, and its children move with it
        (root / "docs/spec/1-EPIC-epic-one").rename(root / "docs/spec/1-epic-one")
        rep, pend = spec.write_items(ctx, [wi(1, "Epic One", typ="Epic", rev=2)], {})
        spec.place_folders(ctx, pend)
        assert (root / "docs/spec/1-EPIC-epic-one/3-TS-story-three/design.md").is_file()
        assert ctx.item(3)["path"] == "1-EPIC-epic-one/3-TS-story-three"
        assert env.spec_state(root, spec.load_config(root), 3)["folder"].endswith("3-TS-story-three")
        assert spec.folder_name(7, "User Story", "Story four", "7-story-four") == "7-US-story-four"
        assert spec.folder_name(8, "Feature", "2026 roadmap", "8-2026-roadmap") == "8-FEAT-2026-roadmap"
        assert spec.folder_name(8, "Feature", "2026 roadmap", "8-US-2026-roadmap") == "8-FEAT-2026-roadmap"
        assert spec.folder_name(9, "Odd Type", "x") == "9-ODDTYPE-x"
        assert {x["id"] for x in spec.links(ctx, 4, 1)} == {2, 3}
        assert [x["id"] for x in spec.overlap(ctx, 4)] == [3]
        # full-spec impact: one entry per pair, never A-B and B-A; scope limits it to a subtree
        import argparse as _ap
        spec.impact_all(ctx, _ap.Namespace(scope=None, hops=2))
        allj = json.loads((root / "docs/spec/.index/impact-all.json").read_text(encoding="utf-8"))
        keys = [(p["a"], p["b"]) for p in allj["pair_list"]]
        assert len(keys) == len(set(keys)) and all(a < b for a, b in keys) and (3, 4) in keys
        assert allj["estimate"]["all"]["tokens_min"] >= allj["estimate"]["strong"]["tokens_min"] > 0
        spec.impact_all(ctx, _ap.Namespace(scope=2, hops=2))
        sub = json.loads(next((root / "docs/spec").rglob("2-FEAT-*/impact-all.json")).read_text(encoding="utf-8"))
        assert all({p["a"], p["b"]} <= {2, 4} for p in sub["pair_list"])  # 3 moved under the epic
        ctx.db.close()

        # decision links: requirements.md always included, a missing ref is an error, never skipped
        lines, send, bad = env.build_refs(root, spec.load_config(root), 4, ["ado", "design.md"])
        assert any("requirements.md" in x for x in lines) and bad == ["ref not found: design.md"]
        lines, send, bad = env.build_refs(root, spec.load_config(root), 3, ["design.md:2-5"])
        assert not bad and any("design.md lines 2-5" in x for x in lines) and len(send) == 2

        # phase guards: offline, from workitem.json alone
        from sddlib import load_config as lc
        cfg = lc(root)
        pk = env.phase_key
        assert pk("bug", "Phase 12 — Pull request") == "Phase 12" and pk("bug", "Phase 11") == "Phase 11"
        assert pk("bug", "Phase 2 — Pick") == "Phase 2" and pk("spec", "Implement (task 3/7)") == "Implement"
        assert env.check_op(root, cfg, 5, "phase", "bug", "Phase 1")[0]            # nothing needed, no folder yet
        assert not env.check_op(root, cfg, 5, "phase", "bug", "Phase 7")[0]        # no folder, needs Approval
        assert not env.check_op(root, cfg, 5, "phase", None, "Phase 1")[0]         # flow unknown
        wdir = root / ".claude/worktrees/5-x"
        wdir.mkdir(parents=True)
        early = {f"Phase {n}": {"at": "t", "status": "done"} for n in range(1, 6)}
        rec = {"id": 5, "flow": "bug", "repos": {}, "gates": {"Claimed": "t"},
              "stages": {**early, "Phase 6": {"at": "t", "status": "worked"}},
              "progress": {"flow": "bug", "phase": "Phase 6", "status": "waiting"}}
        (wdir / "workitem.json").write_text(json.dumps(rec))
        ok, why, _ = env.check_op(root, cfg, 5, "phase", None, "Phase 8 — Apply the fix")
        assert not ok and any("Approval" in w for w in why) and any("Red test" in w for w in why)
        rec["gates"].update({"Approval": "t", "Red test": "t"})
        (wdir / "workitem.json").write_text(json.dumps(rec))
        ok, why, _ = env.check_op(root, cfg, 5, "phase", None, "Phase 8")
        assert not ok and any("Phase 7 was never worked" in w for w in why), why  # no jumping past a stage
        rec["stages"]["Phase 7"] = {"at": "t", "status": "done"}
        (wdir / "workitem.json").write_text(json.dumps(rec))
        assert env.check_op(root, cfg, 5, "phase", None, "Phase 8")[0]
        assert not env.check_op(root, cfg, 5, "phase", None, "Phase 4")[0]         # derived Worktree missing

        # progress: a stage is never skipped silently, only with the user's recorded yes
        import argparse as _ap, contextlib, io

        def progress(phase, status="active", **kw):
            args = dict(id=5, flow="bug", phase=phase, status=status, gate=None, next=None, note=None, ref=[],
                        no_visual=None, passed=[], revoke=[], confirmed=None, caveat=None)
            args.update(kw)
            with contextlib.redirect_stdout(io.StringIO()):
                env.cmd_progress(_ap.Namespace(**args))
            return json.loads((wdir / "workitem.json").read_text(encoding="utf-8"))

        def refused(*a, **kw):
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err):
                    progress(*a, **kw)
            except SystemExit:
                return err.getvalue()
            raise AssertionError("progress should have refused")

        msg = refused("Phase 11 — Manual verification")  # the 93347 jump
        assert "Phase 8, Phase 9, Phase 10 were never worked" in msg, msg
        assert "--confirmed" in refused("Phase 8", "skipped")                              # skip needs the user's yes
        assert "unknown bug stage" in refused("Phase 101")
        got = progress("Phase 8 — Apply the fix")
        assert got["stages"]["Phase 8"]["status"] == "worked"
        got = progress("Phase 9 — Verify", "skipped", confirmed="yes, skip it")
        assert got["stages"]["Phase 8"]["status"] == "done"                               # moving on finishes it
        assert got["stages"]["Phase 9"] == {"at": got["stages"]["Phase 9"]["at"], "status": "skipped",
                                            "confirmed": "yes, skip it"}
        progress("Phase 10 — Commit and push")
        got = progress("Phase 5 — Prove the root cause")                                   # going back
        assert "Phase 8" not in got["stages"] and "Phase 10" not in got["stages"]          # later stages are redone
        assert "Phase 6" in refused("Phase 7")
        assert not env.check_op(root, cfg, 5, "phase", None, "Phase 101")[0]        # unknown phase

        # /sdd done after close-out: status "done" must not block the clean-up (ADO and PRs faked)
        pr_state = {"status": "completed"}
        env.pr_live = lambda cfg, r: dict(pr_state)
        env.live_item = lambda cfg, wid: {"state": "Resolved", "board": "Dev Completed"}
        ddir = root / ".claude/worktrees/6-closed"
        ddir.mkdir(parents=True)
        drec = {"id": 6, "flow": "bug", "gates": {"Claimed": "t"},
                "repos": {"app": {"path": "app", "source": "app", "branch": "bug/6", "base": "main", "pr": {"id": 1, "url": "pr/1"}}},
                "progress": {"flow": "bug", "phase": "Phase 13 — Write back to the work item", "status": "done"},
                "history": [{"at": "t", "phase": p} for p in ("Phase 1", "Phase 2", "Phase 3", "Phase 6", "Phase 7",
                                                               "Phase 8", "Phase 9", "Phase 11", "Phase 12", "Phase 13")]}
        (ddir / "workitem.json").write_text(json.dumps(drec))
        ok, why, _ = env.check_op(root, cfg, 6, "done")                             # 93347: stages left out
        assert not ok and any("Phase 4, Phase 5, Phase 10, Phase 14, Phase 15" in w for w in why), why
        drec["stages"] = {k: {"at": "t", "status": "done"} for k in env.BUG_PHASES}
        drec["stages"]["Phase 14"] = {"at": "t", "status": "skipped", "confirmed": "skip it"}
        (ddir / "workitem.json").write_text(json.dumps(drec))
        ok, why, _ = env.check_op(root, cfg, 6, "done")
        assert ok, why
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            env.cmd_remove(_ap.Namespace(id=6, abandon=False, yes=False))
        assert "will remove" in out.getvalue() and ddir.name in out.getvalue() and "dry run" in out.getvalue() and ddir.is_dir(), out.getvalue()
        assert not env.check_op(root, cfg, 6, "resume")[0]                          # resume still refused
        assert not env.check_op(root, cfg, 6, "phase", None, "Phase 8")[0]          # phase still refused
        assert v(None, drec, [{"pr_live": pr_state}]) == "PRs merged — run /sdd done to clean up"
        assert v(None, drec, []) == "closed out — run /sdd done to clean up"
        pr_state["status"] = "active"
        ok, why, _ = env.check_op(root, cfg, 6, "done")
        assert not ok and any("not merged yet" in w for w in why) and not any("the flow is" in w for w in why), why
        (ddir / "workitem.json").write_text(json.dumps({**drec, "progress": {**drec["progress"], "status": "abandoned"}}))
        pr_state["status"] = "completed"
        ok, why, _ = env.check_op(root, cfg, 6, "done")
        assert not ok and "the flow is abandoned" in why, why
        # a real remove: folder gone, record kept, verdict now "completed"
        (ddir / "workitem.json").write_text(json.dumps({**drec, "repos": {}}))
        with contextlib.redirect_stdout(io.StringIO()):
            env.cmd_remove(_ap.Namespace(id=6, abandon=False, yes=True))
        kept = json.loads((env.done_dir(root, cfg) / "6.json").read_text(encoding="utf-8"))
        assert not ddir.exists() and v(None, kept, []).startswith("completed")
        # Open Questions: conditional stage, driven by the unticked boxes in questions.md
        sdir = root / cfg["specRoot"] / "9-US-asks"
        sdir.mkdir(parents=True)
        qfile = sdir / "questions.md"
        assert env.count_questions("- [ ] Q1\n- [x] Q2 - answered\n* [ ] Q3\nplain") == (2, 3)
        qdir = root / ".claude/worktrees/9-asks"
        qdir.mkdir(parents=True)
        qrec = {"id": 9, "flow": "spec", "repos": {}, "gates": {"Claimed": "t"}, "stages": {"Specify": {"at": "t", "status": "done"}},
                "progress": {"flow": "spec", "phase": "Specify", "status": "active"}}

        def spec_progress(phase, status="active", **kw):
            args = dict(id=9, flow="spec", phase=phase, status=status, gate=None, next=None, note=None, ref=[],
                        no_visual=None, passed=[], revoke=[], confirmed=None, caveat=None)
            args.update(kw)
            with contextlib.redirect_stdout(io.StringIO()):
                env.cmd_progress(_ap.Namespace(**args))
            return json.loads((qdir / "workitem.json").read_text(encoding="utf-8"))

        def spec_refused(*a, **kw):
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err):
                    spec_progress(*a, **kw)
            except SystemExit:
                return err.getvalue()
            raise AssertionError("progress should have refused")

        (qdir / "workitem.json").write_text(json.dumps(qrec))
        qfile.write_text("- [ ] Q1 who signs off?\n- [ ] Q2 which region?\n", encoding="utf-8")
        assert env.open_questions(root, cfg, 9) == 2
        assert "2 open questions" in spec_refused("Open Questions", "skipped")            # cannot skip real questions
        ok, why, _ = env.check_op(root, cfg, 9, "phase", "spec", "Requirements")
        assert not ok and any("Open Questions" in w for w in why), why                     # questions block Requirements
        got = spec_progress("Open Questions")
        assert got["stages"]["Open Questions"]["status"] == "worked"
        assert "--caveat" in spec_refused("Open Questions", "done", passed=["Open questions"])
        assert not env.check_op(root, cfg, 9, "phase", "spec", "Requirements")[0]
        got = spec_progress("Open Questions", "done", passed=["Open questions"], caveat="Q2 region: unanswered")
        assert got["progress"]["caveat"] == "Q2 region: unanswered" and got["progress"]["openQuestions"] == 2
        ok, why, _ = env.check_op(root, cfg, 9, "phase", "spec", "Requirements")
        assert ok, why                                                                   # continued with a caveat
        assert got["progress"]["status"] == "done"                                       # a done stage hands over, the flow goes on
        assert "only for finishing" in spec_refused("Design", caveat="x")
        # answered everything: nothing to ask, the stage records itself skipped without the user's words
        qrec2 = {**qrec, "gates": {"Claimed": "t"}, "stages": {"Specify": {"at": "t", "status": "done"}}}
        (qdir / "workitem.json").write_text(json.dumps(qrec2))
        qfile.write_text("- [x] Q1 who signs off? - Answer: the PM\n", encoding="utf-8")
        assert env.check_op(root, cfg, 9, "phase", "spec", "Requirements")[0]             # no record needed when no questions
        got = spec_progress("Open Questions", "skipped")
        assert got["stages"]["Open Questions"]["status"] == "skipped" and got["stages"]["Open Questions"]["confirmed"]
        # an item from before the stage existed: Requirements agreed is passed, so Design is not blocked
        old = {**qrec, "gates": {"Claimed": "t", "Requirements agreed": "t"},
               "stages": {"Specify": {"at": "t", "status": "done"}}}
        assert env.unaccounted("spec", old, "Design", 1) == ["Open Questions"]
        assert env.unaccounted("spec", old, "Design", 0) == []
        fin = {**old, "gates": {**old["gates"], "Design agreed": "t", "PR approved": "t"},
               "progress": {"flow": "spec", "phase": "Review", "status": "done"}}
        (qdir / "workitem.json").write_text(json.dumps(fin))
        ok, why, _ = env.check_op(root, cfg, 9, "phase", "spec", "Review")
        assert not ok and "the flow is done" in why, why                                   # the last stage done: flow over
        os.chdir(Path(__file__).parent)
    config_upgrade()
    output_style()
    print("ok")


def output_style():
    """The ELI5 style: written to the global output-styles folder and set once in settings.json."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        home = Path(tmp)
        os.environ["CLAUDE_CONFIG_DIR"] = tmp
        try:
            style, settings = home / "output-styles" / "ELI5.md", home / "settings.json"
            text = sddlib.STYLE_SRC.read_text(encoding="utf-8")
            assert "\nname: ELI5\n" in text.split("---")[1]                 # file named after its name field
            changed, notes = sddlib.install_output_style()                  # fresh: folder, file, settings
            assert changed == [style, settings] and not notes
            assert style.read_text(encoding="utf-8") == text
            assert json.loads(settings.read_text()) == {"outputStyle": "ELI5"}
            assert sddlib.install_output_style() == ([], [])                # nothing to do the second time
            settings.write_text(json.dumps({"model": "opus", "outputStyle": "Explanatory"}))
            assert sddlib.install_output_style() == ([], [])                # the person's later pick stays
            assert json.loads(settings.read_text()) == {"model": "opus", "outputStyle": "Explanatory"}
            assert sddlib.install_output_style(force=True)[0] == [settings]  # env.py init sets it again
            assert json.loads(settings.read_text()) == {"model": "opus", "outputStyle": "ELI5"}
            style.write_text("my own words", encoding="utf-8")              # an edited style file stays
            changed, notes = sddlib.install_output_style()
            assert changed == [] and "kept your version" in notes[0]
            assert style.read_text(encoding="utf-8") == "my own words"
            state = home / "sdd" / "state.json"                             # an unedited old copy updates
            old = "---\nname: ELI5\n---\nold words\n"
            style.write_text(old, encoding="utf-8")
            st = json.loads(state.read_text())
            state.write_text(json.dumps({**st, "styleHash": sddlib._sha(old)}))
            assert sddlib.install_output_style()[0] == [style] and style.read_text(encoding="utf-8") == text
            settings.write_text('{"a": 1,')                                  # broken JSON is never written
            state.unlink()
            changed, notes = sddlib.install_output_style()
            assert settings.read_text() == '{"a": 1,' and "not valid JSON" in notes[0]
        finally:
            del os.environ["CLAUDE_CONFIG_DIR"]


def config_upgrade():
    """agents.models: defaults in load_config, written into an existing sdd.json by upgrade-config."""
    plugin = Path(__file__).resolve().parent.parent
    for name, model in sddlib.DEFAULTS["agents"]["models"].items():  # the agent file's own default agrees
        head = (plugin / "agents" / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
        assert f"\nmodel: {model}\n" in head, (name, model)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        path = root / ".claude" / "sdd.json"
        before = {"specRoot": "docs/spec", "ado": {"org": "Org", "projects": ["P"]}}
        path.write_text(json.dumps(before))
        assert sddlib.load_config(root)["agents"]["models"] == {"investigator": "sonnet", "skeptic": "opus"}
        assert sddlib.upgrade_config(root) == ["agents.models.investigator", "agents.models.skeptic"]
        got = json.loads(path.read_text())
        assert got["agents"] == {"models": {"investigator": "sonnet", "skeptic": "opus"}}
        assert {k: got[k] for k in before} == before                    # nothing else written or changed
        assert "view" not in got
        assert sddlib.upgrade_config(root) == []                         # second run: nothing to do
        path.write_text(json.dumps({**before, "agents": {"models": {"skeptic": "sonnet"}, "x": 1}}))
        assert sddlib.upgrade_config(root) == ["agents.models.investigator"]
        got = json.loads(path.read_text())
        assert got["agents"] == {"models": {"skeptic": "sonnet", "investigator": "sonnet"}, "x": 1}  # set value kept
        path.write_text(json.dumps({**before, "agents": "opus"}))       # not an object: left for the person
        assert sddlib.upgrade_config(root) == [] and json.loads(path.read_text())["agents"] == "opus"
        assert sddlib.load_config(root)["agents"]["models"]["skeptic"] == "opus"
        path.write_text(json.dumps({**before, "agents": {"models": {"investigator": "gpt-4"}}}))
        assert sddlib.bad_agent_models(sddlib.load_config(root)) == ["investigator=gpt-4"]


if __name__ == "__main__":
    main()
