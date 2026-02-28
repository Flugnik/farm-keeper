openclaw gateway stop 2>$null
schtasks /End /TN "OpenClaw Gateway" 2>$null
Start-Sleep -Seconds 1
powershell -ExecutionPolicy Bypass -File .\run_all.ps1
