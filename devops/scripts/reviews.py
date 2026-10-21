"""PR reviews from the /devops pane: which PRs wait on the user, whether their vote counts, the diff bundle a
quick review reads, and the comment threads they post under their own name.

Pure functions; devops.py does the ADO calls. The pane makes the one model call (the quick review) on a
press, and posts and votes only on the person's own press after a confirm: the git guard refuses both to the
agent.
"""
import difflib
import json
import re

VOTES = {"approve": 10, "suggest": 5, "reset": 0, "wait": -5, "reject": -10}
VOTE_WORD = {10: "approved", 5: "approved with suggestions", 0: "no vote", -5: "waiting for author", -10: "rejected"}
SEVERITIES = ("high", "medium", "low")


def vote_word(v):
    return VOTE_WORD.get(int(v or 0), str(v))


def my_role(reviewers, me_id, my_groups):
    """(role, vote): role is 'required', 'optional', 'group <name>' (a group I am in), or None."""
    me_id = (me_id or "").lower()
    direct = next((r for r in reviewers or [] if (r.get("id") or "").lower() == me_id), None)
    if direct:
        return ("required" if direct.get("isRequired") else "optional"), int(direct.get("vote") or 0)
    for r in reviewers or []:
        if r.get("isContainer") and (r.get("id") or "").lower() in my_groups:
            return f"group {r.get('displayName', '')}" + (" (required)" if r.get("isRequired") else ""), 0
    return None, 0


def pr_row(org, project, pr, me_id, my_groups, url):
    role, vote = my_role(pr.get("reviewers"), me_id, my_groups)
    author = (pr.get("createdBy") or {})
    mine = (author.get("id") or "").lower() == (me_id or "").lower()
    return {
        "org": org, "project": project, "id": pr["pullRequestId"], "repo": pr["repository"]["name"],
        "title": pr.get("title", ""), "author": author.get("displayName", ""), "mine": mine,
        "source": pr["sourceRefName"][11:], "target": pr["targetRefName"][11:], "created": pr.get("creationDate", ""),
        "draft": bool(pr.get("isDraft")), "conflicts": pr.get("mergeStatus") == "conflicts",
        "role": role, "myVote": vote, "waiting": bool(role) and vote == 0 and not mine and not pr.get("isDraft"),
        "votes": [{"name": r.get("displayName", ""), "vote": int(r.get("vote") or 0), "required": bool(r.get("isRequired"))}
                  for r in pr.get("reviewers") or []],
        "url": url,
    }


def policy_rows(evaluations):
    out = []
    for e in evaluations or []:
        c = e.get("configuration") or {}
        if not c.get("isEnabled", True):
            continue
        out.append({"name": (c.get("type") or {}).get("displayName", "policy"), "status": e.get("status", ""),
                    "blocking": bool(c.get("isBlocking")), "settings": c.get("settings") or {}})
    return out


def can_vote(pr, me_id, policies):
    """(True, why) or (False, why): an author whose policy does not count their own vote may not approve."""
    author = ((pr.get("createdBy") or {}).get("id") or "").lower()
    if author and author == (me_id or "").lower():
        for p in policies:
            if p["name"].lower().startswith("minimum number of reviewers") and p["settings"].get("creatorVoteCounts") is False:
                return False, "you opened this PR, and its reviewer policy does not count the author's vote"
        return True, "you opened this PR: your vote counts only where the policy allows it"
    return True, ""


def number_diff(diff_text, max_chars):
    """A unified diff as the model reads it: each line the PR's right side has, with its line number, so a
    finding names a line that exists. Returns (text, {path: [right-side lines shown]}, truncated)."""
    out, lines, path, right = [], {}, None, 0
    used, truncated = 0, False
    for ln in diff_text.splitlines():
        if ln.startswith("+++ "):
            p = ln[4:].strip()
            path = None if p == "/dev/null" else re.sub(r"^b/", "", p)
            if path:
                head = f"\n### {path}"
                if used + len(head) > max_chars:
                    truncated = True
                    break
                out.append(head)
                used += len(head) + 1
            continue
        if ln.startswith(("--- ", "diff ", "index ", "new file", "deleted file", "similarity", "rename ", "old mode", "new mode", "Binary")):
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", ln)
        if m:
            right = int(m.group(1))
            row = "   …"
        elif path is None:
            continue
        elif ln.startswith("+"):
            row = f"{right:>5} + {ln[1:]}"
            lines.setdefault(path, []).append(right)
            right += 1
        elif ln.startswith("-"):
            row = f"      - {ln[1:]}"
        elif ln.startswith("\\"):
            continue
        else:
            row = f"{right:>5}   {ln[1:] if ln.startswith(' ') else ln}"
            lines.setdefault(path, []).append(right)
            right += 1
        if path is None:
            continue
        if used + len(row) > max_chars:
            truncated = True
            break
        out.append(row)
        used += len(row) + 1
    return "\n".join(out).strip("\n"), lines, truncated


