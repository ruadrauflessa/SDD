// The sdd view: a pane that shows where a work item is in its flow, a band when one waits on the
// person, and a toast when a gate passes. It only reads: `env.py view` (local files, no ADO) and the
// spec documents. It never passes a gate or runs a state-changing command; "Resume" only fills the
// prompt box with `/sdd <id>` for the person to send.
import type { EngineInterface, Register } from 'claude-code'

import type { SddColors, SddDoc, SddItem, SddSnapshot, SddStage } from '../types'
import { decidedGates, fileLinks, idFromArgs, idFromScript, stamp, fileTarget, gateStory, phaseKey, phaseLabel, refLink, stageDocs, stageHistory, stageRows, stageSummary, statusWord, when } from './view/model'
import type { Mark } from './view/model'

const PANE = 'sdd-view'
const snap = { plugin: 'sdd', key: 'snap' } as const
const error = { plugin: 'sdd', key: 'error' } as const
const selected = { plugin: 'sdd', key: 'selected' } as const
const stage = { plugin: 'sdd', key: 'stage' } as const
const doc = { plugin: 'sdd', key: 'doc' } as const
const place = { plugin: 'sdd', key: 'workspace' } as const
const feedback = { plugin: 'sdd', key: 'feedback' } as const
const gate = { plugin: 'sdd', key: 'gate' } as const
const autoOpened = { plugin: 'sdd', key: 'opened' } as const
const mine = { plugin: 'sdd', key: 'mine' } as const

const SCRIPT_RUN = /scripts[\\/]+(env|spec)\.py/
const DOC_LIMIT = 9000
// Colour carries meaning only, and a glyph always says the same thing for the terminal and colour-blind readers.
// The workspace sets them in .claude/sdd.json "view.colors" (env.py view hands them over); these are the
// fallback while nothing is read yet. A line under the pointer turns its text `hoverText` and its icon lighter.
const DEFAULT_COLORS: SddColors = { done: '#3f9a63', now: '#c98a12', work: '#4a7fc4', revoked: '#c0503f', gate: '#8a73c9',
  dim: '#7b8794', line: '#5c6670', hoverText: '#ffffff' }
let C: SddColors = DEFAULT_COLORS

function paint(colors: Partial<SddColors> | undefined): void {
  C = { ...DEFAULT_COLORS, ...(colors ?? {}) }
}

/** The colour halfway to white: an icon under the pointer, still in its status colour. */
function lighten(color: string | undefined): string | undefined {
  const m = /^#([0-9a-f]{6})/i.exec(color ?? '')
  if (!m) return color
  const n = parseInt(m[1], 16)
  const up = (v: number) => Math.round(v + (255 - v) * 0.5).toString(16).padStart(2, '0')
  return `#${up(n >> 16)}${up((n >> 8) & 255)}${up(n & 255)}`
}

function markColor(m: Mark): string | undefined {
  return { done: C.done, active: C.work, waiting: C.now, blocked: C.revoked, abandoned: C.dim, next: C.work, later: undefined }[m]
}
const GLYPH: Record<Mark, string> = { done: '✓', active: '●', waiting: '●', blocked: '✕', abandoned: '–', next: '○', later: '·' }

function stageName(st: SddStage): string {
  return st.key === st.label ? st.label : `${st.key.replace('Phase ', '')}  ${st.label}`
}


let python = 'python'  // module state: lost on reload, which is fine
let isOpen = false
let isWorkspace = false

// Helpers do only the reading and drawing calls. $.state is read and written in the hook bodies
// (and the closures they make), which is where the engine hands it out.

