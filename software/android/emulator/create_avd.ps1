# Creates the AVD "cluster_round" : an Android Automotive emulator whose only
# display matches the production centre panel.
#
#   Panel   TSD TST040HDBC-42 : 4.0 in round, 720 x 720        (docs/mechanical-fit.md)
#   Density 720 px / 4.0 in = 180 ppi -> hw.lcd.density=180 so dp sizes match
#           what the real panel shows
#   Round   hw.lcd.circular=true asks the emulator to mask the window to a circle
#
# Base image: Android 15 automotive, x86_64, Google APIs (no Play Store). Google
# publishes no newer automotive image; the NXP tree is Android 16 (PLAN.md s.6).
# Run: powershell -File create_avd.ps1   (re-running replaces the AVD)
$ErrorActionPreference = "Stop"
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:ANDROID_SDK_ROOT = $sdk
$image = "system-images;android-35-ext15;android-automotive;x86_64"

"no" | & "$sdk\cmdline-tools\latest\bin\avdmanager.bat" create avd `
    -n cluster_round -k $image -d automotive_1024p_landscape --force | Out-Null

$cfg = "$env:USERPROFILE\.android\avd\cluster_round.avd\config.ini"
$set = @{
    "hw.lcd.width"      = "720"
    "hw.lcd.height"     = "720"
    "hw.lcd.density"    = "180"
    "hw.lcd.circular"   = "true"
    "hw.initialOrientation" = "landscape"
    "hw.device.name"    = "cluster_round_720"
    "showDeviceFrame"   = "no"
    "hw.keyboard"       = "yes"
}
$lines = Get-Content $cfg
foreach ($k in $set.Keys) {
    $hit = $false
    $lines = $lines | ForEach-Object {
        if ($_ -like "$k=*") { $hit = $true; "$k=$($set[$k])" } else { $_ }
    }
    if (-not $hit) { $lines += "$k=$($set[$k])" }
}
Set-Content $cfg $lines -Encoding ascii
"cluster_round created: 720x720 @180 dpi, circular"
