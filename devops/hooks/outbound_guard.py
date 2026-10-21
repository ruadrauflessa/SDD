"""Claude Code hook (PreToolUse, matcher mcp__.*): the Azure DevOps MCP tools write only what the user approved.

  - a PR from a protected or sync/* branch into a protected one (a release or sync PR) needs an approved
    devops plan that holds that repo and the exact branch names, and a description that passes the lint
    (no secrets, no `#<id>` mention, at most 4000 characters, no old `AB#<id>` on a sync PR); its work
    items must be the plan's
  - any other PR text, and any wiki page outside /Release Notes, only passes the secrets check
  - completing a PR, setting auto-complete, or voting is refused: a person does that
  - a branch with a protected name is never created, and no branch is locked or unlocked
  - a /Release Notes wiki page must be the approved rendered page, unchanged (or the index with the
    approved entry)
  - a work item is not linked to one of devops' sync PRs unless it is that PR's team-sync item

The tool names differ between versions of the Azure DevOps MCP server (repo_create_pull_request,
repo_pull_request_write action=create, ...), so the rules read the tool's last name part and its action.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_guard as GG  # noqa: E402
import guardlib as G  # noqa: E402
from guardlib import L  # noqa: E402


def ref(v):
    return re.sub(r"^refs/heads/", "", str(v or ""))


def work_item_ids(v):
    if isinstance(v, list):
        return [str(x.get("id") if isinstance(x, dict) else x) for x in v]
    return [x for x in re.split(r"[\s,;]+", str(v or "")) if x]


def sync_pr_story(root, pr_id):
    """The team-sync work item of a sync PR devops opened, or None when the PR is not one."""
    d = L.state_dir(root, "sync")
    if not d.is_dir():
        return None
    for f in d.glob("prs-*.json"):
        for r in L.read_json(f, []) or []:
            if str(r.get("prId")) == str(pr_id):
                return str(r.get("techStoryId"))
    return None


def check(root, name, ti):
    cfg = L.load_config(root)
    action = str(ti.get("action") or "").lower()
    pr_tool = "pull_request" in name and "thread" not in name and "comment" not in name
    if pr_tool and "vote" in (name + action):
        return "approval", "a person reviews and votes on pull requests. Do not vote."
    if pr_tool and ("create" in name or action == "create"):
        return GG.check_pr_text(root, ti.get("repositoryId") or ti.get("repository"), ref(ti.get("sourceRefName")),
                                ref(ti.get("targetRefName")), ti.get("description") or "",
                                work_items=work_item_ids(ti.get("workItems") or ti.get("workItemRefs")))
    if pr_tool and ("update" in name or action in ("update", "complete")):
        status = str(ti.get("status") or "").lower()
        if action == "complete" or status == "completed" or ti.get("autoComplete") in (True, "true") or ti.get("mergeStrategy"):
            return "approval", "a person completes pull requests (and sets auto-complete). Do not complete or merge one."
        if ti.get("description") is not None:
            return GG.check_pr_text(root, None, None, None, ti.get("description"), update=True)
        return None
    if "branch" in name and ("lock" in name or "lock" in action or "isLocked" in ti):
        return "approval", "locking or unlocking a branch is the user's call, made in Azure DevOps."
    if "branch" in name and ("create" in name or action == "create"):
        b = ref(ti.get("branchName") or ti.get("name"))
        if L.branch_matches(b, cfg["guard"]["protectedBranches"]):
            return "approval", (f"{b} is a protected branch name. Release and team branches are cut by the user in Azure "
                                "DevOps; devops never creates them.")
        return None
    if name.startswith("wiki") and ("create_or_update_page" in name or "page" in name and action in ("create", "update", "create_or_update")):
        return GG.check_wiki(root, ti.get("path"), ti.get("content"))
    if "link" in name and ("pull_request" in name or "pull_request" in action):
        pr = ti.get("pullRequestId")
        story = sync_pr_story(root, pr)
        wid = str(ti.get("workItemId") or ti.get("id") or "")
        if story and wid and wid != story:
            return "approval", (f"PR {pr} is a sync PR. It links only its team-sync work item ADO {story}; the old work items "
                                "stay on the PRs where the work happened.")
    return None


def main():
    data = G.read_input()
    if not data:
        return 0
    tool = str(data.get("tool_name") or "")
    if not tool.startswith("mcp__"):
        return 0
    name = tool.split("__")[-1].lower()
    if not re.search(r"pull_request|wiki|branch|link", name):
        return 0
    root = L.find_root(data.get("cwd") or None)
    cfg = L.load_config(root)
    if not cfg["guard"]["enabled"]:
        return 0
    try:
        hit = check(root, name, data.get("tool_input") or {})
    except Exception as e:  # a guard that breaks lets the call through, and says so
        print(f"devops guard: skipped ({type(e).__name__}: {e})", file=sys.stderr)
        return 0
    return G.refuse(root, *hit) if hit else 0


if __name__ == "__main__":
    sys.exit(main())
