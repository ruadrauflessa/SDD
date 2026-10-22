// Pure helpers of the progress page (/sdd-progress): the bars, what a row says, which epics show, the trend, and the
// Rules panel's edit. The numbers come from `spec.py progress` (scripts/progress.py); nothing here counts work.
// No `$` here: the Desktop app's older engine refuses a mod that passes `$` into another file.
import type { ProgressCriteria, ProgressData, ProgressDefects, ProgressMeasure, ProgressMeasureKey, ProgressNode, ProgressRule, ProgressRulesDraft, SddColors, SddItem } from '../../types'

export const MEASURE_KEYS: ProgressMeasureKey[] = ['count', 'points', 'criteria']
export const MEASURE_LABEL: Record<ProgressMeasureKey, string> = { count: 'Work items', points: 'Story points', criteria: 'Acceptance criteria' }
const UNIT: Record<ProgressMeasureKey, [string, string]> = { count: ['item', 'items'], points: ['point', 'points'], criteria: ['criterion', 'criteria'] }
const RULES = ['done', 'active', 'todo', 'ignored'] as const
export type Rule = typeof RULES[number]
export const RULE_WORD: Record<Rule, string> = { done: 'done', active: 'in progress', todo: 'not started', ignored: 'left out' }
export const AUTO_STEPS = [0, 15, 30, 60]

const num = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, ''))
const unit = (m: ProgressMeasureKey, n: number) => UNIT[m][n === 1 ? 0 : 1]

export function pct(m: ProgressMeasure | undefined): number {
  return m && m.total ? Math.round((1000 * m.done) / m.total) / 10 : 0
}

/** The measure a top shows: the page's choice, else its project's own. */
export function measureFor(data: ProgressData | null, project: string, chosen: ProgressMeasureKey | null): ProgressMeasureKey {
  return chosen ?? data?.projects[project]?.rules.measure ?? 'count'
}

/** `62% · 31 of 50 items done · 4 in progress`, and what the measure could not see. */
export function barLabel(m: ProgressMeasure, measure: ProgressMeasureKey): string {
  if (!m.total) return `nothing to count by ${MEASURE_LABEL[measure].toLowerCase()} yet`
  const bits = [`${pct(m)}%`, `${num(m.done)} of ${num(m.total)} ${unit(measure, m.total)} done`]
  if (m.active) bits.push(`${num(m.active)} in progress`)
  if (m.missing) bits.push(measure === 'points' ? `${m.missing} without points` : `${m.missing} without criteria (counted as 1)`)
  return bits.join(' · ')
}

/** `Bugs and issues: 3 open (1 high) · 1 in progress · 9 closed`. */
export function defectText(d: ProgressDefects): string {
  if (!d.total) return 'No bugs or issues'
  const bits = [`${d.todo} open${d.high ? ` (${d.high} high)` : ''}`]
  if (d.active) bits.push(`${d.active} in progress`)
  bits.push(`${d.done} closed`)
  return `Bugs and issues: ${bits.join(' · ')}`
}

/** `▲ 4% since 2026-10-14`, or '' when there is nothing to compare with. */
export function trendText(data: ProgressData | null, id: number, measure: ProgressMeasureKey): string {
  const t = data?.trend?.[String(id)]?.[measure]
  if (!t) return ''
  if (!t.delta) return `no change since ${t.since}`
  return `${t.delta > 0 ? '▲' : '▼'} ${Math.abs(t.delta)}% since ${t.since}`
}

