import { expect, test } from 'claude-code/testing'

import type { DvPlan, DvRelease, DvReleaseRepo, DvStatus } from '../types'
import { activeWord, ago, askText, needs, page, parseArgs, releaseCounts, releaseRows, releaseTone, releaseWord, runArgs, statusText, syncTone, syncWord, versionsNewest, waitingPlans } from './view/model'

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
  notes: { files: [], runs: [] }, plans: [], guard: { recent: [] }, ...extra,
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
  expect(parseArgs('refresh')).toEqual({ view: null, version: null, refresh: true })
  expect(parseArgs('')).toEqual({ view: null, version: null, refresh: false })
  expect(askText('release', '1.1.0')).toBe('/devops:release-prep prepare release 1.1.0')
  expect(askText('verify', 'UserStore')).toContain('sync verify --repo UserStore')
  expect(ago(1000 - 7200, 1000)).toBe('2h ago')
  expect(page([1, 2, 3], 0, 2)).toEqual({ rows: [1, 2], from: 1, to: 2, total: 3 })
})
