chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== memory_service :8011 ==="
try {
  irm http://127.0.0.1:8011/health -TimeoutSec 1 | Format-List
} catch {
  Write-Host "memory_service: DOWN"
}

Write-Host "`n=== gateway :18789 ==="
$g = Get-NetTCPConnection -LocalPort 18789 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($g) {
  $gwPid = $g.OwningProcess
  $cmd = ""
  try { $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$gwPid").CommandLine } catch {}
  Write-Host "gateway: UP pid=$gwPid"
  if ($cmd) { Write-Host $cmd }
} else {
  Write-Host "gateway: DOWN"
}