/** Runs `env.py view` (local files, no ADO) and toasts what changed since `before`. */
async function loadView($: EngineInterface, id: number | null, before: SddSnapshot | null, folder: string | null): Promise<View> {
  const argv = (exe: string) => [exe, `${$.plugin.root}/scripts/env.py`, 'view', '--json', '--compact',
    ...(id != null ? ['--id', String(id)] : [])]
  const cwd = folder || (await $.session.cwd())
  let out: SddSnapshot | null = null
  let why: string | null = null
  for (const exe of [python, 'python3', 'py']) {
    try {
      const r = await $.process.run(argv(exe), { cwd, timeoutMs: 20000 })
      python = exe
      if (r.exitCode === 0) out = JSON.parse(r.stdout) as SddSnapshot
      else why = (r.stderr || r.stdout).trim().split('\n').pop() || `env.py view exited ${r.exitCode}`
      break
    } catch (err) {
      why = `could not run python: ${String(err)}`
    }
  }
  isWorkspace = out !== null
  if (out && before) toastChanges($, before, out)
  return { out, why }
}

type View = { out: SddSnapshot | null; why: string | null }

function toastChanges($: EngineInterface, a: SddSnapshot, b: SddSnapshot): void {
  for (const now of b.items) {
    const was = a.items.find(x => x.id === now.id)
    if (!was) continue
    const passed = Object.keys(now.gates ?? {}).filter(g => !(was.gates ?? {})[g])
    if (passed.length) $.ui.toast(`${now.id} · gate passed: ${passed.join(', ')}`)
    const flow = b.flows[now.flow]
    const from = flow ? phaseKey(flow, was.progress?.phase) : was.progress?.phase
    const to = flow ? phaseKey(flow, now.progress?.phase) : now.progress?.phase
    if (to && from !== to) $.ui.toast(`${now.id} · now in ${phaseLabel(flow, now)}`)
  }
}

async function openPane($: EngineInterface, id: number | null): Promise<void> {
  isOpen = true
  await $.ui.open({ id: PANE, title: id != null ? `sdd ${id}` : 'sdd', closeOnEscape: true, columns: 100 })
}

