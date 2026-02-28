@echo off
rem OpenClaw Gateway (v2026.2.25)
set "TMPDIR=C:\Users\user\AppData\Local\Temp"
set "PATH=C:\Program Files\WindowsApps\Microsoft.PowerShell_7.5.4.0_x64__8wekyb3d8bbwe;C:\Program Files (x86)\Common Files\Oracle\Java\java8path;C:\Program Files (x86)\Common Files\Oracle\Java\javapath;C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0\;C:\Windows\System32\OpenSSH\;C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem;C:\WINDOWS\System32\WindowsPowerShell\v1.0\;C:\WINDOWS\System32\OpenSSH\;C:\Program Files (x86)\dotnet\;C:\Program Files\Git\cmd;C:\Program Files\NVIDIA Corporation\NVIDIA App\NvDLISR;C:\Program Files\nodejs\;C:\Users\user\AppData\Local\Microsoft\WindowsApps;C:\Users\user\AppData\Local\Python\bin;C:\Users\user\AppData\Local\Programs\Ollama;C:\Users\user\AppData\Local\Programs\Microsoft VS Code\bin;C:\Users\user\AppData\Roaming\npm"
set "OPENCLAW_GATEWAY_PORT=18789"
set "OPENCLAW_GATEWAY_TOKEN=d24460cc1b59f0e0592d3a71f694939ef8449028c3b47edb"
set "OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service"
set "OPENCLAW_SERVICE_MARKER=openclaw"
set "OPENCLAW_SERVICE_KIND=gateway"
set "OPENCLAW_SERVICE_VERSION=2026.2.25"
"C:\Program Files\nodejs\node.exe" C:\Users\user\AppData\Roaming\npm\node_modules\openclaw\dist\index.js gateway --port 18789
