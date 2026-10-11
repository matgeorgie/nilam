$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run Setup-ArchAI.ps1 first.' }
$node = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
if (!(Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path $node);$env:PATH"
$env:OMP_NUM_THREADS='2'; $env:MKL_NUM_THREADS='2'
foreach ($port in @(3000,8000)) { if ([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq $port }) { throw "Port $port is already in use." } }
$logs = Join-Path $root 'logs'; New-Item -ItemType Directory -Path $logs -Force | Out-Null
$api = Start-Process -FilePath $python -ArgumentList ('"' + (Join-Path $root 'scripts\run-api.py') + '"') -WorkingDirectory (Join-Path $root 'apps\api') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError (Join-Path $logs 'api-error.log') -PassThru
try { $web = Start-Process -FilePath $node -ArgumentList 'server.mjs' -WorkingDirectory (Join-Path $root 'apps\web') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'web.log') -RedirectStandardError (Join-Path $logs 'web-error.log') -PassThru }
catch { Stop-Process -Id $api.Id; throw }
@{ api=$api.Id; web=$web.Id; root=$root } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs 'processes.json') -Encoding UTF8
Write-Host 'Starting ArchAI. Open http://127.0.0.1:3000/projects after the web log says ready.'
Write-Host 'Logs are in logs/. Run Stop-ArchAI.ps1 when finished.'
