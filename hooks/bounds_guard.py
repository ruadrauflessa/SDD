"""Claude Code hook: in an sdd workspace, nothing runs from, is written to, or moves into a folder outside it.

    pre  (PreToolUse, matcher Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit)
         -> blocks an Edit or Write of a file outside the workspace, and a shell command that
            changes directory to, writes to, or runs from a path outside it

The workspace is the folder holding .claude/sdd.json, found from the hook's cwd (or CLAUDE_PROJECT_DIR):
the folder the person trusted. Reading outside it is fine (cat, Get-Content, ls, grep, git log ...): a
command whose program only reads may name any path. Any other program that names a path outside the
workspace is refused, as is a redirect (>, >>) to one and a cd, Set-Location or pushd to one. A program
run by its full path is refused when that path is outside, unless it is installed software (Program
Files, Windows, /usr, a folder on PATH, the Python running this hook).

Always open: Claude's own ~/.claude (plugins, memory, plans), this plugin, the null device, and the
folders the person lists in .claude/sdd.json "bounds.allow". The agent cannot add to that list: an
Edit or Write of sdd.json that touches "bounds" is refused.

A path in a command is found by its shape: C:\\..., \\\\server\\share, /a/b (Git Bash /c/...), ~, $HOME,
$env:TEMP, %TEMP%, $TMPDIR and the like, and a relative path that climbs out with `..`. This is a
guard on what a command names, not a sandbox. Exit 2 = block, stderr goes to the agent.
"""
import base64
import json
import os
import posixpath
import re
import shlex
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
from agent_guard import VALUED, writes as git_writes  # noqa: E402
from sddlib import CONFIG_REL, find_root, load_config  # noqa: E402

# Programs that only read or print: they may name any path (a redirect of their output is checked apart).
READ = {"cat", "type", "gc", "get-content", "ls", "dir", "gci", "get-childitem", "test-path", "resolve-path",
        "get-item", "gi", "get-itemproperty", "gp", "split-path", "join-path", "head", "tail", "less", "more",
        "grep", "egrep", "fgrep", "rg", "findstr", "select-string", "sls", "wc", "stat", "file", "du", "df",
        "where", "where.exe", "which", "get-command", "gcm", "echo", "write-output", "write-host", "printf",
        "diff", "fc", "compare-object", "get-filehash", "sha256sum", "sha1sum", "md5sum", "certutil",
        "realpath", "readlink", "basename", "dirname", "tree", "get-acl", "measure-object", "format-hex",
        "select-object", "sort-object", "where-object", "format-table", "format-list", "out-string",
        "convertfrom-json", "convertto-json", "get-date", "true", "false", "exit", "test", "["}
CD = {"cd", "chdir", "set-location", "sl", "pushd", "push-location"}
# Programs that run the command after them: the program is the next word.
LAUNCHERS = {"&", ".", "call", "sudo", "env", "nohup", "exec", "time", "xargs", "nice", "command", "start"}
# Options that hand a shell a command to run: their value is checked as a command of its own.
NESTED = {"-c", "/c", "/k", "-command", "-commandwithargs"}
SHELLS = {"bash", "sh", "zsh", "dash", "cmd", "powershell", "pwsh", "bash.exe", "sh.exe", "cmd.exe", "powershell.exe", "pwsh.exe"}
SEPARATORS = {";", "&&", "||", "|", "{", "}", "&"}
NULLS = {"/dev/null", "nul", "$null", "nul:"}
REDIRECT = re.compile(r"^(?:\d|\*|&)?>>?\|?(.*)$")
VAR = re.compile(r"^\$\{?(env:)?(\w+)\}?(?=$|[\\/])|^%(\w+)%(?=$|[\\/])", re.I)
TEMP_CALLS = re.compile(r"\[(?:system\.)?io\.path\]::gettemppath\(\)|\bnew-temporaryfile\b|\bmktemp\b", re.I)


def norm(p):
    """A path as a lower-cased, forward-slash string with . and .. folded away: C:\\A\\..\\b -> c:/b."""
    s = str(p).replace("\\", "/")
    unc = s.startswith("//")
    s = posixpath.normpath(s)
    if unc and not s.startswith("//"):
        s = "/" + s
    if re.match(r"^[A-Za-z]:", s) or os.name == "nt":
        s = s.lower()
    return s.rstrip("/") if len(s) > 3 else s


