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

const ROW = (id: number, extra: Record<string, unknown> = {}) => ({ org: 'O', project: 'P', id, repo: 'Gateway', title: `Fix ${id}`, author: 'Bo',
  mine: false, source: 'dev/bo/fix', target: 'team/1.1.0', created: '2026-10-20T10:00:00Z', draft: false, conflicts: false, role: 'required',
  myVote: 0, waiting: true, votes: [], url: `https://dev.azure.com/O/P/_git/Gateway/pullrequest/${id}`, ...extra })
const REVIEWS = { generated: NOW - 60, me: 'Ann Lee', rows: [ROW(201), ROW(202, { mine: true, waiting: false, role: null, title: 'My own' }),
  ROW(203, { waiting: false, role: null, title: 'Not mine to review' })] }
const detail = (id: number) => ({ ...REVIEWS.rows.find(r => r.id === id), description: 'd', iteration: 2, files: [{ path: 'src/login.cs', change: 'edit' }],
  workItems: [{ id: 12345, type: 'Bug', title: 'Login crash', state: 'Active', criteria: '' }],
  threads: [{ id: 1, status: 'active', file: 'src/login.cs', line: 3, author: 'Cy', text: 'Why null?', replies: 0 }],
  policies: [{ name: 'Minimum number of reviewers', status: 'running', blocking: true }],
  canVote: id !== 202, voteNote: id === 202 ? "you opened this PR, and its reviewer policy does not count the author's vote" : '',
  me: 'Ann Lee', key: `O-P-${id}-2`, review: null })

const PROPS = { title: 'devops', isFocused: true, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 60 }, view: {} } as never

// `claude plugin test .` at the repo root also finds this file and runs it with another plugin under test. These
// tests mean something only when `devops` registered its command; everything a stand-in remembers lives on it.
type Fake = string[][] & { registered: string[]; filled: string[]; approved: boolean; done: boolean; stdin: Record<string, string>; prompts: string[] }

