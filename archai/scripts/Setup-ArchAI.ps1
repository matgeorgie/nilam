$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$runtime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$python = Join-Path $runtime 'python\python.exe'
if (!(Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$node = Join-Path $runtime 'node\bin\node.exe'
if (!(Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path $node);$env:PATH"
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Setup failed with exit code $LASTEXITCODE" } }
$pythonVersion = & $python -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))'; Check-Exit
if ($pythonVersion.Trim() -ne '3.12') { throw 'Install Python 3.12 (64-bit) and add it to PATH. This package uses Python 3.12 model runtimes.' }
$nodeVersion = & $node -p 'process.versions.node.match(/^[0-9]+/)[0]'; Check-Exit
if ([int]$nodeVersion -lt 22) { throw 'Install Node.js 22 or newer, then rerun setup.' }
if (!(Test-Path '.venv\Scripts\python.exe')) { & $python -m venv .venv; Check-Exit }
$venv = Join-Path $root '.venv\Scripts\python.exe'
& $venv -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu; Check-Exit
& $venv -m pip install -r apps/api/requirements.txt; Check-Exit
$pnpm = Join-Path $runtime 'bin\fallback\pnpm.cmd'
if (Test-Path -LiteralPath $pnpm) { & $pnpm --dir apps/web install --ignore-workspace; Check-Exit }
else { Push-Location apps/web; try { & npm install; Check-Exit } finally { Pop-Location } }
& (Join-Path $PSScriptRoot 'Install-LocalAI.ps1')
Write-Host 'Setup complete. Run scripts\Start-ArchAI.ps1'
