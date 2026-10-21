"""Claude Code hook (PreToolUse, matcher Bash|PowerShell): protects branches, uncommitted work and what
leaves the machine, in every session where the devops plugin is on.

Refuses:
  - a push to a protected branch (guard.protectedBranches: main, master, develop, release/*, team/*),
    named or reached through the branch's upstream; a force push; --mirror and --prune; deleting a
    remote branch other than a sync/* one
  - a new branch from origin/<protected> without --no-track (a bare `git push` would then target it)
  - throwing away uncommitted work: reset --hard, checkout/restore of files, checkout -f, clean -f,
    switch --discard-changes, stash drop/clear (guard.protectWorkingTree)
  - stash pop/apply in a repo the sync snapshot holds (the snapshot restores by SHA)
  - resolving, staging or aborting a devops sync merge the user has not resolved yet
  - az: locking or unlocking a branch, completing or approving a PR, changing a branch policy, opening
    a PR or writing a wiki page that no approved devops plan holds
  - running `devops.py approve` or writing the approvals file: only the user approves

Settings in .claude/devops.json under "guard"; "enabled": false turns every rule off.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guardlib as G  # noqa: E402
from guardlib import L  # noqa: E402


def flags_and_positional(args):
    flags = [a for a in args if a.startswith("-")]
    pos = [a for a in args if not a.startswith("-")]
    return flags, pos


def has(flags, *names):
    return any(f == n or f.startswith(n + "=") for f in flags for n in names)


def short_flag(flags, letter):
    """`-f` given alone or combined with other short flags (`-fd`)."""
    return any(re.fullmatch(r"-[a-zA-Z]+", f) and letter in f[1:] for f in flags)


# ---------------------------------------------------------------- push

def push_targets(args, repo):
    """[(destination branch, forced, deleting)] a `git push` would write."""
    flags, pos = flags_and_positional([a for a in args if a not in ("-o", "--push-option")])
    forced = has(flags, "--force", "--force-with-lease", "--force-if-includes") or short_flag(flags, "f")
    deleting = has(flags, "--delete") or short_flag(flags, "d")
    refspecs = pos[1:] if pos else []
    current = G.git_out(repo, ["rev-parse", "--abbrev-ref", "HEAD"]) or ""
    out = []
    if not refspecs:
        up = G.git_out(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]) or ""
        if up and "/" in up:
            out.append((up.split("/", 1)[1], forced, deleting))
        if current and current != "HEAD":
            out.append((current, forced, deleting))
        return out
    for spec in refspecs:
        f = forced or spec.startswith("+")
        spec = spec.lstrip("+")
        if ":" in spec:
            src, dst = spec.split(":", 1)
            d = deleting or src == ""
        else:
            src, dst, d = spec, spec, deleting
        if dst in ("HEAD", "@"):
            dst = current
        dst = re.sub(r"^refs/heads/", "", dst)
        if dst:
            out.append((dst, f, d))
    return out


def check_push(args, repo, cfg):
    flags, _ = flags_and_positional(args)
    g = cfg["guard"]
    if has(flags, "--mirror"):
        return "push", "`git push --mirror` rewrites and deletes every branch on the remote. Push one branch by name."
    if has(flags, "--prune"):
        return "push", "`git push --prune` deletes remote branches. Push one branch by name; deleting is the user's call."
    for dst, forced, deleting in push_targets(args, repo):
        if deleting:
            if dst.lower().startswith("sync/") and not L.branch_matches(dst, g["protectedBranches"]):
                continue
            return "push", (f"this deletes the remote branch {dst}. Deleting a branch on the remote is the user's call: "
                            "they do it in Azure DevOps (Branches page) or with their own git.")
        if L.branch_matches(dst, g["protectedBranches"]):
            return "protected-branch", (f"{dst} is a protected branch (guard.protectedBranches). It changes only by completing "
                                        "a pull request. Push your own branch by name (`git push -u origin <your-branch>`) "
                                        "and open a PR. A bare push here targets it through the branch's upstream.")
        if forced and not g["forcePush"]:
            return "force-push", (f"a force push rewrites {dst} on the remote. Do not force-push; if history must be "
                                  "rewritten, ask the user (guard.forcePush in .claude/devops.json allows it for "
                                  "unprotected branches).")
    return None


# ---------------------------------------------------------------- branches and working tree

def check_new_branch(sub, args, cfg):
    """A new branch from origin/<protected> with tracking on: its upstream would be the protected branch."""
    flags, pos = flags_and_positional(args)
    if has(flags, "--no-track"):
        return None
    creating = (sub == "switch" and (short_flag(flags, "c") or short_flag(flags, "C") or has(flags, "--create", "--force-create"))) \
        or (sub == "checkout" and (short_flag(flags, "b") or short_flag(flags, "B"))) \
        or (sub == "branch" and len(pos) >= 2 and not flags) \
        or (sub == "worktree" and pos[:1] == ["add"] and (short_flag(flags, "b") or short_flag(flags, "B")))
    if not creating:
        return None
    for p in pos:
        m = re.match(r"^(?:refs/remotes/)?origin/(.+)$", p)
        if m and L.branch_matches(m.group(1), cfg["guard"]["protectedBranches"]):
            return "no-track", (f"a branch made from {p} tracks {m.group(1)}, so a bare `git push` targets the protected "
                                "branch. Add --no-track and push your branch by name.")
    return None


def check_working_tree(sub, args, repo, cfg):
    if not cfg["guard"]["protectWorkingTree"]:
        return None
    flags, pos = flags_and_positional(args)
    if sub == "stash" and pos[:1] and pos[0] in ("drop", "clear"):
        return "working-tree", (f"`git stash {pos[0]}` deletes saved work for good. Leave the stash; the user drops it "
                                "when they are sure (a devops snapshot drops its own after a good restore).")
    risky = None
    if sub == "reset" and has(flags, "--hard", "--merge", "--keep"):
        risky = "git reset --hard"
    elif sub == "checkout" and ("--" in args or "." in pos or has(flags, "--force") or short_flag(flags, "f")):
        risky = "git checkout of files (or -f)"
    elif sub == "restore" and not (has(flags, "--staged") and not has(flags, "--worktree")) and not short_flag(flags, "S"):
        risky = "git restore"
    elif sub == "switch" and (has(flags, "--discard-changes", "--force") or short_flag(flags, "f")):
        risky = "git switch --discard-changes"
    elif sub == "clean" and (has(flags, "--force") or short_flag(flags, "f")) and not (has(flags, "--dry-run") or short_flag(flags, "n")):
        risky = "git clean -f"
    if not risky:
        return None
    st = G.git_out(repo, ["status", "--porcelain"])
    if not st:
        return None  # nothing uncommitted to lose (or not a repo)
    if sub == "clean" and not any(ln.startswith("??") for ln in st.splitlines()):
        return None
    n = len(st.splitlines())
    return "working-tree", (f"{risky} would throw away uncommitted work ({n} entr{'y' if n == 1 else 'ies'} in "
                            f"{G.repo_top(repo)}). Do not discard work you did not create. Ask the user; to set it aside, "
                            "`git stash push -m <why>` keeps it.")


def check_snapshot_stash(root, sub, args, repo):
    _, pos = flags_and_positional(args)
    if sub != "stash" or not pos[:1] or pos[0] not in ("pop", "apply"):
        return None
    e = G.snapshot_entry(root, repo)
    if not e:
        return None
    return "snapshot", (f"the sync snapshot holds {e.get('Repo')}'s work as stash {str(e.get('StashSha'))[:10]}. A stash@{{n}} "
                        "index shifts; restore by SHA with the snapshot script: pwsh -File <plugin>/skills/sync-team-branches/"
                        "scripts/Invoke-RepoStateSnapshot.ps1 -Action Restore")


RESOLVING = {"add", "rm", "commit", "mergetool", "checkout-index", "restore", "reset"}


def check_sync_conflict(root, sub, args, repo):
    e = G.active_sync(root, repo)
    if not e or e.get("state") != "conflict":
        return None
    unmerged = G.git_out(repo, ["ls-files", "-u"])
    flags, _ = flags_and_positional(args)
    aborting = sub == "merge" and has(flags, "--abort", "--quit")
    ours = sub == "checkout" and has(flags, "--ours", "--theirs")
    if aborting:
        return "sync-conflict", (f"{e['repo']} has a devops sync merge on {e['branch']}. Never abort it for the user: they "
                                 "decide whether to finish or throw it away.")
    if unmerged and (ours or sub in RESOLVING):
        return "sync-conflict", (f"{e['repo']} has conflicts the user has not resolved yet. The user resolves every hunk "
                                 "and stages it; you may show the paths and explain each side. When they say done, run "
                                 f"devops.py sync verify --repo {e['repo']}.")
    return None


# ---------------------------------------------------------------- az and devops.py

def opt(args, *names):
    for i, a in enumerate(args):
        for n in names:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def check_az(root, args):
    words = [a.lower() for a in args if not a.startswith("-")][:4]
    joined = " ".join(words)
    if joined.startswith("repos ref lock") or joined.startswith("repos ref unlock"):
        return "az", "locking or unlocking a branch is the user's call, made in Azure DevOps. devops never does it."
    if joined.startswith("repos policy") and any(w in words for w in ("delete", "update", "create")):
        return "az", "branch policies are the user's to change. devops never changes them."
    if joined.startswith("repos pr set-vote"):
        return "az", "a person reviews and approves pull requests. Do not vote."
    if joined.startswith("repos pr update"):
        st = (opt(args, "--status") or "").lower()
        auto = (opt(args, "--auto-complete") or "").lower()
        if st == "completed" or auto in ("true", "yes"):
            return "az", "a person completes pull requests (and sets auto-complete). Do not complete or merge one."
        if opt(args, "--description") is not None:
            return check_pr_text(root, None, None, None, opt(args, "--description"), update=True)
    if joined.startswith("repos pr create"):
        src = opt(args, "--source-branch", "-s")
        dst = opt(args, "--target-branch", "-t")
        repo = opt(args, "--repository", "-r")
        return check_pr_text(root, repo, src, dst, opt(args, "--description", "-d") or "",
                             work_items=(opt(args, "--work-items") or "").replace(",", " ").split())
    if joined.startswith("devops wiki page create") or joined.startswith("devops wiki page update"):
        path = opt(args, "--path")
        content = opt(args, "--content")
        fp = opt(args, "--file-path")
        if fp:
            try:
                content = Path(fp).read_text(encoding="utf-8")
            except OSError:
                content = None
        return check_wiki(root, path, content)
    return None


def match_pr(root, repo, src, dst):
    """(approved item, kind) for this PR, or (None, why)."""
    src = re.sub(r"^refs/heads/", "", src or "")
    dst = re.sub(r"^refs/heads/", "", dst or "")
    near = None
    for kind in ("release-prs", "sync-prs"):
        for it in L.approved_items(root, kind):
            if it.get("op") != "create":
                continue
            if repo and repo.lower() not in (str(it.get("repo", "")).lower(), str(it.get("local", "")).lower()) \
                    and not re.fullmatch(r"[0-9a-fA-F-]{36}", repo):
                continue
            if it["source"] == src and it["target"] == dst:
                return it, kind
            if it["source"].lower() == src.lower() and it["target"].lower() == dst.lower():
                near = it
    if near:
        return None, (f"the branch names must be exactly {near['source']} -> {near['target']}: Azure DevOps refuses a "
                      "branch name in the wrong case (TF401398). Use the names the scan resolved.")
    return None, ("no approved devops plan holds this pull request. Run `devops.py release scan` (or `sync plan`), show "
                  "the plan, ask the user with AskUserQuestion, and open it with `devops.py release open` (or `sync open`).")


def check_pr_text(root, repo, src, dst, description, work_items=(), update=False):
    """A PR devops plans (protected or sync/* into protected) needs an approved plan and the full lint; any
    other PR text only the secrets check."""
    cfg = L.load_config(root)
    if update or not L.devops_pr(src, dst, cfg["guard"]["protectedBranches"]) or not cfg["guard"]["requireApproval"]:
        kind = "any" if (update or not L.devops_pr(src, dst, cfg["guard"]["protectedBranches"])) else "pr"
        problems = L.lint_outbound(description, kind)
        return ("outbound", "the PR description cannot go out: " + "; ".join(problems)) if problems else None
    it, why = match_pr(root, repo, src, dst)
    if not it:
        return "approval", why
    problems = L.lint_outbound(description, "sync-pr" if why == "sync-prs" else "pr")
    if problems:
        return "outbound", "the PR description cannot go out: " + "; ".join(problems)
    extra = [w for w in (str(x) for x in work_items) if w and w not in {str(i) for i in it.get("workItems", [])}]
    if extra:
        return "approval", (f"work item(s) {', '.join(extra)} are not in the approved plan for this PR"
                            + (" (a sync PR links only the team-sync work item)" if why == "sync-prs" else ""))
    return None


def check_wiki(root, path, content):
    cfg = L.load_config(root)
    if content is None:
        return "outbound", "the wiki page's content could not be read, so it cannot be checked. Pass it as a file the guard can read."
    env = None
    if not (path or "").strip().startswith("/Release Notes"):
        problems = L.lint_outbound(content, "any")  # not release notes: only what must never leave
        return ("outbound", "the wiki page cannot go out: " + "; ".join(problems)) if problems else None
    if cfg["guard"]["requireApproval"]:
        items = L.approved_items(root, "notes")
        ok = [it for it in items if (path or "").strip() == it["path"] and L.digest(content) == it["digest"]]
        index = [it for it in items if (path or "").strip().rstrip("/") == "/Release Notes" and it["indexEntry"] in content]
        if not ok and not index:
            return "approval", ("no approved release-notes plan holds this wiki page with this content. Render it with "
                                "`devops.py notes render`, ask the user, then `devops.py notes publish` (or send the "
                                "rendered wiki.md unchanged).")
        if ok:
            ref = (L.load_plan(root, ok[0]["_token"]) or {}).get("ref", "")  # "notes <run>"
            meta = L.read_json(L.state_dir(root, "notes", ref.split(" ", 1)[-1], "meta.json")) or {}
            env = (meta.get("facts") or {}).get("env")
    problems = L.lint_outbound(content, "wiki", env)
    return ("outbound", "the wiki page cannot go out: " + "; ".join(problems)) if problems else None


APPROVALS = re.compile(r"approvals\.jsonl", re.I)
WRITERS = re.compile(r">>?|\b(tee|out-file|add-content|set-content|sc|ac)\b", re.I)


def check_self_approval(command, progs):
    for prog, args, _ in progs:
        if prog.startswith("python") or prog in ("py", "uv"):
            if any(re.split(r"[\\/]", a)[-1].lower() == "devops.py" for a in args) and "approve" in args:
                return "approval", "only the user approves a plan: they answer Yes to your AskUserQuestion, or press Approve in the /devops pane."
    if APPROVALS.search(command) and WRITERS.search(command):
        return "approval", "the approvals file is written by the devops hook and the pane only."
    return None


def main():
    data = G.read_input()
    if not data:
        return 0
    command = str((data.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return 0
    cwd = data.get("cwd") or None
    root = L.find_root(cwd)
    cfg = L.load_config(root)
    if not cfg["guard"]["enabled"]:
        return 0
    try:
        progs = G.programs(command, cwd)
        hit = check_self_approval(command, progs)
        if hit:
            return G.refuse(root, *hit)
        for prog, args, _ in progs:
            if prog == "az":
                hit = check_az(root, args)
                if hit:
                    return G.refuse(root, *hit)
        for sub, args, repo in G.git_calls(command, cwd):
            hit = (check_push(args, repo, cfg) if sub == "push" else None) \
                or check_new_branch(sub, args, cfg) \
                or check_sync_conflict(root, sub, args, repo) \
                or check_snapshot_stash(root, sub, args, repo) \
                or check_working_tree(sub, args, repo, cfg)
            if hit:
                return G.refuse(root, *hit)
    except Exception as e:  # a guard that breaks lets the call through, and says so
        print(f"devops guard: skipped ({type(e).__name__}: {e})", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
