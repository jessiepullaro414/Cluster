# Build and open the screen test harness (a native window, via WSLg), and point the Android app at it.
#
#   powershell -File tools\run_harness.ps1              # window, fed by the built-in drive and by Android when it connects
#   powershell -File tools\run_harness.ps1 -NoAndroid   # do not touch the emulator
#
# What it does: builds build/harness in WSL (make harness), starts it with a window on the desktop
# listening on UDP 5005, finds WSL's IP address, and tells the running cluster app to send its
# telemetry there (the emulator can reach the WSL address because its traffic leaves through the PC).
# The window needs the X11 headers once: wsl sh tools/get_x11_headers.sh
param([switch]$NoAndroid, [string]$Distro = "Ubuntu-22.04", [int]$Port = 5005)
$ErrorActionPreference = "Stop"
$fw = Split-Path -Parent $PSScriptRoot
$drive = $fw.Substring(0, 1).ToLower()
$wslFw = "/mnt/$drive" + $fw.Substring(2).Replace("\", "/")

wsl.exe -d $Distro -- bash -c "cd '$wslFw' && make build/harness"
if ($LASTEXITCODE -ne 0) { throw "build failed (is ~/x11sdk there? run: wsl sh tools/get_x11_headers.sh)" }

Get-Process wsl -ErrorAction SilentlyContinue | Out-Null
wsl.exe -d $Distro -- bash -c "pkill -x harness; true" | Out-Null
Start-Process -FilePath "wsl.exe" -WindowStyle Hidden -ArgumentList "-d", $Distro, "--", "bash", "-c",
    "cd '$wslFw' && DISPLAY=:0 exec ./build/harness --udp $Port --record /tmp/android_feed.txt"

$ip = (wsl.exe -d $Distro -- hostname -I).Trim().Split(" ")[0]
Write-Host "harness window started; listening on ${ip}:$Port (recording to /tmp/android_feed.txt in WSL)"

if (-not $NoAndroid) {
    $adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
    if (Test-Path $adb) {
        & $adb shell am broadcast -a com.jessiescars.cluster.SET --es telemetry "${ip}:$Port" | Select-Object -Last 1
        Write-Host "Android app told to send to ${ip}:$Port (start the app if it is not running)"
    } else {
        Write-Host "adb not found; point the app yourself: adb shell am broadcast -a com.jessiescars.cluster.SET --es telemetry ${ip}:$Port"
    }
}
