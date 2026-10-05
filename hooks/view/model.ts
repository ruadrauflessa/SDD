// What the view shows, worked out from one env.py view snapshot. No $ here: plain functions.
import type { SddFlow, SddItem, SddProgress, SddQuestion, SddStage } from '../../types'

// skipped = the user agreed to skip it; missed = never worked and never skipped (the flow jumped it)
export type Mark = 'done' | 'skipped' | 'missed' | 'active' | 'waiting' | 'blocked' | 'abandoned' | 'next' | 'later'

export type StageRow = { stage: SddStage; mark: Mark }


/** 'Phase 10 — Pull request' -> 'Phase 10'; 'Implement (task 3/7)' -> 'Implement'. As env.py phase_key. */
export function phaseKey(flow: SddFlow, name: string | undefined): string | null {
  const phase = (name ?? '').trim()
  const bug = /^Phase\s+(\d+a?)\b/i.exec(phase)
  if (bug) {
    const key = `Phase ${bug[1].toLowerCase()}`
    return flow.stages.some(s => s.key === key) ? key : null
  }
  const hit = flow.stages.find(s => phase.toLowerCase().startsWith(s.key.toLowerCase()))
  return hit ? hit.key : null
}

/** A stage behind the current one, from its record. An old snapshot without records counts it done. */
function pastMark(item: SddItem, key: string): Mark {
  if (!item.stages) return 'done'
  const r = item.stages[key]
  return !r ? 'missed' : r.status === 'skipped' ? 'skipped' : 'done'
}

export function stageRows(flow: SddFlow, item: SddItem): StageRow[] {
  const p = item.progress
  if (p?.status === 'done' && phaseKey(flow, p.phase) === null) {
    return flow.stages.map(stage => ({ stage, mark: pastMark(item, stage.key) }))
  }
  const cur = flow.stages.findIndex(s => s.key === phaseKey(flow, p?.phase))
  return flow.stages.map((stage, i) => {
    if (cur < 0) return { stage, mark: i === 0 ? 'next' : 'later' }
    if (i < cur) return { stage, mark: pastMark(item, stage.key) }
    if (i === cur && item.stages?.[stage.key]?.status === 'skipped') return { stage, mark: 'skipped' }
    if (i === cur) return { stage, mark: (p?.status ?? 'active') as Mark }
    return { stage, mark: i === cur + 1 ? 'next' : 'later' }
  })
}


/** The flow is finished: every stage done, or skipped with the user's yes. */
export function flowFinished(flow: SddFlow, item: SddItem): boolean {
  if (item.removed) return true
  return stageRows(flow, item).every(r => r.mark === 'done' || r.mark === 'skipped')
}

/** The history rows of one stage, newest first. */
export function stageHistory(flow: SddFlow, item: SddItem, key: string): SddProgress[] {
  return (item.history ?? []).filter(h => phaseKey(flow, h.phase) === key).reverse()
}

const DOCS: Record<string, string[]> = {
  Specify: ['requirements.md', 'questions.md', 'impact.md'],
  Design: ['design.md', 'questions.md'],
  Decompose: ['tasks.md'],
  Implement: ['tasks.md'],
  Verify: ['tasks.md', 'design.md'],
  'Phase 0': ['requirements.md'],
  'Phase 2': ['requirements.md', 'questions.md'],
  'Phase 4': ['design.md'],
}

/** The spec documents a stage reads, those that exist. */
export function stageDocs(item: SddItem, key: string): string[] {
  const have = item.spec?.files ?? []
  return (DOCS[key] ?? []).filter(d => have.includes(d))
}

/** 2026-10-01T13:56:47Z -> 10-01 13:56 (UTC, as env.py writes it). */
export function when(at: string | undefined): string {
  return at ? at.slice(5, 16).replace('T', ' ') : ''
}

