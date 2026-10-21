// Pure helpers of the Reviews tab: which PRs show, what a row says, the quick review's findings (kept only on a line the
// diff shows), the drafts the person edits, and what `devops.py reviews post` receives. No `$` here (see model.ts).
import type { DvDraft, DvFinding, DvReviewList, DvReviewRow } from '../../types'

import type { Tone } from './model'

export const VOTES: Array<{ key: string; label: string; vote: number }> = [
  { key: 'approve', label: 'Approve', vote: 10 },
  { key: 'suggest', label: 'Approve with suggestions', vote: 5 },
  { key: 'wait', label: 'Wait for author', vote: -5 },
  { key: 'reject', label: 'Reject', vote: -10 },
  { key: 'reset', label: 'Reset vote', vote: 0 },
]

export function voteWord(v: number): string {
  return ({ 10: 'approved', 5: 'approved with suggestions', 0: 'no vote', [-5]: 'waiting for author', [-10]: 'rejected' } as Record<number, string>)[v] ?? String(v)
}

/** Waiting on the person (default), or every active PR; waiting ones first, oldest first. */
export function reviewRows(list: DvReviewList | null | undefined, all: boolean): DvReviewRow[] {
  const rows = (list?.rows ?? []).filter(r => all || r.waiting)
  return [...rows].sort((a, b) => Number(b.waiting) - Number(a.waiting) || a.created.localeCompare(b.created))
}

export function reviewCounts(list: DvReviewList | null | undefined) {
  const rows = list?.rows ?? []
  return { waiting: rows.filter(r => r.waiting).length, active: rows.length }
}

export function reviewKey(r: { project: string; id: number }): string {
  return `${r.project}/${r.id}`
}

/** The short word on a row: what it wants from the person. */
export function reviewWord(r: DvReviewRow): string {
  if (r.mine) return 'yours'
  if (r.draft) return 'draft'
  if (r.myVote) return `you: ${voteWord(r.myVote)}`
  if (r.waiting) return r.role === 'required' || (r.role ?? '').includes('(required)') ? 'required' : 'waiting on you'
  return r.role ? 'reviewer' : '—'
}

export function reviewTone(r: DvReviewRow): Tone {
  if (r.conflicts) return 'urgent'
  if (r.waiting) return r.role === 'required' || (r.role ?? '').includes('(required)') ? 'urgent' : 'warn'
  return r.myVote > 0 ? 'ok' : 'dim'
}

export function rowFacts(r: DvReviewRow): string {
  const votes = r.votes.filter(v => v.vote !== 0).map(v => `${v.name} ${voteWord(v.vote)}`)
  return [`${r.author} · ${r.source} → ${r.target}`, r.role ? `you: ${r.role}` : 'you are not a reviewer',
    votes.length ? votes.join(', ') : 'no votes yet', r.conflicts ? 'merge conflicts' : ''].filter(Boolean).join(' · ')
}

const SEVERITIES = ['high', 'medium', 'low'] as const

/** The model's findings, kept only where they name a line the diff shows. Returns the kept ones and how many were dropped. */
export function findingsFrom(text: string, lines: Record<string, number[]>, limit: number): { findings: DvFinding[]; dropped: number } {
  const m = /\[[\s\S]*\]/.exec(text ?? '')
  let raw: unknown
  try {
    raw = m ? JSON.parse(m[0]) : []
  } catch {
    return { findings: [], dropped: 0 }
  }
  const list = Array.isArray(raw) ? raw : []
  const out: DvFinding[] = []
  for (const f of list as Array<Record<string, unknown>>) {
    const file = String(f?.file ?? '').replace(/^\/+/, '')
    const line = Number(f?.line)
    const comment = String(f?.comment ?? '').trim()
    if (!comment || !Number.isInteger(line) || !(lines[file] ?? []).includes(line)) continue
    const sev = (SEVERITIES as readonly string[]).includes(String(f.severity)) ? (f.severity as DvFinding['severity']) : 'low'
    const sug = f.suggestion
    out.push({ file, line, severity: sev, comment, suggestion: sug == null || sug === '' || sug === 'null' ? null : String(sug) })
  }
  out.sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity))
  const kept = out.slice(0, limit)
  return { findings: kept, dropped: list.length - kept.length }
}

export function draftsFrom(findings: DvFinding[]): DvDraft[] {
  return findings.map((f, i) => ({ n: i + 1, file: f.file, line: f.line, severity: f.severity, text: f.comment, suggestion: f.suggestion, keep: true }))
}

export function addDraft(drafts: DvDraft[], text: string): DvDraft[] {
  const t = text.trim()
  if (!t) return drafts
  return [...drafts, { n: Math.max(0, ...drafts.map(d => d.n)) + 1, file: null, line: null, severity: null, text: t, suggestion: null, keep: true }]
}

export function editDraft(drafts: DvDraft[], n: number, patch: Partial<DvDraft>): DvDraft[] {
  return drafts.map(d => (d.n === n ? { ...d, ...patch } : d))
}

export function keptDrafts(drafts: DvDraft[]): DvDraft[] {
  return drafts.filter(d => d.keep && d.text.trim())
}

/** What `devops.py reviews post` reads on stdin: the kept drafts, against the iteration the review read. */
export function postPayload(drafts: DvDraft[], iteration: number): string {
  return JSON.stringify({ iteration, drafts: keptDrafts(drafts).map(d => ({ file: d.file, line: d.line, text: d.text.trim(), suggestion: d.suggestion })) })
}

export function draftWhere(d: DvDraft): string {
  return d.file ? `${d.file}:${d.line}` : 'the whole PR'
}
