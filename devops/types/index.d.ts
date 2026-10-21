/** One repo of a release scan (`devops.py release scan`). */
export type DvReleaseRepo = {
  repo: string
  status: 'Ready' | 'Conflicts' | 'UpToDate' | 'Skipped' | 'FetchFailed' | 'MergeError' | 'Unknown'
  source: string | null
  target: string | null
  ahead: number
  behind: number
  files: number
  insertions: number
  deletions: number
  migrations: Array<{ path: string; kind: string }>
  workItems: number[]
  candidates: number[]
  loose: Array<{ sha: string; subject: string }>
  conflicts: string[]
  detail: string
  branchesUrl: string | null
  missingSource: boolean
  missingTarget: boolean
  project: string | null
  org: string | null
  pr?: { id: number; url: string } | null
}

export type DvRelease = {
  version: string
  source: string
  target: string
  generated: number
  fetched: boolean
  ado: boolean
  adoError: string | null
  repos: DvReleaseRepo[]
  /** PRs still headed into the source branch: they ride this release only if they merge first. */
  pending: Array<{ id: number; repo: string; title: string; url: string; case: 'ready' | 'uptodate' | 'other' }>
  workItems: Record<string, { id?: number; type: string; title: string; state: string; url: string }>
  dropped: number[]
  token: string | null
  summary?: string
  results: Array<{ repo: string; prId?: number; url?: string; action?: string; error?: string; missing?: number[] }>
}

export type DvSyncRow = {
  Repo: string
  Status: 'Clean' | 'FastForward' | 'Conflicts' | 'UpToDate' | 'Skipped' | 'PendingPriorHop' | 'Locked' | 'FetchFailed' | 'MergeError'
  Ahead?: number
  Behind?: number
  Dirty?: boolean
  ConflictCount?: number
  Conflicts?: string[] | string | null
  Detail?: string
}

export type DvSyncScan = {
  file: string
  source: string
  destination: string
  generated: number
  repos: DvSyncRow[]
  prs: Array<{ repo: string; prId?: number; prUrl?: string; techStoryId?: number }>
}

/** A sync merge in progress on a sync/* branch: the user resolves it. */
export type DvActiveSync = {
  repo: string
  path: string
  branch: string
  source: string
  destination: string
  state: 'conflict' | 'ready' | 'pushed' | 'error'
  conflicts: string[]
}

export type DvPlan = {
  token: string
  kind: 'release-prs' | 'sync-prs' | 'notes'
  summary: string
  created: number
  items: number
  approved: boolean
  approvedAt?: number | null | false
  done: boolean
  ref?: string
  /** One plain line per write the plan makes. */
  lines: string[]
}

export type DvNotesRun = {
  run: string
  stage: 'collected' | 'rendered' | 'published'
  project?: string
  title?: string
  file?: string
  token?: string
  approved?: boolean
  url?: string | null
  indexUrl?: string | null
  facts?: { version: string; env: string; day: string; wikiPath: string; items: number; needText?: number[] }
}

export type DvStatus = {
  root: string
  generated: number
  config: { reposDir: string; sourcePattern: string; targetPattern: string; branchPrefix: string;
    guard: { enabled: boolean; protectedBranches: string[]; forcePush: boolean; protectWorkingTree: boolean; requireApproval: boolean; approvalHours: number } }
  release: DvRelease[]
  sync: {
    chain: { versions: string[] | string | null; waves: Array<{ Destination: string; Groups: unknown }> | null } | null
    scans: DvSyncScan[]
    active: Record<string, DvActiveSync>
    snapshot: { savedAt?: string; entries?: Array<{ Repo: string; StashSha?: string | null; OriginalBranch?: string | null }> | null } | null
    techStories: Record<string, { id: number; title: string; url: string }>
    reports: string[]
  }
  notes: { files: Array<{ path: string; name: string; at: number }>; runs: DvNotesRun[] }
  plans: DvPlan[]
  guard: { recent: Array<{ at: number; rule: string; detail: string }> }
}

export type DvView = 'overview' | 'release' | 'sync' | 'notes' | 'guard'

declare module 'claude-code' {
  interface PluginState {
    devops: {
      /** What `devops.py status --json` last said; null until read. */
      status: DvStatus | null
      /** Why the last read failed (python missing, a broken file). */
      error: string | null
      /** What the last press said when it could not be done, or what it did. */
      note: string | null
      view: DvView
      /** A command is running: its words. */
      busy: string | null
      /** The open row of a list (its key), or null. */
      open: string | null
      /** The team versions the repos know, newest first; null until read. */
      versions: string[] | null
      /** The version the Release view scans. */
      version: string | null
      /** The plan whose Approve panel is open, or null. */
      confirm: string | null
    }
  }
}
