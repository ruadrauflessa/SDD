"""Claude Code hook: how often the agent asks the code graph, and how often it searches by hand.

    post  (PostToolUse, matcher Bash|PowerShell|Grep|Glob) -> one line in the work item folder's graph-use.jsonl

Counts two kinds of call made against a work item folder (`.claude/worktrees/<id>-<slug>/`, or the
`worktreeRoot` in .claude/sdd.json):
  graph   graphify query, explain, affected or path
  search  the Grep or Glob tool, or grep / rg / findstr / Select-String / git grep / find run as a command
A call counts for the item whose folder it names (a path in the command, the tool's `path`) or runs in
(the shell's cwd). A grep that only filters another command's output (`git log | grep x`) is not a search.
It never blocks and never prints: whatever goes wrong here, the call stands. `env.py status` reports the
totals, per stage, and whether each stage started from the graph.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = "graph-use.jsonl"
GRAPH = re.compile(r"""^(?:&\s*)?["']?(?:[^\s"']*[\\/])?graphify(?:\.exe)?["']?\s+(query|explain|affected|path)\b""", re.I)
SEARCH = re.compile(r"""^(?:&\s*)?["']?(?:[^\s"']*[\\/])?(grep|egrep|fgrep|rg|ag|ack|findstr|find|select-string|sls)"""
                    r"""(?:\.exe)?["']?(?:\s|$)""", re.I)
# git's own options before the subcommand: `git -C <path> --no-pager grep`
GIT_GREP = re.compile(r"""^["']?(?:[^\s"']*[\\/])?git(?:\.exe)?["']?\s+(?:(?:-C|-c)\s+\S+\s+|-\S+\s+)*grep\b""", re.I)
SEGMENT = re.compile(r"&&|\|\||[;\n]")
CD = re.compile(r"""(?:^|[;&|\n])\s*(?:cd|pushd|set-location|sl)\s+["']?([^\s"';&|]+)""", re.I)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def heads(command):
    """The first program of each pipeline in the command: `a | b; c` -> [a, c]."""
    out = []
    for seg in SEGMENT.split(command or ""):
        first = seg.split("|", 1)[0].strip()
        first = re.sub(r"^(?:\w+=\S*\s+)+", "", first)  # X=1 grep ...
        if first:
            out.append(first)
    return out


def kinds(tool, tool_input):
    """The kinds of call this is: a subset of {"graph", "search"}."""
    if tool in ("Grep", "Glob"):
        return {"search"}
    found = set()
    for h in heads((tool_input or {}).get("command") or ""):
        if GRAPH.match(h):
            found.add("graph")
        elif SEARCH.match(h) or GIT_GREP.match(h):
            found.add("search")
    return found


def candidates(tool_input, cwd):
    """Paths the call names, then the folder it runs in, as Paths (relative ones against cwd)."""
    ti = tool_input or {}
    words = [ti.get("path") or ""] + CD.findall(ti.get("command") or "")  # `cd src/X && grep -rn y .`
    words += re.findall(r"""[^\s"'`;|&()]*[\\/][^\s"'`;|&()]*""", ti.get("command") or "")
    words += re.findall(r"""["']([^"']*[\\/][^"']*)["']""", ti.get("command") or "")
    out = []
    for w in words:
        w = w.strip().rstrip(",")
        if not w:
            continue
        p = Path(w)
        out.append(p if p.is_absolute() else Path(cwd) / p)
    out.append(Path(cwd))
    return out


def workspace(start):
    """(workspace root, worktrees folder) at or above `start`, or None."""
    for d in [start, *start.parents]:
        cfg = d / ".claude" / "sdd.json"
        if cfg.is_file():
            try:
                rel = json.loads(cfg.read_text(encoding="utf-8")).get("worktreeRoot") or ".claude/worktrees"
            except (OSError, ValueError, AttributeError):
                rel = ".claude/worktrees"
            return d, (d / rel).resolve()
    return None


def item_folder(paths):
    """The work item folder the first of `paths` inside one lies in, or None."""
    seen = {}
    for p in paths:
        try:
            p = p.resolve()
        except (OSError, RuntimeError):
            continue
        start = p if p.is_dir() else p.parent
        key = str(start)
        if key not in seen:
            seen[key] = workspace(start)
        ws = seen[key]
        if not ws:
            continue
        try:
            rel = p.relative_to(ws[1])
        except ValueError:
            continue
        if rel.parts and re.match(r"^\d+-", rel.parts[0]) and (ws[1] / rel.parts[0] / "workitem.json").is_file():
            return ws[1] / rel.parts[0]
    return None


def stage(folder):
    try:
        prog = json.loads((folder / "workitem.json").read_text(encoding="utf-8")).get("progress") or {}
    except (OSError, ValueError, AttributeError):
        return ""
    return prog.get("phase") or ""


def what(tool, tool_input):
    ti = tool_input or {}
    text = ti.get("command") if tool in ("Bash", "PowerShell") else " ".join(
        str(ti.get(k)) for k in ("pattern", "path", "glob") if ti.get(k))
    return re.sub(r"\s+", " ", text or "").strip()[:200]


def record(data):
    """The lines to append, as (folder, [records]); None when the call is not one this hook counts."""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    found = kinds(tool, ti)
    if not found:
        return None
    folder = item_folder(candidates(ti, data.get("cwd") or "."))
    if not folder:
        return None
    base = {"at": now(), "tool": tool, "agent": (data.get("agent_type") or "").split(":")[-1],
            "session": data.get("session_id") or "", "stage": stage(folder), "what": what(tool, ti)}
    return folder, [{**base, "kind": k} for k in sorted(found)]


def main():
    try:
        got = record(json.load(sys.stdin))
        if got:
            folder, recs = got
            with open(folder / LOG, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r) + "\n" for r in recs))
    except Exception:  # a counter must never get in the way of the call it counts
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
