# Phase 5 — Prove the root cause  *(read-only)*

> Part of the `sdd:bug` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` are in the bug skill's folder.

## Gate 2 — self-verification, before you write the summary

Answer all six honestly. If any answer is weak, keep investigating — do not proceed to Phase 6.

1. **Location** — can I name the file and line where the wrong behaviour originates?
2. **Mechanism** — can I explain the causal chain from that line to the reported symptom, without
   a gap bridged by "presumably"?
3. **Sufficiency** — does this cause explain *all* of the reported symptom, including any error
   message, code, or count quoted in the ticket? A cause explaining half the symptom is the wrong
   cause or an incomplete one.
4. **Alternatives** — what else could produce this symptom, and how did I rule each out?
5. **History** — when did this break? `git log -S` / `git blame` on the suspect line often names
   the change and tells you whether the fix would undo something intentional — which loops back to
   Gate 1, because "intentional" may mean "specified".
6. **Scope** — does the same flawed pattern exist elsewhere in the repo? Grep for it. Report
   siblings even if you only fix the reported one. List every caller of the function you intend to
   change: `graphify affected "<symbol>" --graph <folder>\graph\graph.json`, then confirm each by
   reading it. A fix in the shared function reaches callers the ticket never named.

Items 5 and 6 (history and every caller) are a good fit for **`sdd:investigator`**: give it the
suspect line and the function you intend to change.

Then, before proposing the fix, ask the question that separates a cause fix from a symptom fix:
**if I make this change, what makes the symptom impossible — rather than merely unobserved?**

## Second opinion — before Phase 6

You answered Gate 2 about your own work. Before you build the bug page, hand **`sdd:skeptic`** (mode
`cause`) the reported symptom, the root cause anchor, the evidence and the proposed fix — not your
reasoning, so it judges the evidence, not the argument. On `does not hold`, keep investigating. On
`holds with gaps`, close each gap or show it on the page. Note the verdict on the Phase 5 `done`
checkpoint (`--note "skeptic: holds"`).
