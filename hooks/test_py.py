"""Self-check for py.mjs, the hooks' Python launcher: python test_py.py  (temp folders; needs node).

The fake pythons are shell scripts, so this runs on Linux and macOS; on Windows it says so and stops.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

LAUNCHER = Path(__file__).with_name("py.mjs")
STUB = "#!/bin/sh\necho 'Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.' >&2\nexit 1\n"


def tool(folder, name, text):
    p = folder / name
    p.write_text(text, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def real(log):
    """A python that notes each run in log, then runs the real one."""
    return f'#!/bin/sh\necho run >> "{log}"\nexec "{sys.executable}" "$@"\n'


def launch(folder, args, stdin=""):
    env = dict(os.environ, PATH=str(folder))
    return subprocess.run([NODE, str(LAUNCHER)] + args, input=stdin, capture_output=True, text=True, env=env)


def main():
    if sys.platform == "win32":
        print("skipped: the fake pythons are shell scripts")
        return
    fails = []

    def check(name, ok):
        if not ok:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        script = tmp / "guard.py"
        script.write_text("import sys\ndata = sys.stdin.read()\nprint('out:' + data + ':' + ' '.join(sys.argv[1:]))\n"
                          "print('err', file=sys.stderr)\nsys.exit(2 if 'block' in sys.argv else 0)\n", encoding="utf-8")

        # python is the Store shortcut, no python3: py runs it, once
        a = tmp / "a"
        a.mkdir()
        tool(a, "python", STUB)
        tool(a, "py", real(tmp / "a.log"))
        r = launch(a, [str(script), "pre"], "{}")
        check("stub skipped, py runs", r.returncode == 0 and r.stdout.strip() == "out:{}:pre" and r.stderr.strip() == "err")
        r = launch(a, [str(script), "block"], "{}")
        check("exit 2 goes through", r.returncode == 2 and r.stdout.strip() == "out:{}:block")
        check("a blocked run is not run again", (tmp / "a.log").read_text().split() == ["run", "run"])

        # a real python comes first: py is never run
        b = tmp / "b"
        b.mkdir()
        tool(b, "python", real(tmp / "b-python.log"))
        tool(b, "py", real(tmp / "b-py.log"))
        r = launch(b, [str(script), "pre"], "x")
        check("python first", r.returncode == 0 and r.stdout.strip() == "out:x:pre" and not (tmp / "b-py.log").exists())

        # nothing but the stub: says so, exit 1 (a hook's non-blocking failure)
        c = tmp / "c"
        c.mkdir()
        tool(c, "python", STUB)
        tool(c, "python3", STUB)
        r = launch(c, [str(script), "pre"], "{}")
        check("no python", r.returncode == 1 and "no Python found" in r.stderr and r.stdout == "")

    if fails:
        print("FAIL: " + ", ".join(fails))
        sys.exit(1)
    print("ok")


NODE = shutil.which("node") or "node"

if __name__ == "__main__":
    main()
