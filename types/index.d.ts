// The sdd view's contract: the snapshot `env.py view --json` prints, and the values the view keeps.

export type SddStatus = 'active' | 'waiting' | 'blocked' | 'done' | 'abandoned'

export type SddProgress = {
  at: string
  flow: string
  phase: string
  status: SddStatus
  gate?: string
  next?: string
  note?: string
  refs?: string[]
  gates?: { passed: string[]; revoked: string[] }
}

export type SddRepo = {
  source?: string
  base: string
  version?: string
  branch: string
  path: string
  pr?: { id: number; url: string }
}

export type SddItem = {
  id: number
  type: string
  title: string
  state: string
  project: string
  flow: 'spec' | 'bug' | string
  slug: string
  created: string
  removed?: string
  repos: Record<string, SddRepo>
  gates: Record<string, string>
  progress: SddProgress | null
  folder: string | null
  spec: { folder: string; path: string; files: string[]; tasks_done?: number; tasks_total?: number } | null
  met: string[]
  url: string | null
  history?: SddProgress[]
  /** Stages that take feedback now, each with the gates a reopen there revokes (env.py reopen_plan). */
  feedback?: Record<string, string[]>
}

export type SddStage = { key: string; label: string; needs: string[]; passes: string[]; stop?: boolean; reworkTo?: string }

export type SddFlow = { label: string; prGates: string[]; stages: SddStage[] }

export type SddColors = {
  done: string; now: string; work: string; revoked: string; gate: string
  dim: string; line: string; hoverText: string
}

export type SddSnapshot = {
  root: string
  /** The view's colours: .claude/sdd.json "view.colors" over the defaults in sddlib.py. */
  colors?: Partial<SddColors>
  /** Open the view when a session starts in this workspace (.claude/sdd.json "view.autoOpen"). */
  autoOpen?: boolean
  specRoot: string
  flows: Record<string, SddFlow>
  derived: string[]
  items: SddItem[]
  done: SddItem[]
}

export type SddDoc = { name: string; text: string; isCut: boolean }

declare module 'claude-code' {
  interface PluginState {
    sdd: {
      snap: SddSnapshot | null
      error: string | null
      selected: number | null
      stage: string | null
      doc: SddDoc | null
      /** A folder given to /sdd-view for this session; null = the session's own folder. */
      workspace: string | null
      /** The stage whose feedback box is open (or review:<stage> for a rejected PR), or null. */
      feedback: string | null
      /** The gate whose story is open inside its stage ('gate:Design agreed'), or null. */
      gate: string | null
      /** The view opened by itself in this session already. */
      opened: boolean
      /** This chat's work item: the one it last ran /sdd or an sdd script for. */
      mine: number | null
    }
  }
}
