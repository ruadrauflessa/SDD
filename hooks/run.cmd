:; # Runs a plugin script with the first real Python 3.9+, for every hook in hooks.json. Claude Code runs a hook's command
:; # with sh (on Windows, Git Bash in the Desktop app's engine, cmd.exe in some others). On Windows "python" may be the
:; # Microsoft Store's stand-in (it prints "Python was not found" and exits 9009), so each candidate is tried first. sh reads
:; # the ":;" lines and execs; cmd skips them as labels (no goto: the file is LF). The script's exit code is the hook's
:; # (2 blocks), and only the script reads the hook's input.
:; for p in python python3 py; do "$p" -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1 && exec "$p" "$@"; done
:; echo "sdd: no Python 3.9 or newer found. Install it from python.org; the sdd hooks need it." >&2; exit 1
@echo off
setlocal
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 9))" >NUL 2>&1 && set "PY=python"
if not defined PY (py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >NUL 2>&1 && set "PY=py -3")
if not defined PY (python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >NUL 2>&1 && set "PY=python3")
if not defined PY (echo sdd: no Python 3.9 or newer found. Install it from python.org and tick "Add python.exe to PATH"; the sdd hooks need it. If "python" opens the Microsoft Store, turn off its App execution aliases. 1>&2 & exit /b 1)
%PY% %*
exit /b %errorlevel%
