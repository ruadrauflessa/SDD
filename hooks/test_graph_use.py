"""Self-check for graph_use.py: python test_graph_use.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).with_name("graph_use.py")


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
    print("ok")


if __name__ == "__main__":
    main()
