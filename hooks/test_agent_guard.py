"""Self-check for agent_guard.py: python test_agent_guard.py"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("agent_guard.py")


def run(command, agent="sdd:investigator", agent_id="a1", tool="Bash"):
    data = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}
    if agent:
        data["agent_type"] = agent
    if agent_id:
        data["agent_id"] = agent_id
    p = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(data),
                       capture_output=True, text=True)
    return p.returncode


ALLOWED = [
    "git log -S \"Foo\" --oneline",
    "git -C 'C:/ws/.claude/worktrees/5-x/src/Repo' blame -L 10,40 src/A.cs",
    "git -C \"C:\\ws\\with space\\src\\Repo\" show HEAD~1:src/A.cs",
    "git --no-pager diff origin/team/1.1.0...HEAD",
    "git grep -n Foo && git status --short",
    "git branch", "git branch -a", "git branch --show-current", "git branch --contains abc123",
    "git tag", "git tag -l 'v1.*'",
    "git stash list", "git stash show -p",
    "git worktree list", "git reflog", "git remote -v", "git remote get-url origin",
    "git config user.email", "git config --get remote.origin.url",
    "graphify query \"where is Foo\" --graph C:/ws/graph/graph.json",
    "grep -rn git src/",
    "cat .gitignore | grep git",
    "git log --format=%H -1 | xargs git show",
    "echo $(git rev-parse HEAD)",
]
BLOCKED = [
    "git commit -m 'x'", "git push origin HEAD", "git checkout main", "git switch -c x",
    "git stash", "git stash push", "git stash pop", "git reset --hard HEAD~1",
    "git restore src/A.cs", "git add .", "git rm a", "git clean -fd", "git fetch origin",
    "git pull", "git merge x", "git rebase main", "git cherry-pick abc", "git revert abc",
    "git apply p.diff", "git branch new-branch", "git branch -D old", "git tag v1",
    "git tag -d v1", "git worktree add ../x", "git worktree remove x", "git reflog expire --all",
    "git config user.email a@b", "git config --unset user.email", "git remote add x url",
    "git -C C:/ws/src/Repo commit -am x",
    "git log -1 && git commit --amend --no-edit",
    "git log -1;git checkout .",
    "git status\ngit stash",
    "cd src/Repo && git reset --hard",
    "git log | xargs git rm",
    "\"C:/Program Files/Git/bin/git.exe\" checkout x",
    "& \"C:\\Program Files\\Git\\bin\\git.exe\" -C src/Repo stash",
    "env GIT_DIR=x git commit -m y",
    "git some-unknown-thing",
]

fails = []
for c in ALLOWED:
    if run(c) != 0:
        fails.append(f"blocked but should pass: {c!r}")
for c in BLOCKED:
    if run(c) != 2:
        fails.append(f"passed but should block: {c!r}")
    if run(c, agent="sdd:skeptic", tool="PowerShell") != 2:
        fails.append(f"skeptic passed: {c!r}")
# only this plugin's agents, and only inside a sub-agent
for c in ("git commit -m x", "git push"):
    if run(c, agent=None, agent_id=None) != 0:
        fails.append(f"main conversation blocked: {c!r}")
    if run(c, agent="general-purpose") != 0:
        fails.append(f"other agent blocked: {c!r}")
    if run(c, agent="sdd:investigator", agent_id=None) != 0:
        fails.append(f"--agent main thread blocked: {c!r}")
if run("git log", agent="investigator") != 0 or run("git commit", agent="investigator") != 2:
    fails.append("unprefixed agent name not recognised")

print("\n".join(fails) or "ok")
sys.exit(1 if fails else 0)
