// devops: a pane (/devops) and a status line for the release, sync, release-notes, review and pipeline work. It reads
// `devops.py status --json`, which reads files only (no git, no ADO), at session start, when the pane opens,
// once a minute while it is open, and after every press. Presses that write anything outward (open PRs,
// publish a wiki page) run only an approved plan; Approve itself is the person's press, shown with every
// write the plan makes. The judgement work (what to ask, what to say) stays in the skills: their buttons
// fill the prompt for the person to send.
import type { EngineInterface, Register } from 'claude-code'

import type { DvDraft, DvNotesOpts, DvPlan, DvReviewDetail, DvReviewList, DvReviewPack, DvReviewRow, DvStatus, DvView } from '../types'
import {
  activeWord, ago, askText, asList, needs, page, parseArgs, readyPlans, releaseCounts, releaseRows, releaseTone,
  releaseWord, repoFacts, runArgs, statusText, syncTone, syncWord, versionsNewest, waitingPlans,
} from './view/model'
import type { Tone } from './view/model'
import {
  buildRows, buildTone, buildWord, deployGroups, deployLine, doctorCounts, ENVS, epoch, NOTES_DEFAULTS, notesArgs, PRIORITIES,
  releaseRuns, releaseSteps, SCOPES,
} from './view/pipelines'
import {
  addDraft, draftsFrom, draftWhere, editDraft, findingsFrom, keptDrafts, postPayload, reviewCounts, reviewKey, reviewRows,
  reviewTone, reviewWord, rowFacts, VOTES, voteWord,
} from './view/reviews'

const PANE = 'devops'
const status = { plugin: 'devops', key: 'status' } as const
const error = { plugin: 'devops', key: 'error' } as const
const note = { plugin: 'devops', key: 'note' } as const
const view = { plugin: 'devops', key: 'view' } as const
const busy = { plugin: 'devops', key: 'busy' } as const
const open = { plugin: 'devops', key: 'open' } as const
const versions = { plugin: 'devops', key: 'versions' } as const
const version = { plugin: 'devops', key: 'version' } as const
const confirm = { plugin: 'devops', key: 'confirm' } as const
const reviews = { plugin: 'devops', key: 'reviews' } as const
const reviewsAll = { plugin: 'devops', key: 'reviewsAll' } as const
const review = { plugin: 'devops', key: 'review' } as const
const drafts = { plugin: 'devops', key: 'drafts' } as const
const reviewAsk = { plugin: 'devops', key: 'reviewAsk' } as const
const notesOpts = { plugin: 'devops', key: 'notesOpts' } as const

const TICK_MS = 60_000
const COLORS: Record<Tone, string> = { urgent: '#c0503f', warn: '#c98a12', ok: '#3f9a63', dim: '#7b8794' }
const TABS: Array<[DvView, string]> = [['overview', 'Overview'], ['release', 'Release'], ['sync', 'Sync'], ['notes', 'Notes'], ['reviews', 'Reviews'], ['pipelines', 'Pipelines'], ['guard', 'Guard']]

let python = 'python'  // module state: lost on reload, which is fine
let timer: ReturnType<EngineInterface['clock']['every']> | null = null

type Ran = { code: number; out: string }

/** Runs devops.py; a refusal (exit 1 or 2) is an answer, not a throw. Throws only when python cannot start. */
async function run($: EngineInterface, args: string[], timeoutMs: number, stdin?: string): Promise<Ran> {
  const cwd = await $.session.cwd()
  let why = 'could not run python'
  for (const exe of [python, 'python3', 'py']) {
    try {
      const r = await $.process.run([exe, `${$.plugin.root}/scripts/devops.py`, ...args], { cwd, timeoutMs, ...(stdin != null ? { stdin } : {}) })
      python = exe
      return { code: r.exitCode ?? 0, out: `${r.stdout}${r.stderr ? `\n${r.stderr}` : ''}`.trim() }
    } catch (err) {
      why = String(err instanceof Error ? err.message : err)
      if (!/spawn|ENOENT|not found|could not/i.test(why)) break
    }
  }
  throw new Error(why)
}

/** Reads the status and stores it; the status line follows. */
async function refresh($: EngineInterface): Promise<void> {
  try {
    const r = await run($, ['status', '--json'], 30_000)
    const s = JSON.parse(r.out.split('\n')[0] ?? '') as DvStatus
    await $.state.set(status, s)
    await $.state.set(error, null)
    $.ui.status(statusText(s))
  } catch (err) {
    await $.state.set(error, `devops status: ${String(err instanceof Error ? err.message : err).slice(0, 200)}`)
  }
}

/** A press: runs the command, says what it said (its last lines), and reads the status again. */
async function act($: EngineInterface, label: string, args: string[], timeoutMs = 120_000, stdin?: string): Promise<Ran | null> {
  if ((await $.state.get(busy)).value) return null
  await $.state.set(busy, label)
  let r: Ran | null = null
  try {
    r = await run($, args, timeoutMs, stdin)
    const tail = r.out.split('\n').filter(Boolean).slice(-3).join(' · ').slice(0, 400)
    await $.state.set(note, r.code === 0 ? null : tail)
    $.ui.toast(r.code === 0 ? `${label}: done` : `${label}: ${tail.slice(0, 160)}`)
  } catch (err) {
    await $.state.set(note, String(err instanceof Error ? err.message : err))
  }
  await $.state.set(busy, null)
  await refresh($)
  return r
}

async function loadVersions($: EngineInterface): Promise<void> {
  try {
    const r = await run($, ['versions', '--json'], 60_000)
    const vs = versionsNewest(Object.keys(JSON.parse(r.out.split('\n')[0] ?? '{}') as Record<string, string[]>))
    await $.state.set(versions, vs)
    if (!(await $.state.get(version)).value && vs.length) await $.state.set(version, vs[0] ?? null)
  } catch (err) {
    await $.state.set(note, `Could not read the versions: ${String(err instanceof Error ? err.message : err).slice(0, 200)}`)
  }
}

