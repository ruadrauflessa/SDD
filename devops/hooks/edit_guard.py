"""Claude Code hook (PreToolUse, matcher Edit|Write|MultiEdit|NotebookEdit): protects what devops relies on.

Refuses an edit of:
  - devops' own state under .claude/devops/ (plans, approvals, scans, the sync in progress): devops.py
    writes it; a hand edit would change what the user approved. A run's texts.json is the one exception.
  - a file that still has a merge conflict in a devops sync: the user resolves every hunk
  - a new launcher in the workspace's scripts/ (scripts/run-*.ps1): it is shared and tracked; a generated
    launcher goes in .claude/scripts/
  - a release-notes file that was already published to the wiki: render a new run instead
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as G  # noqa: E402
from guardlib import L  # noqa: E402


def check(root, cfg, p):
    state = L.state_dir(root)
    if state in p.parents:
        if p.name == "texts.json" and p.parent.parent.name == "notes":
            return None
        return "state", (f"{p} is devops state, written only by devops.py. Changing it by hand would change what the user "
                         "approved. Run the devops.py command that makes it (scan, plan, render) again.")
    if p.parent == root / "scripts" and re.fullmatch(r"run-.*\.ps1", p.name, re.I) and not p.exists():
        return "launcher", (f"scripts/ is tracked and shared with the team; a generated launcher is machine-specific. "
                            f"Write it to {root / '.claude' / 'scripts' / p.name} instead (check .claude/scripts is ignored first).")
    folder = p.parent if p.parent.exists() else None
    if folder:
        e = G.active_sync(root, folder)
        if e and e.get("state") == "conflict":
            top = G.repo_top(folder)
            unmerged = G.git_out(top, ["ls-files", "-u"]) or ""
            rel = p.resolve().relative_to(Path(top).resolve()).as_posix() if top else ""
            if rel and any(line.split("\t", 1)[-1] == rel for line in unmerged.splitlines()):
                return "sync-conflict", (f"{rel} has a merge conflict in the devops sync of {e['repo']}. The user resolves "
                                         "every hunk by hand; you may show both sides and explain them. When they say done, "
                                         f"run devops.py sync verify --repo {e['repo']}.")
    notes_dir = (root / cfg["notesDir"]).resolve()
    if notes_dir in p.parents:
        nd = L.state_dir(root, "notes")
        for d in (nd.iterdir() if nd.is_dir() else []):
            m = L.read_json(d / "meta.json") or {}
            if m.get("stage") == "published" and m.get("file") and G.same(m["file"], p):
                return "published", (f"{p.name} was published to the wiki ({m.get('url') or 'see the run'}). Edit the data and "
                                     "render a new run, so the file and the wiki page stay the same.")
    return None


def main():
    data = G.read_input()
    if not data:
        return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path")
    if not path:
        return 0
    cwd = data.get("cwd") or None
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd or ".") / p
    try:
        p = p.resolve()
        root = L.find_root(cwd)
        cfg = L.load_config(root)
        if not cfg["guard"]["enabled"]:
            return 0
        hit = check(root.resolve(), cfg, p)
    except Exception as e:  # a guard that breaks lets the edit through, and says so
        print(f"devops guard: skipped ({type(e).__name__}: {e})", file=sys.stderr)
        return 0
    return G.refuse(root, *hit) if hit else 0


if __name__ == "__main__":
    sys.exit(main())
