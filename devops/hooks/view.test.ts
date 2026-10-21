import { expect, test } from 'claude-code/testing'

import type { DvBuild, DvNotesRun, DvPlan, DvRelease, DvReleaseRepo, DvReviewRow, DvStatus } from '../types'
import { activeWord, ago, askText, needs, page, parseArgs, releaseCounts, releaseRows, releaseTone, releaseWord, runArgs, statusText, syncTone, syncWord, versionsNewest, waitingPlans } from './view/model'
import { buildRows, buildWord, deployGroups, deployLine, NOTES_DEFAULTS, notesArgs, releaseRuns, releaseSteps } from './view/pipelines'
import { addDraft, draftsFrom, editDraft, findingsFrom, keptDrafts, postPayload, reviewCounts, reviewRows, reviewWord } from './view/reviews'

const repo = (r: Partial<DvReleaseRepo>): DvReleaseRepo => ({
  repo: 'x', status: 'UpToDate', source: 'team/1', target: 'release/1', ahead: 0, behind: 0, files: 0, insertions: 0, deletions: 0,
  migrations: [], workItems: [], candidates: [], loose: [], conflicts: [], detail: '', branchesUrl: null, missingSource: false,
  missingTarget: false, project: 'P', org: 'O', ...r,
})

const release = (repos: DvReleaseRepo[]): DvRelease => ({
  version: '1.1.0', source: 'team/1.1.0', target: 'release/1.1.0', generated: 0, fetched: true, ado: true, adoError: null,
  repos, pending: [], workItems: {}, dropped: [], token: 'aaaaaaaaaa', results: [],
})

const plan = (p: Partial<DvPlan>): DvPlan => ({ token: 'aaaaaaaaaa', kind: 'release-prs', summary: 'Open 1 release PR', created: 1, items: 1,
  approved: false, done: false, ref: 'release 1.1.0', lines: ['Open PR Gateway: Team/1.1.0 → Release/1.1.0'], ...p })

const STATUS = (extra: Partial<DvStatus> = {}): DvStatus => ({
  root: '/ws', generated: 0,
  config: { reposDir: 'projects', sourcePattern: 'team/{0}', targetPattern: 'release/{0}', branchPrefix: 'team/',
    guard: { enabled: true, protectedBranches: ['main', 'team/*'], forcePush: false, protectWorkingTree: true, requireApproval: true, approvalHours: 24 } },
  release: [], sync: { chain: null, scans: [], active: {}, snapshot: null, techStories: {}, reports: [] },
  notes: { files: [], runs: [] }, plans: [], guard: { recent: [] }, reviews: null, pipelines: null, deployments: null, doctor: null, ...extra,
})

test('versions sort as numbers, newest first', () => {
  expect(versionsNewest(['1.2.0', '1.10.0', '0.9', '1.2.0-rc1'])).toEqual(['1.10.0', '1.2.0-rc1', '1.2.0', '0.9'])
})

test('a release row says what it needs, and a missing release branch is urgent', () => {
  expect(releaseWord(repo({ status: 'Ready', ahead: 3 }))).toBe('3 to release')
  expect(releaseWord(repo({ status: 'Ready', ahead: 3, pr: { id: 7, url: 'u' } }))).toBe('PR 7 open')
  expect(releaseWord(repo({ status: 'Conflicts', conflicts: ['a', 'b'] }))).toBe('⚠ 2 conflicts')
  expect(releaseWord(repo({ status: 'Skipped', missingTarget: true }))).toBe('no release branch')
  expect(releaseWord(repo({ status: 'Skipped', missingSource: true, missingTarget: true }))).toBe('no work')
  expect(releaseTone(repo({ status: 'Skipped', missingTarget: true }))).toBe('urgent')
  expect(releaseTone(repo({ status: 'Ready', migrations: [{ path: 'm.sql', kind: 'SQL Script' }] }))).toBe('warn')
  const rows = releaseRows(release([repo({ repo: 'b', status: 'UpToDate' }), repo({ repo: 'a', status: 'Ready' }), repo({ repo: 'c', status: 'Conflicts' }),
    repo({ repo: 'd', status: 'Skipped', missingTarget: true })]))
  expect(rows.map(r => r.repo)).toEqual(['c', 'd', 'a', 'b'])
  expect(releaseCounts(release(rows))).toEqual({ ready: 1, conflicts: 1, missing: 1, errors: 0, quiet: 1 })
})

