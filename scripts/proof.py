"""Proof for gates: a gate that says "the test fails" or "the tests pass" passes only on a recorded run.

Each run is kept in workitem.json "runs": the gate, the command, the repo, the exit code, the last
lines of output, and a fingerprint of the repo's working files (`tree`) at the time. flows.json
"proofs" says what each gate needs. A gate marked `current` needs runs made on the files as they are
now: change the code after the run and the proof no longer counts.

The fingerprint is git's tree id of the working files, ignored files left out, made with a scratch
index — so a commit of the same files keeps the proof, and an edit does not. The real index is never
touched.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

TAIL = 40
KEEP_RUNS = 80


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(args, cwd, env=None):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def content_tree(repo_dir):
    """Git's tree id for the files in the worktree as they are now (untracked included, ignored not)."""
    real = Path(_git(["rev-parse", "--git-path", "index"], repo_dir))
    real = real if real.is_absolute() else Path(repo_dir) / real
    with tempfile.TemporaryDirectory() as t:
        idx = Path(t) / "index"
        if real.is_file():
            shutil.copy2(real, idx)  # its stat cache makes `add -A` fast
        env = {**os.environ, "GIT_INDEX_FILE": str(idx)}
        if not real.is_file():
            _git(["read-tree", "HEAD"], repo_dir, env)
        _git(["add", "-A"], repo_dir, env)
        return _git(["write-tree"], repo_dir, env)


def base_commit(repo_dir, base):
    return _git(["merge-base", "HEAD", f"origin/{base}"], repo_dir)


def changed(repo_dir, base):
    """The worktree's files differ from its base branch: this repo carries part of the change."""
    return content_tree(repo_dir) != _git(["rev-parse", f"{base_commit(repo_dir, base)}^{{tree}}"], repo_dir)


def run_command(cmd, cwd, timeout):
    """-> (exit code or None on a timeout, output). Runs through the shell, as typed in a terminal."""
    try:
        r = subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out + f"\n[timed out after {timeout}s]"


def tail(text, n=TAIL):
    return "\n".join((text or "").rstrip().splitlines()[-n:])


def matches(code, expect):
    return code is not None and ((code == 0) if expect == "pass" else (code != 0))


def record(data, entry):
    data["runs"] = (data.get("runs") or [])[-(KEEP_RUNS - 1):] + [entry]
    return entry


def run(data, repo, repo_dir, gate, cmd, expect, repeat=1, suite=False, timeout=1800):
    """Run `cmd` `repeat` times; it passes when every run ends as `expect` says. Recorded either way."""
    results = []
    for _ in range(max(1, repeat)):
        code, out = run_command(cmd, repo_dir, timeout)
        results.append((code, out))
        if not matches(code, expect):
            break
    ok = len(results) == max(1, repeat) and all(matches(c, expect) for c, _ in results)
    last = results[-1]
    return record(data, {"at": now(), "kind": "run", "gate": gate, "repo": repo, "command": cmd,
                         "expect": expect, "repeat": len(results), "suite": bool(suite),
                         "exits": [c for c, _ in results], "ok": ok, "tree": content_tree(repo_dir),
                         "tail": tail(last[1])})


def _touch_after(path, after):
    """Give a swapped file a time stamp later than anything built before, and later than `after`, so an
    incremental build (MSBuild, Python's bytecode cache, ...) sees the change even within one second."""
    t = max(time.time() + 1, after + 2)
    os.utime(path, (t, t))
    return t


def revert_check(data, repo, repo_dir, base, gate, cmd, fix_paths, timeout=1800):
    """The test guards the defect: with the fix files put back to the base branch the test fails, with
    the fix it passes again. The fix files are restored byte for byte in every case, with fresh time
    stamps so a build tool does not reuse what it built from the other version."""
    base_sha = base_commit(repo_dir, base)
    before = content_tree(repo_dir)
    saved, stamp = {}, 0
    for rel in fix_paths:
        p = Path(repo_dir) / rel
        saved[rel] = p.read_bytes() if p.is_file() else None
    try:
        for rel in fix_paths:
            p = Path(repo_dir) / rel
            r = subprocess.run(["git", "show", f"{base_sha}:{Path(rel).as_posix()}"], cwd=str(repo_dir),
                               capture_output=True)
            if r.returncode == 0:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(r.stdout)
                stamp = _touch_after(p, stamp)
            elif p.exists():
                p.unlink()  # a file the fix added
        without, out_without = run_command(cmd, repo_dir, timeout)
    finally:
        for rel, content in saved.items():
            p = Path(repo_dir) / rel
            if content is None:
                if p.exists():
                    p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
                stamp = _touch_after(p, stamp)
    after = content_tree(repo_dir)
    if after != before:
        raise RuntimeError(f"{repo}: the files did not come back as they were after the revert check. "
                           "Check `git status` in the worktree before anything else")
    with_fix, out_with = run_command(cmd, repo_dir, timeout)
    ok = matches(without, "fail") and matches(with_fix, "pass")
    return record(data, {"at": now(), "kind": "revert-check", "gate": gate, "repo": repo, "command": cmd,
                         "fix": list(fix_paths), "exits": [without, with_fix], "ok": ok, "tree": after,
                         "tail": tail(f"--- without the fix (exit {without}) ---\n{tail(out_without, 20)}\n"
                                      f"--- with the fix (exit {with_fix}) ---\n{tail(out_with, 20)}")})


