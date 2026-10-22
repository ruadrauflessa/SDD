// The progress page (/sdd-progress) and its pure helpers. Nothing real runs: a hook beneath the plugin answers
// `spec.py progress --json` with canned numbers and records every spec.py command the page asks for.
import { expect, test } from 'claude-code/testing'

import type { ProgressData, ProgressNode } from '../types'
import { addRule, barLabel, barSvg, defectText, dropRule, fieldLabel, leafLine, measureFor, moveRule, nextRule, pct, pickField, ruleText, rulesArgs, rulesDraft, textBar,
  toggleValue, trendText, visibleTops, workBar } from './view/progress'

const C = { done: '#3f9a63', now: '#c98a12', work: '#4a7fc4', revoked: '#c0503f', gate: '#8a73c9', dim: '#7b8794', line: '#5c6670', hoverText: '#ffffff' }
const M = (total: number, done: number, active: number, missing = 0) => ({ total, done, active, todo: total - done - active, missing })
const NONE = { total: 0, done: 0, active: 0, todo: 0, high: 0, items: [] }

const story = (id: number, title: string, status: 'done' | 'active' | 'todo', extra: Partial<ProgressNode> = {}): ProgressNode => ({
  id, type: 'User Story', title, state: { done: 'Closed', active: 'Active', todo: 'New' }[status], status, project: 'Proj', assigned: '', board: '',
  url: `https://dev.azure.com/Org/Proj/_workitems/edit/${id}`, kids: [], defects: NONE,
  units: { count: 1, points: 3, criteria: 2 },
  measures: { count: M(1, status === 'done' ? 1 : 0, status === 'active' ? 1 : 0), points: M(3, status === 'done' ? 3 : 0, status === 'active' ? 3 : 0),
    criteria: M(2, status === 'done' ? 2 : 0, status === 'active' ? 2 : 0) }, ...extra })

const DATA: ProgressData = {
  generated_at: '2026-10-21T10:00:00Z', syncedAt: '2026-10-21T09:00:00Z', syncMinutes: 0, measures: ['count', 'points', 'criteria'],
  projects: { Proj: { rules: { measure: 'points', work: ['Feature', 'User Story'], defects: ['Bug', 'Issue'], done: ['Closed'], todo: ['New'], ignore: ['Removed'], doneBoards: [],
      rules: [{ field: 'Custom.Stage', values: ['Ready'], as: 'active' }] },
    states: [{ state: 'Active', count: 3, rule: 'active' }, { state: 'Closed', count: 2, rule: 'done' }, { state: 'New', count: 1, rule: 'todo' }],
    fields: [{ field: 'System.State', values: [{ value: 'Active', count: 3 }, { value: 'Closed', count: 2 }] },
      { field: 'Custom.BoardColumnTitle', values: [{ value: 'Dev Completed', count: 2 }, { value: 'QA Deployed', count: 1 }] }] } },
  tops: [
    { id: 800, type: 'Epic', title: 'Invoice platform', state: 'Active', status: 'active', project: 'Proj', assigned: '', board: '',
      url: 'https://dev.azure.com/Org/Proj/_workitems/edit/800', partial: true,
      measures: { count: M(5, 2, 1), points: M(10, 5, 5, 2), criteria: M(8, 3, 3, 3) },
      defects: { total: 2, done: 1, active: 0, todo: 1, high: 1, items: [
        { id: 840, type: 'Bug', title: 'CSV drops cents', state: 'New', status: 'todo', high: true, assigned: 'Ann', url: 'https://dev.azure.com/Org/Proj/_workitems/edit/840' }] },
      kids: [{ id: 810, type: 'Feature', title: 'Export', state: 'Active', status: 'active', project: 'Proj', assigned: '', board: '', url: '',
        measures: { count: M(3, 1, 1), points: M(8, 3, 5, 1), criteria: M(6, 2, 3, 1) }, defects: NONE,
        kids: [story(811, 'CSV', 'done'), story(812, 'PDF', 'active', { withdrawn: 1 })] }] },
    { id: 900, type: 'Epic', title: 'Old platform', state: 'Closed', status: 'done', project: 'Proj', assigned: '', board: '', url: '',
      measures: { count: M(2, 2, 0), points: M(4, 4, 0), criteria: M(2, 2, 0) }, defects: NONE, kids: [] },
  ],
  orphans: { defects: 3 },
  trend: { '800': { points: { delta: 12.5, since: '2026-10-14' }, count: { delta: 0, since: '2026-10-14' } } },
}

