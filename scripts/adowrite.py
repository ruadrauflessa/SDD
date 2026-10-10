"""Rev-tested writes to Azure DevOps work items: the claim, the QA hand-over, the sprint move, a comment.

Every patch starts with a JSON Patch `test /rev` op, so a write never overwrites a change someone
else made since the read. On HTTP 412 it reads the item again, decides again from what is there
now, and retries (3 tries in all). The decisions are plain functions of the item's fields, so they
are tested without ADO. spec.py claim / handover / sprint / comment are the commands.
"""
import re
import subprocess
import urllib.parse
from datetime import date, datetime

from sddlib import ado, get_items, org_url

PATCH = "application/json-patch+json"
ASSIGNED, STATE, COLUMN = "System.AssignedTo", "System.State", "Custom.BoardColumnTitle"
TAGS, ITERATION, TYPE, PROJECT = "System.Tags", "System.IterationPath", "System.WorkItemType", "System.TeamProject"
ROOT_CAUSE_DETAILS, RESOLUTION, ROOT_CAUSE = ("Custom.RootCauseDetails", "Microsoft.VSTS.Common.Resolution",
                                              "Microsoft.VSTS.CMMI.RootCause")
READ = [TYPE, PROJECT, "System.Title", STATE, ASSIGNED, COLUMN, TAGS, ITERATION]
DONE_STATES = ("Resolved", "Closed", "Done", "Removed")
# `#80459` in ADO text is a mention: ADO posts "Mentioned in" back onto that item. `AB#80459` is not.
MENTION = re.compile(r"(?<![\w#&/])#\d{3,}\b")


class Refused(Exception):
    """The item's state says stop: a person decides. The message says what to ask."""


class Conflict(Exception):
    """Someone else kept changing the item while we wrote (HTTP 412 on every try)."""


def mentions(text):
    return MENTION.findall(text or "")


def refuse_mentions(text, what):
    found = mentions(text)
    if found:
        raise Refused(f"{what} names {', '.join(found)}. ADO reads `#<id>` as a mention and posts a comment "
                      f"onto that item. Write `ADO {found[0][1:]}` instead (AB#<id> stays fine in a commit or PR title).")


def my_email():
    r = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
    return (r.stdout or "").strip()


def assignee(fields):
    """(email, display) of System.AssignedTo; ("", "") when unassigned — ADO leaves the field out."""
    v = fields.get(ASSIGNED)
    if isinstance(v, dict):
        return (v.get("uniqueName") or "").lower(), v.get("displayName") or v.get("uniqueName") or ""
    m = re.search(r"<([^>]+)>", v or "")
    return ((m.group(1) if m else (v or "")).lower(), v or "")


def add(field, value):
    return {"op": "add", "path": f"/fields/{field}", "value": value}


# ---------------------------------------------------------------- decisions

def claim_ops(fields, me, reopen=False):
    """The claim: assigned to me, Active, Dev In Progress, written together. Never takes an item from
    someone else; stops on an item that is already resolved or closed."""
    who, display = assignee(fields)
    if who and who != me.lower():
        raise Refused(f"assigned to {display}. Never take a work item from someone else: ask the user")
    state = fields.get(STATE, "")
    if state in DONE_STATES and not reopen:
        raise Refused(f"state is {state}: it is already fixed, or this is a regression. Ask the user; after their "
                      "yes, run claim again with --reopen")
    ops = [] if who else [add(ASSIGNED, me)]
    if state != "Active":
        ops.append(add(STATE, "Active"))
    if fields.get(COLUMN) != "Dev In Progress":
        ops.append(add(COLUMN, "Dev In Progress"))
    return ops