test('sync rows and syncs in progress read plainly', () => {
  expect(syncWord({ Repo: 'a', Status: 'Clean', Ahead: 2 })).toBe('2 to bring')
  expect(syncWord({ Repo: 'a', Status: 'PendingPriorHop' })).toBe('waits on prior hop')
  expect(syncTone({ Repo: 'a', Status: 'Conflicts' })).toBe('urgent')
  expect(activeWord({ repo: 'a', path: '/p', branch: 'sync/x', source: 's', destination: 'd', state: 'conflict', conflicts: [] })).toBe('waiting for you to resolve')
})

test('the status line names what needs the person, and is clear otherwise', () => {
  expect(statusText(null)).toBe(undefined)
  expect(statusText(STATUS())).toBe(undefined)
  const s = STATUS({ release: [release([repo({ status: 'Ready' }), repo({ status: 'Skipped', missingTarget: true })])], plans: [plan({})] })
  expect(statusText(s)).toBe('devops · 1 to approve · release 1.1.0: 1 ready, 1 no release branch')
  expect(statusText(STATUS({ plans: [plan({ approved: true })] }))).toBe(undefined)
  expect(statusText(STATUS({ reviews: { generated: 1, waiting: 2, active: 5 } }))).toBe('devops · 2 to review')
  expect(needs(STATUS({ reviews: { generated: 1, waiting: 1, active: 5 } })).map(n => n.text)).toEqual(['1 PR waits for your review'])
})

test('what needs the person: conflicts first, then plans, then branches to cut and the snapshot', () => {
  const s = STATUS({
    release: [release([repo({ repo: 'Docs', status: 'Skipped', missingTarget: true, source: 'team/1.1.0' })])],
    plans: [plan({}), plan({ token: 'bbbbbbbbbb', approved: true, summary: 'Publish' , kind: 'notes', ref: 'notes r1' }), plan({ token: 'cccccccccc', done: true })],
    sync: { chain: null, scans: [], active: { a: { repo: 'a', path: '/a', branch: 'sync/x', source: 's', destination: 'd', state: 'conflict', conflicts: ['f'] } },
      snapshot: { entries: [{ Repo: 'a' }] }, techStories: {}, reports: [] },
  })
  const ns = needs(s)
  expect(ns.map(n => n.key)).toEqual(['conf-a', 'plan-aaaaaaaaaa', 'run-bbbbbbbbbb', 'miss-Docs', 'snapshot'])
  expect(ns[3]?.text).toBe('Create release/1.1.0 in Docs (from team/1.1.0)')
  expect(waitingPlans(s).map(p => p.token)).toEqual(['aaaaaaaaaa'])
})

test('an approved plan runs with the command its kind and ref name', () => {
  expect(runArgs(plan({}))).toEqual(['release', 'open', '--version', '1.1.0'])
  expect(runArgs(plan({ kind: 'notes', ref: 'notes 20261021-1' }))).toEqual(['notes', 'publish', '--run', '20261021-1'])
  expect(runArgs(plan({ kind: 'sync-prs', ref: 'sync team/1.1.0 -> team/1.2.0' }))).toEqual(['sync', 'open', '--source', 'team/1.1.0', '--destination', 'team/1.2.0'])
  expect(runArgs(plan({ ref: 'odd' }))).toBe(null)
})

test('typed arguments, prompts, times and paging', () => {
  expect(parseArgs('release 1.2.0')).toEqual({ view: 'release', version: '1.2.0', refresh: false })
  expect(parseArgs('SYNC')).toEqual({ view: 'sync', version: null, refresh: false })
  expect(parseArgs('pipelines')).toEqual({ view: 'pipelines', version: null, refresh: false })
  expect(parseArgs('refresh')).toEqual({ view: null, version: null, refresh: true })
  expect(parseArgs('')).toEqual({ view: null, version: null, refresh: false })
  expect(askText('release', '1.1.0')).toBe('/devops:release-prep prepare release 1.1.0')
  expect(askText('verify', 'UserStore')).toContain('sync verify --repo UserStore')
  expect(ago(1000 - 7200, 1000)).toBe('2h ago')
  expect(page([1, 2, 3], 0, 2)).toEqual({ rows: [1, 2], from: 1, to: 2, total: 3 })
})

// ---------------------------------------------------------------- the Reviews tab

const prRow = (r: Partial<DvReviewRow>): DvReviewRow => ({ org: 'O', project: 'P', id: 1, repo: 'Gateway', title: 't', author: 'Bo', mine: false,
  source: 'dev/x', target: 'team/1', created: '2026-10-20T10:00:00Z', draft: false, conflicts: false, role: null, myVote: 0, waiting: false,
  votes: [], url: 'u', ...r })

