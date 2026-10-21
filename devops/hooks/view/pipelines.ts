// Pure helpers of the Pipelines tab, the setup check and the Release tab's steps: what a build row says, what
// each environment runs now, how far a release has come, and the `notes release` arguments. No `$` here (see model.ts).
import type { DvBuild, DvDeploy, DvDeployments, DvDoctor, DvNotesOpts, DvNotesRun, DvPipelines, DvPlan, DvRelease } from '../../types'

import type { Tone } from './model'

export const ENVS = ['QA', 'UAT', 'STAGE', 'PROD'] as const
export const SCOPES: Array<[string, string]> = [['all', 'All items'], ['bugs', 'Bugs'], ['stories', 'Stories'], ['tasks', 'Tasks'], ['features', 'Features']]
export const PRIORITIES: Array<[string, string]> = [['none', 'No priority'], ['order', 'Order'], ['sections', 'Sections'], ['both', 'Sections and order']]
export const NOTES_DEFAULTS: DvNotesOpts = { env: null, scope: 'all', priority: 'none', migrations: true, skills: false }

export function buildWord(b: DvBuild): string {
  if (b.status !== 'completed') return b.status === 'inProgress' ? 'running' : 'queued'
  return ({ succeeded: 'passed', partiallySucceeded: 'partly failed', failed: 'failed', canceled: 'canceled' } as Record<string, string>)[b.result] ?? (b.result || '?')
}

export function buildTone(b: DvBuild): Tone {
  const w = buildWord(b)
  if (w === 'failed' || w === 'partly failed') return 'urgent'
  if (w === 'running' || w === 'queued') return 'warn'
  return w === 'passed' ? 'ok' : 'dim'
}

/** Failed first, then running, then the rest; by repo within each. */
export function buildRows(p: DvPipelines | null | undefined): DvBuild[] {
  const rank = (b: DvBuild) => ({ urgent: 0, warn: 1, ok: 2, dim: 3 } as Record<Tone, number>)[buildTone(b)]
  return [...(p?.rows ?? [])].sort((a, b) => rank(a) - rank(b) || a.repo.localeCompare(b.repo) || a.branch.localeCompare(b.branch))
}

export function failedBuilds(p: DvPipelines | null | undefined): number {
  return (p?.rows ?? []).filter(b => buildTone(b) === 'urgent').length
}

/** Each environment and what its pipelines last deployed there: QA, UAT, STAGE, PROD, then the unnamed ones. */
export function deployGroups(d: DvDeployments | null | undefined): Array<{ env: string; rows: DvDeploy[] }> {
  const groups = new Map<string, DvDeploy[]>()
  for (const r of d?.rows ?? []) {
    const k = r.env ?? r.envName
    groups.set(k, [...(groups.get(k) ?? []), r])
  }
  const rank = (k: string) => { const i = (ENVS as readonly string[]).indexOf(k); return i < 0 ? 9 : i }
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])).map(([env, rows]) => ({ env, rows }))
}

/** `QA 1.1.0 · UAT 1.0.3 · PROD 1.0.2`: the newest deployment into each named environment. */
export function deployLine(d: DvDeployments | null | undefined): string {
  return ENVS.map(env => {
    const rows = (d?.rows ?? []).filter(r => r.env === env)
    if (!rows.length) return ''
    const last = rows.reduce((a, b) => (b.at > a.at ? b : a))
    return `${env} ${last.version ?? last.build ?? '?'}`
  }).filter(Boolean).join(' · ')
}

export const epoch = (iso: string | null | undefined): number => {
  const t = Date.parse(iso ?? '')
  return Number.isNaN(t) ? 0 : Math.floor(t / 1000)
}

export function doctorCounts(d: DvDoctor | null | undefined) {
  const rows = d?.rows ?? []
  return { fail: rows.filter(r => r.state === 'fail').length, warn: rows.filter(r => r.state === 'warn').length }
}

export type Step = { key: string; label: string; state: 'done' | 'now' | 'todo' }

/** The newest notes run of each project made from this version's release PRs. */
export function releaseRuns(runs: DvNotesRun[], version: string | null | undefined): DvNotesRun[] {
  const seen = new Set<string>()
  return runs.filter(r => r.release === version && version != null).filter(r => {
    const k = r.project ?? ''
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

/** How far a release has come, from the scan to the published notes. The first step not done is the one to do now. */
export function releaseSteps(rel: DvRelease | null | undefined, plans: DvPlan[], runs: DvNotesRun[]): Step[] {
  const plan = rel?.token ? plans.find(p => p.token === rel.token) : undefined
  const prs = !!rel && (rel.results.some(r => r.prId) || rel.repos.some(r => r.pr))
  const nothing = !!rel && !rel.token
  const mine = releaseRuns(runs, rel?.version)
  const all = (f: (r: DvNotesRun) => boolean) => mine.length > 0 && mine.every(f)
  const done: Array<[string, string, boolean]> = [
    ['scan', 'Scan', !!rel],
    ['approve-prs', 'Approve the PRs', !!rel && (nothing || !!plan?.approved || !!plan?.done)],
    ['open-prs', 'Open the PRs', prs && (nothing || !!plan?.done)],
    ['notes', 'Write the notes', all(r => r.stage !== 'collected')],
    ['bug-lines', 'Bug lines', all(r => r.stage !== 'collected' && !(r.needText ?? []).length)],
    ['approve-notes', 'Approve the notes', all(r => !!r.approved || r.stage === 'published')],
    ['publish', 'Publish', all(r => r.stage === 'published')],
  ]
  const first = done.findIndex(([, , d]) => !d)
  return done.map(([key, label, d], i) => ({ key, label, state: d ? 'done' : i === first ? 'now' : 'todo' }))
}

/** The `devops.py notes release` arguments for these choices, or null until an environment is picked. */
export function notesArgs(version: string, o: DvNotesOpts): string[] | null {
  if (!o.env) return null
  return ['notes', 'release', '--version', version, '--env', o.env, '--scope', o.scope, '--priority', o.priority,
    ...(o.migrations ? ['--migrations'] : []), ...(o.skills ? ['--skills'] : [])]
}
