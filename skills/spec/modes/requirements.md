# Mode: Requirements

> Part of the `sdd:spec` flow. Its rules (`../SKILL.md`) and the shared flow rules
> (`${CLAUDE_PLUGIN_ROOT}/skills/sdd/references/flow-rules.md`) hold here too. Paths like
> `references/…` and `assets/…` are in the spec skill's folder.

1. **Show where the questions stand** on the requirements page: answered ones with their answers,
   and, when the user continued with a caveat, every question still open, marked as open.
2. **Stop and ask.** Build the `sdd:visual` **requirements** page (`visuals/requirements.html`) — the requirement summary, the answered and open questions and the impact gaps go on the page, not in chat — send it, then run the "Requirements agreed" gate
   with `AskUserQuestion` (see "Approval gates" in `../SKILL.md`). Designing before that answer wastes work
   if the requirement moves.
