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
  /** From the last reviews list: PRs waiting on the user. */
  reviews: { generated: number; waiting: number; active: number } | null
}

/** One active PR in the workspace's projects, from `devops.py reviews list`. */
export type DvReviewRow = {
  org: string
  project: string
  id: number
  repo: string
  title: string
  author: string
  /** The user opened it. */
  mine: boolean
  source: string
  target: string
  created: string
  draft: boolean
  conflicts: boolean
  /** 'required', 'optional', 'group <name>' (a group the user is in), or null: not a reviewer. */
  role: string | null
  myVote: number
  /** A reviewer (directly or through a group), no vote yet, not theirs, not a draft. */
  waiting: boolean
  votes: Array<{ name: string; vote: number; required: boolean }>
  url: string
}

export type DvReviewList = { generated: number; me: string; rows: DvReviewRow[] }

export type DvFinding = { file: string; line: number; severity: 'high' | 'medium' | 'low'; comment: string; suggestion: string | null }

/** One PR opened in the Reviews tab, from `devops.py reviews show`. */
export type DvReviewDetail = DvReviewRow & {
  description: string
  iteration: number
  files: Array<{ path: string; change: string }>
  workItems: Array<{ id: number; type: string; title: string; state: string; criteria: string }>
  threads: Array<{ id: number; status: string; file: string | null; line: number | null; author: string; text: string; replies: number }>
  policies: Array<{ name: string; status: string; blocking: boolean }>
  canVote: boolean
  voteNote: string
  me: string
  key: string
  /** The quick review saved for this iteration, if one ran. */
  review: { findings: DvFinding[]; model?: string; at?: number } | null
}

/** What the quick review sends to the model, from `devops.py reviews pack`. */
export type DvReviewPack = {
  key: string
  iteration: number
  system: string
  prompt: string
  /** The right-side lines the diff shows, per file: a finding must name one. */
  lines: Record<string, number[]>
  truncated: boolean
  model: string
  maxTokens: number
  maxFindings: number
}

/** A comment the person may post: from a finding, or their own. */
export type DvDraft = {
  n: number
  file: string | null
  line: number | null
  severity: 'high' | 'medium' | 'low' | null
  text: string
  suggestion: string | null
  keep: boolean
}

export type DvView = 'overview' | 'release' | 'sync' | 'notes' | 'reviews' | 'guard'

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
      /** The PRs of the Reviews tab, as the last list read them; null until read. */
      reviews: DvReviewList | null
      /** Show every active PR, not only those waiting on the user. */
      reviewsAll: boolean
      /** The PR opened in the Reviews tab, with its detail; null = none. */
      review: DvReviewDetail | null
      /** The comments the person is writing for the opened PR. */
      drafts: DvDraft[]
      /** What the Reviews tab asks to confirm: 'post', or a vote (approve, suggest, wait, reject, reset); null = nothing. */
      reviewAsk: string | null
    }
  }
}
