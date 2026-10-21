"""What the devops guard hooks share: reading the hook input, splitting a shell line into the programs it
runs (with the folder each one runs in), and the devops state the rules look at.

A guard never stops on its own error: a hook that cannot read its input, or a repo it cannot ask,
lets the call through. It only refuses what it is sure breaks a rule. Exit 2 = refuse; stderr goes
to the agent.
"""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import devopslib as L  # noqa: E402,F401

SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
LAUNCHERS = {"xargs", "env", "sudo", "command", "exec", "time", "nice", "call", "&", "."}
CD = {"cd", "set-location", "sl", "pushd", "chdir"}


def read_input():
    try:
        return json.load(sys.stdin)
    except ValueError:
        return None


def refuse(root, rule, msg):
    if root:
        L.guard_log(root, rule, msg)
    print(f"devops guard ({rule}): {msg}", file=sys.stderr)
    return 2


def strip_heredocs(cmd):
    cmd = re.sub(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", "", cmd, flags=re.S | re.M)
    return re.sub(r"@(['\"])\r?\n.*?^\1@", "", cmd, flags=re.S | re.M)


def split_words(seg):
    # posix=False keeps a Windows path's backslashes (C:\repo); the quotes come off by hand
    try:
        words = shlex.split(seg, posix=False)
    except ValueError:
        words = seg.split()
    out = []
    for w in words:
        if len(w) >= 2 and w[0] == w[-1] and w[0] in "\"'":
            w = w[1:-1]
        if w:
            out.append(w)
    return out


def programs(command, cwd):
    """[(program, args, folder)] for each command in the line, following cd/Set-Location/pushd."""
    here = Path(cwd or os.getcwd())
    out = []
    for seg in SEPARATORS.split(strip_heredocs(command or "").replace("`\n", " ").replace("\\\n", " ")):
        words = split_words(seg.strip().lstrip("({").strip())
        while words and (words[0] in LAUNCHERS or re.fullmatch(r"\w+=\S*", words[0])):
            words = words[1:]
        if not words:
            continue
        prog = re.split(r"[\\/]", words[0])[-1].lower()
        if prog.endswith(".exe"):
            prog = prog[:-4]
        if prog in CD and len(words) > 1:
            target = [w for w in words[1:] if not w.startswith("-")]
            if target:
                p = Path(os.path.expanduser(target[-1]))
                here = p if p.is_absolute() else (here / p)
            continue
        out.append((prog, words[1:], here))
    return out


VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"}


def git_calls(command, cwd):
    """[(subcommand, args, repo folder)] for each git run in the line; `git -C <dir>` moves the folder."""
    calls = []
    for prog, args, here in programs(command, cwd):
        if prog != "git":
            continue
        i, d = 0, here
        while i < len(args) and args[i].startswith("-"):
            if args[i] == "-C" and i + 1 < len(args):
                p = Path(args[i + 1])
                d = p if p.is_absolute() else d / p
            i += 2 if args[i] in VALUED else 1
        if i < len(args):
            calls.append((args[i], args[i + 1:], d))
    return calls


def git_out(repo, args):
    try:
        r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def repo_top(folder):
    return git_out(folder, ["rev-parse", "--show-toplevel"])


def same(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def active_sync(root, repo):
    """The devops sync in progress in this repo (from sync/active.json), or None."""
    top = repo_top(repo)
    if not top:
        return None
    for e in (L.read_json(L.state_dir(root, "sync", "active.json"), {}) or {}).values():
        if same(e.get("path", ""), top):
            return e
    return None


def snapshot_entry(root, repo):
    """The repo's entry in the sync snapshot manifest (temp/sync-repo-state.json), or None."""
    top = repo_top(repo)
    if not top:
        return None
    m = L.read_json(Path(root) / "temp" / "sync-repo-state.json") or {}
    entries = m.get("entries") or []
    for e in entries if isinstance(entries, list) else [entries]:
        if same(e.get("Path", ""), top):
            return e
    return None
