// Runs a hook's Python script with the first Python that is really there: python, python3, then py.
//   node py.mjs <script.py> [args...]
// The hook shell is Git Bash or PowerShell on Windows, so a fallback in the hook command itself would not
// work in both, and `a || b` would run the guard again after it blocked (exit 2). On Windows `python` and
// `python3` can be the Microsoft Store shortcut: it prints "Python was not found" and exits 9009. Stdin,
// stdout, stderr and the exit code go through unchanged.
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

let input = Buffer.alloc(0)
try { input = readFileSync(0) } catch { /* no stdin */ }

const storeStub = r => r.status === 9009 || /^Python was not found/.test((String(r.stderr).trim() || String(r.stdout).trim()))

function run() {
  for (const exe of ['python', 'python3', 'py']) {
    const r = spawnSync(exe, process.argv.slice(2), { input, maxBuffer: 64 * 1024 * 1024, windowsHide: true })
    if (r.error && r.error.code === 'ENOENT') continue
    if (r.error) { process.stderr.write(`sdd hook: could not run ${exe}: ${r.error.message}\n`); return 1 }
    if (storeStub(r)) continue
    process.stdout.write(r.stdout)
    process.stderr.write(r.stderr)
    return r.status ?? 1
  }
  process.stderr.write('sdd hook: no Python found (tried python, python3, py). Install Python 3.9 or later.\n')
  return 1
}

// exitCode, not exit(): exit() can cut off what is still being written to a pipe
process.exitCode = run()
