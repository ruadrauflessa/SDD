"""The text of the pull requests devops raises: release PRs (team -> release) and sync PRs (older team
branch -> newer). Pure functions; the 4000-character limit and the mention rules are kept here, once.
"""
import re

from devopslib import PR_LIMIT

ADO_MENTION = re.compile(r"\bAB#(\d+)")
BARE_MENTION = re.compile(r"(?<![\w&/\[])#(\d+)\b")


def sanitize(subject):
    """An old commit subject that cannot link a work item: `AB#123` and `#123` become `AB-123`."""
    return BARE_MENTION.sub(r"AB-\1", ADO_MENTION.sub(r"AB-\1", subject or ""))


def fit(lines, tail_note):
    """Joins lines, dropping from the end (with a note of how many) until it fits PR_LIMIT."""
    text = "\n".join(lines)
    if len(text) <= PR_LIMIT:
        return text
    for cut in range(len(lines) - 1, 0, -1):
        dropped = len(lines) - cut
        text = "\n".join(lines[:cut] + ["", tail_note.format(n=dropped)])
        if len(text) <= PR_LIMIT:
            return text
    return text[:PR_LIMIT]


def release_title(source, target):
    return f"Merge {source} into {target}"


def release_body(row, items, item_url):
    """row: a scan row (Ahead, FilesChanged, Insertions, Deletions, Commits, MigrationFiles, SourceBranch,
    TargetBranch). items: {id: {"title"}} validated work items of this repo. item_url(id) -> link."""
    lines = [f"Merges `{row['SourceBranch']}` into `{row['TargetBranch']}`: {row['Ahead']} commit(s), "
             f"{row['FilesChanged']} file(s), +{row['Insertions']} / -{row['Deletions']}. "
             "The merge is clean: `git merge-tree` checked it before this PR was opened.", ""]
    ids = [i for i in row.get("WorkItems", []) if str(i) in items or i in items]
    if ids:
        lines += ["## Fixes included", ""]
        for i in ids:
            it = items.get(str(i)) or items.get(i)
            lines.append(f"- [ADO {i}]({item_url(i)}) — {sanitize(it['title'])}")
        lines.append("")
    loose = [c for c in row.get("Commits", []) if not c.get("WorkItems")]
    if row.get("MigrationFiles"):
        lines += ["## Database migrations", "", "Decide how these deploy before the PR completes.", ""]
        lines += [f"- `{m['Path']}` ({m['Kind']})" for m in row["MigrationFiles"]]
        lines.append("")
    if loose:
        lines += ["## Commits with no work item", ""]
        lines += [f"- `{c['Short']}` {sanitize(c['Subject'])}" for c in loose]
    return fit(lines, "_{n} more line(s) left out: ADO takes 4000 characters. See the commits tab._")


def sync_title(source, destination):
    return f"Sync {source} into {destination}"


def sync_body(source, destination, commits, conflicted=False, sync_branch=None, note=None):
    """commits: [(short sha, subject)] of destination..source. No work item of an old commit can link."""
    how = (f"Conflicts were resolved by hand on `{sync_branch}`." if conflicted
           else "The merge is clean: `git merge-tree` checked it before this PR was opened.")
    lines = [f"Brings `{source}` forward into `{destination}`: {len(commits)} commit(s). {how}", "",
             "This PR moves work that was already reviewed on the older branch. It links only this run's "
             "team-sync work item; the old work items stay on their own PRs.", ""]
    if note:
        lines += [f"Resolution: {sanitize(note)}", ""]
    if commits:
        lines += ["## Commits", ""] + [f"- `{sha}` {sanitize(subj)}" for sha, subj in commits]
    return fit(lines, "_{n} more commit(s) left out: ADO takes 4000 characters. See the commits tab._")
