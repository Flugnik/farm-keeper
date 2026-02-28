$ErrorActionPreference = "Stop"

# STRICT env
$env:MEMORY_STRICT="1"
$env:MEMORY_WARN_ON_FALLBACK="1"
$env:MEMORY_TIMEOUT="2"

# UTF-8 console
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$healthUrl = "http://127.0.0.1:8011/health"
$gatewayPort = 18789

function Test-Health {
  try {
    $r = Invoke-RestMethod $healthUrl -TimeoutSec 1
    return ($r.status -eq "ok")
  } catch { return $false }
}

function Get-ListenerPid($port) {
  $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $c) { return $null }
  return $c.OwningProcess
}

# Ensure memory_service
if (-not (Test-Health)) {
  Write-Host "[run_all] memory_service not healthy -> starting..."
  Start-Process -WindowStyle Minimized -FilePath "python" -ArgumentList @(
    "-m","uvicorn","memory_service:app","--host","127.0.0.1","--port","8011"
  ) -WorkingDirectory (Get-Location).Path
}

# wait up to 10s for health
$ok = $false
1..20 | ForEach-Object {
  if (Test-Health) { $ok = $true; return }
  Start-Sleep -Milliseconds 500
}
if (-not $ok) { throw "[run_all] memory_service did not become healthy within 10s" }

# If gateway already running -> exit clean
$gPid = Get-ListenerPid $gatewayPort
if ($gPid) {
  $cmd = ""
  try { $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$gPid").CommandLine } catch {}
  Write-Host "[run_all] gateway already running on 127.0.0.1:$gatewayPort (pid $gPid)"
  if ($cmd) { Write-Host "[run_all] $cmd" }
  exit 0
}

Write-Host "[run_all] memory_service ok -> starting gateway..."
openclaw gateway
