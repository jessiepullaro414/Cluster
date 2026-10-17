#!/usr/bin/env python3
"""Record the raw material for the cluster demo video: the Android app in the emulator (adb screenrecord) and the four small gauges
(the real firmware screen code in the harness, which dumps its panels with --frames), while this script drives the app through a
storyboard with the app's debug broadcasts (RUNNING.md). Writes a timeline.json of caption events. compose_demo.py turns the result
into the video.

    python software/demo/record_demo.py [workdir]

Needs the emulator running with the cluster app installed and build/harness built (make harness, in WSL). Do not touch the PC
while it runs (about two minutes): the harness window opens on the desktop.
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adbtools import ADB, adb, clear_app, clear_then_set, key, set_app, wsl_ip  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FW_WIN = os.path.normpath(os.path.join(HERE, "..", "gauges-fw"))
DISTRO = "Ubuntu-22.04"
WORK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "cluster-demo-work")   # not under AppData: Windows apps there are virtualised
PORT = 5005

timeline = []      # {"t": wall seconds, "title": ..., "sub": ...}
marks = {}


def wsl(cmd, wait=True):
    args = ["wsl.exe", "-d", DISTRO, "--", "bash", "-c", cmd]
    if wait:
        return subprocess.run(args, capture_output=True, text=True).stdout
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)


def wslpath(p):
    p = os.path.abspath(p).replace("\\", "/")
    return f"/mnt/{p[0].lower()}{p[2:]}"


def caption(title, sub=""):
    timeline.append({"t": time.time(), "title": title, "sub": sub})
    print(f"[{time.time() - marks['start']:6.1f}s] {title}")


def hold(seconds):
    time.sleep(seconds)


def main():
    global FW
    FW = wslpath(FW_WIN)
    os.makedirs(WORK, exist_ok=True)
    ip = wsl_ip(DISTRO)

    # --- the harness, with its panels dumped as frames
    wsl(f"pkill -x harness; rm -rf $HOME/demo_frames; mkdir -p $HOME/demo_frames; rm -f $HOME/demo_feed.txt")
    wsl(f"cd {FW} && make build/harness >/dev/null 2>&1")
    harness = wsl(f"cd {FW} && DISPLAY=:0 exec ./build/harness --udp {PORT} --scale 1.0 --frames $HOME/demo_frames --record $HOME/demo_feed.txt 2>/tmp/harness.log", wait=False)
    time.sleep(3)

    # --- the app: a known starting point (Android Auto on the phone, so the small gauges keep their own look; maps in the centre)
    adb("shell", "am", "force-stop", "com.jessiescars.cluster")
    time.sleep(1)
    adb("shell", "am", "start", "-n", "com.jessiescars.cluster/.MainActivity")
    time.sleep(2)
    clear_app()
    set_app(telemetry=f"{ip}:{PORT}", theme="modern", units="mph", phone=True, phone_kind="androidauto", flip=False, night=False,
            dimmer=100.0, match_carplay=True, settings=False, high_beam=False, brake=False, alt=False, oil=False, link_dead=False)
    time.sleep(3)

    # --- the emulator screen recording (3 minutes is the most screenrecord does in one file)
    adb("shell", "rm", "-f", "/sdcard/demo.mp4", check=False)
    rec = subprocess.Popen([ADB, "shell", "screenrecord", "--size", "720x720", "--bit-rate", "8000000", "--time-limit", "175", "/sdcard/demo.mp4"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    time.sleep(1.5)
    marks["start"] = time.time()
    marks["rec_start"] = marks["start"]

    caption("The cluster", "an Android centre gauge and four small gauges for a 1966 Mustang")
    hold(5.0)

    # sync event: the centre changes from the map to the speedometer, and the small gauges react to the same app state
    caption("The centre flips between navigation and the speedometer", "the small gauges stop repeating speed and show another gauge")
    marks["sync"] = time.time()
    set_app(flip=True)
    hold(7.0)

    caption("Four looks, chosen in the settings", "Classic: needles and seven-segment digits")
    set_app(theme="classic")
    hold(5.0)
    caption("Four looks, chosen in the settings", "Modern: progress arcs")
    set_app(theme="modern")
    hold(4.0)
    caption("Four looks, chosen in the settings", "CarPlay-inspired: thin rings")
    set_app(theme="carplay")
    hold(4.0)
    caption("Four looks, chosen in the settings", "Factory: the printed faces of the 1966 Mustang gauges")
    set_app(theme="factory")
    hold(6.0)

    caption("Full sweep", "speed and rpm pinned high: the needles and the redline")
    set_app(theme="classic", speed_kph=190.0, rpm=6600.0)
    hold(5.0)
    clear_then_set(theme="classic", flip=True, units="mph", phone=True, phone_kind="androidauto", night=False, dimmer=100.0)
    hold(1.0)

    caption("Metric or imperial", "one setting switches every screen: km/h, degrees C, kPa")
    set_app(units="metric", theme="modern")
    hold(5.0)
    set_app(units="mph")
    hold(1.0)

    caption("Night mode and the dash dimmer", "the lamp-switch feed dims every screen together")
    set_app(night=True, dimmer=35.0, theme="factory")
    hold(5.5)
    set_app(night=False, dimmer=100.0)
    hold(1.0)

    caption("Warning lamps", "brake, alternator, oil and high beam, on the centre gauge")
    set_app(high_beam=True, brake=True, alt=True, oil=True)
    hold(5.5)
    set_app(high_beam=False, brake=False, alt=False, oil=False)
    hold(1.0)

    caption("CarPlay and Android Auto", "while a phone shows CarPlay, the small gauges take its look")
    set_app(flip=False, theme="factory", phone=True, phone_kind="carplay", match_carplay=True)
    hold(6.0)
    caption("CarPlay and Android Auto", "Android Auto keeps your own look")
    set_app(phone_kind="androidauto")
    hold(5.0)
    caption("No phone connected", "the centre shows the speedometer in your look")
    set_app(phone=False, no_phone="gauge")
    hold(5.0)

    caption("Settings", "the list is driven by the rotary dial")
    set_app(settings=True)
    hold(5.0)
    set_app(settings=False)
    hold(1.0)

    caption("If Android stops, the gauges keep working", "the app is force-stopped here: the four small gauges run on their own sensors")
    marks["kill"] = time.time()
    adb("shell", "am", "force-stop", "com.jessiescars.cluster")
    hold(9.0)
    caption("And it picks up again", "the app restarts and the centre gauge is back")
    adb("shell", "am", "start", "-n", "com.jessiescars.cluster/.MainActivity")
    time.sleep(1.5)
    set_app(telemetry=f"{ip}:{PORT}", theme="factory", units="mph", phone=False, no_phone="gauge", flip=True)
    hold(7.0)
    caption("", "")
    marks["end"] = time.time()

    # --- stop and collect
    adb("shell", "pkill", "-2", "screenrecord", check=False)
    time.sleep(3)
    rec.wait(timeout=15)
    wsl("pkill -x harness")
    harness.terminate()
    mp4 = os.path.join(WORK, "emulator.mp4")
    adb("pull", "/sdcard/demo.mp4", mp4)
    fr = os.path.join(WORK, "harness_frames")
    if os.path.exists(fr):
        shutil.rmtree(fr)
    wsl(f"cp -r $HOME/demo_frames {wslpath(fr)}")
    json.dump({"timeline": timeline, "marks": marks}, open(os.path.join(WORK, "timeline.json"), "w"), indent=1)
    n = len(os.listdir(fr))
    print(f"recorded {marks['end'] - marks['start']:.1f} s, {n} harness frames, emulator video {os.path.getsize(mp4) // 1024} KB")


if __name__ == "__main__":
    main()