export type Picture = { source: string; alt: string; width: number; height: number }

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/** A stacked bar as SVG: done, then in progress, on the track; the third part is what is left. */
export function barSvg(parts: Array<{ value: number; color: string; label: string }>, total: number, track: string,
  width = 240, height = 10): Picture {
  const r = height / 2
  let x = 0
  const rects = total > 0 ? parts.filter(p => p.value > 0).map(p => {
    const w = Math.max(1, (width * p.value) / total)
    const out = `<rect x="${x.toFixed(2)}" y="0" width="${w.toFixed(2)}" height="${height}" fill="${p.color}"><title>${esc(p.label)}</title></rect>`
    x += w
    return out
  }).join('') : ''
  const alt = total > 0 ? parts.map(p => `${p.label}: ${Math.round((100 * p.value) / total)}%`).join(', ') : 'nothing to count'
  const source = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`
    + `<defs><clipPath id="c"><rect width="${width}" height="${height}" rx="${r}"/></clipPath></defs>`
    + `<g clip-path="url(#c)"><rect width="${width}" height="${height}" fill="${track}" opacity="0.35"/>${rects}</g></svg>`
  return { source, alt, width, height }
}

/** The bar of one measure: done green, in progress blue, the rest the track. */
export function workBar(m: ProgressMeasure, colors: SddColors, width = 240, height = 10): Picture {
  return barSvg([{ value: m.done, color: colors.done, label: 'done' }, { value: m.active, color: colors.work, label: 'in progress' }],
    m.total, colors.line, width, height)
}

/** The bugs-and-issues bar: closed, in progress, open (red). */
export function defectBar(d: ProgressDefects, colors: SddColors, width = 120, height = 6): Picture {
  return barSvg([{ value: d.done, color: colors.done, label: 'closed' }, { value: d.active, color: colors.now, label: 'in progress' },
    { value: d.todo, color: colors.revoked, label: 'open' }], d.total, colors.line, width, height)
}

/** The same bar in characters, where a picture cannot be drawn: [done, in progress, left] counts of `cols`. */
export function textBar(m: ProgressMeasure, cols = 24): [number, number, number] {
  if (!m.total) return [0, 0, cols]
  const done = Math.round((cols * m.done) / m.total)
  const active = Math.min(cols - done, Math.round((cols * m.active) / m.total))
  return [done, active, cols - done - active]
}

/** The projects that have tops, for the picker. */
export function projectsOf(data: ProgressData | null): string[] {
  return [...new Set((data?.tops ?? []).map(t => t.project))].sort()
}

/** The tops the page lists: the project's (or all), finished ones only on request; in progress first, then not
 *  started, then done; furthest along first within each. */
export function visibleTops(data: ProgressData | null, project: string | null, finished: boolean, measure: ProgressMeasureKey | null): ProgressNode[] {
  const rank: Record<string, number> = { active: 0, todo: 1, done: 2, ignored: 3 }
  return (data?.tops ?? [])
    .filter(t => !project || t.project === project)
    .filter(t => finished || (t.status !== 'done' && t.status !== 'ignored'))
    .sort((a, b) => (rank[a.status] ?? 4) - (rank[b.status] ?? 4)
      || pct(b.measures[measureFor(data, b.project, measure)]) - pct(a.measures[measureFor(data, a.project, measure)]) || a.id - b.id)
}

export function hiddenFinished(data: ProgressData | null, project: string | null): number {
  return (data?.tops ?? []).filter(t => (!project || t.project === project) && (t.status === 'done' || t.status === 'ignored')).length
}

/** A story's line: its state, what it adds, who has it, and its sdd stage when sdd works on it. */
export function leafLine(n: ProgressNode, items: SddItem[] = []): string {
  const bits = [n.state]
  if (n.units) {
    if (n.units.points) bits.push(`${num(n.units.points)} ${unit('points', n.units.points)}`)
    bits.push(`${n.units.criteria} ${unit('criteria', n.units.criteria)}${n.withdrawn ? ` (${n.withdrawn} withdrawn)` : ''}`)
  }
  if (n.assigned) bits.push(n.assigned)
  const sdd = items.find(i => i.id === n.id)?.progress
  if (sdd) bits.push(`sdd: ${sdd.phase}${sdd.status === 'waiting' ? ', waiting on you' : ''}`)
  return bits.join(' · ')
}

/** The head of an opened story's criteria: how many, how many withdrawn, and when they count as met (sdd keeps no
 *  verdict per criterion: they are met when the story is done by the project's rules). */
export function criteriaHead(n: ProgressNode, c: ProgressCriteria['criteria']): string {
  const live = c.filter(x => !x.withdrawn).length
  const gone = c.length - live
  const head = `${live} acceptance criteri${live === 1 ? 'on' : 'a'}${gone ? `, ${gone} withdrawn` : ''}`
  return `${head} · ${n.status === 'done' ? 'met: the story is done' : 'met when the story is done'}`
}

/** The mark of one criterion: ✓ when its story is done, ○ while it is not, – when it was withdrawn. */
export function criterionMark(n: ProgressNode, c: { withdrawn: boolean }): string {
  return c.withdrawn ? '–' : n.status === 'done' ? '✓' : '○'
}

/** What an opened story offers: its sdd view when an sdd flow works on it here, else the command that starts one. */
export function storyAction(n: ProgressNode, items: SddItem[] = []): { kind: 'view' | 'start'; label: string; text: string } {
  return items.some(i => i.id === n.id)
    ? { kind: 'view', label: 'Open in sdd view', text: '' }
    : { kind: 'start', label: `Start /sdd ${n.id}`, text: `/sdd ${n.id}` }
}

/** `synced from ADO 3h ago`. */
export function syncedText(data: ProgressData | null, now: number): string {
  if (!data?.syncedAt) return 'not synced from ADO yet'
  const t = Date.parse(data.syncedAt)
  if (Number.isNaN(t)) return `synced ${data.syncedAt}`
  const s = Math.max(0, now - Math.floor(t / 1000))
  const ago = s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`
  return `synced from ADO ${ago}`
}

