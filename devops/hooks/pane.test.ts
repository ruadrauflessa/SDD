// The pane, drawn and pressed through the engine's test kit. devops.py is never run: a hook beneath the plugin
// answers `process.run` with canned output and records each command, so these tests check what the pane asks
// for and when: above all that nothing outward runs before the person's Approve, and that Approve runs nothing.
import { expect, test } from 'claude-code/testing'

import type { DvStatus } from '../types'

const NOW = Math.floor(Date.now() / 1000)

function status(approved: boolean, done = false): DvStatus {
  return {
    root: '/ws', generated: NOW,
    config: { reposDir: 'projects', sourcePattern: 'team/{0}', targetPattern: 'release/{0}', branchPrefix: 'team/',
      guard: { enabled: true, protectedBranches: ['main', 'release/*', 'team/*'], forcePush: false, protectWorkingTree: true, requireApproval: true, approvalHours: 24 } },
    release: [{
      version: '1.1.0', source: 'team/1.1.0', target: 'release/1.1.0', generated: NOW - 120, fetched: true, ado: true, adoError: null,
      repos: [
        { repo: 'Gateway', status: 'Ready', source: 'Team/1.1.0', target: 'Release/1.1.0', ahead: 3, behind: 1, files: 4, insertions: 9, deletions: 2,
          migrations: [{ path: 'Migrations/20260101_X.cs', kind: 'EF Core Migration' }], workItems: [12345], candidates: [12345],
          loose: [{ sha: 'abc1234', subject: 'bump deps' }], conflicts: [], detail: '', branchesUrl: 'https://dev.azure.com/O/P/_git/Gateway/branches',
          missingSource: false, missingTarget: false, project: 'P', org: 'O' },
        { repo: 'Docs', status: 'Skipped', source: 'team/1.1.0', target: null, ahead: 0, behind: 0, files: 0, insertions: 0, deletions: 0,
          migrations: [], workItems: [], candidates: [], loose: [], conflicts: [], detail: 'no release branch', branchesUrl: 'https://dev.azure.com/O/P/_git/Docs/branches',
          missingSource: false, missingTarget: true, project: 'P', org: 'O' },
      ],
      pending: [{ id: 77, repo: 'Gateway', title: 'Late fix', url: 'https://dev.azure.com/O/P/_git/Gateway/pullrequest/77', case: 'ready' }],
      workItems: {}, dropped: [], token: 'aaaaaaaaaa', summary: 'Open 1 release PR', results: done ? [{ repo: 'Gateway', prId: 101, url: 'https://dev.azure.com/O/P/_git/Gateway/pullrequest/101', action: 'opened' }] : [],
    }],
    sync: { chain: null, scans: [], snapshot: { savedAt: 'today', entries: [{ Repo: 'UserStore', StashSha: '0123456789abcdef', OriginalBranch: 'dev/x' }] },
      active: { UserStore: { repo: 'UserStore', path: '/ws/projects/UserStore', branch: 'sync/ann/1.1.0_to_1.2.0', source: 'team/1.1.0', destination: 'team/1.2.0', state: 'conflict', conflicts: ['a.txt'] } },
      techStories: {}, reports: [] },
    notes: { files: [], runs: [] },
    plans: [{ token: 'aaaaaaaaaa', kind: 'release-prs', summary: 'Open 1 release PR', created: NOW, items: 1, approved, done, ref: 'release 1.1.0',
      lines: ['Open PR Gateway: Team/1.1.0 → Release/1.1.0 · links ADO 12345'] }],
    guard: { recent: [{ at: NOW - 60, rule: 'protected-branch', detail: 'team/1.1.0 is a protected branch' }] },
  }
}

const PROPS = { title: 'devops', isFocused: true, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 60 }, view: {} } as never

// `claude plugin test .` at the repo root also finds this file and runs it with another plugin under test. These
// tests mean something only when `devops` registered its command; everything a stand-in remembers lives on it.
type Fake = string[][] & { registered: string[]; filled: string[]; approved: boolean; done: boolean }

function fake(on: (event: string, hook: (...a: never[]) => unknown) => void): Fake {
  const calls = Object.assign([] as string[][], { registered: [] as string[], filled: [] as string[], approved: false, done: false })
  on('process.run', ((_$: unknown, e: { argv: string[] }) => {
    const mine = String(e.argv[1]).endsWith('devops.py')
    const args = e.argv.slice(2)
    if (mine) calls.push(args)
    let out = mine ? '' : JSON.stringify({ repos: {}, root: '/ws', specRoot: 'docs/spec', flows: {}, derived: [], items: [], done: [] })
    if (mine && args[0] === 'status') out = JSON.stringify(status(calls.approved, calls.done))
    if (mine && args[0] === 'versions') out = JSON.stringify({ '1.0.0': ['a'], '1.1.0': ['a'], '1.10.0': ['a'] })
    if (mine && args[0] === 'approve') { calls.approved = true; out = 'Plan aaaaaaaaaa approved.' }
    if (mine && args[0] === 'release' && args[1] === 'open') { calls.done = true; out = 'OPENED PR 101 Gateway' }
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  }) as never)
  on('session.cwd', (() => ({ value: '/ws' })) as never)
  on('session.start', ((_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd })) as never)
  on('command.register', ((_$: unknown, e: { name: string }) => { calls.registered.push(e.name); return { value: { isRegistered: true } } }) as never)
  on('clock.every', (() => ({ value: { id: 'tick' } })) as never)
  on('ui.open', (() => ({ value: { isPlaced: true } })) as never)
  on('ui.status', (() => ({ value: undefined })) as never)
  on('ui.toast', (() => ({ value: undefined })) as never)
  on('prompt.fill', ((_$: unknown, e: { text: string }) => { calls.filled.push(e.text); return { isFilled: true } }) as never)
  return calls
}

