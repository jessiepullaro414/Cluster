# Build and open the dial HMI simulator window (WSLg).  powershell -File software\hmi-sim\run.ps1
param([string]$Distro = "Ubuntu-22.04")
$ErrorActionPreference = "Stop"
$drive = $PSScriptRoot.Substring(0, 1).ToLower()
$w = "/mnt/$drive" + $PSScriptRoot.Substring(2).Replace("\", "/")
wsl.exe -d $Distro -- bash -c "cd '$w' && make build/hmi_sim"
if ($LASTEXITCODE -ne 0) { throw "build failed (X11 headers: wsl sh software/gauges-fw/tools/get_x11_headers.sh)" }
wsl.exe -d $Distro -- bash -c "pkill -x hmi_sim; true" | Out-Null
Start-Process -FilePath "wsl.exe" -WindowStyle Hidden -ArgumentList "-d", $Distro, "--", "bash", "-c", "cd '$w' && DISPLAY=:0 exec ./build/hmi_sim"
Write-Host "dial simulator window opened"
