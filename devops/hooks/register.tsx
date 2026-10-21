// devops: a pane (/devops) and a status line for the release, sync and release-notes work. It reads
// `devops.py status --json`, which reads files only (no git, no ADO), at session start, when the pane opens,
// once a minute while it is open, and after every press. Presses that write anything outward (open PRs,
// publish a wiki page) run only an approved plan; Approve itself is the person's press, shown with every
// write the plan makes. The judgement work (what to ask, what to say) stays in the skills: their buttons
// fill the prompt for the person to send.
import type { EngineInterface, Register } from 'claude-code'

import type { DvPlan, DvStatus, DvView } from '../types'
import {
  activeWord, ago, askText, asList, needs, page, parseArgs, readyPlans, releaseCounts, releaseRows, releaseTone,
  releaseWord, repoFacts, runArgs, statusText, syncTone, syncWord, versionsNewest, waitingPlans,
} from './view/model'
import type { Tone } from './view/model'

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

const TICK_MS = 60_000
const COLORS: Record<Tone, string> = { urgent: '#c0503f', warn: '#c98a12', ok: '#3f9a63', dim: '#7b8794' }
const TABS: Array<[DvView, string]> = [['overview', 'Overview'], ['release', 'Release'], ['sync', 'Sync'], ['notes', 'Notes'], ['guard', 'Guard']]

let python = 'python'  // module state: lost on reload, which is fine
let timer: ReturnType<EngineInterface['clock']['every']> | null = null

type Ran = { code: number; out: string }

/** Runs devops.py; a refusal (exit 1 or 2) is an answer, not a throw. Throws only when python cannot start. */
async function run($: EngineInterface, args: string[], timeoutMs: number): Promise<Ran> {
  const cwd = await $.session.cwd()
  let why = 'could not run python'
  for (const exe of [python, 'python3', 'py']) {
    try {
      const r = await $.process.run([exe, `${$.plugin.root}/scripts/devops.py`, ...args], { cwd, timeoutMs })
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
async function act($: EngineInterface, label: string, args: string[], timeoutMs = 120_000): Promise<Ran | null> {
  if ((await $.state.get(busy)).value) return null
  await $.state.set(busy, label)
  let r: Ran | null = null
  try {
    r = await run($, args, timeoutMs)
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

function follow($: EngineInterface): void {
  if (!timer) timer = $.clock.every(TICK_MS, () => void refresh($))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'devops',
      description: 'Release prep, team-branch sync and release notes in a pane: what needs you, plans to approve, PRs, conflicts, the guard log',
      argumentHint: '[overview|release [<version>]|sync|notes|guard|refresh]',
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
    return { text: 'devops opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Link } = $.ui.resolve(e)
    const s = (await $.state.get(status)).value ?? null
    const why = (await $.state.get(error)).value ?? null
    const said = (await $.state.get(note)).value ?? null
    const mode = (await $.state.get(view)).value ?? 'overview'
    const working = (await $.state.get(busy)).value ?? null
    const opened = (await $.state.get(open)).value ?? null
    const vs = (await $.state.get(versions)).value ?? null
    const chosen = (await $.state.get(version)).value ?? null
    const asked = (await $.state.get(confirm)).value ?? null
    const now = Math.floor(Date.now() / 1000)
    const color = (t: Tone) => COLORS[t]

    const go = (v: DvView) => async () => {
      await $.state.set(view, v)
      await $.state.set(open, null)
      if (v === 'release' && !vs) await loadVersions($)
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
          </Box>
          <Box gap={1} flexWrap="wrap" marginTop={1}>
            <Button key="ask-release" label="Prepare a release…" onPress={fill(askText('release'))} />
            <Button key="ask-sync" label="Sync team branches…" onPress={fill(askText('sync'))} />
            <Button key="ask-notes" label="Release notes…" onPress={fill(askText('notes'))} />
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
