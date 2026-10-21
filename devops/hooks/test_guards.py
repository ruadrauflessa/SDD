"""Self-check for the devops guard hooks, run as Claude Code runs them: JSON on stdin, exit 2 = refused.

    python devops/hooks/test_guards.py      (needs git; real repos in a temp folder)
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import devopslib as L  # noqa: E402

PY = sys.executable


def hook(name, data):
    r = subprocess.run([PY, str(HERE / name), "pre"], input=json.dumps(data), capture_output=True, text=True)
    return r.returncode, r.stderr + r.stdout


def bash(cwd, command):
    return hook("git_guard.py", {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


def edit(cwd, path):
    return hook("edit_guard.py", {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "x"}, "cwd": str(cwd)})


def mcp(cwd, tool, ti):
    return hook("outbound_guard.py", {"tool_name": f"mcp__ado__{tool}", "tool_input": ti, "cwd": str(cwd)})


def sh(args, cwd):
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"{args}: {r.stderr}"
    return r.stdout.strip()


def _force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def setup(t):
    ws = t / "ws"
    (ws / "projects").mkdir(parents=True)
    (ws / ".claude").mkdir()
    (ws / ".claude" / "devops.json").write_text("{}")
    origin = t / "origin.git"
    sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)], t)
    repo = ws / "projects" / "app"
    sh(["git", "clone", "-q", str(origin), str(repo)], t)
    for k, v in (("user.email", "t@example.com"), ("user.name", "T"), ("commit.gpgsign", "false")):
        sh(["git", "config", k, v], repo)
    (repo / "a.txt").write_text("base\n")
    sh(["git", "add", "."], repo)
    sh(["git", "commit", "-qm", "base"], repo)
    sh(["git", "push", "-q", "-u", "origin", "HEAD:main"], repo)
    for b in ("team/1.1.0", "dev/ann/x"):
        sh(["git", "push", "-q", "origin", f"HEAD:{b}"], repo)
    sh(["git", "fetch", "-q"], repo)
    return ws, repo


def expect(got, code, *words):
    rc, text = got
    assert rc == code, f"expected {code}, got {rc}: {text}"
    for w in words:
        assert w in text, f"{w!r} not in {text!r}"


def check_push(ws, repo):
    expect(bash(repo, "git push origin HEAD:team/1.1.0"), 2, "protected branch")
    expect(bash(repo, "git push origin HEAD:refs/heads/Release/1.0"), 2, "protected branch")
    expect(bash(repo, "git push -u origin dev/ann/x"), 0)
    expect(bash(repo, "git push"), 2, "upstream")                       # main tracks origin/main
    expect(bash(ws, f"cd {repo} && git push origin HEAD:main"), 2)      # the cd is followed
    expect(bash(ws, f'git -C "{repo}" push origin main'), 2)
    expect(bash(repo, "git push --force origin dev/ann/x"), 2, "force")
    expect(bash(repo, "git push origin +dev/ann/x"), 2, "force")
    expect(bash(repo, "git push --force-with-lease origin dev/ann/x"), 2, "force")
    expect(bash(repo, "git push origin --delete dev/ann/x"), 2, "user's call")
    expect(bash(repo, "git push origin :sync/ann/1.1.0_to_1.2.0"), 0)    # a stale sync branch may go
    expect(bash(repo, "git push --mirror"), 2)
    expect(bash(repo, "cat > notes.sh <<'EOF'\ngit push origin main\nEOF"), 0)   # a heredoc body is data
    expect(bash(repo, 'echo "git push origin main"'), 0)                  # git is not the program
    sh(["git", "switch", "-q", "-c", "dev/ann/y", "--no-track", "origin/main"], repo)
    expect(bash(repo, "git push"), 0)                                     # no upstream: pushes its own name
    sh(["git", "switch", "-q", "main"], repo)
    (ws / ".claude" / "devops.json").write_text(json.dumps({"guard": {"enabled": False}}))
    expect(bash(repo, "git push origin HEAD:team/1.1.0"), 0)
    (ws / ".claude" / "devops.json").write_text(json.dumps({"guard": {"protectedBranches": ["prod"]}}))
    expect(bash(repo, "git push origin HEAD:team/1.1.0"), 0)
    expect(bash(repo, "git push origin HEAD:prod"), 2)
    (ws / ".claude" / "devops.json").write_text("{}")


def check_branches_and_tree(ws, repo):
    expect(bash(repo, "git switch -c sync/ann/1_to_2 origin/team/1.1.0"), 2, "--no-track")
    expect(bash(repo, "git switch -c sync/ann/1_to_2 --no-track origin/team/1.1.0"), 0)
    expect(bash(repo, "git checkout -b feat origin/dev/ann/x"), 0)
    expect(bash(repo, "git worktree add -b x ../wt origin/main"), 2, "--no-track")
    expect(bash(repo, "git reset --hard"), 0)                             # clean: nothing to lose
    (repo / "a.txt").write_text("mine\n")
    expect(bash(repo, "git reset --hard origin/main"), 2, "uncommitted")
    expect(bash(repo, "git checkout -- a.txt"), 2)
    expect(bash(repo, "git restore a.txt"), 2)
    expect(bash(repo, "git restore --staged a.txt"), 0)
    expect(bash(repo, "git switch --discard-changes main"), 2)
    expect(bash(repo, "git stash push -m keep"), 0)
    expect(bash(repo, "git stash drop"), 2, "deletes saved work")
    sh(["git", "checkout", "--", "a.txt"], repo)
    (repo / "new.txt").write_text("n")
    expect(bash(repo, "git clean -fd"), 2)
    expect(bash(repo, "git clean -n"), 0)
    (repo / "new.txt").unlink()
    expect(bash(repo, "git clean -fd"), 0)
    # the snapshot holds this repo: a stash@{n} restore is refused
    (ws / "temp").mkdir()
    (ws / "temp" / "sync-repo-state.json").write_text(json.dumps({"entries": [{"Repo": "app", "Path": str(repo), "StashSha": "abc"}]}))
    expect(bash(repo, "git stash pop"), 2, "by SHA")
    expect(bash(repo, "git stash list"), 0)
    (ws / "temp" / "sync-repo-state.json").unlink()
    expect(bash(repo, "git stash pop"), 0)


def check_sync_conflict(ws, repo):
    sh(["git", "switch", "-q", "-c", "side"], repo)
    (repo / "a.txt").write_text("side\n")
    sh(["git", "commit", "-qam", "side"], repo)
    sh(["git", "switch", "-q", "-c", "sync/ann/x_to_y", "main"], repo)
    (repo / "a.txt").write_text("main\n")
    sh(["git", "commit", "-qam", "main side"], repo)
    subprocess.run(["git", "merge", "side"], cwd=str(repo), capture_output=True)
    L.write_json(L.state_dir(ws, "sync", "active.json"), {"app": {"repo": "app", "path": str(repo), "branch": "sync/ann/x_to_y",
                                                                  "state": "conflict", "conflicts": ["a.txt"]}})
    expect(bash(repo, "git checkout --ours a.txt"), 2, "user resolves")
    expect(bash(repo, "git add a.txt"), 2, "user resolves")
    expect(bash(repo, "git merge --abort"), 2, "Never abort")
    expect(bash(repo, "git diff"), 0)
    expect(edit(repo, repo / "a.txt"), 2, "merge conflict")
    expect(edit(repo, repo / "other.txt"), 0)
    (repo / "a.txt").write_text("both\n")
    sh(["git", "add", "a.txt"], repo)                                     # the user staged their resolution
    expect(bash(repo, "git add a.txt"), 0)
    expect(edit(repo, repo / "a.txt"), 0)
    sh(["git", "commit", "-qm", "merge"], repo)
    L.state_dir(ws, "sync", "active.json").unlink()


def approved_release_plan(ws):
    item = {"op": "create", "org": "Org", "project": "Proj", "repo": "Gateway", "local": "Gateway", "source": "Team/1.1.0",
            "target": "Release/1.1.0", "title": "Merge", "description": "ok", "workItems": [12345]}
    tok = L.save_plan(ws, "release-prs", [item], "Open 1 release PR")
    return tok


def check_outbound(ws, repo):
    pr = {"repositoryId": "Gateway", "sourceRefName": "refs/heads/Team/1.1.0", "targetRefName": "refs/heads/Release/1.1.0",
          "title": "Merge", "description": "Fixes [ADO 12345](u)", "workItems": "12345"}
    expect(mcp(ws, "repo_create_pull_request", pr), 2, "no approved devops plan")
    expect(bash(ws, "az repos pr create -r Gateway -s Team/1.1.0 -t Release/1.1.0 --description ok"), 2, "no approved devops plan")
    tok = approved_release_plan(ws)
    expect(mcp(ws, "repo_create_pull_request", pr), 2)                    # planned, not approved yet
    L.approve(ws, tok, "test")
    expect(mcp(ws, "repo_create_pull_request", pr), 0)
    expect(mcp(ws, "repo_pull_request_write", dict(pr, action="create")), 0)
    expect(bash(ws, "az repos pr create -r Gateway -s Team/1.1.0 -t Release/1.1.0 --description ok --work-items 12345"), 0)
    expect(mcp(ws, "repo_create_pull_request", dict(pr, sourceRefName="refs/heads/team/1.1.0")), 2, "exactly Team/1.1.0")
    expect(mcp(ws, "repo_create_pull_request", dict(pr, description="Fixes #12345")), 2, "mention")
    expect(mcp(ws, "repo_create_pull_request", dict(pr, workItems="12345 999")), 2, "999")
    expect(mcp(ws, "repo_create_pull_request", dict(pr, sourceRefName="refs/heads/dev/ann/x", targetRefName="refs/heads/team/1.1.0",
                                                     description="My fix for #12")), 0)  # a developer's PR: not devops'
    expect(mcp(ws, "repo_create_pull_request", dict(pr, sourceRefName="refs/heads/dev/ann/x", targetRefName="refs/heads/team/1.1.0",
                                                     description="conn: Server=a;Password=hunter22")), 2, "connection string")
    expect(mcp(ws, "repo_update_pull_request", {"pullRequestId": 5, "status": "Completed"}), 2, "completes")
    expect(mcp(ws, "repo_update_pull_request", {"pullRequestId": 5, "autoComplete": True}), 2)
    expect(mcp(ws, "repo_update_pull_request", {"pullRequestId": 5, "title": "x"}), 0)
    expect(mcp(ws, "repo_vote_pull_request", {"pullRequestId": 5, "vote": 10}), 2, "vote")
    expect(mcp(ws, "repo_pull_request_thread_write", {"action": "create", "content": "x"}), 0)
    expect(mcp(ws, "repo_create_branch", {"branchName": "release/2.0.0"}), 2, "protected branch name")
    expect(mcp(ws, "repo_create_branch", {"branchName": "dev/ann/z"}), 0)
    expect(bash(ws, "az repos ref lock --name heads/team/1.0.0"), 2)
    expect(bash(ws, "az repos pr update --id 5 --status completed"), 2)
    expect(bash(ws, "az repos pr set-vote --id 5 --vote approve"), 2)
    # wiki: only the approved page, unchanged
    page = "# Release 1.1.0 — QA — 2026-10-21\n\nbody\n"
    run = "20261021-120000"
    tok = L.save_plan(ws, "notes", [{"op": "wiki", "org": "Org", "project": "Proj", "path": "/Release Notes/Release 1.1.0 [QA] - 2026-10-21",
                                     "digest": L.digest(page), "indexEntry": "[Release 1.1.0 [QA] - 2026-10-21]("}], "Publish", {"ref": f"notes {run}"})
    L.write_json(L.state_dir(ws, "notes", run, "meta.json"), {"run": run, "facts": {"env": "QA"}, "token": tok})
    wiki = {"path": "/Release Notes/Release 1.1.0 [QA] - 2026-10-21", "content": page.replace("\n", "\r\n")}
    expect(mcp(ws, "wiki_create_or_update_page", wiki), 2, "no approved release-notes plan")
    L.approve(ws, tok, "test")
    expect(mcp(ws, "wiki_create_or_update_page", wiki), 0)
    expect(mcp(ws, "wiki_create_or_update_page", dict(wiki, content=page + "edited\n")), 2)
    expect(mcp(ws, "wiki_create_or_update_page", {"path": "/Release Notes", "content": "## Releases\n- [Release 1.1.0 [QA] - 2026-10-21](/x)"}), 0)
    expect(mcp(ws, "wiki_create_or_update_page", {"path": "/Team/Notes", "content": "anything"}), 0)
    expect(mcp(ws, "wiki_create_or_update_page", {"path": "/Team/Notes", "content": "-----BEGIN RSA PRIVATE KEY-----"}), 2, "private key")
    # a sync PR links only its team-sync item
    L.write_json(L.state_dir(ws, "sync", "prs-team_1.1.0-to-team_1.2.0.json"), [{"repo": "app", "prId": 102, "techStoryId": 9001}])
    expect(mcp(ws, "wit_link_work_item_to_pull_request", {"pullRequestId": 102, "workItemId": 4471}), 2, "9001")
    expect(mcp(ws, "wit_link_work_item_to_pull_request", {"pullRequestId": 102, "workItemId": 9001}), 0)
    expect(mcp(ws, "wit_work_item_link_write", {"action": "link_to_pull_request", "pullRequestId": 77, "workItemId": 1}), 0)


def check_self_approval(ws):
    expect(bash(ws, "python devops/scripts/devops.py approve --token abc"), 2, "only the user approves")
    expect(bash(ws, "echo {} >> .claude/devops/approvals.jsonl"), 2)
    expect(bash(ws, "cat .claude/devops/approvals.jsonl"), 0)
    expect(bash(ws, "python devops/scripts/devops.py status --json"), 0)
    expect(bash(ws, "python devops/scripts/devops.py reviews post --project P --id 5"), 2, "under the user's own name")
    expect(bash(ws, "python3 devops.py reviews vote --project P --id 5 --vote approve"), 2, "Reviews tab")
    expect(bash(ws, "echo [] | python devops.py reviews save --key k"), 2)
    expect(bash(ws, "python devops/scripts/devops.py reviews list --all"), 0)
    expect(bash(ws, "python devops/scripts/devops.py reviews pack --project P --id 5"), 0)


def check_edits(ws, repo):
    expect(edit(ws, L.state_dir(ws, "plans", "abc.json")), 2, "devops state")
    expect(edit(ws, L.state_dir(ws, "notes", "r1", "texts.json")), 0)
    expect(edit(ws, ws / "scripts" / "run-stack.ps1"), 0)                 # sdd's edit guard holds launchers
    notes = ws / "documents" / "release-notes"
    notes.mkdir(parents=True)
    f = notes / "release-notes-20261021-1.md"
    f.write_text("x")
    L.write_json(L.state_dir(ws, "notes", "r2", "meta.json"), {"stage": "published", "file": str(f), "url": "u"})
    expect(edit(ws, f), 2, "published")
    expect(edit(ws, notes / "release-notes-20261021-2.md"), 0)


def check_approval_hook(ws):
    tok = L.save_plan(ws, "release-prs", [{"op": "create", "x": 1}], "Open 1 release PR")
    q = f"Open 1 release PR? (plan {tok})"
    data = {"tool_name": "AskUserQuestion", "cwd": str(ws),
            "tool_input": {"questions": [{"question": q, "header": "Approve", "options": [], "multiSelect": False}],
                           "answers": {q: "No"}}}
    r = subprocess.run([PY, str(HERE / "approval_hook.py"), "post"], input=json.dumps(data), capture_output=True, text=True)
    assert r.returncode == 0 and not L.approval(ws, tok)
    data["tool_input"]["answers"] = {}
    data["tool_response"] = f'User has answered your questions: "{q}"="Yes, go ahead". You can now continue.'
    r = subprocess.run([PY, str(HERE / "approval_hook.py"), "post"], input=json.dumps(data), capture_output=True, text=True)
    assert r.returncode == 0 and L.approval(ws, tok)["via"] == "question" and tok in r.stdout, r.stdout + r.stderr
    tok2 = L.save_plan(ws, "release-prs", [{"op": "create", "x": 2}], "Other")
    data["tool_input"] = {"questions": [{"question": "Unrelated?"}], "answers": {"Unrelated?": "Yes"}}
    data["tool_response"] = ""
    subprocess.run([PY, str(HERE / "approval_hook.py"), "post"], input=json.dumps(data), capture_output=True, text=True)
    assert not L.approval(ws, tok2)


def main():
    t = Path(tempfile.mkdtemp(prefix="devops-guard-"))
    try:
        ws, repo = setup(t)
        check_push(ws, repo)
        check_branches_and_tree(ws, repo)
        check_sync_conflict(ws, repo)
        check_outbound(ws, repo)
        check_self_approval(ws)
        check_edits(ws, repo)
        check_approval_hook(ws)
        log = L.read_jsonl(L.state_dir(ws, "guard.jsonl"))
        assert log and {"protected-branch", "force-push", "working-tree", "approval", "outbound"} <= {r["rule"] for r in log}
    finally:
        for wait in (0, 0.2, 1, 3):
            time.sleep(wait)
            try:
                shutil.rmtree(t, onerror=_force)
                break
            except OSError:
                continue
        assert not t.exists(), f"could not remove {t}"
    print("guards: ok")


if __name__ == "__main__":
    main()
