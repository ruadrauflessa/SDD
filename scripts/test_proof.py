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
        r = anchors_run()
        assert r.returncode == 1 and "no graph in" in r.stdout and "graphifyy" in r.stdout, r.stdout
        (env_dir / "graph").mkdir()
        (env_dir / "graph" / "graph.json").write_text(json.dumps({"directed": False, "nodes": [
            {"id": "repo_calc", "label": "calc.py", "source_file": "Repo/calc.py", "source_location": "L1"},
            {"id": "repo_calc_add", "label": "add()", "source_file": "Repo/calc.py", "source_location": "L1"},
            {"id": "repo_test_calc", "label": "test_calc.py", "source_file": "Repo/test_calc.py"}], "links": []}))
        r = anchors_run()
        assert r.returncode == 1 and "no record of the code it was built from" in r.stdout, r.stdout
        env.record_graph(env_dir)                                       # what env.py graph does after graphify
        r = anchors_run()
        assert r.returncode == 0 and "anchors OK (2 components)" in r.stdout and "repo_calc_add (Repo/calc.py:L1)" in r.stdout, r.stdout
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

        # code that changed after the graph was built: rebuild it before the check counts
        (spec / "design.md").write_text(table.format(rows=good), encoding="utf-8")
        (wt / "calc.py").write_text(FIXED + "\ndef sub(a, b):\n    return a - b\n")
        r = anchors_run()
        assert r.returncode == 1 and "Repo: the code changed since the graph was built" in r.stdout, r.stdout
        env.record_graph(env_dir)
        assert anchors_run().returncode == 0
        (wt / "calc.py").write_text(FIXED)

        import anchors
        assert anchors.under("Repo/Orders/OrderService.cs", "Orders") and anchors.under("Repo/a/b.py", "src\\Repo\\a")
        assert not anchors.under("Repo/Orders2/x.cs", "Orders") and not anchors.under("Repo/x.cs", "")
        assert anchors.parse("# x\n")[1] == ['design.md has no "## Affected components" section']
        assert anchors.parse("## Affected components\n\nnone yet\n## Risks\n")[1] == ["the Affected components section has no table"]
        rows, _ = anchors.parse("## Affected components\n| Component | Change | Graph node |\n|---|---|---|\n"
                                "| `A/b.py` | **Modified** (rename) | `a_b`, `a_b_c` |\n")
        assert rows == [{"line": 4, "component": "A/b.py", "change": "modified", "nodes": ["a_b", "a_b_c"]}], rows
    print("ok")


if __name__ == "__main__":
    main()