def under(p, base):
    p, base = norm(p), norm(base)
    return p == base or p.startswith(base.rstrip("/") + "/")


def git_bash(s):
    """/c/Users/x (Git Bash) -> C:/Users/x on Windows; unchanged elsewhere."""
    m = re.match(r"^/([A-Za-z])(/.*)?$", s)
    return f"{m.group(1).upper()}:{m.group(2) or '/'}" if m and os.name == "nt" else s


def expand(tok, home, local=None):
    """The absolute path a word names, or None when it names none. A variable set earlier in the command (`local`)
    or in this environment is put in."""
    t = tok.strip("\"'`(),;")
    if not t or t.startswith(("http://", "https://", "file://", "-")) and not re.match(r"^-\w+[:=]", t):
        return None
    m = re.match(r"^-{1,2}[\w-]+[:=](.+)$", t)  # -Destination:C:\x, --output=/x
    if m:
        t = m.group(1).strip("\"'")
    if TEMP_CALLS.search(t):
        return tempfile.gettempdir()
    v = VAR.match(t)
    if v:
        name = (v.group(2) or v.group(3) or "").upper()
        value = (local or {}).get(name.lower()) or {"HOME": home, "USERPROFILE": home}.get(name) or os.environ.get(name) or os.environ.get(name.lower())
        if not value:
            return None
        t = value + t[v.end():]
    if t == "~" or t.startswith(("~/", "~\\")):
        t = home + t[1:]
    if re.match(r"^[A-Za-z]:[\\/]", t) or t.startswith(("\\\\", "//")):
        return t
    if t.startswith("/") and (t.count("/") >= 2 and len(t) > 2 or t in ("/tmp", "/var", "/home", "/root", "/mnt", "/srv")):
        return git_bash(t)
    return None


def climbs(tok, cwd):
    """A relative word that climbs out with `..`: the absolute path it names, else None."""
    t = tok.strip("\"'`(),;")
    if t == ".." or t.startswith(("../", "..\\")) or "/../" in t or "\\..\\" in t:
        return str(Path(cwd) / t)
    return None


def tokens(command):
    command = re.sub(r"(&&|\|\||[;|{}])", r" \1 ", command.replace("\r", "").replace("\n", " ; "))
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def segments(command):
    """The simple commands in a command line: lists of words, split at ; && || | { } and new lines."""
    out, cur = [], []
    for t in tokens(command):
        if t in SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def name_of(word):
    return re.split(r"[\\/]", word.strip("\"'`$();&|"))[-1].lower()


def unquote(word):
    w = word.strip()
    return w[1:-1] if len(w) >= 2 and w[0] == w[-1] and w[0] in "\"'" else w


