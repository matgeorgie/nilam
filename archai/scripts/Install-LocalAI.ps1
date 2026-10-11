$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$venv = Join-Path $root '.venv\Scripts\python.exe'
& $venv -m pip install llama-cpp-python==0.3.36 --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Local inference runtime installation failed.' }
& $venv scripts/download-language-model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
Write-Host 'Local Qwen is installed. No hosted language API is required.'