def handover_ops(fields, tag=None, root_cause_details=None, resolution=None, root_cause=None):
    """The hand-over to QA: Resolved with Dev Completed, written together. An Issue needs Root Cause
    Details and Resolution; a Bug takes them too. A tag is appended to the tags, never replaces them."""
    if fields.get(TYPE) == "Issue" and not (root_cause_details and resolution):
        raise Refused("an Issue needs Root Cause Details and Resolution: pass --root-cause-details-file and "
                      "--resolution-file")
    refuse_mentions(root_cause_details, "Root Cause Details")
    refuse_mentions(resolution, "Resolution")
    ops = []
    if fields.get(COLUMN) != "Dev Completed":
        ops.append(add(COLUMN, "Dev Completed"))
    if fields.get(STATE) != "Resolved":
        ops.append(add(STATE, "Resolved"))
    if root_cause_details:
        ops.append(add(ROOT_CAUSE_DETAILS, root_cause_details))
    if resolution:
        ops.append(add(RESOLUTION, resolution))
    if root_cause:
        ops.append(add(ROOT_CAUSE, root_cause))
    if tag:
        tags = [t.strip() for t in (fields.get(TAGS) or "").split(";") if t.strip()]
        if tag not in tags:
            ops.append(add(TAGS, "; ".join(tags + [tag])))
    return ops


def iteration_ops(fields, path):
    return [] if fields.get(ITERATION) == path else [add(ITERATION, path)]


def _day(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date() if s else None


def pick_iteration(node, today):
    """The iteration path whose dates hold `today`, from the classification-node tree; the shortest
    range wins (a sprint inside a release). Node paths look like \\Project\\Iteration\\2026\\Sprint 18;
    System.IterationPath wants Project\\2026\\Sprint 18."""
    best = None

    def walk(n):
        nonlocal best
        at = n.get("attributes") or {}
        start, end = _day(at.get("startDate")), _day(at.get("finishDate"))
        if start and end and start <= today <= end and (best is None or end - start < best[0]):
            best = (end - start, n.get("path") or "")
        for c in n.get("children") or []:
            walk(c)

    walk(node)
    if not best:
        return None
    parts = [p for p in best[1].split("\\") if p]
    if len(parts) > 1 and parts[1] == "Iteration":
        del parts[1]
    return "\\".join(parts)


# ---------------------------------------------------------------- ADO calls

def read(cfg, wid):
    got = get_items(cfg, [wid], READ)
    if not got:
        raise Refused(f"work item {wid} not found (deleted, or no access)")
    return got[0]


def write(cfg, wid, plan, tries=3, dry_run=False):
    """Read, decide (`plan(fields)` -> ops), patch with the rev test. On 412: read again, decide again.
    -> (item as read, ops written). No ops -> nothing to write, nothing sent."""
    for attempt in range(tries):
        w = read(cfg, wid)
        ops = plan(w["fields"])
        if not ops or dry_run:
            return w, ops
        body = [{"op": "test", "path": "/rev", "value": w["rev"]}] + ops
        try:
            ado("PATCH", f"{org_url(cfg)}/_apis/wit/workitems/{wid}?api-version=7.1", body, content_type=PATCH)
            return w, ops
        except RuntimeError as e:
            if "HTTP 412" not in str(e):
                raise
    raise Conflict(f"work item {wid} changed under every one of {tries} tries. Ask the user what to do")


def current_iteration(cfg, project, team=None, today=None):
    """The current sprint's path: the team's current iteration, else the iteration whose dates hold today
    (a team with no iteration schedule)."""
    today = today or date.today()
    q = urllib.parse.quote
    team = team or f"{project} Team"
    try:
        r = ado("GET", f"{org_url(cfg)}/{q(project)}/{q(team)}/_apis/work/teamsettings/iterations"
                       f"?$timeframe=current&api-version=7.1")
        if (r or {}).get("value"):
            return r["value"][0]["path"]
    except RuntimeError:
        pass
    tree = ado("GET", f"{org_url(cfg)}/{q(project)}/_apis/wit/classificationnodes/Iterations?$depth=20&api-version=7.1")
    path = pick_iteration(tree or {}, today)
    if not path:
        raise Refused(f"no iteration in {project} holds today's date ({today}). Ask the user which sprint to use")
    return path


def comment(cfg, project, wid, html_text):
    refuse_mentions(html_text, "the comment")
    q = urllib.parse.quote
    return ado("POST", f"{org_url(cfg)}/{q(project)}/_apis/wit/workItems/{wid}/comments?format=html"
                       f"&api-version=7.1-preview.4", {"text": html_text})