class Bounds:
    def __init__(self, root, cwd, allow=(), tools=(), home=None):
        self.root, self.cwd = str(root), str(cwd or root)
        self.home = home or str(Path.home())
        self.allow = [str(root)] + [a for a in allow if a]
        self.tools = [t for t in tools if t]
        self.vars = {}  # variables the command sets: $dest = "C:\x", DEST=/x, export DEST=/x

    def inside(self, p):
        return any(under(p, a) for a in self.allow) or norm(p) in NULLS

    def tool(self, p):
        return any(under(p, t) for t in self.tools)

    def path_in(self, word):
        return expand(word, self.home, self.vars) or climbs(word, self.cwd)

    def assigned(self, words):
        """Records `$x = value`, `X=value` and `export X=value`; True when that is all the words do."""
        ws = words[1:] if words and words[0] in ("export", "set") else words
        if len(ws) == 3 and ws[1] == "=" and ws[0].startswith("$"):
            self.vars[ws[0].lstrip("$").split(":")[-1].lower()] = unquote(ws[2])
            return True
        pairs = [re.fullmatch(r"\$?(\w+)=(\S+)", unquote(w)) for w in ws]
        if ws and all(pairs):
            for m in pairs:
                self.vars[m.group(1).lower()] = unquote(m.group(2))
            return True
        return False

    def outside(self, word, tools_ok=True):
        p = self.path_in(word)
        if not p or self.inside(p) or (tools_ok and self.tool(p)):
            return None
        return p

    def check(self, command, depth=0):
        """Why the command is refused, or "" when it may run."""
        if depth > 3:
            return ""
        segs = segments(command)
        if not self.inside(self.cwd) and segs and not (name_of(segs[0][0]) in CD and self.cd_target(segs[0])
                                                       and self.inside(self.resolve(self.cd_target(segs[0])))):
            if any(name_of(seg[0]) not in READ for seg in segs):
                return f"runs in {self.cwd}, outside the workspace: cd {self.root} first"
        for seg in segs:
            why = self.check_segment(seg, depth)
            if why:
                return why
        return ""

    def check_segment(self, seg, depth):
        words, i = list(seg), 0
        # redirects first: they write, whatever the program
        rest = []
        while i < len(words):
            w = words[i]
            m = REDIRECT.match(w) if not w.startswith(("'", '"')) else None
            if m and (w.startswith((">", "1>", "2>", "*>", "&>")) or re.match(r"^\d>", w)):
                target = m.group(1) or (words[i + 1] if i + 1 < len(words) else "")
                i += 1 if m.group(1) else 2
                if target.startswith("&"):  # 2>&1
                    continue
                p = self.outside(target, tools_ok=False)
                if p:
                    return f"writes to {p}"
                continue
            rest.append(w)
            i += 1
        words = rest
        if self.assigned(words):
            return ""
        if len(words) > 2 and words[1] == "=" and words[0].startswith("$"):  # $x = Get-Content C:\a: the command after =
            words = words[2:]
        while words and (re.fullmatch(r"\w+=\S*", words[0]) or name_of(words[0]) in LAUNCHERS and len(words) > 1
                         or words[0] in ("&", ".")):
            if re.fullmatch(r"\w+=\S*", words[0]):
                self.assigned(words[:1])
            words = words[1:]
        if not words:
            return ""
        prog = words[0]
        name = name_of(prog)
        if name in ("start-process", "saps"):
            fp = [words[j + 1] for j in range(1, len(words) - 1) if words[j].lower() == "-filepath"]
            pos = [w for w in words[1:] if not w.startswith("-")]
            target = fp[0] if fp else (pos[0] if pos else "")
            p = self.outside(target) if target else None
            if p:
                return f"runs {p}"
            for j, w in enumerate(words[1:], 1):
                if w.lower() in ("-workingdirectory", "-wd") and j + 1 < len(words):
                    p = self.outside(words[j + 1], tools_ok=False)
                    if p:
                        return f"runs from {p}"
            return self.args(words[1:], name)
        p = self.outside(prog)
        if p:
            return f"runs {p}"
        if name in ("subst", "subst.exe", "mklink", "new-psdrive", "ndr") and len(words) > 1 and words[1] not in ("/?", "/d", "/D"):
            return "maps a drive or link outside the workspace onto its files: run from the workspace's own path"
        if name in CD:
            target = self.cd_target(words)
            p = self.outside(target, tools_ok=False) if target else None
            if p:
                return f"moves the shell to {p}"
            if target:
                self.cwd = self.resolve(target)
            return ""
        if name in SHELLS:
            for j, w in enumerate(words[1:], 1):
                if j + 1 >= len(words):
                    break
                if w.lower() in NESTED:
                    nested = unquote(words[j + 1]) if words[j + 1][0] in "\"'" else " ".join(words[j + 1:])
                    return self.check(nested, depth + 1)
                if w.lower() in ("-encodedcommand", "-enc", "-e", "-ec"):
                    try:
                        return self.check(base64.b64decode(words[j + 1]).decode("utf-16-le"), depth + 1)
                    except (ValueError, UnicodeDecodeError):
                        return ""
        if name in ("invoke-expression", "iex") and len(words) > 1:
            return self.check(unquote(words[1]), depth + 1)
        return self.args(words[1:], name)

    def cd_target(self, words):
        return next((w for w in words[1:] if not w.startswith("-") and not re.fullmatch(r"/\w", w)), "")

    def resolve(self, word):
        p = self.path_in(word)
        return p if p else os.path.normpath(os.path.join(self.cwd, unquote(word)))

    def args(self, args, name):
        if name in READ:
            return ""
        if name in ("git", "git.exe"):
            j = 0
            while j < len(args) and args[j].startswith("-"):
                j += 2 if args[j] in VALUED else 1
            if j < len(args) and not git_writes(args[j].strip("\"'").lstrip("-"), [unquote(a) for a in args[j + 1:]]):
                return ""
        for w in args:
            p = self.outside(w)
            if p:
                return f"{name} on {p}"
        return ""