test('a bar says how far, in the measure shown, and what it could not see', () => {
  expect(pct(M(10, 5, 5))).toBe(50)
  expect(barLabel(M(10, 5, 5, 2), 'points')).toBe('50% · 5 of 10 points done · 5 in progress · 2 without points')
  expect(barLabel(M(1, 1, 0), 'count')).toBe('100% · 1 of 1 item done')
  expect(barLabel(M(8, 3, 3, 3), 'criteria')).toBe('37.5% · 3 of 8 criteria done · 3 in progress · 3 without criteria (counted as 1)')
  expect(barLabel(M(0, 0, 0), 'points')).toBe('nothing to count by story points yet')
  expect(textBar(M(10, 5, 2), 10)).toEqual([5, 2, 3])
  expect(textBar(M(0, 0, 0), 10)).toEqual([0, 0, 10])
  const b = workBar(M(4, 1, 1), C, 200, 10)
  expect(b.source).toContain('width="50.00"')            // done: a quarter of 200
  expect(b.source).toContain('x="50.00" y="0" width="50.00"')   // in progress follows it
  expect(b.alt).toBe('done: 25%, in progress: 25%')
  expect(barSvg([], 0, '#000').alt).toBe('nothing to count')
  expect(barSvg([{ value: 1, color: '#fff', label: 'a <b>' }], 1, '#000').source).toContain('a &lt;b&gt;')
})

test('bugs and issues are their own line, never part of the bar', () => {
  expect(defectText(DATA.tops[0]!.defects)).toBe('Bugs and issues: 1 open (1 high) · 1 closed')
  expect(defectText(NONE)).toBe('No bugs or issues')
})

test('which epics show, in which measure, and the trend', () => {
  expect(measureFor(DATA, 'Proj', null)).toBe('points')
  expect(measureFor(DATA, 'Proj', 'criteria')).toBe('criteria')
  expect(measureFor(DATA, 'Other', null)).toBe('count')
  expect(visibleTops(DATA, null, false, null).map(t => t.id)).toEqual([800])
  expect(visibleTops(DATA, null, true, null).map(t => t.id)).toEqual([800, 900])
  expect(visibleTops(DATA, 'Elsewhere', true, null)).toEqual([])
  expect(trendText(DATA, 800, 'points')).toBe('▲ 12.5% since 2026-10-14')
  expect(trendText(DATA, 800, 'count')).toBe('no change since 2026-10-14')
  expect(trendText(DATA, 800, 'criteria')).toBe('')
  const items = [{ id: 812, progress: { phase: 'Implement', status: 'waiting' } }] as never
  expect(leafLine(story(812, 'PDF', 'active', { withdrawn: 1, assigned: 'Bob' }), items)).toBe('Active · 3 points · 2 criteria (1 withdrawn) · Bob · sdd: Implement, waiting on you')
})

test('the Rules panel cycles a state and saves only done, not started and left out', () => {
  const d = rulesDraft(DATA, 'Proj')
  expect(d).toEqual({ project: 'Proj', measure: 'points', states: { Active: 'active', Closed: 'done', New: 'todo' },
    rules: [{ field: 'Custom.Stage', values: ['Ready'], as: 'active' }], adding: { field: 'Custom.BoardColumnTitle', values: [], as: 'done' } })
  expect(['done', 'active', 'todo', 'ignored'].map(r => nextRule(r as never))).toEqual(['active', 'todo', 'ignored', 'done'])
  expect(rulesArgs({ ...d, states: { ...d.states, Active: 'todo' } }).args).toEqual(['progress-rules', '--project', 'Proj', '--measure', 'points',
    '--done', 'Closed', '--todo', 'Active,New', '--ignore', '', '--rules-json', '[{"field":"Custom.Stage","values":["Ready"],"as":"active"}]'])
  expect(rulesArgs({ ...d, states: { Active: 'active' } })).toEqual({ args: null, problem: 'Mark at least one state, or add a rule, as done.' })
})

test('field rules: put one together from a field and its values, order them, take one out', () => {
  expect(fieldLabel('Custom.BoardColumnTitle')).toBe('Board Column Title')
  expect(fieldLabel('Microsoft.VSTS.Common.Priority')).toBe('Priority')
  expect(ruleText({ field: 'Custom.BoardColumnTitle', values: ['Dev Completed', 'QA Deployed'], and: { 'Custom.Team': ['Blue'] }, as: 'done' }))
    .toBe('Board Column Title is Dev Completed or QA Deployed and Team is Blue')
  let d = rulesDraft(DATA, 'Proj')
  expect(addRule(d)).toBe(d)                                          // no value picked: nothing added
  d = toggleValue(toggleValue(toggleValue(d, 'Dev Completed'), 'QA Deployed'), 'QA Deployed')
  d = addRule(d)
  expect(d.rules[1]).toEqual({ field: 'Custom.BoardColumnTitle', values: ['Dev Completed'], as: 'done' })
  expect(d.adding.values).toEqual([])
  d = moveRule(d, 1, -1)
  expect(d.rules.map(r => r.field)).toEqual(['Custom.BoardColumnTitle', 'Custom.Stage'])
  expect(moveRule(d, 0, -1)).toBe(d)
  expect(dropRule(d, 1).rules.length).toBe(1)
  expect(pickField(toggleValue(d, 'x'), 'System.State').adding).toEqual({ field: 'System.State', values: [], as: 'done' })
  expect(rulesArgs({ ...d, states: {} }).problem).toBe(null)          // a done rule is enough
})

// ---------------------------------------------------------------- the page, mounted

