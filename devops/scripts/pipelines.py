"""Builds, deployments and the setup check for the /devops pane: the newest run of each pipeline on a release's
branches and the step that failed, what each environment runs now, and what `devops.py doctor` found.

Pure functions; devops.py does the ADO reads. Nothing here writes anywhere.
"""
import re

ENV_ORDER = ("QA", "UAT", "STAGE", "PROD")
# Git Repositories security namespace, and the bits devops needs on a repo (and on the wiki's repo)
GIT_NAMESPACE = "2e9eb7ed-3c0a-47d4-87c1-0ffdcd83148b"
CONTRIBUTE, CREATE_BRANCH, PR_CONTRIBUTE = 4, 16, 16384
FAILED = ("failed", "partiallySucceeded")


def env_of(name, aliases):
    """QA, UAT, STAGE or PROD for an ADO environment or stage name, or None. The whole name is tried
    first, so `Pre-Prod` is STAGE (alias `preprod`), not PROD; then each word of it."""
    compact = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    words = [w for w in re.split(r"[^a-z0-9]+", (name or "").lower()) if w]
    for env in ENV_ORDER:
        if compact in [a.lower() for a in aliases.get(env, [])]:
            return env
    for env in ("STAGE", "UAT", "QA", "PROD"):  # the narrower names before the one that hides in others
        if any(w in [a.lower() for a in aliases.get(env, [])] for w in words):
            return env
    return None


def bare_branch(ref):
    return re.sub(r"^refs/heads/", "", ref or "")


def version_of_branch(branch, patterns):
    """1.1.0 for release/1.1.0 when a pattern (release/{0}) matches, case-insensitively; else None."""
    b = bare_branch(branch)
    for p in patterns:
        rx = "^" + re.escape(p).replace(re.escape("{0}"), "(.+)") + "$"
        m = re.match(rx, b, re.I)
        if m:
            return m.group(1)
    return None


def latest_builds(builds):
    """The newest build of each pipeline on each branch (ADO lists newest first; the id breaks ties)."""
    best = {}
    for b in builds:
        key = ((b.get("definition") or {}).get("id"), bare_branch(b.get("sourceBranch")).lower())
        if key not in best or int(b.get("id", 0)) > int(best[key].get("id", 0)):
            best[key] = b
    return list(best.values())


def failing_step(records):
    """{step, message} of the first task that failed in a build's timeline, or None."""
    tasks = [r for r in records or [] if r.get("type") == "Task" and r.get("result") == "failed"]
    if not tasks:
        return None
    tasks.sort(key=lambda r: (r.get("startTime") or "", r.get("order") or 0))
    t = tasks[0]
    msg = next((i.get("message", "") for i in t.get("issues") or [] if i.get("type") == "error"), "")
    return {"step": t.get("name", ""), "message": re.sub(r"\s+", " ", msg).strip()[:300]}


def build_row(org, project, b, failing=None):
    link = (((b.get("_links") or {}).get("web") or {}).get("href")
            or f"https://dev.azure.com/{org}/{project}/_build/results?buildId={b.get('id')}")
    return {"org": org, "project": project, "repo": (b.get("repository") or {}).get("name", ""),
            "branch": bare_branch(b.get("sourceBranch")), "pipeline": (b.get("definition") or {}).get("name", ""),
            "id": b.get("id"), "number": b.get("buildNumber", ""), "status": b.get("status", ""), "result": b.get("result") or "",
            "queued": b.get("queueTime") or "", "finished": b.get("finishTime") or "", "url": link, "failing": failing}


def build_word(row):
    if row["status"] != "completed":
        return "running" if row["status"] == "inProgress" else "queued"
    return {"succeeded": "passed", "partiallySucceeded": "partly failed", "failed": "failed", "canceled": "canceled"}.get(row["result"], row["result"] or "?")


def pipeline_counts(rows):
    out = {"failed": 0, "running": 0, "passed": 0}
    for r in rows:
        w = build_word(r)
        if w in ("failed", "partly failed"):
            out["failed"] += 1
        elif w in ("running", "queued"):
            out["running"] += 1
        elif w == "passed":
            out["passed"] += 1
    return out


