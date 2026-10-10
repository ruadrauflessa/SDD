"""Claude Code hook: while an sdd flow runs, repo files are edited in the work item's worktree, never in
the main checkout.

    pre  (PreToolUse, matcher Edit|Write|MultiEdit|NotebookEdit) -> blocks a file inside a repo folder
                                                                   of the main checkout

Only the repo folders are guarded (the ones env.py works with: .gitmodules, child and grandchild git
folders, or sdd.json repoDirs). The spec folder, .claude/ (worktrees, scripts), the workspace
CLAUDE.md and anything outside the workspace stay open. Active only when this session ran an sdd
script (the same signal question_guard uses). Exit 2 = block, stderr goes to the agent.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
from question_guard import current_turn, flow_this_session, ran_sdd_script, rows  # noqa: E402
from sddlib import discover_repos, find_root, load_config, wt_root  # noqa: E402


def target(data):
    ti = data.get("tool_input") or {}
    return ti.get("file_path") or ti.get("notebook_path") or ""


def guarded_repo(path, cwd):
    """(root, repo name, repo dir) when `path` is inside a repo folder of the main checkout, else None."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd or ".") / p
    p = p.resolve()
    root = find_root(cwd) or find_root(p.parent if p.parent.exists() else None)
    if not root:
        return None
    cfg = load_config(root)
    if wt_root(root, cfg).resolve() in p.parents:
        return None
    for name, d in discover_repos(root, cfg).items():
        if d == p or d in p.parents:
            return root, cfg, name, d, p
    return None


def worktree_copies(root, cfg, name, rel):
    """The same file in each work item folder that has this repo: where the edit belongs."""
    base = wt_root(root, cfg)
    if not base.is_dir():
        return []
    return [d / "src" / name / rel for d in sorted(base.iterdir())
            if d.is_dir() and (d / "src" / name).is_dir()]


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    path = target(data)
    if not path:
        return 0
    rs = rows(data.get("transcript_path", ""))
    if not (ran_sdd_script(current_turn(rs)) or flow_this_session(rs, data.get("cwd"))):
        return 0
    try:
        hit = guarded_repo(path, data.get("cwd"))
    except (OSError, ValueError, KeyError):
        return 0
    if not hit:
        return 0
    root, cfg, name, repo, p = hit
    rel = p.relative_to(repo)
    where = worktree_copies(root, cfg, name, rel)
    hint = ("Edit it there instead: " + " or ".join(str(w) for w in where)) if where else (
        f"No work item folder has {name} yet: add it with `env.py new --id <id> --repos {name} --version <v>`, "
        "then edit it in that worktree.")
    print(f"sdd: {p} is in the main checkout of {name}. In an sdd flow every repo change happens in the work "
          f"item's worktree, never in the main checkout. {hint}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
