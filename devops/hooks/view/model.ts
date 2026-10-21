// Pure helpers of the /devops pane: what a row says, its colour, the status line, what needs the person.
// No `$` here: register.tsx keeps every engine call (the Desktop app's older engine refuses a mod that passes
// `$` into another file).
import type { DvActiveSync, DvPlan, DvRelease, DvReleaseRepo, DvStatus, DvSyncRow, DvView } from '../../types'

export type Tone = 'urgent' | 'warn' | 'ok' | 'dim'

export const asList = <T>(x: T[] | T | null | undefined): T[] => (x == null ? [] : Array.isArray(x) ? x : [x])

export function ago(ts: number | null | undefined, now: number): string {
  if (!ts) return 'never'
  const s = Math.max(0, now - ts)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

/** Numeric version order, newest first: 1.10.0 before 1.2.0. */
export function versionsNewest(vs: string[]): string[] {
  const key = (v: string) => v.split(/[.-]/).map(p => (/^\d+$/.test(p) ? [0, Number(p), ''] : [1, 0, p]) as [number, number, string])
  const cmp = (a: string, b: string) => {
    const ka = key(a), kb = key(b)
    for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
      const x = ka[i], y = kb[i]
      if (!x) return -1
      if (!y) return 1
      if (x[0] !== y[0]) return x[0] - y[0]
      if (x[1] !== y[1]) return x[1] - y[1]
      if (x[2] !== y[2]) return x[2] < y[2] ? -1 : 1
    }
    return 0
  }
  return [...vs].sort(cmp).reverse()
}

export function releaseWord(r: DvReleaseRepo): string {
  switch (r.status) {
    case 'Ready': return r.pr ? `PR ${r.pr.id} open` : `${r.ahead} to release`
    case 'Conflicts': return `⚠ ${r.conflicts.length} conflict${r.conflicts.length === 1 ? '' : 's'}`
    case 'UpToDate': return 'up to date'
    case 'Skipped': return r.missingTarget && !r.missingSource ? 'no release branch' : 'no work'
    default: return 'error'
  }
}

export function releaseTone(r: DvReleaseRepo): Tone {
  if (r.status === 'Conflicts' || r.status === 'FetchFailed' || r.status === 'MergeError' || r.status === 'Unknown') return 'urgent'
  if (r.status === 'Skipped' && r.missingTarget && !r.missingSource) return 'urgent'
  if (r.status === 'Ready') return r.migrations.length ? 'warn' : 'ok'
  return 'dim'
}

const ORDER: Record<string, number> = { Conflicts: 0, FetchFailed: 0, MergeError: 0, Unknown: 0, Ready: 1, Skipped: 2, UpToDate: 3 }

/** Repos to act on first; a missing release branch counts as one to act on. */
export function releaseRows(rel: DvRelease | null | undefined): DvReleaseRepo[] {
  const rank = (r: DvReleaseRepo) => (r.status === 'Skipped' && r.missingTarget && !r.missingSource ? 0.5 : ORDER[r.status] ?? 4)
  return [...(rel?.repos ?? [])].sort((a, b) => rank(a) - rank(b) || a.repo.localeCompare(b.repo))
}

export function releaseCounts(rel: DvRelease | null | undefined) {
  const rs = rel?.repos ?? []
  return {
    ready: rs.filter(r => r.status === 'Ready').length,
    conflicts: rs.filter(r => r.status === 'Conflicts').length,
    missing: rs.filter(r => r.status === 'Skipped' && r.missingTarget && !r.missingSource).length,
    errors: rs.filter(r => ['FetchFailed', 'MergeError', 'Unknown'].includes(r.status)).length,
    quiet: rs.filter(r => r.status === 'UpToDate' || (r.status === 'Skipped' && !(r.missingTarget && !r.missingSource))).length,
  }
}

export function repoFacts(r: DvReleaseRepo): string[] {
  const out: string[] = []
  if (r.source && r.target) out.push(`${r.source} → ${r.target}`)
  if (r.status === 'Ready' || r.status === 'Conflicts' || r.status === 'UpToDate') {
    out.push(`${r.ahead} ahead${r.behind ? ` · ${r.behind} behind (normal)` : ''}`)
  }
  if (r.files) out.push(`${r.files} files +${r.insertions} -${r.deletions}`)
  if (r.workItems.length) out.push(`work items ${r.workItems.map(i => `ADO ${i}`).join(', ')}`)
  if (r.detail && r.status !== 'Ready') out.push(r.detail)
  return out
}

export function syncWord(r: DvSyncRow): string {
  switch (r.Status) {
    case 'Clean': return `${r.Ahead ?? 0} to bring`
    case 'FastForward': return `${r.Ahead ?? 0} to bring (ff)`
    case 'Conflicts': return `⚠ ${r.ConflictCount ?? asList(r.Conflicts).length} conflict${(r.ConflictCount ?? 0) === 1 ? '' : 's'}`
    case 'UpToDate': return 'up to date'
    case 'Skipped': return 'not applicable'
    case 'PendingPriorHop': return 'waits on prior hop'
    case 'Locked': return 'locked'
    default: return 'error'
  }
}

export function syncTone(r: DvSyncRow): Tone {
  if (r.Status === 'Conflicts' || r.Status === 'FetchFailed' || r.Status === 'MergeError') return 'urgent'
  if (r.Status === 'Clean' || r.Status === 'FastForward') return 'warn'
  if (r.Status === 'PendingPriorHop') return 'warn'
  return 'dim'
}

export function activeWord(a: DvActiveSync): string {
  return { conflict: 'waiting for you to resolve', ready: 'merged, ready to push', pushed: 'pushed, ready for its PR', error: 'merge failed' }[a.state] ?? a.state
}

