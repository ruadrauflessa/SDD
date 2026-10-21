"""Claude Code hook (PostToolUse, matcher AskUserQuestion): records the user's Yes to a devops plan.

devops.py prints the question to ask: "<summary>? (plan <token>)". When the user picks an answer that
starts with "Yes" to a question naming a plan that exists, the approval is written to
.claude/devops/approvals.jsonl, and the agent is told. Only this hook and the /devops pane write that
file; the git guard refuses anything else that tries.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as G  # noqa: E402
from guardlib import L  # noqa: E402

PLAN = re.compile(r"\(plan ([0-9a-f]{10})\)")


def answers(data):
    """{question text: answer text} from the tool's input (answers the dialog filled in) and its result."""
    out = {}
    for src in (data.get("tool_input") or {}, data.get("tool_response")):
        if isinstance(src, dict):
            for k, v in (src.get("answers") or {}).items():
                out[str(k)] = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        elif isinstance(src, str):
            for q, a in re.findall(r'"([^"]+)"\s*=\s*"([^"]*)"', src):
                out[q] = a
    resp = data.get("tool_response")
    if isinstance(resp, dict) and isinstance(resp.get("content"), str):
        for q, a in re.findall(r'"([^"]+)"\s*=\s*"([^"]*)"', resp["content"]):
            out[q] = a
    return out


def main():
    data = G.read_input()
    if not data or data.get("tool_name") != "AskUserQuestion":
        return 0
    root = L.find_root(data.get("cwd") or None)
    said = answers(data)
    approved = []
    for q in (data.get("tool_input") or {}).get("questions") or []:
        text = str(q.get("question", ""))
        m = PLAN.search(text)
        if not m or not L.load_plan(root, m.group(1)):
            continue
        a = said.get(text, "")
        if a.strip().lower().startswith("yes"):
            L.approve(root, m.group(1), "question")
            approved.append(m.group(1))
    if approved:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                          f"devops: the user approved plan {', '.join(approved)}. Run the open/publish command now."}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never break the question itself
        print(f"devops approval hook: skipped ({type(e).__name__}: {e})", file=sys.stderr)
        sys.exit(0)
