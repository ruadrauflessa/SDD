"""Self-check for graph_use.py: python test_graph_use.py   (temp folders; needs git)"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).with_name("graph_use.py")
sys.path.insert(0, str(HOOK.parent.parent / "scripts"))
from test_proof import fake_graphify  # noqa: E402  (a stand-in graphify, also for Windows)
SDD = "python C:/plugins/sdd/scripts/env.py progress --id 5 --flow bug --phase \"Phase 4\" --status active"


def run(ws, tool, tool_input, cwd=None, agent=None):
    data = {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": tool_input,
            "cwd": str(cwd or ws), "session_id": "s1"}
    if agent:
        data["agent_type"], data["agent_id"] = agent, "a1"
    p = subprocess.run([sys.executable, str(HOOK), "post"], input=json.dumps(data), capture_output=True, text=True)
    assert p.returncode == 0 and not p.stdout and not p.stderr, (tool_input, p.stdout, p.stderr)


def lines(folder):
    f = folder / "graph-use.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []


def main():
    with tempfile.TemporaryDirectory() as t:
        ws = Path(t) / "ws"
        (ws / ".claude").mkdir(parents=True)
        (ws / ".claude" / "sdd.json").write_text(json.dumps({"specRoot": "docs/spec"}))
        item = ws / ".claude" / "worktrees" / "5-guest-checkout"
        (item / "src" / "Shop").mkdir(parents=True)
        (item / "workitem.json").write_text(json.dumps({"id": 5, "progress": {"phase": "Phase 4"}}))
        other = ws / ".claude" / "worktrees" / "6-other"
        (other / "src").mkdir(parents=True)
        (other / "workitem.json").write_text(json.dumps({"id": 6, "progress": {"phase": "Design"}}))
        graph = item / "graph" / "graph.json"

        counted = [  # (tool, tool_input, cwd, kinds)
            ("Bash", {"command": f'graphify query "where is the total" --graph "{graph}"'}, ws, ["graph"]),
            ("PowerShell", {"command": f"& graphify.exe explain fmt_total --graph {graph}"}, ws, ["graph"]),
            ("Bash", {"command": f"/usr/local/bin/graphify affected Foo --graph {graph}"}, ws, ["graph"]),
            ("Bash", {"command": "grep -rn fmt_total src/"}, item, ["search"]),
            ("Bash", {"command": f"rg fmt_total {item / 'src'}"}, ws, ["search"]),
            ("Bash", {"command": f"git -C {item / 'src' / 'Shop'} --no-pager grep -n fmt_total"}, ws, ["search"]),
            ("Bash", {"command": "cd .claude/worktrees/5-guest-checkout/src/Shop && grep -rn x ."}, ws, ["search"]),
            ("PowerShell", {"command": f"Select-String -Path {item / 'src'}/*.cs -Pattern Total"}, ws, ["search"]),
            ("Bash", {"command": f"find {item / 'src'} -name '*.py'"}, ws, ["search"]),
            ("Grep", {"pattern": "fmt_total", "path": str(item / "src")}, ws, ["search"]),
            ("Glob", {"pattern": "**/*.cs", "path": str(item)}, ws, ["search"]),
            ("Bash", {"command": f"graphify query x --graph {graph} && grep -rn x {item / 'src'}"}, ws,
             ["graph", "search"]),
        ]
        for tool, ti, cwd, want in counted:
            before = len(lines(item))
            run(ws, tool, ti, cwd)
            got = lines(item)[before:]
            assert [r["kind"] for r in got] == want, (ti, got)
            assert all(r["stage"] == "Phase 4" and r["tool"] == tool and r["session"] == "s1" for r in got), got
        n = len(lines(item))

        ignored = [  # not a graph query or a search of an item folder: no line anywhere
            ("Bash", {"command": "grep -n phase_key scripts/env.py"}, ws),          # the workspace, not an item
            ("Bash", {"command": "git log --oneline | grep fix"}, item),            # filters output
            ("Bash", {"command": "cat src/Shop/a.py"}, item),                        # reading is not searching
            ("Bash", {"command": f"graphify update {item / 'src'}"}, ws),            # building, not asking
            ("Read", {"file_path": str(item / "src" / "Shop" / "a.py")}, ws),
            ("Grep", {"pattern": "x", "path": str(ws / "docs")}, ws),
            ("Bash", {"command": "echo grep"}, item),
            ("Bash", {"command": "python scripts/env.py status --id 5"}, item),
        ]
        for tool, ti, cwd in ignored:
            run(ws, tool, ti, cwd)
        assert len(lines(item)) == n, lines(item)[n:]
        assert not lines(other)

        run(ws, "Grep", {"pattern": "x", "path": str(other / "src")}, ws, agent="sdd:investigator")
        got = lines(other)
        assert len(got) == 1 and got[0]["agent"] == "investigator" and got[0]["stage"] == "Design", got
        assert len(lines(item)) == n

        # a broken input never fails the call
        p = subprocess.run([sys.executable, str(HOOK), "post"], input="not json", capture_output=True, text=True)
        assert p.returncode == 0 and not p.stderr
        run(ws, "Bash", {"command": None}, item)
        run(Path(t) / "nowhere", "Bash", {"command": "grep -rn x ."}, Path(t))
    guard()
    print("ok")


def sh(args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


def pre(ws, tool, tool_input, cwd=None, session="s1", agent_id=None, transcript=None, path=None):
    """Run the guard, and the recorder after it as Claude Code does when the call goes ahead."""
    data = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd or ws),
            "session_id": session, "transcript_path": str(transcript or "")}
    if agent_id:
        data["agent_id"], data["agent_type"] = agent_id, "sdd:investigator"
    env = {**os.environ, "PATH": path if path is not None else os.environ["PATH"]}
    p = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(data), capture_output=True, text=True, env=env)
    assert p.returncode in (0, 2), p.stderr
    if p.returncode == 0:
        subprocess.run([sys.executable, str(HOOK), "post"], input=json.dumps({**data, "hook_event_name": "PostToolUse"}),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def guard():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t).resolve()
        gitcfg = t / "gitconfig"
        gitcfg.write_text("[user]\n\tname = Dev\n\temail = dev@x.co\n")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gitcfg)
        with_graphify = str(fake_graphify(t)) + os.pathsep + os.environ["PATH"]
        ws = t / "ws"
        (ws / ".claude").mkdir(parents=True)
        (ws / ".claude" / "sdd.json").write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "O", "projects": ["P"]}}))
        (ws / "Shop" / ".git").mkdir(parents=True)                  # the main checkout of repo Shop
        item = ws / ".claude" / "worktrees" / "5-fix-it"
        code = item / "src" / "Shop"
        code.mkdir(parents=True)
        (code / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        sh(["git", "init", "-q"], code)
        sh(["git", "add", "-A"], code)
        sh(["git", "commit", "-q", "-m", "base"], code)
        rec = {"id": 5, "flow": "bug", "repos": {"Shop": {"path": "src/Shop", "base": "team/1.0.0", "source": "Shop"}},
               "progress": {"flow": "bug", "phase": "Phase 4 — Reproduce", "status": "active"}}
        (item / "workitem.json").write_text(json.dumps(rec))
        graph = item / "graph" / "graph.json"
        query = {"command": f'graphify query "where is add" --graph "{graph}"'}
        search = {"command": f"grep -rn add {code}"}
        P = os.environ["PATH"]

        code_, err = pre(ws, "Bash", search)
        assert code_ == 2 and "from its graph first" in err and "graphify query" in err and str(graph) in err, err
        assert pre(ws, "Grep", {"pattern": "add", "path": str(code)})[0] == 2
        assert pre(ws, "Glob", {"pattern": ".claude/worktrees/5-fix-it/src/**/*.py"})[0] == 2
        assert pre(ws, "Bash", {"command": "grep -rn add ."}, cwd=item)[0] == 2           # the whole folder holds the code
        assert pre(ws, "Bash", {"command": f"grep -n phase {item / 'workitem.json'}"})[0] == 0   # not the code
        assert pre(ws, "Bash", {"command": f"cat {code / 'calc.py'}"})[0] == 0                   # reading is open
        assert pre(ws, "Read", {"file_path": str(code / "calc.py")})[0] == 0

        code_, err = pre(ws, "Bash", query, path=P)                        # no graphify: no graph to read
        assert code_ == 2 and "could not be rebuilt" in err and "graphify is not on PATH" in err, err
        assert pre(ws, "Bash", query, path=with_graphify)[0] == 0          # builds the graph before the query runs
        assert graph.is_file() and (item / "graph" / "built.json").is_file()
        assert pre(ws, "Bash", search)[0] == 0                             # asked the graph in Phase 4: search is open
        assert pre(ws, "Grep", {"pattern": "add", "path": str(code)})[0] == 0
        assert pre(ws, "Bash", search, agent_id="a7")[0] == 2              # a sub-agent asks the graph itself
        assert pre(ws, "Bash", query, agent_id="a7", path=with_graphify)[0] == 0
        assert pre(ws, "Bash", search, agent_id="a7")[0] == 0
        assert pre(ws, "Bash", search, session="s2")[0] == 2               # a new session starts from the graph again
        rec["progress"]["phase"] = "Phase 4"                               # the same stage, written another way
        (item / "workitem.json").write_text(json.dumps(rec))
        assert pre(ws, "Bash", search)[0] == 0
        rec["progress"]["phase"] = "Phase 5 — Root cause"                  # a new stage: the graph first again
        (item / "workitem.json").write_text(json.dumps(rec))
        assert pre(ws, "Bash", search)[0] == 2

        # the graph is rebuilt before any read of it once the code changed
        built = (item / "graph" / "built.json").read_text()
        (code / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")
        assert pre(ws, "Read", {"file_path": str(item / "graph" / "GRAPH_REPORT.md")}, path=with_graphify)[0] == 0
        assert (item / "graph" / "built.json").read_text() != built and "shop_calc_sub" in graph.read_text()
        (code / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        code_, err = pre(ws, "Bash", query, path=P)                        # stale, and graphify is gone
        assert code_ == 2 and "older than the code" in err, err
        built = (item / "graph" / "built.json").read_text()
        assert pre(ws, "Bash", query, path=with_graphify)[0] == 0 and (item / "graph" / "built.json").read_text() != built
        assert pre(ws, "Bash", search)[0] == 0

        # the main checkout is not searched while a flow runs in this session
        tp = t / "t.jsonl"
        tp.write_text("\n".join(json.dumps(r) for r in [
            {"type": "user", "message": {"role": "user", "content": "fix 5"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": SDD}}]}}]))
        code_, err = pre(ws, "Bash", {"command": "grep -rn add Shop/"}, transcript=tp)
        assert code_ == 2 and "main checkout of Shop" in err and str(code) in err, err
        assert pre(ws, "Grep", {"pattern": "add", "path": str(ws / "Shop")}, transcript=tp)[0] == 2
        assert pre(ws, "Bash", {"command": "grep -rn add Shop/"})[0] == 0  # no flow in this session: left alone
        assert pre(ws, "Bash", {"command": "grep -rn x docs/"}, transcript=tp)[0] == 0


if __name__ == "__main__":
    main()