test('the Reviews tab lists what waits on the person by default, and every active PR on request', () => {
  const list = { generated: 1, me: 'Ann', rows: [prRow({ id: 1 }), prRow({ id: 2, waiting: true, role: 'required', created: '2026-10-21T00:00:00Z' }),
    prRow({ id: 3, waiting: true, role: 'optional', created: '2026-10-19T00:00:00Z' })] }
  expect(reviewRows(list, false).map(r => r.id)).toEqual([3, 2])
  expect(reviewRows(list, true).map(r => r.id)).toEqual([3, 2, 1])
  expect(reviewCounts(list)).toEqual({ waiting: 2, active: 3 })
  expect(reviewWord(prRow({ waiting: true, role: 'group Leads (required)' }))).toBe('required')
  expect(reviewWord(prRow({ myVote: 10, role: 'optional' }))).toBe('you: approved')
  expect(reviewWord(prRow({ mine: true }))).toBe('yours')
})

test('a finding stays only on a line the diff shows, most severe first', () => {
  const text = 'Sure: [{"file":"/src/a.cs","line":3,"severity":"low","comment":"Name it"},{"file":"src/a.cs","line":9,"severity":"high","comment":"Made up"},' +
    '{"file":"src/a.cs","line":4,"severity":"high","comment":"Null deref","suggestion":"x?.y"},{"file":"src/b.cs","line":1,"comment":"Not in the diff"}]'
  const got = findingsFrom(text, { 'src/a.cs': [3, 4] }, 12)
  expect(got.findings.map(f => [f.line, f.severity])).toEqual([[4, 'high'], [3, 'low']])
  expect(got.dropped).toBe(2)
  expect(findingsFrom('no json here', {}, 12)).toEqual({ findings: [], dropped: 0 })
  expect(findingsFrom('[{"file":"a","line":1,"comment":"x"},{"file":"a","line":2,"comment":"y"}]', { a: [1, 2] }, 1).findings.length).toBe(1)
})

test('drafts: kept ones are posted, dropped and empty ones are not, and the person can add their own', () => {
  let ds = draftsFrom([{ file: 'a.cs', line: 4, severity: 'high', comment: 'Null deref', suggestion: 'x?.y' },
    { file: 'a.cs', line: 3, severity: 'low', comment: 'Name it', suggestion: null }])
  ds = editDraft(ds, 2, { keep: false })
  ds = editDraft(ds, 1, { text: 'This dereferences null when the token is empty.' })
  ds = addDraft(ds, '  Looks right otherwise.  ')
  ds = addDraft(ds, '   ')
  expect(keptDrafts(ds).map(d => d.n)).toEqual([1, 3])
  expect(JSON.parse(postPayload(ds, 2))).toEqual({ iteration: 2, drafts: [
    { file: 'a.cs', line: 4, text: 'This dereferences null when the token is empty.', suggestion: 'x?.y' },
    { file: null, line: null, text: 'Looks right otherwise.', suggestion: null }] })
})

// ---------------------------------------------------------------- pipelines, deployments, setup, the release's steps

const build = (b: Partial<DvBuild>): DvBuild => ({ org: 'O', project: 'P', repo: 'Gateway', branch: 'team/1.1.0', pipeline: 'CI', id: 1, number: 'n1',
  status: 'completed', result: 'succeeded', queued: '', finished: '', url: 'u', failing: null, ...b })