const tail = (r: Ran) => r.out.split('\n').filter(Boolean).slice(-3).join(' · ').slice(0, 400)
const firstLine = (r: Ran) => r.out.split('\n')[0] ?? ''

/** A Reviews-tab step: says what runs, and what failed. Returns false when another step is running. */
async function reviewStep($: EngineInterface, label: string, work: () => Promise<void>): Promise<boolean> {
  if ((await $.state.get(busy)).value) return false
  await $.state.set(busy, label)
  try {
    await work()
  } catch (err) {
    await $.state.set(note, String(err instanceof Error ? err.message : err).slice(0, 400))
  }
  await $.state.set(busy, null)
  return true
}

/** Every active PR of the workspace's projects (the tab filters to those waiting on the person). Reads ADO. */
async function loadReviews($: EngineInterface): Promise<void> {
  await reviewStep($, 'Reading the PRs from Azure DevOps', async () => {
    const r = await run($, ['reviews', 'list', '--all', '--json'], 300_000)
    if (r.code !== 0) {
      await $.state.set(note, tail(r))
      return
    }
    await $.state.set(reviews, JSON.parse(firstLine(r)) as DvReviewList)
    await $.state.set(note, null)
  })
  await refresh($)
}

async function readReview($: EngineInterface, project: string, id: number): Promise<DvReviewDetail | null> {
  const r = await run($, ['reviews', 'show', '--project', project, '--id', String(id), '--json'], 180_000)
  if (r.code !== 0) {
    await $.state.set(note, tail(r))
    return null
  }
  return JSON.parse(firstLine(r)) as DvReviewDetail
}

/** Opens a PR (or closes it when it is the open one): its detail, and the drafts of a review saved for this push. */
async function openReview($: EngineInterface, row: DvReviewRow): Promise<void> {
  const cur = (await $.state.get(review)).value ?? null
  await $.state.set(reviewAsk, null)
  if (cur && reviewKey(cur) === reviewKey(row)) {
    await $.state.set(review, null)
    return
  }
  await reviewStep($, `Reading PR ${row.id}`, async () => {
    const d = await readReview($, row.project, row.id)
    if (!d) return
    await $.state.set(review, d)
    await $.state.set(drafts, draftsFrom(d.review?.findings ?? []))
    await $.state.set(note, null)
  })
}

/** The quick review: devops.py builds the prompt, one model call answers, and only findings on a line the diff shows
 *  become drafts. The person's own drafts stay. Nothing is posted. */
async function quickReview($: EngineInterface, d: DvReviewDetail): Promise<void> {
  await reviewStep($, `Reviewing PR ${d.id} (one model call)`, async () => {
    const r = await run($, ['reviews', 'pack', '--project', d.project, '--id', String(d.id)], 300_000)
    if (r.code !== 0) {
      await $.state.set(note, tail(r))
      return
    }
    const pack = JSON.parse(firstLine(r)) as DvReviewPack
    const m = await $.model.complete({ model: pack.model, system: pack.system, prompt: pack.prompt, maxTokens: pack.maxTokens, timeoutMs: 300_000 })
    if (!m.isAnswered) {
      await $.state.set(note, `The review call ended with ${m.reason}${'status' in m && m.status ? ` (HTTP ${m.status})` : ''}.`)
      return
    }
    const got = findingsFrom(m.text, pack.lines, pack.maxFindings)
    await run($, ['reviews', 'save', '--key', pack.key], 30_000, JSON.stringify({ findings: got.findings, model: pack.model }))
    const own = ((await $.state.get(drafts)).value ?? []).filter(x => !x.file)
    const fresh = draftsFrom(got.findings)
    await $.state.set(drafts, [...fresh, ...own.map((x, i) => ({ ...x, n: fresh.length + i + 1 }))])
    await $.state.set(review, { ...d, review: { findings: got.findings, model: pack.model, at: Math.floor(Date.now() / 1000) } })
    await $.state.set(note, null)
    $.ui.toast(`${got.findings.length} finding${got.findings.length === 1 ? '' : 's'}${got.dropped ? ` (${got.dropped} dropped: not on a line the diff shows)` : ''}${pack.truncated ? '; the diff was cut to fit' : ''}. Nothing is posted until you press Post.`)
  })
}

/** Posts the kept drafts under the person's name, then reads the PR again. */
async function postDrafts($: EngineInterface, d: DvReviewDetail, ds: DvDraft[]): Promise<void> {
  await reviewStep($, `Posting to PR ${d.id}`, async () => {
    const r = await run($, ['reviews', 'post', '--project', d.project, '--id', String(d.id)], 180_000, postPayload(ds, d.iteration))
    await $.state.set(reviewAsk, null)
    if (r.code !== 0) {
      await $.state.set(note, tail(r))
      return
    }
    $.ui.toast(tail(r))
    await $.state.set(drafts, ds.filter(x => !x.keep))
    const again = await readReview($, d.project, d.id)
    if (again) await $.state.set(review, again)
    await $.state.set(note, null)
  })
}

/** The person's vote, under their name; then the list and the PR are read again. */
async function castVote($: EngineInterface, d: DvReviewDetail, vote: string): Promise<void> {
  const ok = await reviewStep($, `Voting on PR ${d.id}`, async () => {
    const r = await run($, ['reviews', 'vote', '--project', d.project, '--id', String(d.id), '--vote', vote], 120_000)
    await $.state.set(reviewAsk, null)
    if (r.code !== 0) {
      await $.state.set(note, tail(r))
      return
    }
    $.ui.toast(tail(r))
    const again = await readReview($, d.project, d.id)
    if (again) await $.state.set(review, again)
    await $.state.set(note, null)
  })
  if (ok) await loadReviews($)
}

/** The builds on a version's branches, then what each environment runs now. Both read ADO, on a press. */
async function loadPipelines($: EngineInterface, version: string | null): Promise<void> {
  await act($, `Reading the builds${version ? ` of ${version}` : ''}`, ['pipelines', ...(version ? ['--version', version] : [])], 300_000)
  await act($, 'Reading the deployments', ['deployments'], 300_000)
}