/** Opens a folder on this computer in the file manager or VS Code. It changes nothing in sdd. */
async function openIn($: EngineInterface, app: 'files' | 'code', path: string): Promise<void> {
  const isWin = /^[A-Za-z]:[\\/]/.test(path)
  const native = isWin ? path.replace(/\//g, '\\') : path
  const argv = app === 'code'
    ? (isWin ? ['cmd', '/c', 'code', native] : ['code', native])
    : (isWin ? ['cmd', '/c', 'explorer', native] : ['open', native])  // through cmd, as code: explorer.exe started directly misreads a path with spaces
  try {
    const r = await $.process.run(argv, { timeoutMs: 15000 })
    if (r.exitCode > 1) $.ui.toast(`Could not open ${path}: ${(r.stderr || r.stdout).trim().slice(0, 160) || `exit ${r.exitCode}`}`)  // explorer exits 1 even when it opened
  } catch (err) {
    $.ui.toast(`Could not open ${app === 'code' ? 'VS Code' : 'the folder'}: ${String(err)}`)
  }
}

/** Opens a code file in VS Code at its line (or, with no line, in the app the computer uses for it). */
async function openFile($: EngineInterface, path: string, line?: number): Promise<void> {
  const isWin = /^[A-Za-z]:[\\/]/.test(path)
  const native = isWin ? path.replace(/\//g, '\\') : path
  const argv = line
    ? (isWin ? ['cmd', '/c', 'code', '-g', `${native}:${line}`] : ['code', '-g', `${native}:${line}`])
    : (isWin ? ['cmd', '/c', 'explorer', native] : ['open', native])  // explorer opens a file in its default app
  try {
    await $.process.run(argv, { timeoutMs: 15000 })
  } catch (err) {
    $.ui.toast(`Could not open ${path}: ${String(err)}`)
  }
}

async function readDoc($: EngineInterface, item: SddItem, name: string): Promise<SddDoc> {
  try {
    const text = await $.fs.read(`${item.spec?.path}/${name}`)
    const isCut = text.length > DOC_LIMIT
    return { name, text: isCut ? text.slice(0, DOC_LIMIT) : text, isCut }
  } catch (err) {
    return { name, text: `Could not read ${name}: ${String(err)}`, isCut: false }
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'sdd-view',
      description: 'Show the sdd flow of the work item this chat works on (or the one given) in a pane',
      argumentHint: '[work item id] [workspace folder]',
    })
    const sync = async () => {
      const v = await loadView($, (await $.state.get(selected)).value ?? (await $.state.get(mine)).value ?? null,
        (await $.state.get(snap)).value ?? null, (await $.state.get(place)).value ?? null)
      await $.state.set(snap, v.out)
      await $.state.set(error, v.why)
    }
    void sync()
    $.clock.every(30_000, () => {
      if (isOpen || isWorkspace) void sync()
    })
    return next(e)
  })

  // This chat's work item is the one it runs /sdd for. The view follows it, and opens by itself the
  // first time the chat takes one up (once per session; "view.autoOpen": false in sdd.json turns it off).
  for (const command of ['sdd', 'sdd:sdd'] as const) {
    on('command.run', { command }, async ($, e, next) => {
      const id = idFromArgs(e.args)
      if (id != null) {
        await $.state.set(mine, id)
        await $.state.set(selected, id)
        const v = await loadView($, id, (await $.state.get(snap)).value ?? null, (await $.state.get(place)).value ?? null)
        await $.state.set(snap, v.out)
        await $.state.set(error, v.why)
        if (v.out && v.out.autoOpen !== false && !(await $.state.get(autoOpened)).value) {
          await $.state.set(autoOpened, true)
          await openPane($, id)
        }
      }
      return next(e)
    })
  }

  on('command.run', { command: 'sdd-view' }, async ($, e) => {
    const [, num, rest] = /^(\d+)?\s*(.*)$/s.exec(e.args.trim()) ?? []
    const folder = (rest ?? '').trim().replace(/^["']|["']$/g, '')
    if (folder) await $.state.set(place, folder)
    // every get of one dispatch reads its start, so use what was just parsed
    const where = folder || ((await $.state.get(place)).value ?? null)
    const id = num ? Number(num) : ((await $.state.get(mine)).value ?? null)
    await $.state.set(selected, id)
    await $.state.set(stage, null)
    await $.state.set(doc, null)
    await openPane($, id)
    const v = await loadView($, id, (await $.state.get(snap)).value ?? null, where)
    await $.state.set(snap, v.out)
    await $.state.set(error, v.why)
    return { text: `sdd view${id != null ? ` of ${id}` : ''} opened${where ? ` on ${where}` : ''}.` }
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) isOpen = false
    return next(e)
  })

  for (const tool of ['Bash', 'PowerShell'] as const) {
    on('tool.call', { tool }, async ($, e, next) => {
      const ran = await next(e)
      const cmd = String((e as { command?: unknown }).command ?? '')
      if (SCRIPT_RUN.test(cmd)) {
        const id = idFromScript(cmd)
        if (id != null && id !== ((await $.state.get(mine)).value ?? null)) {
          await $.state.set(mine, id)
          await $.state.set(selected, id)
        }
        const v = await loadView($, id ?? (await $.state.get(selected)).value ?? null, (await $.state.get(snap)).value ?? null, (await $.state.get(place)).value ?? null)
        await $.state.set(snap, v.out)
        await $.state.set(error, v.why)
        if (id != null && v.out && v.out.autoOpen !== false && !(await $.state.get(autoOpened)).value) {
          await $.state.set(autoOpened, true)
          await openPane($, id)
        }
      }
      return ran
    })
  }

  on('turn.complete', async ($, e, next) => {
    if (isOpen || isWorkspace) {
      const v = await loadView($, (await $.state.get(selected)).value ?? null, (await $.state.get(snap)).value ?? null, (await $.state.get(place)).value ?? null)
      await $.state.set(snap, v.out)
      await $.state.set(error, v.why)
    }
    return next(e)
  })

  // ---------------------------------------------------------------- band above the prompt

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = (await $.state.get(snap)).value ?? null
    paint(s?.colors)
    const own = (await $.state.get(mine)).value ?? null
    const first = (s?.items ?? []).find(i => i.id === own && i.progress?.status === 'waiting')
    if (e.props.hasSurvey || !first) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box flexDirection="row" gap={1} width={e.props.bodyColumns}>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={C.now} wrap="truncate-end">
            {`${first.id} · ${phaseLabel(s?.flows[first.flow], first)} · waiting on you: ${first.progress?.gate || '—'}`}
          </Text>
        </Box>
        <Button key="band-open" label="Open sdd view" onPress={() => void (async () => {
          await $.state.set(selected, first.id)
          await $.state.set(stage, null)
          await $.state.set(doc, null)
          await openPane($, first.id)
          const v = await loadView($, first.id, s, (await $.state.get(place)).value ?? null)
          await $.state.set(snap, v.out)
          await $.state.set(error, v.why)
        })()} />
      </Box>
    )
  })

  // ---------------------------------------------------------------- the pane

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const t = $.ui.resolve(e)
    const { Box, Text, Button, Markdown } = t
    const cols = e.props.bodyColumns
    const s = (await $.state.get(snap)).value ?? null
    paint(s?.colors)
    const why = (await $.state.get(error)).value ?? null
    const id = (await $.state.get(selected)).value ?? (await $.state.get(mine)).value ?? null
    // what the presses do; they run after the drawing, so they may write
    const sync = async (to: number | null, isAsked = false) => {
      const v = await loadView($, to, (await $.state.get(snap)).value ?? null, (await $.state.get(place)).value ?? null)
      await $.state.set(snap, v.out)
      await $.state.set(error, v.why)
      // a refresh the person asked for says so, since an item that did not change looks the same
      if (isAsked) $.ui.toast(v.out ? `Refreshed ${stamp(new Date().toISOString())}` : `Refresh failed: ${v.why ?? 'no answer from env.py'}`)
    }
    if (!s) {
      return (
        <Box flexDirection="column" width={cols}>
          <Text bold>sdd view</Text>
          <Text dimColor>{why ?? 'Reading the work items…'}</Text>
          <Text dimColor>The view reads .claude/sdd.json at or above the session folder.</Text>
          <Button key="retry" label="Try again" hotkey="r" onPress={() => void sync(id, true)} />
        </Box>
      )
    }

    const item = id != null ? (s.items.find(i => i.id === id) ?? s.done.find(i => i.id === id)) : undefined

    // ---- no work item for this chat yet
    if (!item) {
      return (
        <Box flexDirection="column" width={cols} gap={1}>
          <Box flexDirection="row" gap={1}>
            <Box flexGrow={1}><Text bold>sdd view</Text></Box>
            <Button key="refresh" label="↻" hotkey="r" onPress={() => void sync(id, true)} />
          </Box>
          <Text wrap="wrap">{id != null ? `Work item ${id} is not in this workspace.` : 'This chat is not working on a work item yet.'}</Text>
          <Text dimColor wrap="wrap">Start one with /sdd &lt;id&gt;, or open one with /sdd-view &lt;id&gt;.</Text>
        </Box>
      )
    }

    // ---- one item: a decision log you open row by row
    const flow = s.flows[item.flow]
    const p = item.progress
    const openGate = (await $.state.get(gate)).value ?? null  // 'gate:Design agreed'
    const open = (await $.state.get(stage)).value ?? null        // 'stage:Design'
    const shown = (await $.state.get(doc)).value ?? null
    const typing = (await $.state.get(feedback)).value ?? null   // the stage whose feedback box is open
    const isDone = p?.status === 'done' || p?.status === 'abandoned' || !!item.removed
    const isWaiting = p?.status === 'waiting'
    const canOpen = e.surface !== 'mobile' && !!item.folder && !item.removed
    const hasInput = 'Input' in t
    const Input = hasInput ? t.Input : undefined
    const rows = flow ? stageRows(flow, item) : []
    const links = [item.url ? `[ADO ${item.id}](${item.url})` : `ADO ${item.id}`,
      ...Object.values(item.repos ?? {}).filter(r => r.pr).map(r => `[PR ${r.pr!.id}](${r.pr!.url})`)].join('  |  ')
    const toggle = (key: string) => void (async () => {
      await $.state.set(stage, open === key ? null : key)
      await $.state.set(gate, null)
      await $.state.set(doc, null)
      await $.state.set(feedback, null)
    })()
    const refsLine = (refs: string[]) => refs.map(r => refLink(item, r)).filter(Boolean).join('   ')
    // pages and documents open in Claude Code as the app opens any link; only a code link with a line
    // is answered here, to open VS Code at that line, which the app cannot do
    const linkMd = (key: string, text: string) => {
      const files = fileLinks(text).filter(h => fileTarget(h)?.line)
      return files.length
        ? <Markdown key={key} text={text} pressableLinks={files} onLinkPress={link => {
            const target = fileTarget(link.href)
            if (target) void openFile($, target.path, target.line)
          }} />
        : <Markdown text={text} />
    }

    return (
      <Box flexDirection="column" width={cols} gap={1}>
        <Box flexDirection="column">
          <Box flexDirection="row" gap={1}>
            <Box flexGrow={1} flexShrink={1}><Text bold wrap="wrap">{`${item.id} ${item.title}`}</Text></Box>
            <Button key="refresh" label="↻" hotkey="r" onPress={() => void sync(id, true)} />
          </Box>
          <Text dimColor>{`${item.type}, ${item.state} in ADO, ${flow?.label.toLowerCase() ?? item.flow}`}</Text>
          <Markdown text={links} />
        </Box>

        {p && isWaiting && (
          <Box flexDirection="column" borderStyle="round" borderColor={C.now} paddingX={1}>
            <Text bold color={C.now} wrap="wrap">{`Your turn: ${p.gate || 'a decision'}`}</Text>
            {p.next && <Text wrap="wrap">{`Then: ${p.next}`}</Text>}
            {p.note && <Text dimColor wrap="wrap">{p.note}</Text>}
          </Box>
        )}
        {p && !isWaiting && (
          <Text color={markColor(p.status as Mark)} wrap="wrap">
            {isDone ? `This item is ${p.status}${item.removed ? ` since ${when(item.removed)}` : ''}.` : `Now: ${phaseLabel(flow, item)}, ${statusWord(item)}.`}
          </Text>
        )}

        {flow && (
          <Box flexDirection="column" gap={1}>
            {rows.map(r => {
              const key = `stage:${r.stage.key}`
              const sum = stageSummary(flow, item, r.stage.key)
              const gates = decidedGates(r.stage, s.derived)
              return (
                <Box flexDirection="column">
                  <Box key={`row-${key}`} flexDirection="row" gap={1} width="100%">
                    <Text hover={{ color: lighten(markColor(r.mark)) ?? C.hoverText }} color={markColor(r.mark)} dimColor={r.mark === 'later'}>{GLYPH[r.mark]}</Text>
                    <Box flexGrow={1} flexShrink={1}>
                      <Button hover={{ color: C.hoverText, dimColor: false }} key={key} plain dimColor label={stageName(r.stage)}
                        onPress={() => toggle(key)} />
                    </Box>
                    {stamp(sum.lastAt) && (
                      <Button hover={{ color: C.hoverText, dimColor: false }} key={`${key}-at`} plain dimColor label={stamp(sum.lastAt)} onPress={() => toggle(key)} />
                    )}
                  </Box>
                  {open === key && (() => {
                    const lkey = `log:${r.stage.key}`
                    return (
                      <Box flexDirection="column" marginLeft={2}>
                        <Box key={`row-${lkey}`} flexDirection="row" gap={1} width="100%">
                          <Text hover={{ color: lighten(C.work) }} color={C.work}>≡</Text>
                          {/* the whole line is the button: name and count in one label */}
                          <Box flexGrow={1} flexShrink={1}>
                            <Button hover={{ color: C.hoverText, dimColor: false }} key={lkey} plain dimColor
                              label="Stage log"
                              onPress={() => void $.state.set(gate, openGate === lkey ? null : lkey)} />
                          </Box>
                        </Box>
                        {openGate === lkey && drawLog(r.stage.key, r.mark)}
                      </Box>
                    )
                  })()}
                  {open === key && gates.map(g => {
                    const gkey = `gate:${g}`
                    const story = gateStory(item, g)
                    const at = item.gates?.[g]
                    // the row shows the last recorded status only; earlier rounds are in the story
                    const last = at ? 'passed' : story.length ? story[story.length - 1].kind : 'open'
                    const lastAt = at ?? story[story.length - 1]?.at
                    const tone = last === 'passed' ? C.done : last === 'revoked' ? C.revoked : last === 'asked' ? C.now : undefined
                    return (
                      <Box flexDirection="column" marginLeft={2}>
                        <Box key={`row-${gkey}`} flexDirection="row" gap={1} width="100%">
                          <Text hover={{ color: lighten(tone ?? C.dim) }} color={tone ?? C.dim}>{at ? '◆' : '◇'}</Text>
                          {/* name left, time right: two buttons that do the same, so the whole line opens the gate */}
                          <Box flexGrow={1} flexShrink={1}>
                            <Button hover={{ color: C.hoverText, dimColor: false }} key={gkey} plain dimColor label={g}
                              onPress={() => void $.state.set(gate, openGate === gkey ? null : gkey)} />
                          </Box>
                          {stamp(lastAt) && (
                            <Button hover={{ color: C.hoverText, dimColor: false }} key={`${gkey}-at`} plain dimColor label={stamp(lastAt)}
                              onPress={() => void $.state.set(gate, openGate === gkey ? null : gkey)} />
                          )}
                        </Box>
                        {openGate === gkey && drawGate(story)}
                      </Box>
                    )
                  })}
                  {open === key && drawTools(r.stage.key)}
                </Box>
              )
            })}
          </Box>
        )}

        {Object.keys(item.repos ?? {}).length > 0 && (
          <Box flexDirection="column">
            {Object.entries(item.repos).map(([name, r]) => (
              <Box flexDirection="row" gap={1} alignItems="center" borderStyle="round" borderColor={C.line} paddingX={1}>
                <Box flexDirection="column" flexGrow={1} flexShrink={1}>
                  <Text bold wrap="wrap">{`Worktree ${name}`}</Text>
                  <Text dimColor wrap="wrap">{`${r.branch} from ${r.base}`}</Text>
                </Box>
                {canOpen && (
                  <Box flexDirection="row" gap={1} flexShrink={0}>
                    {/* icon buttons: 📁 the file manager, </> VS Code */}
                    <Button key={`open-${name}-files`} label="📁" onPress={() => void openIn($, 'files', `${item.folder}/${r.path}`)} />
                    <Button key={`open-${name}-code`} label="</>" onPress={() => void openIn($, 'code', `${item.folder}/${r.path}`)} />
                  </Box>
                )}
              </Box>
            ))}
          </Box>
        )}

      </Box>
    )

    function entryRow(at: string, word: string, color: string | undefined, text: string, refs: string[]) {
      return (
        <Box flexDirection="row" gap={1}>
          <Box width={11} flexShrink={0}><Text dimColor>{when(at)}</Text></Box>
          <Box flexDirection="column" flexGrow={1} flexShrink={1}>
            <Text color={color} wrap="wrap">{`${word}${text ? `  ${text}` : ''}`}</Text>
            {refs.length > 0 && linkMd(`refs-${at}-${word}`, refsLine(refs))}
          </Box>
        </Box>
      )
    }

    function drawGate(story: ReturnType<typeof gateStory>) {
      if (!story.length) return <Box marginLeft={3}><Text dimColor>Not asked yet.</Text></Box>
      return (
        <Box flexDirection="column" marginLeft={3} paddingLeft={1} borderStyle="single" borderColor={C.line}>
          {story.map(x => entryRow(x.at,
            x.kind === 'asked' ? 'Asked' : x.kind === 'passed' ? 'Passed. Your answer:' : 'Revoked:',
            x.kind === 'passed' ? C.done : x.kind === 'revoked' ? C.revoked : undefined,
            x.text, x.refs))}
        </Box>
      )
    }

    function drawLog(key: string, mark: Mark) {
      const hist = [...stageHistory(flow!, item!, key)].reverse()
      const word = (h: (typeof hist)[number]) => h.status === 'waiting' ? 'Asked' : h.status === 'done' ? 'Done'
        : h.status === 'blocked' ? 'Blocked' : h.status === 'abandoned' ? 'Abandoned' : 'Note'
      return (
        <Box flexDirection="column" marginLeft={3} paddingLeft={1} borderStyle="single" borderColor={C.line}>
          {hist.length === 0 && <Text dimColor>{mark === 'later' || mark === 'next' ? 'Not started yet.' : 'No log entries for this stage.'}</Text>}
          {hist.map(h => entryRow(h.at, word(h), h.status === 'waiting' ? C.now : h.status === 'blocked' ? C.revoked : undefined,
            [h.gate, h.note, h.gates?.passed?.length ? `Passed: ${h.gates.passed.join(', ')}.` : '',
              h.gates?.revoked?.length ? `Revoked: ${h.gates.revoked.join(', ')}.` : ''].filter(Boolean).join(' '),
            h.refs ?? []))}
        </Box>
      )
    }

    function drawTools(key: string) {
      const docs = stageDocs(item!, key)
      const st = flow!.stages.find(x => x.key === key)!
      // a review stage waiting on the PR's reviewers gets Approved / Merged / Rejected in place of feedback
      const isReview = !!st.reworkTo && phaseKey(flow!, item!.progress?.phase) === key && item!.progress?.status === 'waiting'
      const revokes = isReview ? undefined : item!.feedback?.[key]
      const rejecting = typing === `review:${key}`
      if (!docs.length && !revokes && !isReview) return null
      const answer = (text: string, done: string) => void (async () => {
        // posted as the person's own answer, so it shows in the chat; the flow skill takes it from there
        await $.state.set(feedback, null)
        try {
          const sent = await $.prompt.submit({ text, asUser: true })
          if ('drop' in sent && sent.drop) throw new Error(String(sent.drop))
          $.ui.toast(done)
        } catch (err) {
          await $.prompt.fill({ text })
          $.ui.toast(`Not sent (${String(err).slice(0, 160)}). It is in the prompt box instead.`)
        }
      })()
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1} gap={1}>
          {isReview && (
            <Box flexDirection="row" gap={1} flexWrap="wrap">
              <Button key={`rv-approved-${key}`} label="Approved"
                onPress={() => answer(`sdd review for ${item!.id}: approved`, 'Sent: the PR is approved.')} />
              <Button key={`rv-merged-${key}`} label="Merged"
                onPress={() => answer(`sdd review for ${item!.id}: merged`, 'Sent: the PR is merged.')} />
              <Button key={`rv-rejected-${key}`} label="Rejected" variant={rejecting ? 'primary' : undefined}
                onPress={() => void $.state.set(feedback, rejecting ? null : `review:${key}`)} />
            </Box>
          )}
          {isReview && rejecting && (
            <Box flexDirection="column" borderStyle="round" borderColor={C.revoked} paddingX={1}>
              {Input
                ? (
                  <Box flexDirection="row" gap={1} alignItems="center">
                    <Button key={`rv-cancel-${key}`} label="X" role="dismiss" onPress={() => void $.state.set(feedback, null)} />
                    <Box flexGrow={1} flexShrink={1}>
                      <Input key={`rv-why-${key}`} autoFocus submitLabel="Send to Claude"
                        placeholder={`Why was the PR rejected? The item goes back to ${st.reworkTo}.`}
                        onSubmit={v => {
                          const why = v.trim()
                          if (!why) { $.ui.toast('Say why the PR was rejected first'); return }
                          answer(`sdd review for ${item!.id}: rejected: ${why}`, `Sent: the PR was rejected. Back to ${st.reworkTo}.`)
                        }} />
                    </Box>
                  </Box>
                )
                : (
                  <Box flexDirection="row" gap={1}>
                    <Button key={`rv-cancel-${key}`} label="X" role="dismiss" onPress={() => void $.state.set(feedback, null)} />
                    <Button key={`rv-fill-${key}`} variant="primary" label="Write why in the prompt"
                      onPress={() => void $.prompt.fill({ text: `sdd review for ${item!.id}: rejected: ` })} />
                  </Box>
                )}
            </Box>
          )}
          {(docs.length > 0 || revokes) && (
            <Box flexDirection="row" gap={1} flexWrap="wrap">
              {docs.map(d => (
                <Button key={`doc-${key}-${d}`} label={d} variant={shown?.name === d ? 'primary' : undefined}
                  onPress={() => void (async () => {
                    await $.state.set(feedback, null)  // and a file closes the feedback box
                    await $.state.set(doc, shown?.name === d ? null : await readDoc($, item!, d))
                  })()} />
              ))}
              {revokes && (
                <Button key={`fb-open-${key}`} label={`Give feedback on ${stageName(flow!.stages.find(x => x.key === key)!)}`}
                  variant={typing === key ? 'primary' : undefined}
                  onPress={() => void (async () => {
                    // one thing at a time: the feedback box closes the open file
                    await $.state.set(doc, null)
                    await $.state.set(feedback, typing === key ? null : key)
                  })()} />
              )}
            </Box>
          )}
          {shown && docs.includes(shown.name) && (
            <Box flexDirection="column">
              <Markdown text={shown.text} />
              {shown.isCut && <Text dimColor>{`Cut at ${DOC_LIMIT} characters. Open the file for the rest.`}</Text>}
            </Box>
          )}
          {revokes && typing === key && (() => {
            const send = (v: string) => void (async () => {
              const text = v.trim()
              if (!text) {
                $.ui.toast('Type your feedback first')
                return
              }
              // sent as the person's own message, so it shows in the chat as theirs; the sdd skill reads
              // "sdd feedback for <id>, stage <stage>: <text>" as its feedback route. A plugin may not
              // send a text that starts with "/", so this is plain words, not the slash command.
              const prompt = `sdd feedback for ${item!.id}, stage ${key}: ${text}`
              await $.state.set(feedback, null)
              try {
                const sent = await $.prompt.submit({ text: prompt, asUser: true })
                if ('drop' in sent && sent.drop) throw new Error(String(sent.drop))
                $.ui.toast(`Feedback on ${key} sent to Claude.`)
              } catch (err) {
                // not sent: leave it in the prompt box so nothing typed is lost, and say why
                await $.prompt.fill({ text: prompt })
                $.ui.toast(`Not sent (${String(err).slice(0, 160)}). It is in the prompt box instead.`)
              }
            })()
            const close = () => void $.state.set(feedback, null)
            const hint = `What should change in ${key}?` + (revokes.length ? ` Sending revokes ${revokes.join(', ')}.` : '')
            return (
              <Box flexDirection="column" gap={1} borderStyle="round" borderColor={C.now} paddingX={1}>
                {Input
                  ? (
                    // the field's own submit button sends; X closes the box
                    <Box flexDirection="row" gap={1} alignItems="center">
                      <Button key={`fb-cancel-${key}`} label="X" role="dismiss" onPress={close} />
                      <Box flexGrow={1} flexShrink={1}>
                        <Input key={`fb-${key}`} autoFocus placeholder={hint} submitLabel="Send to Claude" onSubmit={send} />
                      </Box>
                    </Box>
                  )
                  : (
                    <Box flexDirection="column" gap={1}>
                      <Text dimColor wrap="wrap">{hint}</Text>
                      <Box flexDirection="row" gap={1}>
                        <Button key={`fb-cancel-${key}`} label="X" role="dismiss" onPress={close} />
                        <Button key={`fb-fill-${key}`} variant="primary" label="Write it in the prompt"
                          onPress={() => void $.prompt.fill({ text: `/sdd:sdd ${item!.id} feedback ${key}: ` })} />
                      </Box>
                    </Box>
                  )}
              </Box>
            )
          })()}
        </Box>
      )
    }
  })
}