/** An absolute Windows or POSIX path as a file:/// URL. */
export function fileUrl(path: string): string {
  const p = path.replace(/\\/g, '/')
  return encodeURI(`file://${p.startsWith('/') ? '' : '/'}${p}`).replace(/#/g, '%23').replace(/\?/g, '%3F')
}

function join(base: string, rel: string): string {
  return `${base.replace(/[\\/]+$/, '')}/${rel.replace(/^[\\/]+/, '')}`
}

/** A progress ref as a markdown link: `ado`, a spec file, a path under the work item folder, or absolute. */
export function refLink(item: SddItem, ref: string): string | null {
  if (ref === 'ado') return item.url ? `[ADO ${item.id}](${item.url})` : null
  const [, path, lines] = /^(.*?)(?::(\d+(?:-\d+)?))?$/.exec(ref) ?? [ref, ref, undefined]
  const label = `${path.split(/[\\/]/).pop()}${lines ? `:${lines}` : ''}`
  let abs: string | null = null
  if (/^([A-Za-z]:)?[\\/]/.test(path)) abs = path
  else if (/^src[\\/]/.test(path) && item.folder) abs = join(item.folder, path)
  else if (item.spec) abs = join(item.spec.path, path)
  return abs ? `[${label}](${fileUrl(abs)}${lines ? `#L${lines.split('-')[0]}` : ''})` : `\`${ref}\``
}

/** A file: link the view drew -> the path on this computer and the line to open at, if any. */
export function fileTarget(href: string): { path: string; line?: number } | null {
  const m = /^file:\/\/\/?([^#]*)(?:#L(\d+))?$/.exec(href)
  if (!m) return null
  const path = decodeURI(m[1]).replace(/%23/g, '#').replace(/%3F/g, '?')
  return { path: /^[A-Za-z]:/.test(path) ? path : `/${path}`, line: m[2] ? Number(m[2]) : undefined }
}

/** The file: links in a piece of markdown, so a Markdown element answers only those itself. */
export function fileLinks(markdown: string): string[] {
  return [...markdown.matchAll(/\]\((file:[^)\s]+)\)/g)].map(x => x[1])
}

export function statusWord(item: SddItem): string {
  const p = item.progress
  if (!p) return 'not started'
  if (p.status === 'waiting') return 'waiting on you'
  return p.status
}

export function phaseLabel(flow: SddFlow | undefined, item: SddItem): string {
  const p = item.progress
  if (!p) return ''
  if (!flow) return p.phase
  const key = phaseKey(flow, p.phase)
  const stage = flow.stages.find(s => s.key === key)
  if (!stage) return p.status === 'done' ? 'Done' : p.phase
  return stage.key === stage.label ? stage.label : `${stage.key} · ${stage.label}`
}


export type StoryEvent = { at: string; kind: 'asked' | 'passed' | 'revoked'; text: string; refs: string[] }

/** One gate as a decision, oldest first: each question asked before it passed, the pass with its
 *  note (the answer), and every revoke with why. A waiting row belongs to the gate the next pass passes.
 *  `open` names the stage of a gate still waiting on the person: its questions asked since the last
 *  pass are in the story too, so the gate shows what it waits on. */
export function gateStory(item: SddItem, gate: string, open?: { flow: SddFlow; key: string }): StoryEvent[] {
  const out: StoryEvent[] = []
  const asked = (a: SddProgress): StoryEvent => ({ at: a.at, kind: 'asked', text: [a.gate, a.note].filter(Boolean).join('. '), refs: a.refs ?? [] })
  let asks: SddProgress[] = []
  for (const h of item.history ?? []) {
    if (h.status === 'waiting') asks.push(h)
    const passed = h.gates?.passed ?? []
    if (passed.includes(gate)) {
      for (const a of asks) out.push(asked(a))
      out.push({ at: h.at, kind: 'passed', text: h.note ?? '', refs: h.refs ?? [] })
    }
    if ((h.gates?.revoked ?? []).includes(gate)) out.push({ at: h.at, kind: 'revoked', text: h.note ?? '', refs: [] })
    if (passed.length) asks = []
  }
  if (open) {
    for (const a of asks) if (phaseKey(open.flow, a.phase) === open.key) out.push(asked(a))
  }
  return out.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0))
}

/** The gate the item waits on the person for: the first gate its waiting stage passes that is not
 *  passed yet. Null when it waits on nothing, or on a go-ahead that passes no gate. */
export function pendingGate(flow: SddFlow, item: SddItem, derived: string[]): { gate: string; key: string } | null {
  const p = item.progress
  if (p?.status !== 'waiting') return null
  const stage = flow.stages.find(s => s.key === phaseKey(flow, p.phase))
  const gate = stage ? decidedGates(stage, derived).find(g => !item.gates?.[g]) : undefined
  return stage && gate ? { gate, key: stage.key } : null
}

/** What to read before answering the question the item waits on, as markdown links: the refs Claude
 *  gave with the question first, then the stage's spec documents not among them. */
export function reviewLinks(item: SddItem, key: string): string[] {
  const refs = item.progress?.status === 'waiting' ? item.progress.refs ?? [] : []
  const named = new Set(refs.map(r => r.replace(/:\d[\d-]*$/, '').split(/[\\/]/).pop()))
  const docs = stageDocs(item, key).filter(d => !named.has(d))
  return [...refs, ...docs].map(r => refLink(item, r)).filter((x): x is string => !!x)
}