def yaml_rows(org, project, env, records, builds_by_id, aliases, patterns):
    """What a YAML environment runs now: the newest successful deployment of each pipeline into it."""
    best = {}
    for r in records or []:
        if r.get("result") not in ("succeeded", "succeededWithIssues"):
            continue
        key = (r.get("definition") or {}).get("id")
        if key not in best or (r.get("finishTime") or "") > (best[key].get("finishTime") or ""):
            best[key] = r
    out = []
    for r in best.values():
        b = builds_by_id.get(int((r.get("owner") or {}).get("id") or 0), {})
        branch = bare_branch(b.get("sourceBranch"))
        out.append({"org": org, "project": project, "env": env_of(env.get("name"), aliases), "envName": env.get("name", ""),
                    "pipeline": (r.get("definition") or {}).get("name", ""), "repo": (b.get("repository") or {}).get("name", ""),
                    "branch": branch, "version": version_of_branch(branch, patterns), "build": b.get("buildNumber", ""),
                    "commit": (b.get("sourceVersion") or "")[:10], "at": r.get("finishTime") or "", "kind": "yaml",
                    "url": ((b.get("_links") or {}).get("web") or {}).get("href")
                    or f"https://dev.azure.com/{org}/{project}/_environments/{env.get('id')}"})
    return out


def classic_rows(org, project, deployments, aliases, patterns):
    """What each classic release stage runs now: the newest successful deployment per definition and stage."""
    best = {}
    for d in deployments or []:
        if d.get("deploymentStatus") not in ("succeeded", "partiallySucceeded"):
            continue
        key = ((d.get("releaseDefinition") or {}).get("id"), (d.get("releaseEnvironment") or {}).get("name"))
        when = d.get("completedOn") or d.get("startedOn") or ""
        if key not in best or when > (best[key].get("completedOn") or best[key].get("startedOn") or ""):
            best[key] = d
    out = []
    for d in best.values():
        rel = d.get("release") or {}
        arts = rel.get("artifacts") or []
        art = next((a for a in arts if a.get("isPrimary")), arts[0] if arts else {})
        ref = art.get("definitionReference") or {}
        branch = bare_branch((ref.get("branch") or {}).get("name") or (ref.get("branches") or {}).get("name"))
        stage = (d.get("releaseEnvironment") or {}).get("name", "")
        out.append({"org": org, "project": project, "env": env_of(stage, aliases), "envName": stage,
                    "pipeline": (d.get("releaseDefinition") or {}).get("name", ""),
                    "repo": (ref.get("repository") or {}).get("name") or (ref.get("definition") or {}).get("name", ""),
                    "branch": branch, "version": version_of_branch(branch, patterns), "build": (ref.get("version") or {}).get("name", ""),
                    "commit": ((ref.get("sourceVersion") or {}).get("id") or "")[:10], "at": d.get("completedOn") or d.get("startedOn") or "",
                    "kind": "classic", "url": rel.get("webAccessUri") or (((rel.get("_links") or {}).get("web") or {}).get("href")) or ""})
    return out


def last_deploy(rows, project, env):
    """The newest deployment of this project into this environment (QA, UAT, STAGE, PROD), or None."""
    hits = [r for r in rows or [] if r.get("env") == env and (r.get("project") or "").lower() == (project or "").lower()]
    return max(hits, key=lambda r: r.get("at") or "") if hits else None


def check(name, state, detail, fix=""):
    """One row of `devops.py doctor`: state is ok, warn or fail."""
    return {"name": name, "state": state, "detail": detail, "fix": fix}


def missing_bits(granted):
    """The plain names of the git permissions a repo lacks, from {bit: bool}."""
    words = {CONTRIBUTE: "push (Contribute)", CREATE_BRANCH: "create branches", PR_CONTRIBUTE: "contribute to pull requests"}
    return [words[b] for b in (PR_CONTRIBUTE, CONTRIBUTE, CREATE_BRANCH) if not granted.get(b, True)]
