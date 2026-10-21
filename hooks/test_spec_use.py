"""Self-check for spec_use.py: python test_spec_use.py   (temp folders; a stand-in Ollama on a local port)"""
import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOOK = Path(__file__).with_name("spec_use.py")
QUERY = 'python C:/plugins/sdd/scripts/spec.py query search "guest checkout"'


class Tags(BaseHTTPRequestHandler):
    models = ["nomic-embed-text:latest"]

    def do_GET(self):  # noqa: N802 (http.server's name)
        body = json.dumps({"models": [{"name": n} for n in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(mode, ws, tool, tool_input, cwd=None, session="s1", agent=None, transcript=None):
    data = {"hook_event_name": "PreToolUse" if mode == "pre" else "PostToolUse", "tool_name": tool,
            "tool_input": tool_input, "cwd": str(cwd or ws), "session_id": session,
            "transcript_path": str(transcript or "")}
    if agent:
        data["agent_type"], data["agent_id"] = agent, "a1"
    p = subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(data), capture_output=True, text=True)
    assert p.returncode in (0, 2) and not p.stdout, (tool_input, p.stdout, p.stderr)
    assert mode == "pre" or (p.returncode == 0 and not p.stderr), p.stderr
    return p.returncode, p.stderr


def turn(path, at):
    """A transcript whose last message from the user was sent at `at`."""
    path.write_text("\n".join(json.dumps(r) for r in [
        {"type": "user", "timestamp": "2000-01-01T00:00:00.000Z", "message": {"role": "user", "content": "first"}},
        {"type": "user", "timestamp": at, "message": {"role": "user", "content": "find the checkout specs"}}]))
    return path


def main():
    server = HTTPServer(("127.0.0.1", 0), Tags)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as t:
        t = Path(t).resolve()
        ws = t / "ws"
        cfg = {"specRoot": "docs/spec", "embeddings": {"url": f"http://127.0.0.1:{server.server_port}"}}
        (ws / ".claude").mkdir(parents=True)
        (ws / ".claude" / "sdd.json").write_text(json.dumps(cfg))
        spec = ws / "docs" / "spec"
        epic = spec / "1-EPIC-shop"
        story = epic / "2-US-guest-checkout"
        story.mkdir(parents=True)
        (story / "requirements.md").write_text("Guest checkout")
        (ws / "src").mkdir()
        (spec / ".index").mkdir()
        db = sqlite3.connect(spec / ".index" / "spec.db")
        db.execute("CREATE TABLE emb(id INTEGER PRIMARY KEY, hash TEXT, model TEXT, vec BLOB)")
        db.execute("INSERT INTO emb VALUES(2, 'h', 'nomic-embed-text', x'00')")
        db.commit()
        db.close()
        log = ws / ".claude" / "sdd" / "spec-use.jsonl"
        tp = turn(t / "t.jsonl", "2000-01-02T00:00:00.000Z")

        # a search of many specs is blocked until this turn's meaning query
        code, err = call("pre", ws, "Bash", {"command": "grep -rn checkout docs/spec"}, transcript=tp)
        assert code == 2 and "by meaning first" in err and "query search" in err and "nomic-embed-text" in err, err
        assert call("pre", ws, "Grep", {"pattern": "checkout", "path": str(spec)}, transcript=tp)[0] == 2
        assert call("pre", ws, "Bash", {"command": f"rg checkout {epic}"}, transcript=tp)[0] == 2   # holds items
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec/*/requirements.md"}, transcript=tp)[0] == 2
        assert call("pre", ws, "Bash", {"command": "grep -rn checkout ."}, cwd=spec, transcript=tp)[0] == 2
        assert call("pre", ws, "PowerShell", {"command": f"Select-String -Path {spec} -Pattern x"}, transcript=tp)[0] == 2

        # reading one spec, finding a folder, and every search outside the specs stay open
        open_calls = [
            ("Bash", {"command": f"grep -n Guest {story / 'requirements.md'}"}),   # a file
            ("Bash", {"command": f"grep -rn Guest {story}"}),                       # one item's own folder
            ("Grep", {"pattern": "x", "path": str(spec / ".index")}),               # the index
            ("Glob", {"pattern": "docs/spec/**/2-*"}),
            ("Read", {"file_path": str(story / "requirements.md")}),
            ("Bash", {"command": "grep -rn checkout src/"}),
            ("Bash", {"command": f"cat {story / 'requirements.md'}"}),
            ("Bash", {"command": "git log --oneline | grep checkout"}),
        ]
        for tool, ti in open_calls:
            assert call("pre", ws, tool, ti, transcript=tp)[0] == 0, ti
        assert call("pre", ws, "Grep", {"pattern": "x", "path": str(spec)}, agent="sdd:investigator",
                    transcript=tp)[0] == 0                                        # may not run spec.py

        # only a real run of the query counts
        for cmd in ["echo spec.py query search x", "grep -n 'query search' C:/plugins/sdd/scripts/spec.py",
                    "python C:/plugins/sdd/scripts/spec.py query term Guest"]:
            call("post", ws, "Bash", {"command": cmd})
        assert not log.exists()
        call("post", ws, "Bash", {"command": f"cd {ws} && {QUERY}"})
        recs = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        assert len(recs) == 1 and recs[0]["caller"] == "s1/main" and "query search" in recs[0]["what"], recs

        assert call("pre", ws, "Bash", {"command": "grep -rn checkout docs/spec"}, transcript=tp)[0] == 0
        assert call("pre", ws, "Grep", {"pattern": "x", "path": str(spec)}, agent="general-purpose",
                    transcript=tp)[0] == 2                                        # a sub-agent asks itself
        call("post", ws, "PowerShell", {"command": "& python C:/p/scripts/spec.py query similar --id 2"},
             agent="general-purpose")
        assert call("pre", ws, "Grep", {"pattern": "x", "path": str(spec)}, agent="general-purpose",
                    transcript=tp)[0] == 0
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, session="s2")[0] == 2   # another session
        later = turn(t / "t2.jsonl", "2999-01-01T00:00:00.000Z")                 # the user wrote again: a new turn
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, transcript=later)[0] == 2
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"})[0] == 0   # no transcript: this session

        # meaning search off: the guard is silent
        Tags.models = ["llama3:latest"]                                          # the model is not pulled
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, transcript=later)[0] == 0
        Tags.models = ["nomic-embed-text:latest"]
        db = sqlite3.connect(spec / ".index" / "spec.db")
        db.execute("DELETE FROM emb")
        db.commit()
        db.close()
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, transcript=later)[0] == 0  # nothing embedded
        db = sqlite3.connect(spec / ".index" / "spec.db")
        db.execute("INSERT INTO emb VALUES(2, 'h', 'nomic-embed-text', x'00')")
        db.commit()
        db.close()
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, transcript=later)[0] == 2
        cfg["embeddings"]["url"] = f"http://127.0.0.1:{free_port()}"            # Ollama is not running
        (ws / ".claude" / "sdd.json").write_text(json.dumps(cfg))
        assert call("pre", ws, "Bash", {"command": "grep -rn x docs/spec"}, transcript=later)[0] == 0

        # a broken input never fails the call
        for mode in ("pre", "post"):
            p = subprocess.run([sys.executable, str(HOOK), mode], input="not json", capture_output=True, text=True)
            assert p.returncode == 0 and not p.stderr
        assert call("pre", ws, "Bash", {"command": None})[0] == 0
        assert call("pre", t / "nowhere", "Bash", {"command": "grep -rn x ."}, cwd=t)[0] == 0
    server.shutdown()
    print("ok")


if __name__ == "__main__":
    main()