export function autoNext(m: number): number {
  const i = AUTO_STEPS.indexOf(m)
  return AUTO_STEPS[(i + 1) % AUTO_STEPS.length] ?? 0
}

/** `Board Column Title` for `Custom.BoardColumnTitle`: the last part of the reference name, its words apart. */
export function fieldLabel(name: string): string {
  const last = name.split('.').pop() ?? name
  return last.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
}

/** `Board Column Title is Dev Completed or QA Deployed and Team is Blue`. */
export function ruleText(r: ProgressRule): string {
  const one = (f: string, vs: string[]) => `${fieldLabel(f)} is ${vs.map(v => v || '(empty)').join(' or ')}`
  return [one(r.field, r.values), ...Object.entries(r.and ?? {}).map(([f, vs]) => one(f, vs))].join(' and ')
}

/** The Rules panel, started from the project's field rules and what its rules make of each state it uses. A new rule
 *  starts on the board column when the items have one, else on the first field. */
export function rulesDraft(data: ProgressData | null, project: string): ProgressRulesDraft {
  const p = data?.projects[project]
  const fields = (p?.fields ?? []).map(f => f.field)
  const start = fields.find(f => /boardcolumn/i.test(f)) ?? fields[0] ?? null
  return { project, measure: p?.rules.measure ?? 'count', states: Object.fromEntries((p?.states ?? []).map(s => [s.state, s.rule])),
    rules: [...(p?.rules.rules ?? [])], adding: { field: start, values: [], as: 'done' } }
}

/** The values a field holds in the project's items, most used first. */
export function fieldValues(data: ProgressData | null, project: string, field: string | null): Array<{ value: string; count: number }> {
  return data?.projects[project]?.fields.find(f => f.field === field)?.values ?? []
}

export function pickField(d: ProgressRulesDraft, field: string): ProgressRulesDraft {
  return { ...d, adding: { ...d.adding, field, values: [] } }
}

export function toggleValue(d: ProgressRulesDraft, value: string): ProgressRulesDraft {
  const vs = d.adding.values.includes(value) ? d.adding.values.filter(v => v !== value) : [...d.adding.values, value]
  return { ...d, adding: { ...d.adding, values: vs } }
}

/** The rule being put together, added last; nothing happens until it has a field and a value. */
export function addRule(d: ProgressRulesDraft): ProgressRulesDraft {
  if (!d.adding.field || !d.adding.values.length) return d
  return { ...d, rules: [...d.rules, { field: d.adding.field, values: d.adding.values, as: d.adding.as }], adding: { ...d.adding, values: [] } }
}

export function moveRule(d: ProgressRulesDraft, i: number, by: -1 | 1): ProgressRulesDraft {
  const j = i + by
  if (j < 0 || j >= d.rules.length) return d
  const rules = [...d.rules]
  ;[rules[i], rules[j]] = [rules[j]!, rules[i]!]
  return { ...d, rules }
}

export function dropRule(d: ProgressRulesDraft, i: number): ProgressRulesDraft {
  return { ...d, rules: d.rules.filter((_, k) => k !== i) }
}

export function nextRule(r: Rule): Rule {
  return RULES[(RULES.indexOf(r) + 1) % RULES.length] ?? 'done'
}

/** The `spec.py progress-rules` arguments for the draft, or why it cannot be saved. In progress is "anything else":
 *  only done, not started and left out states are written; the field rules go as JSON, in their order. */
export function rulesArgs(d: ProgressRulesDraft): { args: string[] | null; problem: string | null } {
  const of = (r: Rule) => Object.entries(d.states).filter(([, v]) => v === r).map(([k]) => k)
  const done = of('done')
  if (!done.length && !d.rules.some(r => r.as === 'done')) return { args: null, problem: 'Mark at least one state, or add a rule, as done.' }
  return { args: ['progress-rules', '--project', d.project, '--measure', d.measure, '--done', done.join(','),
    '--todo', of('todo').join(','), '--ignore', of('ignored').join(','), '--rules-json', JSON.stringify(d.rules)], problem: null }
}
