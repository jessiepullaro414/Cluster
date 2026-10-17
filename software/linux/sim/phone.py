#!/usr/bin/env python3
"""Plug the emulated phone into the bench, or unplug it: the car_sim.py panel's phone buttons. Runs on Windows (adb and
the relay live there; WSL cannot reach adb's forward).

    py phone.py connect       # fresh Android Auto head unit server on the aa_phone emulator + one relay into LIVI
    py phone.py disconnect    # stop the relay and Android Auto on the phone

Needs the aa_phone emulator running with Android Auto set up (software/linux/aa-bench/README.md).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "software", "demo"))   # record_livi_demo's adb helpers, wincap
import record_livi_demo as R  # noqa: E402  (adb helpers: the head unit server, the phone's screen)

RELAY = os.path.join(REPO, "software", "linux", "aa-bench", "relay.ps1")


def stop_relays():
    """Only one relay may run: LIVI drops a session that a newer connection supersedes."""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -like '*relay.ps1*' }"
                    " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True, timeout=60)


def start_emulator(timeout=240):
    """Start the aa_phone emulator (its window opens on the desktop) and wait until Android has booted."""
    sdk = os.path.dirname(os.path.dirname(R.ADB))
    subprocess.Popen([os.path.join(sdk, "emulator", "emulator.exe"), "-avd", "aa_phone", "-no-snapshot-save", "-gpu", "auto"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("starting the phone emulator...", flush=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if R.adb("shell", "getprop", "sys.boot_completed", timeout=5).strip() == "1":
                time.sleep(15)                     # let Google Play services and Android Auto settle
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(3)


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "connect"
    stop_relays()
    if what == "disconnect":
        R.adb("shell", "am", "force-stop", "com.google.android.projection.gearhead")
        print("unplugged")
        return
    if "emulator" not in R.adb("devices"):
        start_emulator()
        if "emulator" not in R.adb("devices"):
            print("no phone: the aa_phone emulator did not start")
            return
    # The emulator runs the arm64 Android Auto and Google Play services through ARM translation, and they crash now
    # and then (SIGSEGV), more often just after a boot: the session connects but the centre stays black. So check
    # LIVI's window for a picture and plug in again if there is none.
    for attempt in range(3):
        if attempt:
            stop_relays()
            print(f"no picture on the centre, plugging in again ({attempt + 1}/3)", flush=True)
        R.start_head_unit_server()
        R.adb("shell", "am", "start", "-n", "com.google.android.apps.maps/com.google.android.maps.MapsActivity")
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", RELAY],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000)
        if centre_has_picture():
            print("plugged in: Android Auto is on the centre")
            return
    print("plugged in, but the centre is still black: try Disconnect, wait a minute, Connect")


def livi_projecting():
    """LIVI's own state: Android Auto is the active projection (state/status.json in the bench distro)."""
    r = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "-u", "root", "-e", "cat", "/root/.config/LIVI/state/status.json"],
                       capture_output=True, text=True, timeout=20)
    return '"active": "aa"' in r.stdout


def centre_has_picture(timeout=40.0):
    """True once LIVI projects Android Auto and its window shows a picture. Before the phone connects LIVI shows our
    own (bright) speedometer, so the picture only counts once LIVI says Android Auto is active."""
    from wincap import capture, find_window
    t0 = time.time()
    while time.time() - t0 < timeout:
        if livi_projecting():
            # Android Auto's splash is dark for a few seconds; give the picture up to 15 s (LIVI's content area:
            # below its 32 px title strip, 752 px square at this display scale)
            for _ in range(15):
                time.sleep(1)
                h = find_window("LIVI")
                if h is not None and capture(h)[32:784, 0:752].mean() > 30:
                    return True
            return False
        time.sleep(1)
    return False


if __name__ == "__main__":
    main()
