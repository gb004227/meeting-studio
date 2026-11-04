$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$bootstrapPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $bootstrapPython)) { $bootstrapPython = Join-Path $projectRoot 'python\python.exe' }
$env:PYTHONUTF8 = '1'
$env:HF_HOME = 'K:\工具箱\MOSS model\.cache\huggingface'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_DISABLE_XET = '1'
$env:UV_LINK_MODE = 'copy'
Write-Output 'Preparing the isolated local MOSS environment...'
if (-not (Test-Path -LiteralPath '.moss-venv\Scripts\python.exe')) {
    uv venv --python 3.12 .moss-venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create MOSS Python environment.' }
}
if (-not (Test-Path -LiteralPath 'vendor\moss\pyproject.toml')) {
    & $bootstrapPython (Join-Path $PSScriptRoot 'download-moss-source.py')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download official MOSS source.' }
}
& '.moss-venv\Scripts\python.exe' -c 'import torch, torchaudio; assert torch.ones(1).item() == 1'
if ($LASTEXITCODE -ne 0) {
    & $bootstrapPython (Join-Path $PSScriptRoot 'with-system-proxy.py') uv pip install --python .moss-venv\Scripts\python.exe torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install CPU PyTorch.' }
}
uv pip install --python .moss-venv\Scripts\python.exe -e ./vendor/moss funasr
if ($LASTEXITCODE -ne 0) { throw 'Cannot install MOSS dependencies.' }
& $bootstrapPython (Join-Path $PSScriptRoot 'with-system-proxy.py') '.moss-venv\Scripts\python.exe' (Join-Path $PSScriptRoot 'download-models.py')
if ($LASTEXITCODE -ne 0) { throw 'Model download incomplete. Re-run this script to resume.' }
Write-Output 'Local MOSS environment and models are ready.'