const texts = async (ui: { findAll: (q: { type: string }) => Promise<Array<{ text?: string }>> }) =>
  (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '').join('\n')

for (const surface of ['terminal', 'desktop'] as const) {
  const mount = async ($: any, calls: Fake, args = '') => {
    await $.session.start({ cwd: '/ws', surface, isInteractive: true })
    if (!calls.registered.includes('devops')) {
      await new Promise(r => setTimeout(r, 100))
      return null
    }
    await $.command.run({ command: 'devops', args })
    const ui = await $.ui.mount({ plugin: 'devops', surface, component: 'Pane', props: PROPS, requestId: 'devops', viewport: { columns: 100, rows: 60 } })
    for (let i = 0; i < 100 && !(await texts(ui)).includes('Needs you') && !(await texts(ui)).includes('scanned'); i++) await new Promise(r => setTimeout(r, 10))
    return ui
  }

  test(`${surface}: the overview lists what needs the person, the conflict first`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls)
    if (!ui) return
    expect(calls[0]).toEqual(['status', '--json'])
    const t = await texts(ui)
    expect(t).toContain('Needs you')
    const needs = (await ui.findAll({ type: 'Button' })).map((b: any) => b.props.label).filter((l: string) => l && !['Overview', '[Overview]', 'Release', 'Sync', 'Notes', 'Guard', 'Refresh'].includes(l))
    expect(needs[0]).toContain('Resolve the conflicts in UserStore')
    expect(needs.some((l: string) => l.includes('Approve or turn down: Open 1 release PR'))).toBe(true)
    expect(needs.some((l: string) => l.includes('Create release/1.1.0 in Docs'))).toBe(true)
    await ui.press({ key: 'ask-release' })
    expect(calls.filled).toEqual(['/devops:release-prep'])
  })

  test(`${surface}: Approve shows every write, runs nothing outward, and only then can the PRs be opened`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls, 'release 1.1.0')
    if (!ui) return
    expect(calls).toContainEqual(['versions', '--json'])
    expect(await texts(ui)).toContain('waiting for your approval')
    expect(await ui.find({ key: 'run-aaaaaaaaaa' })).toBe(undefined)   // no Open button before the Yes
    await ui.press({ key: 'review-aaaaaaaaaa' })
    expect(await texts(ui)).toContain('Open PR Gateway: Team/1.1.0 → Release/1.1.0 · links ADO 12345')
    await ui.press({ key: 'cancel' })
    expect(calls.some(c => c[0] === 'approve')).toBe(false)
    await ui.press({ key: 'review-aaaaaaaaaa' })
    await ui.press({ key: 'approve-aaaaaaaaaa' })
    expect(calls).toContainEqual(['approve', '--token', 'aaaaaaaaaa', '--via', 'pane'])
    expect(calls.some(c => c[0] === 'release' && c[1] === 'open')).toBe(false)  // approving opens nothing
    expect(await texts(ui)).toContain('approved')
    await ui.press({ key: 'run-aaaaaaaaaa' })
    expect(calls).toContainEqual(['release', 'open', '--version', '1.1.0'])
    expect(await texts(ui)).toContain('done')
  })

  test(`${surface}: the release view shows a repo's facts on a press, and the scan runs only on its button`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls, 'release 1.1.0')
    if (!ui) return
    expect(calls.some(c => c[1] === 'scan')).toBe(false)
    expect(await texts(ui)).not.toContain('bump deps')
    await ui.press({ key: 'rel-Gateway' })
    const t = await texts(ui)
    expect(t).toContain('Team/1.1.0 → Release/1.1.0')
    expect(t).toContain('migration (EF Core Migration): Migrations/20260101_X.cs')
    expect(t).toContain('no work item: abc1234 bump deps')
    await ui.press({ key: 'v-1.10.0' })
    await ui.press({ key: 'scan' })
    expect(calls).toContainEqual(['release', 'scan', '--version', '1.10.0'])
  })

  test(`${surface}: a sync conflict waits for the person; Restore asks before it runs`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls, 'sync')
    if (!ui) return
    const t = await texts(ui)
    expect(t).toContain('waiting for you to resolve')
    expect(t).toContain('Claude will not edit these files')
    await ui.press({ key: 'verify-UserStore' })
    expect(calls.filled[0]).toContain('sync verify --repo UserStore')
    await ui.press({ key: 'restore' })
    expect(calls.some(c => c[1] === 'restore')).toBe(false)
    await ui.press({ key: 'restore-yes' })
    expect(calls).toContainEqual(['sync', 'restore'])
  })

  test(`${surface}: the guard view shows its rules and what it refused`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls, 'guard')
    if (!ui) return
    const t = await texts(ui)
    expect(t).toContain('Guard on')
    expect(t).toContain('main, release/*, team/*')
    expect(t).toContain('protected-branch')
  })
}
