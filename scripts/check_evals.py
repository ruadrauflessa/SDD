"""Static check of evals/ against the `claude plugin eval` case schema, without running anything.

    python scripts/check_evals.py

Checks each case.yaml (schema_version, known keys, execution limits, scaffold script present and
executable) and each grader's frontmatter (type, the fields that type allows, a body where the type
needs one). A real run is `claude plugin eval . --runs 1 --no-publish` (it asks you to trust the
plugin directory once).
"""
import os
import re
import sys
from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parent.parent / "evals"
TOP = {"schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome", "context",
       "execution", "graders"}
CONTEXT = {"scaffold_script", "history_file", "add_dirs"}
EXECUTION = {"prompt", "max_turns", "timeout_seconds", "model", "allowed_tools", "artifact_publish",
             "growthbook_overrides", "append_system_prompt", "env"}
GRADERS = {"regex": {"target", "match", "flags", "weight", "arm"},
           "tool_order": {"before", "after", "weight", "arm"},
           "tool_used": {"tool", "input_match", "min", "max", "weight", "arm"},
           "file_exists": {"path", "exists", "weight", "arm"},
           "llm": {"focus", "weight", "arm"}}
NEEDS_BODY = {"regex", "llm"}


def front(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    return (yaml.safe_load(m.group(1)) or {}, m.group(2).strip()) if m else (None, text)


def main():
    errors, cases = [], [d for d in sorted(EVALS.iterdir()) if (d / "case.yaml").is_file()]
    for d in cases:
        err = lambda msg: errors.append(f"{d.name}: {msg}")
        c = yaml.safe_load((d / "case.yaml").read_text(encoding="utf-8"))
        if not isinstance(c, dict) or not isinstance(c.get("schema_version"), str):
            err("case.yaml needs schema_version as a string")
            continue
        for k in set(c) - TOP:
            err(f"unknown key {k}")
        for k in set(c.get("context") or {}) - CONTEXT:
            err(f"unknown context key {k}")
        ex = c.get("execution") or {}
        for k in set(ex) - EXECUTION:
            err(f"unknown execution key {k}")
        if not (ex.get("prompt") or "").strip():
            err("no execution.prompt")
        if not 0 < ex.get("max_turns", 10) <= 200 or not 0 < ex.get("timeout_seconds", 300) <= 3600:
            err("max_turns must be 1..200 and timeout_seconds 1..3600")
        sc = (c.get("context") or {}).get("scaffold_script")
        if sc and not (d / sc).is_file():
            err(f"scaffold {sc} missing")
        elif sc and not os.access(d / sc, os.X_OK):
            err(f"scaffold {sc} is not executable")
        graders = sorted((d / "graders").glob("*.md"))
        if not graders:
            err("no graders")
        for g in graders:
            fm, body = front(g.read_text(encoding="utf-8"))
            if not isinstance(fm, dict) or fm.get("type") not in GRADERS:
                err(f"{g.name}: type must be one of {', '.join(GRADERS)}")
                continue
            extra = set(fm) - GRADERS[fm["type"]] - {"type"}
            if extra:
                err(f"{g.name}: {fm['type']} does not take {', '.join(sorted(extra))}")
            if fm["type"] in NEEDS_BODY and not body:
                err(f"{g.name}: a {fm['type']} grader needs a body")
            if fm["type"] == "regex":
                re.compile(body)
            if fm["type"] == "tool_used" and fm["tool"] not in ex.get("allowed_tools", []):
                err(f"{g.name}: {fm['tool']} is not in allowed_tools")
            if fm.get("arm") not in (None, "with-only", "both"):
                err(f"{g.name}: arm must be with-only or both")
    print("\n".join(errors) or f"ok: {len(cases)} cases")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
