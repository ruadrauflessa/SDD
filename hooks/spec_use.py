"""Claude Code hook: while meaning search is on, the synced specs are searched by meaning first.

    pre   (PreToolUse, matcher Bash|PowerShell|Grep) -> a text search of the spec folder, or of a folder of items
          in it, is blocked until this caller (the main conversation, or this sub-agent) ran
          `spec.py query search` or `spec.py query similar` in this turn
    post  (PostToolUse, matcher Bash|PowerShell) -> one line in .claude/sdd/spec-use.jsonl for each of those runs

Only while meaning search is on: Ollama answers, the embeddings model is pulled and the index holds its
embeddings. Without Ollama the guard is silent, and `query search` is a word search as before.
A search is the Grep tool, or grep / rg / findstr / Select-String / git grep / find run as a command (graph_use's
rule). A file, or one item's own folder (no item folders inside it), stays open: that is reading a spec, not
searching the specs. So are Glob (finding a folder by its id) and Read. The sdd sub-agents (investigator,
skeptic) may not run spec.py, so they are not asked to. Exit 2 = block, stderr goes to the agent; every other
failure here lets the call through.
"""
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
from graph_use import candidates, caller, heads, kinds, now  # noqa: E402
from question_guard import SCRIPT, is_real_user, rows  # noqa: E402

LOG = Path(".claude") / "sdd" / "spec-use.jsonl"
AGENTS = {"investigator", "skeptic"}   # agent_guard keeps them from running spec.py
ITEM = re.compile(r"^\d+-")            # an item folder: {id}-{TYPE}-{slug}
QUERY = re.compile(r"\bquery\s+(search|similar)\b")
SPEC_PY = (HERE.parent / "scripts" / "spec.py").as_posix()


def workspace(cwd):
    """(workspace root, its config, the spec folder), or None outside a workspace."""
    from sddlib import find_root, load_config
    root = find_root(cwd)
    if not root:
        return None
    cfg = load_config(root)
    return root, cfg, (root / cfg["specRoot"]).resolve()


def searches_specs(paths, spec):
    """A path is the spec folder, or a folder in it that holds item folders: a search of many specs."""
    for p in paths:
        try:
            p = p.resolve()
        except (OSError, RuntimeError):
            continue
        while not p.exists() and p != spec and spec in p.parents:  # docs/spec/*/requirements.md -> docs/spec
            p = p.parent
        if p != spec and spec not in p.parents:
            continue
        if ".index" in p.relative_to(spec).parts or not p.is_dir():
            continue
        if p == spec or any(c.is_dir() and ITEM.match(c.name) for c in p.iterdir()):
            return True
    return False


def meaning_on(cfg, spec):
    """The embeddings model, when a meaning search would run now; else None. Read-only and quick."""
    model = cfg["embeddings"]["model"]
    db = spec / ".index" / "spec.db"
    if not db.is_file():
        return None
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    try:
        if not con.execute("SELECT 1 FROM emb WHERE model=? LIMIT 1", (model,)).fetchone():
            return None
    except sqlite3.Error:
        return None
    finally:
        con.close()
    url = cfg["embeddings"]["url"].rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except (OSError, ValueError, KeyError):
        return None
    return model if any(n.split(":")[0] == model.split(":")[0] for n in names) else None


def turn_start(transcript):
    """When the user's last message was sent (the transcript's timestamp, to the second), or "" when unknown."""
    for r in reversed(rows(transcript or "")):
        if is_real_user(r) and r.get("timestamp"):
            return str(r["timestamp"])[:19]
    return ""


def asked(root, who, session, since):
    """This caller ran a meaning query in this turn (or, with no turn to go by, in this session)."""
    try:
        lines = (root / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("caller") == who and \
                (str(r.get("at", ""))[:19] >= since if since else r.get("session") == session):
            return True
    return False


def pre(data):
    """-> a message to block with, or None to let the call run."""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if tool == "Glob" or "search" not in kinds(tool, ti):
        return None
    if data.get("agent_id") and (data.get("agent_type") or "").split(":")[-1] in AGENTS:
        return None
    cwd = data.get("cwd") or "."
    ws = workspace(cwd)
    if not ws:
        return None
    root, cfg, spec = ws
    if not searches_specs(candidates(tool, ti, cwd), spec):
        return None
    model = meaning_on(cfg, spec)
    if not model or asked(root, caller(data), data.get("session_id") or "", turn_start(data.get("transcript_path"))):
        return None
    return (f'sdd: search the specs by meaning first. Run: python "{SPEC_PY}" query search "<what you are looking '
            f'for>" (it ranks every synced item by its words and by its meaning, with {model}), or '
            f'query similar --id <id> for items like one you know. Then read the items it lists. After that, in this '
            "turn, grep and Grep are open for exact text: an id, a field name, a quoted phrase.")


def meaning_query(head):
    """A real run of `spec.py query search|similar`, not a grep or echo that only names it."""
    m = SCRIPT.match(head)
    return bool(m and m.group(1) == "spec" and m.group(2) == "query" and QUERY.search(head))


def record(data):
    """(workspace root, [records]) for each meaning query the call ran; None when it ran none."""
    if (data.get("tool_name") or "") not in ("Bash", "PowerShell"):
        return None
    runs = [h for h in heads((data.get("tool_input") or {}).get("command") or "") if meaning_query(h)]
    ws = workspace(data.get("cwd") or ".") if runs else None
    if not ws:
        return None
    base = {"at": now(), "caller": caller(data), "session": data.get("session_id") or "",
            "agent": (data.get("agent_type") or "").split(":")[-1]}
    return ws[0], [{**base, "what": re.sub(r"\s+", " ", h).strip()[:200]} for h in runs]


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
            root, recs = got
            (root / LOG).parent.mkdir(parents=True, exist_ok=True)
            with open(root / LOG, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r) + "\n" for r in recs))
    except Exception:  # a counter must never get in the way of the call it counts
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
