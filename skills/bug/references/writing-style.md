# House writing style

Everything this skill writes for a person — the work item, the PR, the commit message, the report in
chat — uses **ASD-STE100 Simplified Technical English** (STE: a controlled-English standard written
for maintenance manuals, so a tired reader, or a reader working in a second language, cannot misread
it).

This is not decoration. The person who reported the bug is often not a developer. The QA person who
picks the item up from `Dev Completed` reads the two write-back fields and nothing else.

## Where it applies

| Output | Phase |
| --- | --- |
| `Custom.RootCauseDetails` and `Microsoft.VSTS.Common.Resolution` | 11 |
| Comments on the work item | 0b, 2, 11 |
| PR title and PR description | 10 |
| Commit message subject and body | 9 |
| The Phase 5 summary, and every report to the user in chat | 5, 8, 9a |

It does **not** apply to anything a machine reads, or anything a person will copy and paste. Keep
these exact. Never "simplify" them:

- file paths, branch names, worktree paths, URLs
- field reference names (`Custom.BoardColumnTitle`), states, picklist values
- error codes (`E200801`), test names, class names, method names
- commands and their flags

## The ten rules

1. **One idea per sentence.** If a sentence holds an "and", a "but", or a comma splice, make it two
   sentences.
2. **Short sentences.** 20 words maximum for an instruction. 25 words maximum for a statement.
3. **Short paragraphs.** 6 sentences maximum. One topic each.
4. **Active voice.** Say who or what did the thing. Write "the gateway dropped the header", not "the
   header was not forwarded". Use the passive only when nobody knows the actor.
5. **Simple tense.** Use the present tense or the simple past. No "would have been". No "will have
   been".
6. **Small words, one meaning each.** Use the swap table below.
7. **Explain a technical word once, in brackets, right after you use it.** Example: "The route had no
   header transform (a rule that adds a header to the call it sends on)."
8. **No filler.** Cut "in order to", "it should be noted that", "as mentioned above", "please be
   aware", "leverage", "utilise", "robust", "seamless", "simply", "basically".
9. **Keep the articles.** Write "the header", not "header". Telegraphic text is not plain text.
10. **Three nouns in a row, maximum.** "User data export failure count" becomes "the number of failed
    user-data exports".

## Word swaps

| Do not write | Write |
| --- | --- |
| utilise, leverage | use |
| commence, initiate | start |
| terminate | stop, end |
| prior to | before |
| subsequent to, following | after |
| in the event that | if |
| in order to | to |
| due to the fact that | because |
| attempt | try |
| sufficient | enough |
| additional | more, extra |
| approximately | about |
| assist | help |
| obtain, acquire | get |
| require | need |
| modify, amend | change |
| verify, validate | check |
| perform, execute | do, run |
| ensure | make sure |
| encounter | get, find |
| occur | happen |
| provide | give |
| regarding, with respect to | about |
| via | by, through |
| erroneous | wrong |
| functionality | what it does, the feature |

## Rewrites

Real cause text, then the same text in house style.

**Before** (one 38-word sentence, passive, no full stops):

> The user was created twice and the first one was deleted, however their password was configured to
> auto sign them in to the first user key thus the second user key would not work

**After**:

> Someone made this user two times. Someone then deleted the first user. The user's password still
> signs them in to the first user key. So the second user key does not work.

**Before**:

> The user with the slower network pulls the chat first, the user with the faster network also pulls
> it, one wins, solution is to do another check before assigning to confirm it was not assigned

**After**:

> Two users opened the same chat at the same moment. The service gave the chat to both of them. It
> did not check the chat again before it assigned the chat.

**Before** (a PR root-cause paragraph):

> The absence of an upstream header transform on the Ocelot route configuration results in the
> application key not being propagated, thereby causing UserStore to reject the proxied request.

**After**:

> The Ocelot route for `lumina_Userstore` has no header transform (a rule that copies a header onto
> the call the gateway sends on). So the gateway drops the `X-Application-Key` header. UserStore then
> rejects the call with `E200801`.

## Reporting to the user in chat

Same rules, plus these:

- Answer three things, in this order. What you did. Did it work. What the user does now.
- A decision gets **two options, maximum**. Give the one fact needed to choose. Say which one you
  would pick, and why, in one sentence.
- One line per verification gate. Give the real number or the real message, not "tests pass".
- No preamble. No summary of the summary.

## HTML for the two long-text fields

Both fields are HTML. Pass `format=Html`. Keep the markup plain:

- one `<div>` per sentence, or one `<div>` with `<br>` between sentences
- no markdown — it does not render
- no headings, no bold, no lists unless there are genuinely three or more items