/** Plans that wait for the person's Yes (not approved, not done), newest first. */
export function waitingPlans(s: DvStatus | null | undefined): DvPlan[] {
  return (s?.plans ?? []).filter(p => !p.approved && !p.done && p.items > 0)
}

/** Approved plans whose writes have not run yet: a press (or the agent) runs them. */
export function readyPlans(s: DvStatus | null | undefined): DvPlan[] {
  return (s?.plans ?? []).filter(p => p.approved && !p.done)
}

/** The devops.py arguments that carry out an approved plan, from its kind and ref. */
export function runArgs(p: DvPlan): string[] | null {
  const ref = p.ref ?? ''
  if (p.kind === 'release-prs' && ref.startsWith('release ')) return ['release', 'open', '--version', ref.slice('release '.length)]
  if (p.kind === 'notes' && ref.startsWith('notes ')) return ['notes', 'publish', '--run', ref.slice('notes '.length)]
  const m = /^sync (\S+) -> (\S+)$/.exec(ref)
  if (p.kind === 'sync-prs' && m) return ['sync', 'open', '--source', m[1] ?? '', '--destination', m[2] ?? '']
  return null
}

export type Need = { key: string; tone: Tone; text: string; view: DvView }

/** What needs the person now, most urgent first. */
export function needs(s: DvStatus | null | undefined): Need[] {
  if (!s) return []
  const out: Need[] = []
  for (const a of Object.values(s.sync.active ?? {})) {
    if (a.state === 'conflict') out.push({ key: `conf-${a.repo}`, tone: 'urgent', view: 'sync', text: `Resolve the conflicts in ${a.repo} (${a.branch}), then tell Claude it is done` })
  }
  for (const p of waitingPlans(s)) out.push({ key: `plan-${p.token}`, tone: 'warn', view: viewOf(p), text: `Approve or turn down: ${p.summary}` })
  for (const p of readyPlans(s)) out.push({ key: `run-${p.token}`, tone: 'ok', view: viewOf(p), text: `Approved, not run yet: ${p.summary}` })
  const rel = s.release[0]
  if (rel) {
    for (const r of rel.repos) {
      if (r.status === 'Skipped' && r.missingTarget && !r.missingSource) {
        out.push({ key: `miss-${r.repo}`, tone: 'urgent', view: 'release', text: `Create ${rel.target} in ${r.repo} (from ${r.source ?? rel.source})` })
      }
    }
  }
  const rv = s.reviews?.waiting ?? 0
  if (rv) out.push({ key: 'reviews', tone: 'warn', view: 'reviews', text: `${rv} PR${rv === 1 ? ' waits' : 's wait'} for your review` })
  const snap = asList(s.sync.snapshot?.entries)
  if (snap.length) out.push({ key: 'snapshot', tone: 'warn', view: 'sync', text: `${snap.length} repo${snap.length === 1 ? '' : 's'} stashed by the sync snapshot: restore when the hop is done` })
  return out
}

function viewOf(p: DvPlan): DvView {
  return p.kind === 'release-prs' ? 'release' : p.kind === 'sync-prs' ? 'sync' : 'notes'
}

/** The status line: short, and clear when nothing needs the person. */
export function statusText(s: DvStatus | null | undefined): string | undefined {
  if (!s) return undefined
  const bits: string[] = []
  const conf = Object.values(s.sync.active ?? {}).filter(a => a.state === 'conflict').length
  if (conf) bits.push(`${conf} sync conflict${conf === 1 ? '' : 's'}`)
  const w = waitingPlans(s).length
  if (w) bits.push(`${w} to approve`)
  const rv = s.reviews?.waiting ?? 0
  if (rv) bits.push(`${rv} to review`)
  const rel = s.release[0]
  if (rel) {
    const c = releaseCounts(rel)
    const parts = [c.ready ? `${c.ready} ready` : '', c.conflicts ? `${c.conflicts} conflict` : '', c.missing ? `${c.missing} no release branch` : ''].filter(Boolean)
    if (parts.length) bits.push(`release ${rel.version}: ${parts.join(', ')}`)
  }
  return bits.length ? `devops · ${bits.join(' · ')}` : undefined
}

/** What a typed /devops argument asks for. */
export function parseArgs(raw: string): { view: DvView | null; version: string | null; refresh: boolean } {
  const words = raw.trim().split(/\s+/).filter(Boolean)
  const first = (words[0] ?? '').toLowerCase()
  const views: DvView[] = ['overview', 'release', 'sync', 'notes', 'reviews', 'guard']
  if (first === 'refresh') return { view: null, version: null, refresh: true }
  if ((views as string[]).includes(first)) {
    const v = first === 'release' && words[1] && /^[\w.-]+$/.test(words[1]) ? words[1] : null
    return { view: first as DvView, version: v, refresh: false }
  }
  return { view: null, version: null, refresh: false }
}

/** The prompt a button fills for the person to send: the skill does the judgement, devops.py the mechanics. */
export function askText(what: 'release' | 'sync' | 'notes' | 'verify', arg?: string): string {
  switch (what) {
    case 'release': return `/devops:release-prep ${arg ? `prepare release ${arg}` : ''}`.trim()
    case 'sync': return '/devops:sync-team-branches sync the team branches'
    case 'notes': return '/devops:release-notes generate the release notes'
    case 'verify': return `I resolved the conflicts in ${arg}. Run devops.py sync verify --repo ${arg}, and if it passes, finish the sync.`
  }
}

export function page<T>(rows: T[], from: number, size: number) {
  const start = Math.min(Math.max(0, from), Math.max(0, rows.length - 1))
  const slice = rows.slice(start, start + size)
  return { rows: slice, from: slice.length ? start + 1 : 0, to: start + slice.length, total: rows.length }
}
