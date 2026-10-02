# Writing the three files

Each file answers one question and stops. Content that answers a different question belongs in a
different file — that boundary is what keeps specs short enough to be read.

| File | Answers | Written by |
| --- | --- | --- |
| `requirements.md` | *What must be true when this is done?* | ADO, mirrored |
| `design.md` | *How will it be built, and what did we rule out?* | Repo |
| `tasks.md` | *In what order, touching which files?* | Repo |

## requirements.md — mirrored, not authored

The body is a rendering of ADO fields. The rules that matter:

- **Never supply what ADO doesn't say.** A thin work item stays thin and the gap becomes a
  question to the author. Prose you invented becomes intent nobody agreed to, and it survives
  every future regeneration because nobody remembers it wasn't theirs.
- **Never edit it to fix something.** Fix it in ADO and re-sync; an edit here is overwritten
  silently and the fix is lost.
- Acceptance criteria are mirrored as ADO holds them. Where they are loose, write a
  Given/When/Then reading in `questions.md` **and flag that you reshaped them** — that shape is
  what Verify checks against, and the author confirms it in ADO, not you in the mirror.
- The whole file is machine-owned. `spec.py sync --id <id>` writes it; questions and gaps go in
  `questions.md` next to it, which the sync never touches.

## design.md — the one file with genuine judgment in it

- **Read the code before writing anything.** State what the codebase actually looks like today,
  including the parts that contradict the obvious approach.
- **Anchors earn their place.** File paths, exported symbols and signatures, API routes, event
  and topic names, database tables and migration targets, feature flag keys, config keys. These
  are what overlap detection compares across branches — vague anchors mean a real gate with
  nothing to match on.
- **Record what you rejected and why.** The alternative someone will suggest at review is the one
  worth pre-empting, and in six months the reason is the only part still useful.
- **Risks are specific or absent.** "Performance may be a concern" is noise; "the batch read is
  capped at 200 ids, so a feature with more children needs paging" is a risk.
- A story's design inherits its parent feature's by reference. Link to it; copying guarantees
  divergence.

## tasks.md — executable, not aspirational

- **2–5 minutes of agent work each.** If a task needs a paragraph to explain, it is two tasks.
- Every task names the files it touches and how it is verified — a command, a test name, an
  observable behaviour.
- **Every task traces** to an acceptance criterion or an explicit design decision. One that
  traces to neither is scope creep: drop it, or raise it as its own work item.
- Tests are tasks in sequence, not a trailing "add tests" item.
- Tick tasks as they land. Completed tasks are what a cascade block shows a reviewer, so an
  unticked done task makes the gate less useful, not more.

## Sizing

A story spec that runs past roughly 150 lines across all three files is usually a story that
should have been split. The structural fix beats the editing fix: a spec open three days
accumulates almost no drift or interaction risk, one open six weeks accumulates it regardless of
how well it was written.
