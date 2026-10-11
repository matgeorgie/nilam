$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($service in @('api','web')) {
  $file = Join-Path $root "logs\$service-runtime.json"
  if (!(Test-Path -LiteralPath $file)) { continue }
  $record = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
  $owned = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
  if ($owned -and $owned.Path -eq $record.path -and [Math]::Abs(($owned.StartTime.ToUniversalTime()-([DateTime]::Parse($record.started).ToUniversalTime())).TotalSeconds) -lt 120) {
    $owned.Kill()
    $owned.WaitForExit(10000) | Out-Null
  }
  Remove-Item -LiteralPath $file
}