def unified(path, old, new):
    """A unified diff of one file from its two texts (None = absent), for a repo with no local clone."""
    a = (old or "").splitlines()
    b = (new or "").splitlines()
    head = [f"--- {'a/' + path if old is not None else '/dev/null'}", f"+++ {'b/' + path if new is not None else '/dev/null'}"]
    body = list(difflib.unified_diff(a, b, lineterm="", n=3))[2:]
    return "\n".join(head + body)


SYSTEM = """You review a pull request for a senior developer who will decide what to post. Find real problems only:
bugs, wrong logic, missing null or error handling, security issues, data loss, broken contracts, missing tests for
risky changes, and code that does not meet the linked work items' acceptance criteria. Ignore style unless it hides
a bug. Each finding names a file and a line number exactly as the diff shows it on the left of the line. Write each
comment in plain English: one or two short sentences, active voice, no praise, no hedging. Offer a suggestion only
when you can give the exact replacement code for that one line. Never write `#` followed by a number.

Answer with JSON only, no prose around it:
[{"file": "path", "line": 12, "severity": "high|medium|low", "comment": "...", "suggestion": "replacement line or null"}]
Return [] when you find nothing worth a comment. At most %d findings, most severe first."""


def prompt(detail, bundle, truncated):
    wi = "\n".join(f"- ADO {w['id']} {w['type']}: {w['title']}" + (f"\n  Acceptance criteria: {w['criteria']}" if w.get("criteria") else "")
                   for w in detail.get("workItems", [])) or "(none linked)"
    desc = (detail.get("description") or "").strip()[:2000] or "(no description)"
    note = "\n\n(The diff was cut to fit; review what is shown.)" if truncated else ""
    return (f"PR {detail['id']} in {detail['repo']}: {detail['title']}\n{detail['source']} -> {detail['target']}\n\n"
            f"Description:\n{desc}\n\nLinked work items:\n{wi}\n\nThe diff (right-side line numbers on the left):\n{bundle}{note}")


def thread_body(draft, iteration, tracking=None):
    """An ADO comment thread from one draft: on a file and line when it has one, else on the whole PR. ADO needs
    the file's changeTrackingId (from the iteration's changes) on a PR with iteration support."""
    text = draft["text"].strip()
    if draft.get("suggestion"):
        text += "\n\n```suggestion\n" + str(draft["suggestion"]).rstrip("\n") + "\n```"
    body = {"comments": [{"parentCommentId": 0, "content": text, "commentType": 1}], "status": 1}
    if draft.get("file") and draft.get("line"):
        pos = {"line": int(draft["line"]), "offset": 1}
        body["threadContext"] = {"filePath": "/" + draft["file"].lstrip("/"), "rightFileStart": pos, "rightFileEnd": dict(pos, offset=2)}
        if iteration:
            ctx = {"iterationContext": {"firstComparingIteration": 1, "secondComparingIteration": int(iteration)}}
            tid = (tracking or {}).get(draft["file"].lstrip("/"))
            if tid is not None:
                ctx["changeTrackingId"] = int(tid)
            body["pullRequestThreadContext"] = ctx
    return body


def thread_rows(threads):
    """The human threads of a PR (no system notes), newest first, short."""
    out = []
    for t in threads or []:
        if t.get("isDeleted"):
            continue
        comments = [c for c in t.get("comments") or [] if c.get("commentType") in ("text", 1, None) and not c.get("isDeleted")]
        if not comments:
            continue
        ctx = t.get("threadContext") or {}
        line = (ctx.get("rightFileStart") or {}).get("line")
        first = comments[0]
        out.append({"id": t.get("id"), "status": t.get("status", ""), "file": (ctx.get("filePath") or "").lstrip("/") or None,
                    "line": line, "author": (first.get("author") or {}).get("displayName", ""),
                    "text": (first.get("content") or "")[:300], "replies": len(comments) - 1})
    return out


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def key_of(org, project, pr_id, iteration):
    return re.sub(r"[^\w.-]", "_", f"{org}-{project}-{pr_id}-{iteration}")


def parse_findings(text, lines, limit):
    """The model's findings, kept only where they name a line the diff shows (pure; the pane does the same)."""
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        raw = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    out = []
    for f in raw if isinstance(raw, list) else []:
        try:
            path, line = str(f.get("file", "")).lstrip("/"), int(f.get("line"))
        except (TypeError, ValueError, AttributeError):
            continue
        if line not in set(lines.get(path, [])) or not str(f.get("comment", "")).strip():
            continue
        sev = f.get("severity") if f.get("severity") in SEVERITIES else "low"
        sug = f.get("suggestion")
        out.append({"file": path, "line": line, "severity": sev, "comment": str(f["comment"]).strip(),
                    "suggestion": str(sug) if sug not in (None, "", "null") else None})
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(out, key=lambda f: order[f["severity"]])[:limit]