test('builds: failed first, then running; the status line and Overview name the failures', () => {
  const p = { generated: 1, version: '1.1.0', branches: ['release/1.1.0', 'team/1.1.0'], errors: [],
    rows: [build({ id: 1, repo: 'A' }), build({ id: 2, repo: 'B', status: 'inProgress', result: '' }), build({ id: 3, repo: 'C', result: 'failed' }),
      build({ id: 4, repo: 'D', result: 'partiallySucceeded' })] }
  expect(buildRows(p).map(b => b.id)).toEqual([3, 4, 2, 1])
  expect([1, 2, 3, 4].map(i => buildWord(p.rows[i - 1] as DvBuild))).toEqual(['passed', 'running', 'failed', 'partly failed'])
  expect(statusText(STATUS({ pipelines: p }))).toBe('devops · 2 builds failed')
  expect(needs(STATUS({ pipelines: p })).map(n => n.text)).toEqual(['2 builds failed on release/1.1.0, team/1.1.0'])
  const doctor = { generated: 1, root: '/ws', rows: [{ name: 'x', state: 'fail' as const, detail: 'd', fix: 'f' }, { name: 'y', state: 'warn' as const, detail: 'd', fix: '' }] }
  expect(needs(STATUS({ doctor })).map(n => [n.text, n.view])).toEqual([['Setup: 1 problem (see Setup below)', 'overview']])
  const notes = { files: [], runs: [{ run: 'r1', stage: 'rendered' as const, release: '1.1.0', token: 'nnnnnnnnnn', needText: [{ id: 1, title: 't' }] }] }
  expect(needs(STATUS({ notes, plans: [plan({ token: 'nnnnnnnnnn', kind: 'notes', summary: 'Publish the notes' })] })).map(n => [n.text, n.view]))
    .toEqual([['Write 1 bug line, then approve: Publish the notes', 'release']])
})

test('what each environment runs now: QA to PROD, then the unnamed ones, the newest per environment', () => {
  const row = (env: 'QA' | 'PROD' | null, envName: string, version: string | null, at: string) => ({ org: 'O', project: 'P', env, envName, pipeline: 'CD',
    repo: 'Gateway', branch: `release/${version}`, version, build: 'b', commit: '', at, kind: 'yaml' as const, url: '' })
  const d = { generated: 1, errors: [], rows: [row('PROD', 'Production', '1.0.2', '2026-10-01'), row(null, 'Sandbox', '1.2.0', '2026-10-02'),
    row('QA', 'qa', '1.1.0', '2026-10-03'), row('PROD', 'Production', '1.0.1', '2026-09-01')] }
  expect(deployGroups(d).map(g => [g.env, g.rows.length])).toEqual([['QA', 1], ['PROD', 2], ['Sandbox', 1]])
  expect(deployLine(d)).toBe('QA 1.1.0 · PROD 1.0.2')
  expect(deployLine(null)).toBe('')
})

test("a release's steps: the first one not done is the one to do now", () => {
  const rel = release([repo({ status: 'Ready' })])
  const run = (r: Partial<DvNotesRun>): DvNotesRun => ({ run: 'r1', stage: 'rendered', release: '1.1.0', project: 'P', token: 'n', approved: false, needText: [], ...r })
  const state = (st: ReturnType<typeof releaseSteps>) => st.map(x => `${x.key}:${x.state}`).join(' ')
  expect(state(releaseSteps(undefined, [], []))).toBe('scan:now approve-prs:todo open-prs:todo notes:todo bug-lines:todo approve-notes:todo publish:todo')
  expect(state(releaseSteps(rel, [plan({})], []))).toContain('scan:done approve-prs:now')
  const opened = { ...rel, results: [{ repo: 'Gateway', prId: 101, url: 'u', action: 'opened' }] }
  const done = [plan({ approved: true, done: true })]
  expect(state(releaseSteps(opened, done, []))).toContain('open-prs:done notes:now')
  expect(state(releaseSteps(opened, done, [run({ needText: [{ id: 1, title: 't' }] })]))).toContain('notes:done bug-lines:now')
  expect(state(releaseSteps(opened, done, [run({})]))).toContain('bug-lines:done approve-notes:now')
  expect(state(releaseSteps(opened, done, [run({ stage: 'published', approved: true })]))).toContain('publish:done')
  // nothing to open, and the PR is already there: those steps are done
  const quiet = { ...release([repo({ status: 'Ready', pr: { id: 7, url: 'u' } })]), token: null }
  expect(state(releaseSteps(quiet, [], []))).toContain('open-prs:done notes:now')
  // the newest run of each project counts; another version's runs do not
  expect(releaseRuns([run({ run: 'r2' }), run({ run: 'r1' }), run({ run: 'r0', release: '1.0.0' })], '1.1.0').map(r => r.run)).toEqual(['r2'])
})

test('the notes press needs an environment, and passes the choices as they are', () => {
  expect(notesArgs('1.1.0', NOTES_DEFAULTS)).toBe(null)
  expect(notesArgs('1.1.0', { ...NOTES_DEFAULTS, env: 'UAT', skills: true })).toEqual(['notes', 'release', '--version', '1.1.0', '--env', 'UAT',
    '--scope', 'all', '--priority', 'none', '--migrations', '--skills'])
  expect(askText('bugs', 'r1')).toContain('notes run r1')
})
