"""Self-check for bounds_guard.py: python test_bounds_guard.py  (temp files only)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bounds_guard as bg  # noqa: E402

HOOK = HERE / "bounds_guard.py"
ROOT = "C:/GitProjects/Lumina"
WT = ROOT + "/.claude/worktrees/96324-help-docs/src/Docs"
HOME = "C:/Users/dev"
TOOLS = ["C:/Program Files", "C:/Windows", "C:/Users/dev/AppData/Local/Programs"]


def win(command, cwd=ROOT, allow=()):
    b = bg.Bounds(ROOT, cwd, [HOME + "/.claude", "C:/Users/dev/.claude/plugins/cache/sdd"] + list(allow), TOOLS, HOME)
    return b.check(command)


def main():
    fails = []
    os.environ["TEMP"] = r"C:\Users\dev\AppData\Local\Temp"

    def refused(command, part="", **kw):
        why = win(command, **kw)
        if not why or part.lower() not in why.lower().replace("\\", "/"):
            fails.append(f"not refused as wanted ({part!r}): {command!r} -> {why!r}")

    def allowed(command, **kw):
        why = win(command, **kw)
        if why:
            fails.append(f"refused: {command!r} -> {why}")

    # what the screenshot showed: the code copied to a short folder and run from there
    refused(r"robocopy C:\GitProjects\Lumina\.claude\worktrees\96324-help-docs\src\Docs C:\h96324\docs /E", "c:/h96324/docs")
    refused(r'Copy-Item -Recurse "C:\GitProjects\Lumina\.claude\worktrees\x" -Destination C:\h96324', "c:/h96324")
    refused(r"Copy-Item src -Destination:C:\h96324", "c:/h96324")
    refused(r"cd C:\h96324\docs; dotnet run --urls http://localhost:7101", "moves the shell")
    refused(r"Set-Location -Path 'C:\h96324\docs'", "moves the shell")
    refused(r"cd /d C:\h96324", "moves the shell")
    refused(r"Push-Location C:\h96324; dotnet build; Pop-Location", "moves the shell")
    refused(r"dotnet run --project C:\h96324\docs\Docs.csproj", "dotnet on")
    refused(r"C:\h96324\docs\bin\Debug\net8.0\Docs.exe --urls http://localhost:7101", "runs c:/h96324")
    refused(r'& "C:\h96324\docs\run.ps1" -Only docs', "runs c:/h96324")
    refused(r"Start-Process dotnet -ArgumentList run -WorkingDirectory C:\h96324", "runs from")
    refused(r"Start-Process -FilePath C:\h96324\Docs.exe", "runs c:/h96324")
    refused(r"New-Item -ItemType Directory C:\h96324", "new-item on")
    refused(r"mkdir C:\h96324 && xcopy src C:\h96324 /E", "mkdir on")
    refused(r"subst X: C:\GitProjects\Lumina\.claude\worktrees\x", "drive")  # a second name for the folder, outside it
    allowed("subst")
    refused(r"git worktree add C:\wt\96324 dev/x", "git on")
    refused(r"git clone https://dev.azure.com/o/p/_git/r C:\src\r", "git on")
    refused(r"echo done > C:\out.txt", "writes to")
    refused(r"Get-Content a.txt | Out-File C:\Users\dev\Desktop\a.txt", "out-file on")
    refused(r"Copy-Item x $env:TEMP\x", "c:/users")  # temp is outside too (the hint names .claude/tmp)
    refused(r"cp a ~/scratch/a", "c:/users/dev/scratch")
    refused(r'$dest = "C:\h96324\docs"; robocopy src $dest /E', "c:/h96324/docs")
    refused(r"cd ..\..\..; dotnet build", "moves the shell", cwd=ROOT + "/.claude/worktrees")
    refused(r'cmd /c "robocopy src C:\h96324 /E"', "robocopy on")
    refused(r'pwsh -NoProfile -Command "Copy-Item a C:\h96324"', "copy-item on")
    enc = base64.b64encode("Copy-Item a C:\\h96324".encode("utf-16-le")).decode()
    refused(f"powershell -EncodedCommand {enc}", "copy-item on")
    refused(r"python C:\h96324\tool.py", "python on")
    refused(r"dotnet build", "outside the workspace", cwd="C:/h96324/docs")

    # inside the workspace, reads anywhere, installed software, Claude's own folder
    allowed(r"cd C:\GitProjects\Lumina\.claude\worktrees\96324-help-docs\src\Docs && dotnet run --urls http://localhost:7101")
    allowed(r"dotnet build .claude\worktrees\96324-help-docs\src\Docs\Docs.csproj -o .claude\worktrees\96324-help-docs\out")
    allowed(r"cd ..\.. && git status", cwd=WT)
    allowed(r"robocopy /?")
    allowed(r"Get-Content C:\Users\dev\AppData\Local\Docs\log.txt -Tail 50")
    allowed(r"cat ~/.gitconfig; ls C:\ ; Test-Path C:\h96324")
    allowed(r"git -C C:\Other\repo log --oneline -5")
    allowed(r"Select-String -Path C:\logs\*.log -Pattern error")
    allowed(r'& "C:\Program Files\dotnet\dotnet.exe" build')
    allowed(r'"C:\Users\dev\AppData\Local\Programs\Python\Python311\python.exe" -X utf8 C:\Users\dev\.claude\plugins\cache\sdd\scripts\env.py status --id 1')
    allowed(r"python C:\Users\dev\.claude\plugins\cache\sdd\scripts\env.py stack --id 96324 > .claude\tmp\stack.txt 2>&1")
    allowed(r"dotnet test > $null; npm --prefix .claude\worktrees\x\src\Ui install 2>/dev/null")
    allowed(r"robocopy C:\data\in C:\GitProjects\Lumina\.claude\tmp\in", allow=["C:/data"])  # a folder the user trusts
    allowed(r'git commit -m "fix: copy to C:\h96324 no longer needed"')
    allowed(r"curl -s http://localhost:7101/api/v1/documents?activeOnly=true")
    allowed(r"Invoke-RestMethod -Uri http://localhost:7101/api/v1/x")
    allowed(r'cmd /c "type C:\logs\a.log"')
    allowed(r"cd C:\GitProjects\Lumina; dotnet build", cwd="C:/h96324/docs")
    allowed(r"Get-Content C:\x.txt", cwd="C:/h96324/docs")
    allowed("python - <<'EOF'\nprint(1)\nEOF")

    # through stdin, as Claude Code calls it
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
        root = Path(tmp).resolve()
        (root / ".claude").mkdir()
        cfgp = root / ".claude" / "sdd.json"
        cfgp.write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "O", "projects": ["P"]}}))
        out = Path(other).resolve()

        def hook(tool, ti, cwd=root):
            data = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti, "cwd": str(cwd)}
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            p = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(data), capture_output=True, text=True, env=env)
            return p.returncode, p.stderr

        def expect(code, tool, ti, why, **kw):
            got, err = hook(tool, ti, **kw)
            if got != code:
                fails.append(f"{why}: exit {got}, wanted {code} ({err.strip()[:200]})")
            return err

        err = expect(2, "Bash", {"command": f"cp -r src {out}/copy"}, "a copy out of the workspace")
        if "trusted workspace" not in err or "bounds.allow" not in err:
            fails.append(f"no workspace hint in: {err}")
        expect(0, "Bash", {"command": f"ls {out}"}, "a read outside")
        expect(0, "Bash", {"command": f"mkdir -p {root}/.claude/tmp && cp a {root}/.claude/tmp/"}, "a write inside")
        expect(2, "Write", {"file_path": str(out / "a.txt"), "content": "x"}, "Write outside")
        expect(0, "Write", {"file_path": str(root / "notes.md"), "content": "x"}, "Write inside")
        expect(0, "Edit", {"file_path": "notes.md", "old_string": "a", "new_string": "b"}, "a relative Edit inside")
        expect(2, "Edit", {"file_path": "../x/notes.md", "old_string": "a", "new_string": "b"}, "a relative Edit that climbs out")
        expect(0, "Write", {"file_path": str(Path.home() / ".claude" / "plans" / "p.md"), "content": "x"}, "Claude's own folder")
        err = expect(2, "Edit", {"file_path": str(cfgp), "old_string": "{", "new_string": '{"bounds": {"allow": ["/"]},'}, "the agent widening the bounds")
        if "Only the user" not in err:
            fails.append(f"no user-only hint in: {err}")
        expect(0, "Edit", {"file_path": str(cfgp), "old_string": "docs/spec", "new_string": "docs/specs"}, "another sdd.json edit")
        expect(0, "Bash", {"command": f"cp -r src {out}/copy"}, "no sdd workspace: the guard stays out", cwd=out)
        cfgp.write_text(json.dumps({"specRoot": "docs/spec", "ado": {"org": "O", "projects": ["P"]}, "bounds": {"allow": [str(out)]}}))
        expect(0, "Bash", {"command": f"cp -r src {out}/copy"}, "a folder in bounds.allow")
        expect(0, "Write", {"file_path": str(out / "a.txt"), "content": "x"}, "Write to a folder in bounds.allow")

    if fails:
        print("\n".join(fails))
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