function fake(on: (event: string, hook: (...a: never[]) => unknown) => void): Fake {
  const calls = Object.assign([] as string[][], { registered: [] as string[], filled: [] as string[], approved: false, done: false,
    stdin: {} as Record<string, string>, prompts: [] as string[] })
  on('process.run', ((_$: unknown, e: { argv: string[]; init?: { stdin?: string } }) => {
    const mine = String(e.argv[1]).endsWith('devops.py')
    const args = e.argv.slice(2)
    if (mine) calls.push(args)
    let out = mine ? '' : JSON.stringify({ repos: {}, root: '/ws', specRoot: 'docs/spec', flows: {}, derived: [], items: [], done: [] })
    if (mine && args[0] === 'status') out = JSON.stringify(status(calls.approved, calls.done))
    if (mine && args[0] === 'versions') out = JSON.stringify({ '1.0.0': ['a'], '1.1.0': ['a'], '1.10.0': ['a'] })
    if (mine && args[0] === 'approve') { calls.approved = true; out = 'Plan aaaaaaaaaa approved.' }
    if (mine && args[0] === 'release' && args[1] === 'open') { calls.done = true; out = 'OPENED PR 101 Gateway' }
    if (mine && args[0] === 'reviews') {
      if (e.init?.stdin != null) calls.stdin[args[1] ?? ''] = e.init.stdin
      const id = Number(args[args.indexOf('--id') + 1])
      if (args[1] === 'list') out = JSON.stringify(REVIEWS)
      if (args[1] === 'show') out = JSON.stringify(detail(id))
      if (args[1] === 'pack') out = JSON.stringify({ key: `O-P-${id}-2`, iteration: 2, system: 'SYS', prompt: `PROMPT ${id}`, lines: { 'src/login.cs': [1, 2, 3, 4] },
        truncated: false, model: 'sonnet', maxTokens: 4000, maxFindings: 12 })
      if (args[1] === 'save') out = 'Saved 1 findings.'
      if (args[1] === 'post') out = 'Posted 2 comments on PR 201.'
      if (args[1] === 'vote') out = `Voted on PR ${id}: approved.`
    }
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
  on('model.complete', ((_$: unknown, e: { prompt: string }) => {
    calls.prompts.push(e.prompt)
    return { value: { isAnswered: true, usage: { input_tokens: 900, output_tokens: 200 }, text:
      '[{"file":"src/login.cs","line":3,"severity":"high","comment":"Returns before the token is checked.","suggestion":"if (user is null) throw;"},' +
      '{"file":"src/login.cs","line":99,"severity":"low","comment":"A line the diff does not have."}]' } }
  }) as never)
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
    for (let i = 0; i < 100 && !/Needs you|scanned|As Ann Lee/.test(await texts(ui)); i++) await new Promise(r => setTimeout(r, 10))
    return ui
  }

  test(`${surface}: the overview lists what needs the person, the conflict first`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mount($, calls)
    if (!ui) return
    expect(calls[0]).toEqual(['status', '--json'])
    const t = await texts(ui)
    expect(t).toContain('Needs you')
    const needs = (await ui.findAll({ type: 'Button' })).map((b: any) => b.props.label).filter((l: string) => l && !['Overview', '[Overview]', 'Release', 'Sync', 'Notes', 'Reviews', 'Guard', 'Refresh'].includes(l))
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

for (const surface of ['terminal', 'desktop'] as const) {
  const mountReviews = async ($: any, calls: Fake) => {
    await $.session.start({ cwd: '/ws', surface, isInteractive: true })
    if (!calls.registered.includes('devops')) {
      await new Promise(r => setTimeout(r, 100))
      return null
    }
    await $.command.run({ command: 'devops', args: 'reviews' })
    const ui = await $.ui.mount({ plugin: 'devops', surface, component: 'Pane', props: PROPS, requestId: 'devops', viewport: { columns: 100, rows: 60 } })
    for (let i = 0; i < 100 && !(await texts(ui)).includes('As Ann Lee'); i++) await new Promise(r => setTimeout(r, 10))
    return ui
  }

  test(`${surface}: the Reviews tab lists the PRs waiting on the person, and every active one on request`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mountReviews($, calls)
    if (!ui) return
    expect(calls).toContainEqual(['reviews', 'list', '--all', '--json'])
    expect(await ui.find({ key: 'pr-P/201' })).toBeTruthy()
    expect(await ui.find({ key: 'pr-P/202' })).toBe(undefined)
    expect((await ui.find({ key: 'rv-waiting' }))?.props.label).toBe('[Waiting on me (1)]')
    await ui.press({ key: 'rv-all' })
    expect(await ui.find({ key: 'pr-P/202' })).toBeTruthy()
    expect(await ui.find({ key: 'pr-P/203' })).toBeTruthy()
  })

  test(`${surface}: a quick review makes drafts only on lines the diff shows; nothing posts before Post`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mountReviews($, calls)
    if (!ui) return
    await ui.press({ key: 'pr-P/201' })
    expect(calls).toContainEqual(['reviews', 'show', '--project', 'P', '--id', '201', '--json'])
    expect(await texts(ui)).toContain('ADO 12345 Bug [Active] Login crash')
    await ui.press({ key: 'quick-review' })
    expect(calls).toContainEqual(['reviews', 'pack', '--project', 'P', '--id', '201'])
    expect(calls.prompts).toEqual(['PROMPT 201'])
    const t = await texts(ui)
    expect(t).toContain('Returns before the token is checked.')
    expect(t).not.toContain('A line the diff does not have.')
    expect(JSON.parse(calls.stdin.save ?? '{}').findings.length).toBe(1)
    expect(calls.some(c => c[1] === 'post')).toBe(false)
    await ui.press({ key: 'post' })
    expect(await texts(ui)).toContain('Post 1 comment on PR 201 as Ann Lee?')
    expect(calls.some(c => c[1] === 'post')).toBe(false)
    await ui.press({ key: 'post-no' })
    if (surface !== 'terminal' || (await ui.find({ key: 'add-comment' }))) {
      await ui.input({ key: 'add-comment', text: 'Looks right otherwise.' })
    }
    await ui.press({ key: 'post' })
    await ui.press({ key: 'post-yes' })
    const sent = JSON.parse(calls.stdin.post ?? '{}')
    expect(sent.iteration).toBe(2)
    expect(sent.drafts[0]).toEqual({ file: 'src/login.cs', line: 3, text: 'Returns before the token is checked.', suggestion: 'if (user is null) throw;' })
    expect(sent.drafts.length).toBe((await ui.find({ key: 'add-comment' })) ? 2 : 1)
  })

  test(`${surface}: a vote runs only after its confirm, and the person's own PR offers only Reset`, async ($: any, on: any) => {
    const calls = fake(on)
    const ui = await mountReviews($, calls)
    if (!ui) return
    await ui.press({ key: 'pr-P/201' })
    await ui.press({ key: 'vote-approve' })
    expect(await texts(ui)).toContain('Approve PR 201 as Ann Lee?')
    expect(calls.some(c => c[1] === 'vote')).toBe(false)
    await ui.press({ key: 'vote-yes' })
    expect(calls).toContainEqual(['reviews', 'vote', '--project', 'P', '--id', '201', '--vote', 'approve'])
    await ui.press({ key: 'rv-all' })
    await ui.press({ key: 'pr-P/202' })
    expect(await texts(ui)).toContain('does not count the author')
    expect(await ui.find({ key: 'vote-approve' })).toBe(undefined)
    expect(await ui.find({ key: 'vote-reset' })).toBeTruthy()
  })
}