def tool_dirs(home):
    """Installed software: a program there may run, and be named, from any command."""
    out = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData", "SystemRoot", "windir")]
    local = os.environ.get("LOCALAPPDATA")
    out += [os.path.join(local, "Programs")] if local else []
    out += ["/usr", "/bin", "/sbin", "/opt", "/etc", "/Applications", "/Library", "/System", "/nix", "/snap"]
    out += [sys.base_prefix, sys.prefix]
    temp = tempfile.gettempdir()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isabs(d) or under(d, temp) or norm(d) in (norm(home), norm(os.path.dirname(home))):
            continue
        if len(norm(d).strip("/").split("/")) < 2:  # a drive or / itself
            continue
        out.append(d)
    return [d for d in out if d]


def workspace(cwd):
    root = find_root(cwd) if cwd and Path(cwd).is_dir() else None
    if not root and os.environ.get("CLAUDE_PROJECT_DIR"):
        root = find_root(os.environ["CLAUDE_PROJECT_DIR"])
    return root


def bounds_for(root, cwd, home=None):
    home = home or str(Path.home())
    try:
        extra = load_config(root).get("bounds", {}).get("allow") or []
    except (OSError, ValueError, AttributeError):
        extra = []
    extra = [os.path.expanduser(os.path.expandvars(str(a))) for a in extra if isinstance(a, str)]
    allow = [os.path.join(home, ".claude"), str(HERE.parent), os.environ.get("CLAUDE_PLUGIN_ROOT"), os.environ.get("CLAUDE_PLUGIN_DATA")] + extra
    root = root.resolve()
    tools = [t for t in tool_dirs(home) if not under(root, t)]  # a workspace under a tool folder is still the boundary
    return Bounds(root, cwd, [a for a in allow if a], tools, home)


def hint(root, what):
    temp = norm(tempfile.gettempdir())
    tmp_note = (f" For scratch files use {Path(root) / '.claude' / 'tmp'} (or the work item's folder under .claude/worktrees)."
                if temp in norm(what) or "/tmp" in norm(what) else "")
    return (f"sdd: this {what}, outside the trusted workspace {root}. In an sdd workspace nothing runs from, is written to "
            f"or moves into a folder outside it.{tmp_note} Work in the item's worktree. If a path is too long for a tool, "
            "do not copy the code out of the workspace: tell the user and stop. A folder the user trusts too goes in "
            "\"bounds.allow\" in .claude/sdd.json, and only the user adds it.")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    root = workspace(cwd)
    if not root:
        return 0
    ti = data.get("tool_input") or {}
    tool = data.get("tool_name") or ""
    b = bounds_for(root, cwd)
    if tool in ("Bash", "PowerShell"):
        why = b.check(ti.get("command") or "")
        if why:
            print(hint(b.root, f"command {why}"), file=sys.stderr)
            return 2
        return 0
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path:
        return 0
    p = Path(path) if Path(path).is_absolute() else Path(cwd) / path
    p = Path(os.path.normpath(str(p)))
    if not b.inside(str(p)):
        print(hint(b.root, f"{tool} is of {p}"), file=sys.stderr)
        return 2
    if under(str(p), str(Path(b.root) / CONFIG_REL)):
        new = json.dumps(ti.get("content") or ti.get("new_string") or ti.get("edits") or "")
        if "bounds" in new:
            print(f"sdd: {p} \"bounds\" says which folders outside the workspace are trusted. Only the user changes it: "
                  "ask them to, and say which folder and why.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