# ---------------------------------------------------------------- tasks.md (spec flow)

TASK = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(\d+)\.\s*(.+)$")
FIELD = re.compile(r"^\s+-\s*(Files|Verify|Repo|Traces to)\s*:\s*(.*)$", re.I)


def parse_tasks(text):
    """[{n, title, done, files, verify, repo}] from tasks.md; `verify` is the raw Verify line. Lines under
    a "## Not doing" heading are work left out on purpose, not tasks."""
    tasks, cur, skip = [], None, False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            cur, skip = None, bool(re.match(r"##\s*not doing\b", line, re.I))
            continue
        m = None if skip else TASK.match(line)
        if m:
            cur = {"n": int(m.group(2)), "title": m.group(3).strip(), "done": m.group(1) != " ",
                   "files": "", "verify": "", "repo": ""}
            tasks.append(cur)
            continue
        f = FIELD.match(line)
        if cur and f:
            cur[f.group(1).lower().split()[0]] = f.group(2).strip()
    return tasks


def verify_command(task):
    """The command of a Verify line written as `cmd` (first backticked span at its start), else None:
    an observable outcome, checked by hand."""
    m = re.match(r"\s*`([^`]+)`", task["verify"] or "")
    return m.group(1).strip() if m else None


def task_repo(task, repos):
    """The repo a task's command runs in: its Repo field, else the repo its Files path names
    (src/<Repo>/… or <Repo>/…), else the only repo. None when that is not clear."""
    names = list(repos)
    want = re.sub(r"[`\s]", "", task.get("repo") or "")
    if want:
        return want if want in repos else None
    for name in names:
        if re.search(rf"(^|[`\s/\\]){re.escape(name)}[/\\]", task.get("files") or ""):
            return name
    return names[0] if len(names) == 1 else None


def verify(data, repo_dirs, tasks, gate, timeout=1800):
    """Run every task's Verify command in its repo. One "verify" record per repo: ok when each of its
    commands exits 0 and no task's repo is unclear. -> (records, manual tasks, unclear tasks)."""
    per, manual, unclear = {r: [] for r in repo_dirs}, [], []
    for t in tasks:
        cmd = verify_command(t)
        if not cmd:
            manual.append(t)
            continue
        repo = task_repo(t, repo_dirs)
        if repo is None:
            unclear.append(t)
            continue
        code, out = run_command(cmd, repo_dirs[repo][0], timeout)
        per[repo].append({"task": t["n"], "command": cmd, "exit": code, "ok": matches(code, "pass"),
                          "tail": tail(out, 15)})
    recs = []
    for repo, res in per.items():
        d = repo_dirs[repo][0]
        if not Path(d).exists():
            continue
        recs.append(record(data, {"at": now(), "kind": "verify", "gate": gate, "repo": repo, "tasks": res,
                                  "ok": all(x["ok"] for x in res) and not unclear, "tree": content_tree(d),
                                  "manual": [t["n"] for t in manual], "unclear": [t["n"] for t in unclear]}))
    return recs, manual, unclear


# ---------------------------------------------------------------- what a gate still needs

def need_text(need):
    if need.get("kind") == "revert-check":
        return "a revert check (env.py revert-check)"
    if need.get("kind") == "verify":
        return "every task's Verify command passing (env.py verify)"
    bits = [f"a run expected to {need.get('expect', 'pass')}"]
    if need.get("repeat", 1) > 1:
        bits.append(f"{need['repeat']} times in a row (--repeat {need['repeat']})")
    if need.get("suite"):
        bits.append("of the full test suite (--suite)")
    return " ".join(bits)


def satisfies(r, gate, need):
    if r.get("gate") != gate or not r.get("ok"):
        return False
    kind = need.get("kind", "run")
    if r.get("kind", "run") != kind:
        return False
    if kind == "run":
        return (r.get("expect") == need.get("expect", "pass") and r.get("repeat", 1) >= need.get("repeat", 1)
                and (r.get("suite") or not need.get("suite")))
    return True


def missing(data, gate, rule, repo_dirs, trees=None):
    """What `gate` still lacks under `rule` ({"current": bool, "needs": [...]}), as sentences.
    `repo_dirs` {repo: (dir, base)}: for a `current` gate, every repo that carries a change must have
    each need met by a run on its files as they are now. Otherwise one matching run anywhere will do."""
    runs = data.get("runs") or []
    out = []
    if not rule.get("current"):
        for need in rule["needs"]:
            if not any(satisfies(r, gate, need) for r in runs):
                out.append(f"'{gate}' needs {need_text(need)}")
        return out
    trees = trees if trees is not None else {}
    for repo, (d, base) in repo_dirs.items():
        if not Path(d).exists():
            continue
        if repo not in trees:
            trees[repo] = content_tree(d) if changed(d, base) else None
        if trees[repo] is None:
            continue  # this repo carries no change
        for need in rule["needs"]:
            if not any(satisfies(r, gate, need) and r.get("repo") == repo and r.get("tree") == trees[repo]
                       for r in runs):
                stale = any(satisfies(r, gate, need) and r.get("repo") == repo for r in runs)
                out.append(f"{repo}: '{gate}' needs {need_text(need)}"
                           + (" on the code as it is now (it changed since the last one)" if stale else ""))
    return out

