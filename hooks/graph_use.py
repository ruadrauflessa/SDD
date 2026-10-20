"""Claude Code hook: the code is explored from the graph, the graph is current, and its use is counted.

    pre   (PreToolUse, matcher Bash|PowerShell|Grep|Glob|Read)
          - a read of a work item's graph (graphify query|explain|affected|path, or any file in its graph/)
            -> rebuilds the graph first when the code changed since it was built; blocks when it cannot
          - a search of a work item's code -> blocked until this caller (the main conversation, or this
            sub-agent) has asked the graph in the current stage of this session
          - a search of a repo in the main checkout while an sdd flow runs in this session -> blocked:
            search the work item's worktree, from its graph
    post  (PostToolUse, matcher Bash|PowerShell|Grep|Glob) -> one line in the folder's graph-use.jsonl

A search is the Grep or Glob tool, or grep / rg / findstr / Select-String / git grep / find run as a command.
A grep that only filters another command's output (`git log | grep x`) is not one. A call belongs to the
work item whose folder (`.claude/worktrees/<id>-<slug>/`, or sdd.json `worktreeRoot`) it names or runs in.
After the stage's first graph query, searches are open: the graph does not hold string literals, config
keys or SQL. `env.py status` reports the counts. Exit 2 = block, stderr goes to the agent; every other
failure here lets the call through.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
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
    if tool not in ("Bash", "PowerShell"):
        return found
    for h in heads((tool_input or {}).get("command") or ""):
        if GRAPH.match(h):
            found.add("graph")
        elif SEARCH.match(h) or GIT_GREP.match(h):
            found.add("search")
    return found


def candidates(tool, tool_input, cwd):
    """Paths the call names, then the folder it runs in, as Paths (relative ones against cwd)."""
    ti = tool_input or {}
    cmd = (ti.get("command") or "") if tool in ("Bash", "PowerShell") else ""
    words = [ti.get("path") or "", ti.get("file_path") or ""] + CD.findall(cmd)  # `cd src/X && grep -rn y .`
    if tool == "Glob":
        words.append(re.split(r"[*?\[{]", ti.get("pattern") or "", maxsplit=1)[0])  # a pattern's fixed head: a/b/**/*.cs
    words += re.findall(r"""[^\s"'`;|&()]*[\\/][^\s"'`;|&()]*""", cmd)
    words += re.findall(r"""["']([^"']*[\\/][^"']*)["']""", cmd)
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


def hits(paths):
    """[(work item folder, part)] for each path inside a work item folder, first-seen order. part is
    "graph" (its graph/), "code" (src/, or the whole folder) or "other" (workitem.json, the logs)."""
    seen, out = {}, []
    for p in paths:
        try:
            p = p.resolve()
        except (OSError, RuntimeError):
            continue
        start = p if p.is_dir() else p.parent
        if str(start) not in seen:
            seen[str(start)] = workspace(start)
        ws = seen[str(start)]
        if not ws:
            continue
        try:
            rel = p.relative_to(ws[1])
        except ValueError:
            continue
        if rel.parts and re.match(r"^\d+-", rel.parts[0]) and (ws[1] / rel.parts[0] / "workitem.json").is_file():
            part = "code" if len(rel.parts) == 1 or rel.parts[1] == "src" else \
                "graph" if rel.parts[1] == "graph" else "other"
            hit = (ws[1] / rel.parts[0], part)
            if hit not in out:
                out.append(hit)
    return out


def item_folder(paths):
    """The work item folder the first of `paths` inside one lies in, or None."""
    h = hits(paths)
    return h[0][0] if h else None


def progress(folder):
    try:
        data = json.loads((folder / "workitem.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    return data, (data.get("progress") or {}) if isinstance(data, dict) else {}


def stage(folder):
    return progress(folder)[1].get("phase") or ""


def env_module():
    sys.path.insert(0, str(HERE.parent / "scripts"))
    import env  # noqa: E402  (only when a call touches a work item: it is the slow import)
    return env


def stage_key(folder, phase=None):
    """The stage a phase belongs to ("Phase 4 — Reproduce" -> "Phase 4"), for comparing records."""
    data, prog = progress(folder)
    phase = prog.get("phase") if phase is None else phase
    flow = prog.get("flow") or data.get("flow")
    try:
        return env_module().phase_key(flow, phase or "") or (phase or "")
    except Exception:
        return phase or ""


def caller(data):
    """Who asks: this session's main conversation, or one sub-agent in it."""
    return f"{data.get('session_id') or ''}/{data.get('agent_id') or 'main'}"


def asked_graph(folder, who, key):
    """This caller has a graph query on record for the folder, in the stage `key`."""
    try:
        lines = (folder / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == "graph" and r.get("caller") == who \
                and stage_key(folder, r.get("stage") or "") == key:
            return True
    return False


def main_checkout_repo(paths, cwd, transcript):
    """(repo name, worktree copies) when a path is in a main-checkout repo folder and an sdd flow runs in
    this session (the edit guard's rule, for searches); else None."""
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent / "scripts"))
    from sddlib import discover_repos, find_root, load_config, wt_root  # noqa: E402
    root = find_root(cwd)
    if not root:
        return None
    cfg = load_config(root)
    base = wt_root(root, cfg).resolve()
    repos = {n: d.resolve() for n, d in discover_repos(root, cfg).items()}
    hit = None
    for p in paths:
        try:
            p = p.resolve()
        except (OSError, RuntimeError):
            continue
        if base == p or base in p.parents:
            continue
        hit = next((n for n, d in repos.items() if d == p or d in p.parents), None)
        if hit:
            break
    if not hit:
        return None
    from question_guard import current_turn, flow_this_session, ran_sdd_script, rows  # noqa: E402
    rs = rows(transcript or "")
    if not (ran_sdd_script(current_turn(rs)) or flow_this_session(rs, cwd)):
        return None
    copies = [d / "src" / hit for d in sorted(base.iterdir()) if (d / "src" / hit).is_dir()] if base.is_dir() else []
    return hit, copies


def query_hint(folder):
    g = folder / "graph" / "graph.json"
    return (f'graphify query "<what you are looking for>" --graph "{g}"  (or graphify explain "<name>" / '
            f'graphify affected "<name>" --graph "{g}")')


def pre(data):
    """-> a message to block with, or None to let the call run."""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or "."
    found = kinds(tool, ti)
    paths = candidates(tool, ti, cwd)
    if tool == "Read" and "graph" not in str(ti.get("file_path") or ""):
        return None  # the common Read: no work item's graph, nothing to check
    item = hits(paths)
    for folder in dict.fromkeys(f for f, part in item if part == "graph"):  # graphify --graph <it>, a Read of the report
        try:
            env_module().ensure_graph(folder)
        except Exception as e:
            return (f"sdd: the code graph in {folder / 'graph'} is older than the code and could not be rebuilt, "
                    f"so it would answer for code that is not there any more:\n{e}")
    if "search" not in found:
        return None
    code = [f for f, part in item if part == "code"]
    who = caller(data)
    for folder in dict.fromkeys(code):
        key = stage_key(folder)
        if not asked_graph(folder, who, key):
            return (f"sdd: explore ADO {folder.name.split('-', 1)[0]}'s code from its graph first. Ask it: "
                    f"{query_hint(folder)}. Then read the files it points at. Once you have asked the graph in this "
                    f"stage ({key or 'no stage recorded'}), grep and Grep are open for what a graph does not hold: "
                    "string literals, config keys, SQL, one pattern across many files.")
    if not item:
        got = main_checkout_repo(paths, cwd, data.get("transcript_path"))
        if got:
            repo, copies = got
            where = (" Search the worktree instead, starting from its graph: " + " or ".join(str(c) for c in copies)) \
                if copies else (f" No work item folder has {repo} yet: add it with `env.py new --id <id> --repos "
                                f"{repo} --version <v>`, then ask its graph.")
            return (f"sdd: that search is in the main checkout of {repo}. In an sdd flow the code is explored in "
                    f"the work item's worktree, from its code graph, never in the main checkout.{where}")
    return None


def what(tool, tool_input):
    ti = tool_input or {}
    text = ti.get("command") if tool in ("Bash", "PowerShell") else " ".join(
        str(ti.get(k)) for k in ("pattern", "path", "glob") if ti.get(k))
    return re.sub(r"\s+", " ", text or "").strip()[:200]


def record(data):
    """The lines to append, as (folder, [records]); None when the call is not one this hook counts.
    A graph query counts for the folder whose graph it asks; a search, for the folder whose code it searches."""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    found = kinds(tool, ti)
    if not found:
        return None
    item = hits(candidates(tool, ti, data.get("cwd") or "."))
    if not item:
        return None
    want = [k for k in sorted(found) if (k == "graph") or any(part == "code" for _, part in item)]
    if not want:
        return None  # a grep of the graph files, or of workitem.json: not a search of the code
    folder = item[0][0]
    base = {"at": now(), "tool": tool, "agent": (data.get("agent_type") or "").split(":")[-1],
            "session": data.get("session_id") or "", "caller": caller(data), "stage": stage(folder),
            "what": what(tool, ti)}
    return folder, [{**base, "kind": k} for k in want]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "post"
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if mode == "pre":
        try:
            why = pre(data)
        except Exception:  # a guard that breaks must not stop the work
            return 0
        if why:
            print(why, file=sys.stderr)
            return 2
        return 0
    try:
        got = record(data)
        if got:
            folder, recs = got
            with open(folder / LOG, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r) + "\n" for r in recs))
    except Exception:  # a counter must never get in the way of the call it counts
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
