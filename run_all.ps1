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

# Tunables for cold start
$healthTimeoutSec = 5     # per-request timeout
$waitTotalSec     = 60    # total warmup time
$waitStepMs       = 500   # polling interval

function Test-Health {
  try {
    $r = Invoke-RestMethod $healthUrl -TimeoutSec $healthTimeoutSec
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

# wait for health
$ok = $false
$maxIters = [int](($waitTotalSec * 1000) / $waitStepMs)
for ($i=1; $i -le $maxIters; $i++) {
  if (Test-Health) { $ok = $true; break }
  if ($i -eq 1 -or ($i % 10 -eq 0)) { Write-Host "[run_all] waiting memory_service warmup... ($([int]($i*$waitStepMs/1000))s)" }
  Start-Sleep -Milliseconds $waitStepMs
}

if (-not $ok) {
  $pid8011 = Get-ListenerPid 8011
  if ($pid8011) {
    Write-Host "[run_all] memory_service port 8011 is listening (pid $pid8011) but /health not OK within ${waitTotalSec}s"
  }
  throw "[run_all] memory_service did not become healthy within ${waitTotalSec}s"
}

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
