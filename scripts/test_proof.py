"""Self-check for gate proofs (proof.py, env.py run / revert-check / verify / anchors) on a real git worktree.

    python scripts/test_proof.py      (temp folders only; needs git)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ENV_PY = str(HERE / "env.py")
PY = sys.executable
TEST = f'"{PY}" test_calc.py'
BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"


def sh(args, cwd, check=True):
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed:\n{r.stdout}\n{r.stderr}")
    return r


def env_py(root, *args, check=True):
    return sh([PY, ENV_PY, *args], root, check)


FAKE_GRAPHIFY = r'''"""A stand-in for `graphify update <src>`: a node per .py file and per def, in $GRAPHIFY_OUT."""
import json, os, re, sys
from pathlib import Path
if os.environ.get("FAKE_GRAPHIFY_FAIL"):
    print("boom", file=sys.stderr)
    sys.exit(3)
src, out = Path(sys.argv[2]), Path(os.environ["GRAPHIFY_OUT"])
nodes = []
for f in sorted(src.rglob("*.py")):
    rel = f.relative_to(src).as_posix()
    base = re.sub(r"\W+", "_", rel[:-3]).lower()
    nodes.append({"id": base, "label": f.name, "source_file": rel, "source_location": "L1"})
    for n, line in enumerate(f.read_text().splitlines(), 1):
        m = re.match(r"def (\w+)", line)
        if m:
            nodes.append({"id": base + "_" + m.group(1).lower(), "label": m.group(1) + "()", "source_file": rel,
                          "source_location": "L%d" % n})
out.mkdir(parents=True, exist_ok=True)
(out / "graph.json").write_text(json.dumps({"nodes": nodes, "links": []}))
(out / "GRAPH_REPORT.md").write_text("# report\n")
print("[graphify watch] Rebuilt: %d nodes" % len(nodes))
'''


def fake_graphify(tmp):
    """A folder holding a `graphify` that runs FAKE_GRAPHIFY, for PATH (a .cmd beside it on Windows)."""
    d = Path(tmp) / "fakebin"
    d.mkdir()
    (d / "graphify.py").write_text(FAKE_GRAPHIFY)
    if os.name == "nt":
        (d / "graphify.cmd").write_text(f'@"{PY}" "%~dp0graphify.py" %*\r\n')
    else:
        exe = d / "graphify"
        exe.write_text(f"#!{PY}\n" + FAKE_GRAPHIFY)
        exe.chmod(0o755)
    return d


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gitcfg = tmp / "gitconfig"
        gitcfg.write_text("[user]\n\tname = Dev\n\temail = dev@x.co\n[init]\n\tdefaultBranch = main\n")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gitcfg)

        origin, root = tmp / "origin.git", tmp / "ws"
        sh(["git", "init", "--bare", str(origin)], tmp)
        repo = root / "Repo"
        repo.mkdir(parents=True)
        (root / ".claude").mkdir()
        (root / ".claude" / "sdd.json").write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "O", "projects": ["P"]}}))
        sh(["git", "init"], repo)
        (repo / "calc.py").write_text(BUGGY)
        (repo / ".gitignore").write_text("__pycache__/\n")
        sh(["git", "add", "-A"], repo)
        sh(["git", "commit", "-m", "base"], repo)
        sh(["git", "remote", "add", "origin", str(origin)], repo)
        sh(["git", "push", "origin", "HEAD:refs/heads/team/1.0.0"], repo)

        env_py(root, "new", "--id", "5", "--repos", "Repo", "--version", "1.0.0", "--title", "Fix add",
               "--type", "Bug", "--no-graph")
        env_dir = next((root / ".claude" / "worktrees").glob("5-*"))
        wt = env_dir / "src" / "Repo"
        (wt / "test_calc.py").write_text("from calc import add\nassert add(2, 2) == 4, f'add(2, 2) = {add(2, 2)}'\n")

        import env
        import proof

        r = env_py(root, "can", "--id", "5", "--op", "phase", "--flow", "bug", "--phase", "Phase 1")
        assert "read:" in r.stdout and "01-load-and-claim.md" in r.stdout, r.stdout

        def lacks(flow, gate):
            return env.proof_missing(flow, env.read_env(env_dir), env_dir, gate)

        # Red test: the new test fails on the buggy code; a run expected to fail proves it
        assert lacks("bug", "Red test") == ["'Red test' needs a run expected to fail"]
        r = env_py(root, "run", "--id", "5", "--gate", "Red test", "--expect", "fail", "--", TEST)
        assert "OK" in r.stdout and "add(2, 2) = 0" in r.stdout, r.stdout
        assert lacks("bug", "Red test") == []
        assert env_py(root, "run", "--id", "5", "--gate", "Red test", "--expect", "pass", "--", TEST,
                      check=False).returncode == 1                            # it does fail: "pass" is NOT OK

        # the fix; the revert check puts calc.py back to base, sees the failure, restores the fix
        (wt / "calc.py").write_text(FIXED)
        before = proof.content_tree(wt)
        r = env_py(root, "revert-check", "--id", "5", "--fix", "calc.py", "--", TEST)
        assert "OK" in r.stdout, r.stdout
        assert (wt / "calc.py").read_text() == FIXED and proof.content_tree(wt) == before

        # Verified also needs 5 passing runs and the full suite, on the code as it is now
        left = lacks("bug", "Verified")
        assert len(left) == 2 and "--repeat 5" in left[0] and "--suite" in left[1], left
        env_py(root, "run", "--id", "5", "--gate", "Verified", "--expect", "pass", "--repeat", "5", "--", TEST)
        env_py(root, "run", "--id", "5", "--gate", "Verified", "--expect", "pass", "--suite", "--", TEST)
        assert lacks("bug", "Verified") == []

        # an edit after the runs voids them; committing the same files does not
        (wt / "calc.py").write_text(FIXED + "# note\n")
        left = lacks("bug", "Verified")
        assert len(left) == 3 and all("changed since" in x for x in left), left
        (wt / "calc.py").write_text(FIXED)
        sh(["git", "add", "-A"], wt)
        sh(["git", "commit", "-m", "fix add"], wt)
        assert lacks("bug", "Verified") == []
        assert (wt / ".git").exists() and not sh(["git", "status", "--porcelain"], wt).stdout.strip()  # index untouched

        # the PR guard asks the same question
        rec = env.read_env(env_dir)
        rec["gates"] = {"Approval": "t", "Verified": "t", "Manual verification": "t"}
        env.write_env(env_dir, rec)
        cfg = env.load_config(root)
        ok, why, _ = env.check_op(root, cfg, 5, "pr")
        assert not any("Verified" in w for w in why), why
        (wt / "calc.py").write_text(FIXED + "# changed after Verified\n")
        sh(["git", "commit", "-am", "late change"], wt)
        ok, why, _ = env.check_op(root, cfg, 5, "pr")
        assert any("Verified" in w and "changed since" in w for w in why), why
        sh(["git", "revert", "--no-edit", "HEAD"], wt)

        # a test that passes without the fix guards nothing: the revert check says NOT OK
        (wt / "test_calc.py").write_text("assert True\n")
        r = env_py(root, "revert-check", "--id", "5", "--fix", "calc.py", "--", TEST, check=False)
        assert r.returncode == 1 and "guards nothing" in r.stdout, r.stdout
        assert (wt / "calc.py").read_text() == FIXED
        sh(["git", "checkout", "--", "test_calc.py"], wt)

        # spec flow: tasks.md Verify commands; Ready to PR needs them all passing on the current code
        spec = root / "docs" / "spec" / "5-BUG-fix-add"
        spec.mkdir(parents=True)
        tasks = (f"# 5 — Tasks\n\n- [x] 1. Fix add\n      - Files: `src/Repo/calc.py`\n      - Verify: `{TEST}`\n"
                 "- [x] 2. Check the page\n      - Files: `docs/x.md`\n      - Verify: the page shows 4\n"
                 "\n## Not doing\n\n- [ ] 9. nothing\n")
        (spec / "tasks.md").write_text(tasks, encoding="utf-8")
        parsed = proof.parse_tasks(tasks)
        assert [t["n"] for t in parsed] == [1, 2] and proof.verify_command(parsed[1]) is None
        assert proof.task_repo(parsed[0], {"Repo": None, "Other": None}) == "Repo"
        assert lacks("spec", "Ready to PR") == ["Repo: 'Ready to PR' needs every task's Verify command passing (env.py verify)"]
        r = env_py(root, "verify", "--id", "5")
        assert "1 passed, 0 failed, 1 by hand" in r.stdout and "check by hand" in r.stdout, r.stdout
        assert lacks("spec", "Ready to PR") == []
        (spec / "tasks.md").write_text(tasks.replace(TEST, f'"{PY}" -c "raise SystemExit(3)"'), encoding="utf-8")
        r = env_py(root, "verify", "--id", "5", check=False)
        assert r.returncode == 1 and "0 passed, 1 failed" in r.stdout, r.stdout

        runs = env.read_env(env_dir)["runs"]
        assert all(set(x) >= {"at", "gate", "repo", "ok", "tree"} for x in runs), runs[-1]

        # the code graph: required, built by graphify into graph/, rebuilt whenever the code changed
        bin_dir = fake_graphify(tmp)
        no_graphify = os.environ["PATH"]
        with_graphify = str(bin_dir) + os.pathsep + no_graphify
        state = env.read_env(env_dir)
        state["gates"] = {"Claimed": "t"}
        state["stages"] = {"Phase 1": {"at": "t", "status": "done"}, "Phase 2": {"at": "t", "status": "done"}}
        env.write_env(env_dir, state)

        def graph_reasons():
            return [w for w in env.check_op(root, cfg, 5, "phase", "bug", "Phase 3")[1] if "raph" in w]

        assert graph_reasons() == ["Phase 3 needs 'Graph' first — not true on disk yet: env.py graph --id 5"]
        r = env_py(root, "graph", "--id", "5", check=False)
        assert r.returncode == 1 and "graphify is not on PATH" in r.stderr and "graphifyy" in r.stderr, r.stderr
        os.environ["PATH"] = with_graphify
        r = env_py(root, "graph", "--id", "5")
        assert "graph:" in r.stdout and (env_dir / "graph" / "graph.json").is_file(), r.stdout
        assert not (env_dir / "src" / "graphify-out").exists() and not (env_dir / "graph.lock").exists()
        built = json.loads((env_dir / "graph" / "built.json").read_text())
        assert built["trees"] == {"Repo": proof.content_tree(wt)} and "graph" not in env.read_env(env_dir), built
        assert graph_reasons() == [] and "Graph" in env.gates_met(root, cfg, 5, env.read_env(env_dir), env_dir)
        assert "current" in env_py(root, "graph", "--id", "5", "--if-stale").stdout
        (wt / "calc.py").write_text(FIXED + "\ndef sub(a, b):\n    return a - b\n")
        assert graph_reasons() == ["Phase 3 needs the graph current — Repo: the code changed since the graph was built: "
                                   "env.py graph --id 5"]
        assert "rebuilt" in env_py(root, "graph", "--id", "5", "--if-stale").stdout
        assert "repo_calc_sub" in (env_dir / "graph" / "graph.json").read_text() and graph_reasons() == []
        os.environ["FAKE_GRAPHIFY_FAIL"] = "1"
        (wt / "calc.py").write_text(FIXED)
        r = env_py(root, "graph", "--id", "5", "--if-stale", check=False)
        assert r.returncode == 1 and "graphify failed (exit 3)" in r.stderr and "boom" in r.stderr, r.stderr
        del os.environ["FAKE_GRAPHIFY_FAIL"]
        (env_dir / "graph.lock").write_text("1")                        # a lock left by a build that died
        os.utime(env_dir / "graph.lock", (1, 1))
        assert "rebuilt" in env_py(root, "graph", "--id", "5", "--if-stale").stdout
        assert not (env_dir / "graph.lock").exists()

        # env.py new fails without a graph, and leaves the worktree in place
        os.environ["PATH"] = no_graphify
        r = env_py(root, "new", "--id", "6", "--repos", "Repo", "--version", "1.0.0", "--title", "Other",
                   "--type", "Bug", check=False)
        six = next((root / ".claude" / "worktrees").glob("6-*"))
        assert r.returncode == 1 and "graphify is not on PATH" in r.stderr and "env.py graph --id 6" in r.stderr, r.stderr
        assert (six / "src" / "Repo" / "calc.py").is_file() and not (six / "graph" / "graph.json").exists()
        os.environ["PATH"] = with_graphify
        env_py(root, "graph", "--id", "6")
        assert (six / "graph" / "graph.json").is_file()
        assert "--no-graph" not in env_py(root, "new", "--help").stdout     # for the tests' fixtures only

        # Design agreed: design.md's Affected components checked against the code graph (env.py anchors)
        def design_lacks():
            return env.proof_missing("spec", env.read_env(env_dir), env_dir, "Design agreed", root, cfg)

        def anchors_run():
            return env_py(root, "anchors", "--id", "5", check=False)

        need = "'Design agreed' needs design.md's Affected components checked against the code graph (env.py anchors)"
        assert design_lacks() == [need]
        r = anchors_run()
        assert r.returncode == 1 and "no design.md" in r.stderr, (r.stdout, r.stderr)
        table = ("# Design\n\n## Affected components\n\n| Component | Change | Graph node | Notes |\n| --- | --- | --- | --- |\n"
                 "{rows}\n## Contracts and data\n\n- Endpoints: none\n")
        good = ("| `src/Repo/calc.py` | modified | `repo_calc_add` | the sum |\n"
                "| `Repo/money.py` | new | new | a helper |\n")
        (spec / "design.md").write_text(table.format(rows=good), encoding="utf-8")
        os.environ["PATH"] = no_graphify
        (wt / "calc.py").write_text(FIXED + "# stale\n")
        r = anchors_run()
        assert r.returncode == 1 and "graphify is not on PATH" in r.stdout, r.stdout   # a stale graph it cannot rebuild
        os.environ["PATH"] = with_graphify
        r = anchors_run()                                               # rebuilds the stale graph, then checks
        assert r.returncode == 0 and "anchors OK (2 components)" in r.stdout and "repo_calc_add (Repo/calc.py:L1)" in r.stdout, r.stdout
        (wt / "calc.py").write_text(FIXED)
        assert design_lacks() == []
        assert env.proof_missing("spec", env.read_env(env_dir), env_dir, "Design agreed") == [need]  # no design.md to compare
        (spec / "design.md").write_text(table.format(rows=good).replace("\n", "\r\n"), encoding="utf-8")
        assert design_lacks() == []                                     # line ends do not count as a change
        (spec / "design.md").write_text(table.format(rows=good + "| `Repo/calc.py` | removed | `repo_calc` | x |\n"),
                                        encoding="utf-8")
        assert design_lacks() == [need + " on design.md as it is now (it changed since the last check)"]
        assert anchors_run().returncode == 0 and design_lacks() == []

        # every way a row can be wrong, each named
        bad = ("| `Repo/calc.py` | modified | `repo_nothing` | unknown node |\n"
               "| `Repo/calc.py` | modified | `repo_test_calc` | a node of another file |\n"
               "| `calc.py` | new | new | exists already |\n"
               "| `Repo/calc.py` | modified | new | no node |\n"
               "| `Repo/calc.py` | tweaked | `repo_calc` | odd change |\n"
               "| `{path or project}` | new | new | the template |\n")
        (spec / "design.md").write_text(table.format(rows=bad), encoding="utf-8")
        r = anchors_run()
        out = r.stdout
        assert r.returncode == 1 and "NOT OK (6 components)" in out, out
        for x in ("no node 'repo_nothing' in the graph", "node 'repo_test_calc' is in Repo/test_calc.py, not in Repo/calc.py",
                  "is marked new but already exists in src/", "a modified component needs its graph node",
                  "Change is 'tweaked'", "still the template's placeholder"):
            assert x in out, (x, out)
        assert design_lacks() == [need + " on design.md as it is now (it changed since the last check)"]  # a failed check proves nothing
        (spec / "design.md").write_text(table.format(rows=good).replace("| Graph node ", "").replace("| `repo_calc_add` ", "")
                                        .replace("| new | a helper", "| a helper").replace("| --- | --- | --- | --- |", "| --- | --- | --- |"),
                                        encoding="utf-8")
        r = anchors_run()
        assert r.returncode == 1 and "no Graph node column" in r.stdout, r.stdout

        import anchors
        assert anchors.under("Repo/Orders/OrderService.cs", "Orders") and anchors.under("Repo/a/b.py", "src\\Repo\\a")
        assert not anchors.under("Repo/Orders2/x.cs", "Orders") and not anchors.under("Repo/x.cs", "")
        assert anchors.parse("# x\n")[1] == ['design.md has no "## Affected components" section']
        assert anchors.parse("## Affected components\n\nnone yet\n## Risks\n")[1] == ["the Affected components section has no table"]
        rows, _ = anchors.parse("## Affected components\n| Component | Change | Graph node |\n|---|---|---|\n"
                                "| `A/b.py` | **Modified** (rename) | `a_b`, `a_b_c` |\n")
        assert rows == [{"line": 4, "component": "A/b.py", "change": "modified", "nodes": ["a_b", "a_b_c"]}], rows

        # graph-focus: the code graph with the item's design, or its changes, lit (graphify's files are faked)
        gdir = env_dir / "graph"
        gdir.mkdir(exist_ok=True)
        node = lambda i, label, f, line: {"id": i, "label": label, "source_file": f, "source_location": f"L{line}"}
        (gdir / "graph.json").write_text(json.dumps({"nodes": [
            node("calc", "calc.py", "Repo/calc.py", 1), node("add", "add()", "Repo/calc.py", 1), node("sub", "sub()", "Repo/calc.py", 10),
            node("newfn", "newfn()", "Repo/new.py", 1), node("far", "far()", "Repo/far.py", 1)],
            "links": [{"source": "add", "target": "far", "relation": "calls"}]}), encoding="utf-8")
        (gdir / "graph.html").write_text("<html><body><script>const nodesDS = 1</script></body></html>", encoding="utf-8")
        (spec / "design.md").write_text("# Design\n\nAdd `sub()` next to it. Touch `src/Repo/calc.py`.\n", encoding="utf-8")
        rec = env.read_env(env_dir)
        rec["progress"] = {"flow": "bug", "phase": "Phase 8 — Apply the fix", "status": "active"}
        env.write_env(env_dir, rec)
        (wt / "calc.py").write_text(FIXED + "# a line the work added\n")           # uncommitted, below the committed fix
        (wt / "new.py").write_text("def newfn():\n    pass\n")                      # a new file
        r = env_py(root, "graph-focus", "--id", "5", "--json")
        got = json.loads(r.stdout)
        assert got["ok"] and got["mode"] == "implementation" and got["stage"].startswith("Phase 8"), got
        focus = json.loads((gdir / "focus.json").read_text(encoding="utf-8"))
        assert focus["files"] == ["Repo/calc.py", "Repo/new.py"], focus
        page = (gdir / "graph-focus.html").read_text(encoding="utf-8")
        assert 'id="sdd-graph-focus"' in page and page.index("sdd-graph-focus") < page.rindex("</body>")
        injected = json.loads(page.split("var F = ")[1].split(";\n  if (typeof nodesDS")[0].replace("<\\/", "</"))
        assert sorted(injected["primary"]) == ["add", "newfn"], injected                    # the function the lines are in, and the new file
        assert "sub" in injected["planned"] and "far" in injected["neighbors"], injected    # named in design.md, not changed
        r = env_py(root, "graph-focus", "--id", "5", "--mode", "design", "--json")
        got = json.loads(r.stdout)
        assert got["mode"] == "design" and got["primary"] >= 2 and got["planned"] == 0, got
        rec["progress"] = {"flow": "bug", "phase": "Phase 4 — Reproduce and locate", "status": "active"}
        env.write_env(env_dir, rec)
        assert json.loads(env_py(root, "graph-focus", "--id", "5", "--json").stdout)["mode"] == "none"   # a stage with nothing to light
        assert 'sdd-graph-focus' not in (gdir / "graph-focus.html").read_text(encoding="utf-8")
        (gdir / "graph.json").unlink()
        os.environ["PATH"] = no_graphify
        r = env_py(root, "graph-focus", "--id", "5", "--json", check=False)
        got = json.loads(r.stdout)                                                   # no graph, and nothing here can build one
        assert r.returncode == 1 and got["ok"] is False and "graphify is not on PATH" in got["error"], (r.stdout, r.stderr)
        os.environ["PATH"] = with_graphify
    print("ok")


if __name__ == "__main__":
    main()
