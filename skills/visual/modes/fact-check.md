# Mode: fact-check — verify a page against the code and git history

Args: the page path; none = the newest `.html` under the current work item's `visuals/`, else in
`~/.agent/diagrams/`. Renderer: edit the existing page in place.

1. **Extract claims**: file paths, function/type/module names, behaviour, architecture, data flow,
   APIs, commands, dependencies, tests, performance/security statements, git history. Skip
   subjective design opinions.
2. **Verify each** against the source or git history. Re-read the referenced files. For diff
   reviews compare before/after with `git show` or the range. For plans, check that referenced
   files/functions/types exist and behave as described.
3. **Classify**: verified, corrected, unsupported, unverifiable.
4. **Fix in place**, keeping the page's structure and style, and add a short "Verification" section
   listing what was checked and changed. For a Markdown file, report the path in chat.
5. Send the corrected page again.
