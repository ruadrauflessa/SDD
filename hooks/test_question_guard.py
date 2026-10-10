"""Self-check for question_guard.py: python test_question_guard.py  (temp files only)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).with_name("question_guard.py")
SDD = "python C:/plugins/sdd/scripts/env.py new --id 5 --repos A --version 1.0.0"
REFS = "python C:/plugins/sdd/scripts/env.py refs --id 5 --ref ado"
WAIT = "python C:/plugins/sdd/scripts/env.py progress --id 5 --flow bug --phase P1 --status waiting --ref ado"
LINKS = "- ADO: [ADO 5 — x](https://dev.azure.com/o/p/_workitems/edit/5)\n- [requirements.md](docs/spec/5-US-x/requirements.md)"


def ts(i):
    return f"2026-09-30T10:00:{i:02d}.000Z"


def user(text, i=0):
    return {"type": "user", "timestamp": ts(i), "message": {"role": "user", "content": text}}


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool(cmd):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "PowerShell", "input": {"command": cmd}}]}}


def run(mode, transcript, cwd, **extra):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in transcript))
    payload = {"transcript_path": f.name, "cwd": str(cwd), **extra}
    r = subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(payload), capture_output=True, text=True)
    return r.returncode


def main():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        ask = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [{"question": "Approve?"}]}}
        # no sdd flow in the session: never blocks
        assert run("pre", [user("hi"), say("Approve?")], cwd, **ask) == 0
        assert run("stop", [user("hi"), say("Shall I?")], cwd) == 0
        # init/doctor alone is not a flow
        assert run("stop", [user("x"), tool("python .../scripts/env.py doctor"), say("Ok?")], cwd) == 0
        assert run("stop", [user("x"), tool("python .../scripts/env.py upgrade-config"), say("Ok?")], cwd) == 0
        # the view's snapshot is read-only too
        assert run("stop", [user("x"), tool("python C:/plugins/sdd/scripts/env.py view --id 5 --json"), say("Ok?")], cwd) == 0
        # sdd flow: a question without links is blocked, with links it passes
        flow = [user("go"), tool(SDD)]
        assert run("pre", flow + [say("Here is the design.")], cwd, **ask) == 2
        assert run("pre", flow + [say(LINKS)], cwd, **ask) == 0
        # links inside the question are refused, even when the chat has them too
        linked = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [{"question": "PR [33600](https://dev.azure.com/o/p/_git/r/pullrequest/33600) — approved?"}]}}
        assert run("pre", flow + [say(LINKS)], cwd, **linked) == 2
        bare = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [{"question": "Merged?", "options": [{"label": "Yes", "description": "see https://x/pr/1"}]}]}}
        assert run("pre", flow + [say(LINKS)], cwd, **bare) == 2
        # the chat text is not always in the transcript when the hook runs: a links script run this
        # turn (refs, or a waiting checkpoint) is enough, as long as the question itself has no link
        assert run("pre", flow + [tool(REFS)], cwd, **ask) == 0
        assert run("pre", flow + [tool(WAIT)], cwd, **ask) == 0
        assert run("pre", flow + [tool(REFS)], cwd, **linked) == 2
        # links only inside the question no longer count as the Links block
        assert run("pre", flow + [say("Here is the design.")], cwd, **{"tool_name": "AskUserQuestion", "tool_input": {"questions": [{"question": LINKS}]}}) == 2
        # plain-text question at the end of a flow turn is sent back, even with links
        assert run("stop", flow + [say(LINKS + "\n\nDo you approve the design?")], cwd) == 2
        assert run("stop", flow + [say("Done. The PR is open.")], cwd) == 0
        assert run("stop", flow + [say("See `why?` and https://x/?a=1")], cwd) == 0   # ? only in code/URL
        # never loops: a second stop in the same turn passes
        assert run("stop", flow + [say("Approve?")], cwd, stop_hook_active=True) == 0
        # a "?" earlier in the reply (a heading) is not a question; only the last line counts
        assert run("stop", flow + [say("**Did it work?** Yes.\n\nStart a new session.")], cwd) == 0
        assert run("stop", flow + [say("Done.\n\n**Shall I raise the PR?**")], cwd) == 2
        # only a real run counts: a command that just names the script is not a flow (bug seen 2026-10-02)
        for named in ['grep -rn "x" ~/.claude/skills/sdd-workspace/scripts/env.py sdd-workspace/scripts/env.py new',
                      'cat C:/plugins/sdd/scripts/env.py progress',
                      'Select-String -Path C:/plugins/sdd/scripts/spec.py -Pattern "sync"',
                      'git log -- scripts/env.py new --id 5',
                      "        'python3 -u ~/x/scripts/env.py new --id 5',   # a quoted string in code, not a run",
                      "cat > t.py <<'EOF'\ncd x && python C:/p/scripts/env.py status --id 5\nEOF",
                      "python - <<EOF\npython C:/p/scripts/env.py new --id 5\nEOF\necho done",
                      "$s = @'\npython C:/p/scripts/env.py new --id 5\n'@"]:
            assert run("pre", [user("q"), tool(named), say("Which one?")], cwd, **ask) == 0, named
            assert run("stop", [user("q"), tool(named), say("Which one?")], cwd) == 0, named
        # real runs in other shapes still count
        for real in ['cd x && python "C:/Program Files/sdd/scripts/env.py" status --id 5',
                     r'& "C:/Program Files/Python312/python.exe" C:\plugins\sdd\scripts\spec.py sync --id 5',
                     'python3 -u ~/.claude/skills/sdd-workspace/scripts/env.py new --id 5',
                     'uv run python scripts/env.py can --id 5 --op pr',
                     "cat > a.md <<'EOF'\nnotes\nEOF\npython C:/p/scripts/env.py new --id 5"]:
            assert run("stop", [user("q"), tool(real), say("Approve?")], cwd) == 2, real
        # a waiting checkpoint split over lines (bash \ or PowerShell `) still prints the Links block
        for cont in ["\\\n", "`\n"]:
            split = f"python C:/plugins/sdd/scripts/env.py progress --id 5 --flow bug {cont}  --phase P1 --status waiting --ref ado"
            assert run("pre", flow + [tool(split)], cwd, **ask) == 0, cont
        # a flow started earlier in THIS session still counts in a later turn with no script run
        assert run("stop", [user("start", 1), tool(SDD), say("a"), user("next", 9), say("Approve?")], cwd) == 2
        # another session's work item progress does not turn this session into a flow
        (cwd / ".claude/worktrees/5-x").mkdir(parents=True)
        (cwd / ".claude/sdd.json").write_text("{}")
        (cwd / ".claude/worktrees/5-x/workitem.json").write_text(json.dumps(
            {"progress": {"status": "waiting", "at": "2026-09-30T10:00:05Z"}}))
        assert run("stop", [user("start", 1), say("a"), user("next", 9), say("Approve?")], cwd) == 0
    print("ok")


if __name__ == "__main__":
    main()
