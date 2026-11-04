$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is required: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 22 or newer is required.' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment.' }
}
uv pip install --python .venv\Scripts\python.exe -e './backend[test]'
if ($LASTEXITCODE -ne 0) { throw 'Cannot install backend.' }
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Cannot install desktop dependencies.' }
if (-not (Test-Path -LiteralPath 'node_modules\electron\dist\electron.exe')) {
    & '.venv\Scripts\python.exe' (Join-Path $PSScriptRoot 'download-electron.py')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare Electron runtime.' }
}
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Cannot build app.' }
Write-Output 'Ready. Use Start.cmd to launch Meeting Studio.'