function follow($: EngineInterface): void {
  if (!timer) timer = $.clock.every(TICK_MS, () => void refresh($))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'devops',
      description: 'Release prep, team-branch sync, release notes, PR reviews and pipelines in a pane: what needs you, plans to approve, PRs to review and vote on, builds and deployments, conflicts, the guard log',
      argumentHint: '[overview|release [<version>]|sync|notes|reviews|pipelines|guard|refresh]',
    })
    void refresh($).catch(() => undefined)  // one read for the status line; files only
    return next(e)
  })

  on('command.run', { command: 'devops' }, async ($, e) => {
    const a = parseArgs(e.args)
    await $.ui.open({ id: PANE, title: 'devops', closeOnEscape: true, columns: 100 })
    if (a.view) await $.state.set(view, a.view)
    if (a.version) await $.state.set(version, a.version)
    await $.state.set(open, null)
    follow($)
    await refresh($)
    if (a.view === 'release' && !(await $.state.get(versions)).value) await loadVersions($)
    if (a.view === 'reviews' && !(await $.state.get(reviews)).value) await loadReviews($)
    if (a.view === 'pipelines' && !(await $.state.get(status)).value?.pipelines) await loadPipelines($, (await $.state.get(version)).value ?? null)
    return { text: 'devops opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const t = $.ui.resolve(e)
    const { Box, Text, Button, Link } = t
    const Input = 'Input' in t ? t.Input : undefined
    const s = (await $.state.get(status)).value ?? null
    const why = (await $.state.get(error)).value ?? null
    const said = (await $.state.get(note)).value ?? null
    const mode = (await $.state.get(view)).value ?? 'overview'
    const working = (await $.state.get(busy)).value ?? null
    const opened = (await $.state.get(open)).value ?? null
    const vs = (await $.state.get(versions)).value ?? null
    const chosen = (await $.state.get(version)).value ?? null
    const asked = (await $.state.get(confirm)).value ?? null
    const rvList = (await $.state.get(reviews)).value ?? null
    const rvAll = (await $.state.get(reviewsAll)).value ?? false
    const rv = (await $.state.get(review)).value ?? null
    const ds = (await $.state.get(drafts)).value ?? []
    const rvAsk = (await $.state.get(reviewAsk)).value ?? null
    const nOpts = (await $.state.get(notesOpts)).value ?? NOTES_DEFAULTS
    const now = Math.floor(Date.now() / 1000)
    const color = (t: Tone) => COLORS[t]

    const go = (v: DvView) => async () => {
      await $.state.set(view, v)
      await $.state.set(open, null)
      if (v === 'release' && !vs) await loadVersions($)
      if (v === 'reviews' && !rvList) await loadReviews($)
      if (v === 'pipelines' && !s?.pipelines) await loadPipelines($, chosen)
    }
    const toggle = (key: string) => () => $.state.set(open, opened === key ? null : key)
    const fill = (text: string) => () => $.prompt.fill({ text })

    const header = (
      <Box flexDirection="column">
        <Box gap={1} flexWrap="wrap">
          {TABS.map(([v, label]) => <Button key={`tab-${v}`} label={mode === v ? `[${label}]` : label} onPress={go(v)} />)}
          <Text> </Text>
          <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
        </Box>
        {working && <Text color={COLORS.warn}>{working}…</Text>}
        {why && <Text color={COLORS.urgent}>{why}</Text>}
        {said && <Text color={COLORS.urgent} wrap="wrap">{said}</Text>}
      </Box>
    )

    if (!s) {
      return (
        <Box flexDirection="column">
          {header}
          <Text dimColor>{why ? '' : 'Reading the devops state…'}</Text>
        </Box>
      )
    }

    // ---- a plan: what it writes, Approve (the person's own Yes), or run it once approved
    const planBox = (p: DvPlan | undefined) => {
      if (!p) return null
      const args = runArgs(p)
      if (p.done) return <Text dimColor>Plan {p.token}: done.</Text>
      if (asked === p.token && !p.approved) {
        return (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>{p.summary}?</Text>
            {p.lines.map((ln, i) => <Text key={`pl-${i}`} dimColor wrap="wrap">  {ln}</Text>)}
            <Text dimColor>Approving lets these writes run now, or when Claude runs them. Nothing runs on this press.</Text>
            <Box gap={1}>
              <Button key={`approve-${p.token}`} label="Approve" onPress={async () => {
                await act($, 'Approving', ['approve', '--token', p.token, '--via', 'pane'], 30_000)
                await $.state.set(confirm, null)
              }} />
              <Button key="cancel" label="Cancel" onPress={() => $.state.set(confirm, null)} />
            </Box>
          </Box>
        )
      }
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text color={p.approved ? COLORS.ok : COLORS.warn} wrap="wrap">
            Plan {p.token}: {p.summary} · {p.approved ? 'approved' : 'waiting for your approval'}
          </Text>
          <Box gap={1} flexWrap="wrap">
            {!p.approved && <Button key={`review-${p.token}`} label="Review & approve…" onPress={() => $.state.set(confirm, p.token)} />}
            {p.approved && args && <Button key={`run-${p.token}`} label={p.kind === 'notes' ? 'Publish now' : 'Open the PRs now'}
              onPress={() => act($, p.kind === 'notes' ? 'Publishing' : 'Opening the PRs', args, 600_000)} />}
          </Box>
        </Box>
      )
    }
    const planOf = (token: string | null | undefined) => (token ? s.plans.find(p => p.token === token) : undefined)

    // ---- overview: what needs the person
    if (mode === 'overview') {
      const ns = needs(s)
      const rel = s.release[0]
      const doc = s.doctor
      const dc = doctorCounts(doc)
      return (
        <Box flexDirection="column">
          {header}
          <Text bold>Needs you</Text>
          {ns.length === 0 && <Text color={COLORS.ok}>Nothing waits for you.</Text>}
          {ns.map(n => (
            <Box key={n.key} gap={1}>
              <Text color={color(n.tone)}>●</Text>
              <Button key={`need-${n.key}`} label={n.text} onPress={go(n.view)} />
            </Box>
          ))}
          <Box flexDirection="column" marginTop={1}>
            {rel && <Text dimColor>Release {rel.version}: {(() => { const c = releaseCounts(rel); return `${c.ready} ready · ${c.conflicts} conflicts · ${c.missing} without a release branch · scanned ${ago(rel.generated, now)}` })()}</Text>}
            <Text dimColor>{s.sync.scans.length} sync scans · {Object.keys(s.sync.active ?? {}).length} syncs in progress · {s.notes.runs.length} release-notes runs · {s.guard.recent.length} recent guard refusals</Text>
            {deployLine(s.deployments) && <Text dimColor>Deployed now: {deployLine(s.deployments)} · read {ago(s.deployments?.generated, now)}</Text>}
          </Box>
          <Box gap={1} flexWrap="wrap" marginTop={1}>
            <Button key="ask-release" label="Prepare a release…" onPress={fill(askText('release'))} />
            <Button key="ask-sync" label="Sync team branches…" onPress={fill(askText('sync'))} />
            <Button key="ask-notes" label="Release notes…" onPress={fill(askText('notes'))} />
          </Box>
          <Box flexDirection="column" marginTop={1}>
            <Box gap={1}>
              <Text bold>Setup</Text>
              {doc ? <Text color={dc.fail ? COLORS.urgent : dc.warn ? COLORS.warn : COLORS.ok}>{dc.fail ? `${dc.fail} problem${dc.fail === 1 ? '' : 's'}` : dc.warn ? `${dc.warn} warning${dc.warn === 1 ? '' : 's'}` : 'all good'} · checked {ago(doc.generated, now)}</Text>
                : <Text dimColor>not checked yet</Text>}
              <Button key="doctor" label="Check setup" onPress={() => act($, 'Checking the setup (tools, sign-in, access, wiki)', ['doctor'], 300_000)} />
            </Box>
            {(doc?.rows ?? []).filter(r => r.state !== 'ok').map((r, i) => (
              <Box key={`doc-${i}`} flexDirection="column" marginLeft={1}>
                <Text color={r.state === 'fail' ? COLORS.urgent : COLORS.warn} wrap="wrap">● {r.name}: {r.detail}</Text>
                {r.fix && <Text dimColor wrap="wrap">    {r.fix}</Text>}
              </Box>
            ))}
          </Box>
        </Box>
      )
    }

    // ---- release prep: the scan, the plan, the PRs
    if (mode === 'release') {
      const rel = s.release.find(r => r.version === chosen) ?? (chosen ? undefined : s.release[0])
      const rows = releaseRows(rel)
      const c = releaseCounts(rel)
      const p = page(rows, 0, 40)
      const steps = releaseSteps(rel, s.plans, s.notes.runs)
      const runsOf = releaseRuns(s.notes.runs, rel?.version)
      const hasPrs = !!rel && (rel.results.some(x => x.prId) || rel.repos.some(x => x.pr))
      const setOpts = (patch: Partial<DvNotesOpts>) => () => $.state.set(notesOpts, { ...nOpts, ...patch })
      const writeNotes = async () => {
        const args = rel ? notesArgs(rel.version, nOpts) : null
        if (!args) {
          await $.state.set(note, 'Pick the environment the notes are for first (QA, UAT, STAGE or PROD): it is never guessed.')
          return
        }
        await act($, `Writing the release notes for ${rel?.version} (${nOpts.env})`, args, 600_000)
      }
      return (
        <Box flexDirection="column">
          {header}
          <Box gap={1} flexWrap="wrap">
            <Text dimColor>Version:</Text>
            {(vs ?? []).slice(0, 6).map(v => <Button key={`v-${v}`} label={v === chosen ? `[${v}]` : v} onPress={() => $.state.set(version, v)} />)}
            {!vs && <Button key="load-versions" label="Read versions" onPress={() => loadVersions($)} />}
          </Box>
          {chosen && (
            <Box gap={1} flexWrap="wrap">
              <Button key="scan" label={`Scan ${chosen}`} onPress={() => act($, `Scanning ${chosen} (fetching every repo)`, ['release', 'scan', '--version', chosen], 600_000)} />
              <Button key="ask-prep" label={`Ask Claude to prepare ${chosen}`} onPress={fill(askText('release', chosen))} />
            </Box>
          )}
          {rel && (
            <Box gap={1} flexWrap="wrap">
              {steps.map(st => (
                <Text key={`step-${st.key}`} color={st.state === 'done' ? COLORS.ok : st.state === 'now' ? COLORS.warn : COLORS.dim}>
                  {st.state === 'done' ? '✓' : st.state === 'now' ? '▶' : '○'} {st.label}
                </Text>
              ))}
            </Box>
          )}
          {!rel && <Text dimColor>{chosen ? `No scan of ${chosen} yet. Press Scan, or ask Claude.` : 'Pick a version.'}</Text>}
          {rel && (
            <Box flexDirection="column">
              <Text dimColor>{rel.source} → {rel.target} · scanned {ago(rel.generated, now)}{rel.fetched ? '' : ' without a fetch'}</Text>
              <Box gap={2}>
                {c.conflicts > 0 && <Text color={COLORS.urgent}>● {c.conflicts} conflict</Text>}
                {c.missing > 0 && <Text color={COLORS.urgent}>● {c.missing} no release branch</Text>}
                {c.ready > 0 && <Text color={COLORS.ok}>● {c.ready} ready</Text>}
                <Text color={COLORS.dim}>● {c.quiet} nothing to do</Text>
              </Box>
              {!rel.ado && <Text color={COLORS.warn} wrap="wrap">ADO not read ({rel.adoError ?? 'skipped'}): pending PRs and work items are not checked.</Text>}
              {p.rows.map(r => {
                const key = `rel-${r.repo}`
                const tone = color(releaseTone(r))
                return (
                  <Box key={key} flexDirection="column">
                    <Box gap={1}>
                      <Text color={tone}>●</Text>
                      <Box flexGrow={1} flexShrink={1} minWidth={0}><Button key={key} label={r.repo} onPress={toggle(key)} /></Box>
                      <Text color={tone}>{releaseWord(r)}</Text>
                    </Box>
                    {opened === key && (
                      <Box flexDirection="column" marginLeft={2} marginBottom={1}>
                        {repoFacts(r).map((f, i) => <Text key={`f${i}`} dimColor wrap="wrap">{f}</Text>)}
                        {r.migrations.map(m => <Text key={m.path} color={COLORS.warn} wrap="wrap">migration ({m.kind}): {m.path}</Text>)}
                        {r.loose.map(l => <Text key={l.sha} dimColor wrap="wrap">no work item: {l.sha} {l.subject}</Text>)}
                        {r.conflicts.map(f => <Text key={f} color={COLORS.urgent}>conflict: {f}</Text>)}
                        {r.missingTarget && !r.missingSource && r.branchesUrl && <Link href={r.branchesUrl} label={`Create ${rel.target} from ${r.source ?? rel.source} (branches page)`} />}
                        {r.pr && <Link href={r.pr.url} label={`Open release PR ${r.pr.id}`} />}
                      </Box>
                    )}
                  </Box>
                )
              })}
              {rel.pending.length > 0 && <Text bold>PRs still headed into {rel.source}</Text>}
              {rel.pending.map(x => (
                <Box key={`pend-${x.id}`} flexDirection="column" marginLeft={1}>
                  <Link href={x.url} label={`PR ${x.id} ${x.repo}: ${x.title}`} />
                  <Text dimColor wrap="wrap">{x.case === 'ready' ? 'rides this release only if it merges before the release PR completes'
                    : x.case === 'uptodate' ? 'needs a release PR this run did not raise, once it merges' : 'repo not in this release'}</Text>
                </Box>
              ))}
              {planBox(planOf(rel.token))}
              {rel.results.map((x, i) => (x.url
                ? <Link key={`res-${i}`} href={x.url} label={`${x.action ?? 'PR'} ${x.prId} ${x.repo}${x.missing?.length ? ` (could not link ${x.missing.join(', ')})` : ''}`} />
                : <Text key={`res-${i}`} color={COLORS.urgent} wrap="wrap">{x.repo}: {x.error}</Text>))}
              <Box flexDirection="column" marginTop={1}>
                <Text bold>Release notes</Text>
                {!hasPrs && <Text dimColor>Open the release PRs first: the notes are made from them.</Text>}
                {hasPrs && (
                  <Box flexDirection="column">
                    <Box gap={1} flexWrap="wrap">
                      <Text dimColor>Environment:</Text>
                      {ENVS.map(e => <Button key={`env-${e}`} label={nOpts.env === e ? `[${e}]` : e} onPress={setOpts({ env: e })} />)}
                    </Box>
                    <Box gap={1} flexWrap="wrap">
                      <Text dimColor>Scope:</Text>
                      {SCOPES.map(([k, label]) => <Button key={`scope-${k}`} label={nOpts.scope === k ? `[${label}]` : label} onPress={setOpts({ scope: k })} />)}
                    </Box>
                    <Box gap={1} flexWrap="wrap">
                      <Text dimColor>Priority:</Text>
                      {PRIORITIES.map(([k, label]) => <Button key={`prio-${k}`} label={nOpts.priority === k ? `[${label}]` : label} onPress={setOpts({ priority: k })} />)}
                    </Box>
                    <Box gap={1} flexWrap="wrap">
                      <Text dimColor>Look for:</Text>
                      <Button key="opt-mig" label={`Migrations: ${nOpts.migrations ? 'yes' : 'no'}`} onPress={setOpts({ migrations: !nOpts.migrations })} />
                      <Button key="opt-skills" label={`Skill files: ${nOpts.skills ? 'yes' : 'no'}`} onPress={setOpts({ skills: !nOpts.skills })} />
                    </Box>
                    <Box marginTop={1}><Button key="write-notes" label={runsOf.length ? `Write the notes for ${rel.version} again` : `Write the notes for ${rel.version}`} onPress={writeNotes} /></Box>
                  </Box>
                )}
                {runsOf.map(r => (
                  <Box key={`rn-${r.run}`} flexDirection="column" marginTop={1}>
                    <Text color={r.stage === 'published' ? COLORS.ok : COLORS.warn}>{r.title ?? `run ${r.run}`} · {r.stage}{r.facts?.since ? ` · after ${r.facts.env} ${r.facts.since.version ?? r.facts.since.build}` : ''}</Text>
                    {r.file && <Text dimColor wrap="wrap">  {r.file}</Text>}
                    {(r.needText ?? []).length > 0 && (
                      <Box flexDirection="column">
                        <Text color={COLORS.warn} wrap="wrap">Each bug needs one line on what its fix changed for the user:</Text>
                        {(r.needText ?? []).map(b => (
                          <Box key={`bug-${r.run}-${b.id}`} flexDirection="column" marginLeft={1}>
                            <Text wrap="wrap">ADO {b.id} {b.title}</Text>
                            {Input && <Input key={`bugline-${r.run}-${b.id}`} placeholder="One sentence, plain English (Enter saves and renders again)" submitLabel="Save"
                              onSubmit={v => { if (v.trim()) void act($, `Saving the line for ADO ${b.id}`, ['notes', 'text', '--run', r.run, '--id', String(b.id)], 120_000, v.trim()) }} />}
                          </Box>
                        ))}
                        <Box marginLeft={1}><Button key={`ask-bugs-${r.run}`} label="Ask Claude to write these lines" onPress={fill(askText('bugs', r.run))} /></Box>
                      </Box>
                    )}
                    {r.url && <Link href={r.url} label="Open the wiki page" />}
                    {r.stage === 'rendered' && !(r.needText ?? []).length && planBox(planOf(r.token))}
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Box>
      )
    }

    // ---- team-branch sync: conflicts that wait for the person, the snapshot, the scans, the plan
    if (mode === 'sync') {
      const active = Object.values(s.sync.active ?? {})
      const snap = asList(s.sync.snapshot?.entries)
      const syncPlans = s.plans.filter(p => p.kind === 'sync-prs' && !p.done)
      const waves = asList(s.sync.chain?.waves)
      return (
        <Box flexDirection="column">
          {header}
          {active.length > 0 && <Text bold>Sync merges in progress</Text>}
          {active.map(a => (
            <Box key={`act-${a.repo}`} flexDirection="column">
              <Box gap={1}>
                <Text color={a.state === 'conflict' ? COLORS.urgent : COLORS.ok}>●</Text>
                <Text>{a.repo} · {a.branch}</Text>
                <Text color={a.state === 'conflict' ? COLORS.urgent : COLORS.dim}>{activeWord(a)}</Text>
              </Box>
              {a.state === 'conflict' && a.conflicts.map(f => <Text key={`${a.repo}-${f}`} color={COLORS.urgent}>    {f}</Text>)}
              {a.state === 'conflict' && <Text dimColor>    in {a.path}. Resolve each hunk and stage it; Claude will not edit these files.</Text>}
              {a.state === 'conflict' && <Box marginLeft={4}><Button key={`verify-${a.repo}`} label="I resolved it: ask Claude to verify" onPress={fill(askText('verify', a.repo))} /></Box>}
            </Box>
          ))}
          {snap.length > 0 && (
            <Box flexDirection="column" marginTop={1}>
              <Text bold>Snapshot (saved {s.sync.snapshot?.savedAt ?? '?'})</Text>
              {snap.map(x => <Text key={`snap-${x.Repo}`} dimColor>  {x.Repo}: back to {x.OriginalBranch ?? '(detached)'}{x.StashSha ? `, stash ${x.StashSha.slice(0, 10)}` : ', was clean'}</Text>)}
              {opened === 'restore'
                ? (
                  <Box gap={1}>
                    <Text color={COLORS.warn}>Switch these repos back and re-apply their stashes now?</Text>
                    <Button key="restore-yes" label="Restore" onPress={async () => { await $.state.set(open, null); await act($, 'Restoring the snapshot', ['sync', 'restore'], 300_000) }} />
                    <Button key="restore-no" label="Cancel" onPress={() => $.state.set(open, null)} />
                  </Box>
                )
                : <Button key="restore" label="Restore…" onPress={() => $.state.set(open, 'restore')} />}
            </Box>
          )}
          {waves.length > 0 && (
            <Box flexDirection="column" marginTop={1}>
              <Text bold>Chain: {asList(s.sync.chain?.versions).join(' → ')}</Text>
              {waves.map(w => <Text key={`w-${w.Destination}`} dimColor>  → {w.Destination}: {asList(w.Groups as Array<{ Source: string; Repos: string[] | string }>).map(g => `${g.Source} [${asList(g.Repos).join(', ')}]`).join(' · ')}</Text>)}
            </Box>
          )}
          {s.sync.scans.slice(0, 3).map(sc => (
            <Box key={sc.file} flexDirection="column" marginTop={1}>
              <Text bold>{sc.source} → {sc.destination} <Text dimColor>· scanned {ago(sc.generated, now)}</Text></Text>
              {sc.repos.map(r => {
                const pr = sc.prs.find(x => x.repo === r.Repo)
                return (
                  <Box key={`${sc.file}-${r.Repo}`} gap={1}>
                    <Text color={color(syncTone(r))}>●</Text>
                    <Box flexGrow={1} flexShrink={1} minWidth={0}><Text>{r.Repo}</Text></Box>
                    {pr?.prUrl ? <Link href={pr.prUrl} label={`PR ${pr.prId}`} /> : <Text color={color(syncTone(r))}>{syncWord(r)}</Text>}
                  </Box>
                )
              })}
            </Box>
          ))}
          {syncPlans.map(p => <Box key={`sp-${p.token}`}>{planBox(p)}</Box>)}
          {Object.entries(s.sync.techStories ?? {}).map(([proj, t]) => <Link key={`ts-${proj}`} href={t.url} label={`${proj}: team-sync work item ADO ${t.id}`} />)}
          {s.sync.reports.slice(0, 3).map(r => <Text key={r} dimColor wrap="wrap">report: {r}</Text>)}
          {!active.length && !snap.length && !s.sync.scans.length && <Text dimColor>No sync yet.</Text>}
          <Box marginTop={1}><Button key="ask-sync2" label="Ask Claude to sync team branches" onPress={fill(askText('sync'))} /></Box>
        </Box>
      )
    }

    // ---- release notes: runs, approval, publishing
    if (mode === 'notes') {
      return (
        <Box flexDirection="column">
          {header}
          {s.notes.runs.length === 0 && <Text dimColor>No release notes yet.</Text>}
          {s.notes.runs.map(r => (
            <Box key={`run-${r.run}`} flexDirection="column" marginBottom={1}>
              <Box gap={1}>
                <Text color={r.stage === 'published' ? COLORS.ok : r.stage === 'rendered' ? COLORS.warn : COLORS.dim}>●</Text>
                <Text>{r.title ?? `run ${r.run}`}</Text>
                <Text dimColor>{r.stage}{r.facts ? ` · ${r.facts.items} items · ${r.facts.day}` : ''}</Text>
              </Box>
              {r.file && <Text dimColor wrap="wrap">  {r.file}</Text>}
              {r.url && <Link href={r.url} label="  Open the wiki page" />}
              {r.stage === 'rendered' && planBox(planOf(r.token))}
            </Box>
          ))}
          {s.notes.files.length > 0 && <Text bold>Files</Text>}
          {s.notes.files.slice(0, 6).map(f => <Text key={f.path} dimColor>  {f.name} · {ago(f.at, now)}</Text>)}
          <Box marginTop={1}><Button key="ask-notes2" label="Ask Claude for release notes" onPress={fill(askText('notes'))} /></Box>
        </Box>
      )
    }

    // ---- PR reviews: what waits on the person, a quick review, their comments and their vote
    if (mode === 'reviews') {
      const rows = reviewRows(rvList, rvAll)
      const c = reviewCounts(rvList)
      const sev: Record<string, string> = { high: COLORS.urgent, medium: COLORS.warn, low: COLORS.dim }
      const kept = keptDrafts(ds)
      const detail = (d: DvReviewDetail) => {
        const ask = VOTES.find(v => v.key === rvAsk)
        return (
          <Box flexDirection="column" marginLeft={2} marginBottom={1}>
            <Text dimColor wrap="wrap">{rowFacts(d)}</Text>
            <Link href={d.url} label={`Open PR ${d.id} in Azure DevOps`} />
            {d.policies.length > 0 && (
              <Text wrap="wrap">{d.policies.map(p => `${p.status === 'approved' ? '✓' : p.status === 'rejected' ? '✗' : '…'} ${p.name}${p.blocking ? '' : ' (optional)'}`).join('   ')}</Text>
            )}
            {d.workItems.map(w => <Text key={`wi-${w.id}`} dimColor wrap="wrap">ADO {w.id} {w.type} [{w.state}] {w.title}</Text>)}
            <Text dimColor>{d.files.length} files · {d.threads.length} comment threads · iteration {d.iteration}</Text>
            {d.threads.slice(0, 5).map(th => (
              <Text key={`th-${th.id}`} dimColor wrap="wrap">  {th.file ? `${th.file}:${th.line} ` : ''}{th.author}: {th.text}{th.replies ? ` (+${th.replies})` : ''} [{th.status}]</Text>
            ))}
            <Box gap={1} flexWrap="wrap" marginTop={1}>
              <Button key="quick-review" label={d.review ? 'Review again' : 'Quick review'} onPress={() => quickReview($, d)} />
              {d.review && <Text dimColor>{d.review.findings.length} findings from {d.review.model ?? 'the model'} on this push</Text>}
            </Box>
            {ds.map(x => (
              <Box key={`draft-${x.n}`} flexDirection="column" marginTop={1}>
                <Box gap={1}>
                  <Text color={x.severity ? sev[x.severity] : COLORS.dim}>{x.severity ? `[${x.severity}]` : '[yours]'}</Text>
                  <Text dimColor>{draftWhere(x)}</Text>
                  <Button key={`keep-${x.n}`} label={x.keep ? 'Keep' : 'Dropped'} onPress={() => $.state.set(drafts, editDraft(ds, x.n, { keep: !x.keep }))} />
                </Box>
                <Text wrap="wrap" dimColor={!x.keep}>{x.text}</Text>
                {x.suggestion && <Text dimColor wrap="wrap">  suggestion: {x.suggestion}</Text>}
                {Input && x.keep && (
                  <Input key={`edit-${x.n}`} placeholder="Rewrite this comment (Enter saves)" submitLabel="Save"
                    onSubmit={v => { if (v.trim()) void $.state.set(drafts, editDraft(ds, x.n, { text: v.trim() })) }} />
                )}
              </Box>
            ))}
            {Input && (
              <Box marginTop={1}>
                <Input key="add-comment" placeholder="Add a comment on the whole PR (Enter adds it)" submitLabel="Add"
                  onSubmit={v => void $.state.set(drafts, addDraft(ds, v))} />
              </Box>
            )}
            {rvAsk === 'post' ? (
              <Box flexDirection="column" marginTop={1}>
                <Text bold>Post {kept.length} comment{kept.length === 1 ? '' : 's'} on PR {d.id} as {d.me}?</Text>
                {kept.map(x => <Text key={`pp-${x.n}`} dimColor wrap="wrap">  {draftWhere(x)}: {x.text}</Text>)}
                <Box gap={1}>
                  <Button key="post-yes" label="Post" onPress={() => postDrafts($, d, ds)} />
                  <Button key="post-no" label="Cancel" onPress={() => $.state.set(reviewAsk, null)} />
                </Box>
              </Box>
            ) : kept.length > 0 && (
              <Box marginTop={1}><Button key="post" label={`Post ${kept.length} comment${kept.length === 1 ? '' : 's'}…`} onPress={() => $.state.set(reviewAsk, 'post')} /></Box>
            )}
            <Box flexDirection="column" marginTop={1}>
              <Text>Your vote: {voteWord(d.myVote)}</Text>
              {!d.canVote && <Text color={COLORS.urgent} wrap="wrap">{d.voteNote}</Text>}
              {d.canVote && d.voteNote && <Text dimColor wrap="wrap">{d.voteNote}</Text>}
              {ask ? (
                <Box gap={1}>
                  <Text color={COLORS.warn}>{ask.label} PR {d.id} as {d.me}?</Text>
                  <Button key="vote-yes" label="Vote" onPress={() => castVote($, d, ask.key)} />
                  <Button key="vote-no" label="Cancel" onPress={() => $.state.set(reviewAsk, null)} />
                </Box>
              ) : (
                <Box gap={1} flexWrap="wrap">
                  {VOTES.filter(v => d.canVote || v.key === 'reset').map(v => (
                    <Button key={`vote-${v.key}`} label={v.label} onPress={() => $.state.set(reviewAsk, v.key)} />
                  ))}
                </Box>
              )}
            </Box>
          </Box>
        )
      }
      return (
        <Box flexDirection="column">
          {header}
          <Box gap={1} flexWrap="wrap">
            <Button key="rv-waiting" label={rvAll ? `Waiting on me (${c.waiting})` : `[Waiting on me (${c.waiting})]`} onPress={() => $.state.set(reviewsAll, false)} />
            <Button key="rv-all" label={rvAll ? `[All active (${c.active})]` : `All active (${c.active})`} onPress={() => $.state.set(reviewsAll, true)} />
            <Button key="rv-refresh" label="Refresh list" onPress={() => loadReviews($)} />
          </Box>
          {rvList ? <Text dimColor>As {rvList.me || 'you'} · read {ago(rvList.generated, now)}</Text> : <Text dimColor>Not read yet: press Refresh list.</Text>}
          {rvList && rows.length === 0 && <Text color={COLORS.ok}>{rvAll ? 'No active PRs in the workspace projects.' : 'No PR waits for your review.'}</Text>}
          {rows.map(r => {
            const key = reviewKey(r)
            const tone = color(reviewTone(r))
            return (
              <Box key={`row-${key}`} flexDirection="column">
                <Box gap={1}>
                  <Text color={tone}>●</Text>
                  <Box flexGrow={1} flexShrink={1} minWidth={0}><Button key={`pr-${key}`} label={`${r.repo} · ${r.title}`} onPress={() => openReview($, r)} /></Box>
                  <Text color={tone}>{reviewWord(r)}</Text>
                </Box>
                {rv && reviewKey(rv) === key && detail(rv)}
              </Box>
            )
          })}
        </Box>
      )
    }

    // ---- pipelines: the newest build of each pipeline on the version's branches, and what each environment runs now
    if (mode === 'pipelines') {
      const pl = s.pipelines
      const dep = s.deployments
      const builds = buildRows(pl)
      return (
        <Box flexDirection="column">
          {header}
          <Box gap={1} flexWrap="wrap">
            <Text dimColor>Version:</Text>
            {(vs ?? []).slice(0, 6).map(v => <Button key={`pv-${v}`} label={v === chosen ? `[${v}]` : v} onPress={() => $.state.set(version, v)} />)}
            {!vs && <Button key="p-load-versions" label="Read versions" onPress={() => loadVersions($)} />}
            <Button key="read-builds" label={`Read builds${chosen ? ` of ${chosen}` : ''}`} onPress={() => act($, `Reading the builds${chosen ? ` of ${chosen}` : ''}`, ['pipelines', ...(chosen ? ['--version', chosen] : [])], 300_000)} />
            <Button key="read-deploys" label="Read deployments" onPress={() => act($, 'Reading the deployments', ['deployments'], 300_000)} />
          </Box>
          <Text bold>Builds{pl ? ` on ${pl.branches.join(', ')}` : ''}</Text>
          {!pl && <Text dimColor>Not read yet: press Read builds.</Text>}
          {pl && <Text dimColor>read {ago(pl.generated, now)}{pl.version !== chosen && chosen ? ` (version ${pl.version}; press Read builds for ${chosen})` : ''}</Text>}
          {pl && builds.length === 0 && pl.errors.length === 0 && <Text dimColor>No builds on these branches.</Text>}
          {builds.map(b => {
            const key = `b-${b.id}`
            const tone = color(buildTone(b))
            return (
              <Box key={`row-${key}`} flexDirection="column">
                <Box gap={1}>
                  <Text color={tone}>●</Text>
                  <Box flexGrow={1} flexShrink={1} minWidth={0}><Button key={key} label={`${b.repo} · ${b.pipeline} · ${b.branch}`} onPress={toggle(key)} /></Box>
                  <Text color={tone}>{buildWord(b)}</Text>
                </Box>
                {b.failing && <Text color={COLORS.urgent} wrap="wrap">    {b.failing.step}{b.failing.message ? `: ${b.failing.message}` : ''}</Text>}
                {opened === key && (
                  <Box flexDirection="column" marginLeft={2}>
                    <Text dimColor>{b.number} · queued {ago(epoch(b.queued), now)}{b.finished ? ` · finished ${ago(epoch(b.finished), now)}` : ''}</Text>
                    <Link href={b.url} label="Open the build in Azure DevOps" />
                  </Box>
                )}
              </Box>
            )
          })}
          {(pl?.errors ?? []).map((e, i) => <Text key={`pe-${i}`} color={COLORS.urgent} wrap="wrap">could not read {e}</Text>)}
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Deployed now</Text>
            {!dep && <Text dimColor>Not read yet: press Read deployments.</Text>}
            {dep && <Text dimColor>read {ago(dep.generated, now)}</Text>}
            {dep && dep.rows.length === 0 && dep.errors.length === 0 && <Text dimColor>No deployments found (YAML environments or classic release stages).</Text>}
            {deployGroups(dep).map(g => (
              <Box key={`env-${g.env}`} flexDirection="column">
                <Text>{g.env}</Text>
                {g.rows.map((d, i) => (
                  <Box key={`dep-${g.env}-${i}`} gap={1} marginLeft={2}>
                    <Box flexGrow={1} flexShrink={1} minWidth={0}>
                      {d.url ? <Link href={d.url} label={`${d.pipeline} → ${d.repo || d.project} ${d.version ?? d.branch}${d.build ? ` (${d.build})` : ''}`} />
                        : <Text>{d.pipeline} → {d.repo || d.project} {d.version ?? d.branch}</Text>}
                    </Box>
                    <Text dimColor>{ago(epoch(d.at), now)}</Text>
                  </Box>
                ))}
              </Box>
            ))}
            {(dep?.errors ?? []).map((e, i) => <Text key={`de-${i}`} color={COLORS.warn} wrap="wrap">could not read {e}</Text>)}
          </Box>
        </Box>
      )
    }

    // ---- the guard: what it protects, and what it refused lately
    const g = s.config.guard
    return (
      <Box flexDirection="column">
        {header}
        <Text color={g.enabled ? COLORS.ok : COLORS.urgent}>● Guard {g.enabled ? 'on' : 'OFF (guard.enabled is false in .claude/devops.json)'}</Text>
        <Text dimColor wrap="wrap">Protected branches: {g.protectedBranches.join(', ')}</Text>
        <Text dimColor wrap="wrap">Force push {g.forcePush ? 'allowed on unprotected branches' : 'refused'} · uncommitted work {g.protectWorkingTree ? 'protected' : 'not protected'} · release/sync PRs and release-notes pages {g.requireApproval ? `need your approval (valid ${g.approvalHours}h)` : 'need no approval'}</Text>
        <Text bold>Recent refusals</Text>
        {s.guard.recent.length === 0 && <Text dimColor>None.</Text>}
        {s.guard.recent.map((x, i) => (
          <Box key={`g-${i}`} flexDirection="column">
            <Text color={COLORS.warn}>{ago(x.at, now)} · {x.rule}</Text>
            <Text dimColor wrap="wrap">  {x.detail}</Text>
          </Box>
        ))}
        {waitingPlans(s).length + readyPlans(s).length > 0 && <Text dimColor>Plans waiting: see Overview.</Text>}
      </Box>
    )
  })
}