/** The answers AskUserQuestion returns, per question text: the picked labels (comma-joined, as the
 *  chat's dialog joins a multi-select) or else the typed text, as under "Other". Null while a
 *  question has neither. */
export function answersFor(questions: SddQuestion[], picks: Record<string, string[]>, other: string): Record<string, string> | null {
  const out: Record<string, string> = {}
  for (const q of questions) {
    const picked = (picks[q.question] ?? []).filter(l => q.options.some(o => o.label === l))
    const text = picked.length ? picked.join(', ') : other.trim()
    if (!text) return null
    out[q.question] = text
  }
  return out
}

/** The answers as the person's own message, for when the chat's dialog is no longer open. The sdd
 *  skill reads "sdd answer for <id>, stage <stage>: …" as the answer to the gate question. */
export function answerMessage(id: number, key: string, questions: SddQuestion[], answers: Record<string, string>): string {
  return `sdd answer for ${id}, stage ${key}: ` + questions.map(q => `"${q.question}" = "${answers[q.question]}"`).join('; ')
}

/** A stage's row: how many log entries it has, its latest note, and when it last moved. */
export function stageSummary(flow: SddFlow, item: SddItem, key: string): { count: number; note: string; lastAt?: string } {
  const rows = stageHistory(flow, item, key)  // newest first
  return { count: rows.length, note: rows.find(r => r.note)?.note ?? '', lastAt: rows[0]?.at }
}

/** The gates a stage records that a person decides (not read from disk), in flow order. */
export function decidedGates(stage: SddStage, derived: string[]): string[] {
  return stage.passes.filter(g => !derived.includes(g))
}

/** 2026-10-01T12:41:15Z -> 10/01/2026 12h41, in this computer's time zone: the stamp a row's label carries. */
export function stamp(at: string | undefined): string {
  if (!at) return ''
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return ''
  const two = (n: number) => String(n).padStart(2, '0')
  return `${two(d.getMonth() + 1)}/${two(d.getDate())}/${d.getFullYear()} ${two(d.getHours())}h${two(d.getMinutes())}`
}

/** `/sdd 92012`, `/sdd spec 92012`, `/sdd 92012 feedback …` -> 92012; `/sdd help`, `/sdd sync` -> null. */
export function idFromArgs(args: string): number | null {
  const m = /^\s*(?:(?:bug|spec|status|done|abandon|impact)\s+)?(\d+)\b/i.exec(args)
  return m ? Number(m[1]) : null
}

/** The work item an env.py / spec.py run names with --id. */
export function idFromScript(cmd: string): number | null {
  const m = /scripts[\\/]+(?:env|spec)\.py["']?\s+\w+[^\n]*?--id\s+(\d+)/.exec(cmd)
  return m ? Number(m[1]) : null
}

/** The spec flow stops the view approves with one button: the button's label, and the go-ahead
 *  option each one's gate question offers, as the spec skill's gate table names it. */
const APPROVE: Record<string, { label: string; option: string }> = {
  Specify: { label: 'Approve Spec', option: 'Approve — start Design' },
  Design: { label: 'Approve Design', option: 'Approve — start Decompose' },
  Decompose: { label: 'Approve Task List', option: 'Approve — start Implement' },
  Verify: { label: 'Raise PR', option: 'Raise the PR' },
}

/** The go-ahead the Approve button gives: the stage it approves, its label and the option it picks.
 *  Null unless the item is in the spec flow and waits on the person at one of those stops. */
export function approveFor(flow: SddFlow, item: SddItem): { key: string; label: string; option: string } | null {
  const p = item.progress
  if (item.flow !== 'spec' || p?.status !== 'waiting') return null
  const key = phaseKey(flow, p.phase)
  return key && APPROVE[key] ? { key, ...APPROVE[key] } : null
}

/** The go-ahead as answers to an open question: per question, the option named `option`, else the
 *  one that starts with "Approve". Null when a question has neither: Claude asked something else. */
export function approveAnswers(questions: SddQuestion[], option: string): Record<string, string> | null {
  const out: Record<string, string> = {}
  for (const q of questions) {
    const hit = q.options.find(o => o.label === option) ?? q.options.find(o => /^approve\b/i.test(o.label))
    if (!hit) return null
    out[q.question] = hit.label
  }
  return out
}

/** The go-ahead as the person's own message. The sdd skill reads "sdd approve for <id>, stage <stage>"
 *  as the go-ahead option of that stage's gate question. */
export function approveMessage(id: number, key: string): string {
  return `sdd approve for ${id}, stage ${key}`
}