const PROPS = { title: 'sdd progress', isFocused: true, bodyColumns: 120, placement: 'dock', scroll: { offset: 0, bodyRows: 60 }, view: {} } as never
const ok = (value: unknown) => ({ value })
const SNAP = { root: '/ws', specRoot: 'docs/spec', flows: {}, derived: [], done: [], items: [] }

function engine(on: any) {
  const runs: string[][] = []
  const filled: string[] = []
  on('process.run', ((_$: unknown, e: { argv: string[] }) => {
    const spec = e.argv.findIndex(a => a.endsWith('spec.py'))
    const args = spec >= 0 ? e.argv.slice(spec + 1) : []
    if (spec >= 0) runs.push(args)
    const out = args[0] === 'progress' ? JSON.stringify(DATA) : spec >= 0 ? 'done' : JSON.stringify(SNAP)
    return ok({ exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false })
  }) as never)
  on('fs.read', (() => { throw new Error('ENOENT') }) as never)
  on('session.cwd', (() => ok('/ws')) as never)
  on('session.surfaces' as never, (() => ok(['desktop'])) as never)
  on('session.start', ((_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd })) as never)
  on('command.register', (() => ok({ isRegistered: true })) as never)
  on('clock.every', (() => ok({ id: 'tick' })) as never)
  on('ui.open', (() => ok({ isPlaced: true })) as never)
  on('ui.toast', (() => ok(undefined)) as never)
  on('prompt.fill', ((_$: unknown, e: { text: string }) => { filled.push(e.text); return { isFilled: true } }) as never)
  return { runs, filled }
}

const texts = async (ui: { findAll: (q: { type: string }) => Promise<Array<{ text?: string }>> }) =>
  (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '').join('\n')

async function mountPage($: any) {
  await $.session.start({ cwd: '/ws', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'sdd-progress', args: '' })
  const ui = await $.ui.mount({ plugin: 'sdd', surface: 'desktop', component: 'Pane', props: PROPS, requestId: 'sdd-progress', viewport: { columns: 120, rows: 60 } })
  for (let i = 0; i < 100 && !(await texts(ui)).includes('Project progress'); i++) await new Promise(r => setTimeout(r, 10))
  return ui
}

test('desktop: the page lists the open epics with their bar in the project\'s measure, and bugs apart', async ($: any, on: any) => {
  const world = engine(on)
  const ui = await mountPage($)
  expect(world.runs).toContainEqual(['progress', '--json'])
  let t = await texts(ui)
  expect(t).toContain('50% · 5 of 10 points done · 5 in progress · 2 without points')
  expect(t).toContain('▲ 12.5% since 2026-10-14')
  expect(t).toContain('Bugs and issues: 1 open (1 high) · 1 closed')
  expect(t).toContain('Only part of it is synced')
  expect(await ui.find({ key: 'prog-900' })).toBe(undefined)              // finished: on request
  await ui.press({ key: 'prog-finished' })
  expect(await ui.find({ key: 'prog-900' })).toBeTruthy()
  await ui.press({ key: 'measure-count' })
  expect(await texts(ui)).toContain('40% · 2 of 5 items done · 1 in progress')
  await ui.press({ key: 'prog-800' })
  await ui.press({ key: 'prog-810' })
  t = await texts(ui)
  expect(t).toContain('Closed · 3 points · 2 criteria')
  expect(t).toContain('Active · 3 points · 2 criteria (1 withdrawn)')
  expect(world.runs.some(r => r[0] === 'sync')).toBe(false)              // reading never syncs
})

test('desktop: a sync runs on a press, a partly synced epic syncs whole, and the rules save through spec.py', async ($: any, on: any) => {
  const world = engine(on)
  const ui = await mountPage($)
  await ui.press({ key: 'prog-sync' })
  expect(world.runs).toContainEqual(['sync', '--no-embed'])
  await ui.press({ key: 'sync-800' })
  expect(world.runs).toContainEqual(['sync', '--id', '800', '--no-embed'])
  await ui.press({ key: 'rules-Proj' })
  expect(await texts(ui)).toContain('Rules for Proj')
  expect(await texts(ui)).toContain('1. Stage is Ready → in progress')
  await ui.press({ key: 'rule-Active' })                                 // in progress -> not started
  await ui.press({ key: 'rule-measure-criteria' })
  await ui.press({ key: 'rule-value-Dev Completed' })                   // the board column is picked to start with
  await ui.press({ key: 'rule-add' })
  expect(await texts(ui)).toContain('2. Board Column Title is Dev Completed → done')
  await ui.press({ key: 'rule-up-1' })
  await ui.press({ key: 'rules-save' })
  expect(world.runs).toContainEqual(['progress-rules', '--project', 'Proj', '--measure', 'criteria', '--done', 'Closed', '--todo', 'Active,New', '--ignore', '',
    '--rules-json', '[{"field":"Custom.BoardColumnTitle","values":["Dev Completed"],"as":"done"},{"field":"Custom.Stage","values":["Ready"],"as":"active"}]'])
  expect(await texts(ui)).not.toContain('Rules for Proj')               // saved: the panel closes
  await ui.press({ key: 'prog-auto' })
  expect((await ui.find({ key: 'prog-auto' }))?.props.label).toBe('Auto sync: 15 min')
})
