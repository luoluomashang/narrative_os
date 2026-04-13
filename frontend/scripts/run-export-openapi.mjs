import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const frontendRoot = process.cwd()
const repoRoot = path.resolve(frontendRoot, '../..')
const packageRoot = path.join(repoRoot, 'narrative_os')
const exportScript = path.join(packageRoot, 'scripts', 'export_openapi.py')
const outputPath = path.resolve(
  frontendRoot,
  process.env.NARRATIVE_OPENAPI_OUT ?? '../../openapi.json',
)

const candidateExecutables = [
  process.env.PYTHON,
  path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
  path.join(repoRoot, '.venv', 'bin', 'python'),
  process.platform === 'win32' ? 'py' : null,
  'python',
  'python3',
].filter(Boolean)

let lastFailure = null

for (const executable of candidateExecutables) {
  if (executable.includes(path.sep) && !fs.existsSync(executable)) {
    continue
  }

  const args = executable === 'py'
    ? ['-3', exportScript, outputPath]
    : [exportScript, outputPath]

  const result = spawnSync(executable, args, {
    cwd: packageRoot,
    stdio: 'inherit',
  })

  if (!result.error && result.status === 0) {
    process.exit(0)
  }

  lastFailure = result.error ?? new Error(`OpenAPI export exited with code ${result.status ?? 'unknown'}`)
}

throw lastFailure ?? new Error('Unable to locate a Python interpreter for OpenAPI export.')