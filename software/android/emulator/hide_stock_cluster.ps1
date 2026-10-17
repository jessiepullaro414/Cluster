# Blank the second display of the Android Automotive emulator image (the stock instrument cluster, "Welcome, ClusterHome").
# The image creates that display itself and the AVD cannot remove it; disabling the two stock cluster apps leaves it black so
# only our app is visible. Survives emulator restarts (it is stored in the AVD's user data); undo with -Undo.
param([switch]$Undo)
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb root | Out-Null
Start-Sleep 2
$verb = if ($Undo) { "enable" } else { "disable-user" }
foreach ($p in "com.android.car.cluster.osdouble", "com.android.car.cluster.home") {
    & $adb shell pm $verb --user 0 $p
}
