"""Claude Code hook: the sdd sub-agents (investigator, skeptic) may read a repository, never change it.

    pre  (PreToolUse, matcher Bash|PowerShell) -> blocks a git command that is not on the read list,
                                                  and any run of the plugin's env.py or spec.py

Acts only on a tool call made inside one of this plugin's agents: the hook input carries `agent_id`
there, and `agent_type` names the agent. The main conversation and every other agent pass untouched.
An allowlist, not a blocklist: a git subcommand this file does not know is treated as a write.
env.py and spec.py write the flow's state and ADO; only the main conversation runs them. Reading
either file (cat, grep) is fine: only running one with a Python interpreter is blocked.
Exit 2 = block, stderr goes to the agent.
"""
import json
import re
import shlex
import sys

AGENTS = {"investigator", "skeptic"}

# Subcommands that never change the repository, whatever their arguments.
READ = {"log", "show", "blame", "annotate", "diff", "grep", "status", "rev-parse", "ls-files",
        "ls-tree", "cat-file", "shortlog", "describe", "merge-base", "rev-list", "name-rev",
        "for-each-ref", "show-ref", "show-branch", "whatchanged", "count-objects", "check-ignore",
        "var", "help", "version"}
# git options before the subcommand that take a separate value: `git -C <path> log`.
VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"}
# `git branch` / `git tag` flags that list rather than create.
LISTING = {"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
BRANCH_WRITE = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                "-u", "--set-upstream-to", "--unset-upstream", "--edit-description", "-t", "--track"}
TAG_WRITE = {"-d", "--delete", "-a", "--annotate", "-s", "--sign", "-u", "--local-user", "-m",
             "--message", "-F", "--file", "-f", "--force", "-e", "--edit"}
CONFIG_READ = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l"}
CONFIG_WRITE = {"--add", "--unset", "--unset-all", "--replace-all", "--rename-section",
                "--remove-section", "-e", "--edit"}
# subcommand -> its read-only actions (the first argument that is not a flag); none = read too
ACTIONS = {"stash": ({"list", "show"}, False), "worktree": ({"list"}, False),
           "reflog": ({"show"}, True), "remote": ({"show", "get-url"}, True),
           "notes": ({"list", "show"}, True), "submodule": ({"status", "summary"}, True)}


def tokens(command):
    # `a&&b`, `a;b` and a new line all separate commands, with or without spaces around them
    command = re.sub(r"(&&|\|\||[;|])", r" \1 ", command.replace("\n", " ; "))
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def is_git(token):
    name = re.split(r"[\\/]", token.strip("\"'`$();&|"))[-1].lower()
    return name in ("git", "git.exe")


SEPARATORS = {"&&", "||", ";", "|", "&"}
# programs that run the command after them: `xargs git add`, `env X=1 git commit`
LAUNCHERS = {"xargs", "env", "sudo", "command", "exec", "time", "nice", "call", "&"}


def in_command_position(toks, i):
    """`git` as the program, not as a word in a grep pattern or a path."""
    t, prev = toks[i], toks[i - 1] if i else ""
    return (i == 0 or prev in SEPARATORS or prev.endswith((";", "|", "&")) or t[:1] in "$(`&"
            or prev in LAUNCHERS or re.fullmatch(r"\w+=\S*", prev) is not None)


def git_calls(command):
    """Each git invocation in the command as (subcommand, args), args up to the next separator."""
    toks = tokens(command)
    calls = []
    for i, t in enumerate(toks):
        if not (is_git(t) and in_command_position(toks, i)):
            continue
        j = i + 1
        while j < len(toks) and toks[j].startswith("-") and toks[j] not in ("--version", "--help"):
            j += 2 if toks[j] in VALUED else 1
        if j >= len(toks):
            continue  # bare `git`, or only options: prints help
        sub = toks[j].strip("\"'").lstrip("-")
        args = []
        for a in toks[j + 1:]:
            if a in SEPARATORS or a.endswith((";", ")")):
                break
            args.append(a.strip("\"'"))
        calls.append((sub, args))
    return calls


PYTHON = re.compile(r"(?:python3?(?:\.\d+)?|py|pythonw?)(?:\.exe)?", re.I)
SDD_SCRIPTS = ("env.py", "spec.py")


def basename(token):
    return re.split(r"[\\/]", token.strip("\"'`$();&|"))[-1]


def sdd_script_runs(command):
    """The sdd scripts the command runs: `python .../env.py progress`, `uv run python spec.py sync`,
    `& "C:/Python/python.exe" -X utf8 env.py`, or the script as the program itself."""
    toks = tokens(command)
    runs = []
    for i, t in enumerate(toks):
        name = basename(t).lower()
        if name not in SDD_SCRIPTS:
            continue
        j = i - 1  # back over the interpreter's flags: -u, -I, -X utf8, -W ignore
        while j >= 0:
            if toks[j].startswith("-"):
                j -= 1
            elif j >= 1 and toks[j - 1] in ("-X", "-W"):
                j -= 2
            else:
                break
        if (j >= 0 and PYTHON.fullmatch(basename(toks[j]))) or in_command_position(toks, i):
            runs.append(name)
    return runs


def writes(sub, args):
    flags = {a.split("=", 1)[0] for a in args if a.startswith("-")}
    positional = [a for a in args if not a.startswith("-")]
    if sub in READ:
        return False
    if sub == "branch":
        return bool(flags & BRANCH_WRITE) or bool(positional and not flags & LISTING)
    if sub == "tag":
        return bool(flags & TAG_WRITE) or bool(positional and not flags & LISTING)
    if sub == "config":
        return bool(flags & CONFIG_WRITE) or not (flags & CONFIG_READ or len(positional) == 1)
    if sub in ACTIONS:
        allowed, bare_ok = ACTIONS[sub]
        if not positional:
            return not bare_ok
        return positional[0] not in allowed
    return True


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    agent = (data.get("agent_type") or "").split(":")[-1]
    if not data.get("agent_id") or agent not in AGENTS:
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    for name in sdd_script_runs(command):
        print(f"sdd: the {agent} agent does not run {name}: it writes the flow's progress, gates and ADO, "
              "and only the agent that called you runs it. Read the files it would read (requirements.md, "
              "workitem.json, the spec folder) instead, or say in your report what you need.", file=sys.stderr)
        return 2
    for sub, args in git_calls(command):
        if writes(sub, args):
            print(f"sdd: the {agent} agent is read-only, and `git {sub}` can change the repository. "
                  "Read with git log, show, blame, diff or grep. If the work needs a change, say so in "
                  "your report: the agent that called you makes it.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
