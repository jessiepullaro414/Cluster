#!/usr/bin/env python3
"""Record the raw material for the Linux-option demo video: LIVI's window (our speedometer, then real Android Auto from the emulated
phone) and the four small gauges (gauges-fw's harness dumping its panels), while this script drives the bench through a storyboard
with the dial (clusterd's dial pipe) and the phone (adb). Writes timeline.json with the captions and the clock offset between Windows
and WSL; compose_livi_demo.py turns the result into the video.

    py software/demo/record_livi_demo.py [workdir]

Needs the bench of software/linux/aa-bench/README.md: the Ubuntu-24.04 WSL distro with the patched LIVI under
/root/livi-bench/app, clusterd at /root/livi-bench/clusterd-bin, drive.txt, LIVI's config from livi_config.py; the aa_phone emulator
running with Android Auto set up (developer mode on); gauges-fw build/harness. LIVI's window is captured with PrintWindow, so
other windows may cover it, but leave the harness and emulator windows alone while it runs (about two minutes).
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adbtools import ADB  # noqa: E402
from wincap import capture, find_window  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
DISTRO = "Ubuntu-24.04"
BENCH = "/root/livi-bench"
WSL_WORK = "/root/demo-livi"
WORK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "cluster-demo-livi")
FPS = 25

timeline, marks = [], {}


def wsl(cmd, wait=True, timeout=60):
    args = ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "-c", cmd]
    if wait:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)


def adb(*args, timeout=20):
    r = subprocess.run([ADB, *args], capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def caption(title, sub=""):
    timeline.append({"t": time.time(), "title": title, "sub": sub})
    print(f"[{time.time() - marks['start']:6.1f}s] {title}  {sub}", flush=True)


def dial(keys, gap=0.6):
    """Dial gestures through clusterd's pipe: a/d turn, c click, h hold 0.7 s, m hold 1.6 s."""
    for k in keys:
        wsl(f"timeout 5 bash -c 'printf {k} > /tmp/dial'", timeout=15)
        time.sleep({"h": 1.0, "m": 1.9}.get(k, gap))


# ---- the phone ----------------------------------------------------------------------------------------------------

def ui_nodes():
    """Texts on the phone's screen and their centres. uiautomator cannot dump a screen that keeps animating (Maps
    navigating), so this retries and gives an empty list rather than failing."""
    root = None
    for _ in range(3):
        adb("shell", "rm", "-f", "/sdcard/ui.xml")
        adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        xml = adb("shell", "cat", "/sdcard/ui.xml")
        try:
            root = ET.fromstring(xml[xml.find("<?xml"):])
            break
        except ET.ParseError:
            time.sleep(1)
    if root is None:
        return []
    out = []
    for n in root.iter("node"):
        t = n.get("text") or n.get("content-desc") or ""
        m = re.findall(r"\d+", n.get("bounds", ""))
        if t and len(m) == 4:
            x1, y1, x2, y2 = map(int, m)
            out.append((t, (x1 + x2) // 2, (y1 + y2) // 2))
    return out


def tap(text):
    for t, x, y in ui_nodes():
        if text.lower() in t.lower():
            adb("shell", "input", "tap", str(x), str(y))
            return True
    return False


def start_head_unit_server():
    """A fresh head unit server: a server left over from an earlier session does not answer (aa-bench README).
    The phone is woken and unlocked first: after a reboot it sits on its lock screen, and Android Auto then sends
    navigation data but a black picture."""
    adb("shell", "svc", "power", "stayon", "true")
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb("shell", "wm", "dismiss-keyguard")
    time.sleep(1)
    adb("shell", "am", "force-stop", "com.google.android.projection.gearhead")
    adb("shell", "am", "start", "-n", "com.google.android.projection.gearhead/.companion.settings.DefaultSettingsActivity")
    time.sleep(4)
    if not tap("More options"):
        raise SystemExit("record: Android Auto settings did not open")
    time.sleep(1.5)
    if not tap("Start head unit server"):
        raise SystemExit("record: no 'Start head unit server' (is Android Auto developer mode on?)")
    adb("forward", "tcp:5277", "tcp:5277")


# A drive north on N Shoreline Blvd, Mountain View, at about 40 km/h (one fix every half second).
ROUTE = [(37.4105 + i * 0.00006, -122.0775) for i in range(240)]


def gps_drive(stop):
    for lat, lon in ROUTE:
        if stop.is_set():
            return
        adb("emu", "geo", "fix", f"{lon:.6f}", f"{lat:.6f}")
        time.sleep(0.5)


# ---- the centre: LIVI's window ----------------------------------------------------------------------------------

def record_centre(stop, out_dir):
    h = find_window("LIVI")
    if not h:
        raise SystemExit("record: no LIVI window")
    n, period = 0, 1.0 / FPS
    nxt = time.time()
    while not stop.is_set():
        t = time.time()
        img = capture(h)
        cv2.imwrite(os.path.join(out_dir, f"{int(t * 1000)}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        n += 1
        nxt += period
        time.sleep(max(0.0, nxt - time.time()))
    marks["centre_frames"] = n


def main():
    centre_dir = os.path.join(WORK, "centre")
    os.makedirs(centre_dir, exist_ok=True)
    for f in os.listdir(centre_dir):
        os.remove(os.path.join(centre_dir, f))

    # clean bench: LIVI restarted (fresh log), harness dumping frames, clusterd fed by the replayed drive, dial pipe.
    # A relay left running from earlier would connect too, and LIVI drops a session that a newer connection supersedes.
    print("record: restarting LIVI, harness and clusterd", flush=True)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -like '*relay.ps1*' }"
                    " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True, timeout=60)
    wsl("for p in livi-ui livi-core livi-compositor livi-helperd livi-gst-host livi clusterd-bin harness; do pkill -x $p; done;"
        "pkill -f '[s]leep 100001'; sleep 2; "    # [s]: the pattern must not match this shell's own command line
        f"rm -rf {WSL_WORK} && mkdir -p {WSL_WORK}/hf && printf 'theme = 1\\nimperial = 1\\n' > {WSL_WORK}/settings.conf")
    livi = wsl(f"cd {BENCH}/app/squashfs-root && LIVI_AA_TCP_WITHOUT_BT=1 LIVI_AA_H264_ONLY=1 LIVI_PORT=5278 "
               f"exec ./livi --no-sandbox > {WSL_WORK}/livi.log 2>&1", wait=False)
    for _ in range(60):
        if "compositor display" in wsl(f"cat {WSL_WORK}/livi.log 2>/dev/null"):
            break
        time.sleep(1)
    else:
        raise SystemExit("record: LIVI did not start (see livi.log)")
    time.sleep(3)
    fw = "/mnt/c" + REPO[2:].replace("\\", "/") + "/software/gauges-fw"
    cd_dir = "/mnt/c" + REPO[2:].replace("\\", "/") + "/software/linux/clusterd"
    harness = wsl(f"cd {fw} && exec ./build/harness --udp 5005 --scale 1.0 --frames {WSL_WORK}/hf --frames-fps 25", wait=False)
    clusterd = wsl("rm -f /tmp/dial && mkfifo /tmp/dial && (sleep 100001 > /tmp/dial &) && "
                   f"exec {BENCH}/clusterd-bin --can none --dial-stdin --replay {BENCH}/drive.txt --config /dev/null "
                   f"--settings {WSL_WORK}/settings.conf --web {cd_dir}/web --livi-status /root/.config/LIVI/state/status.json "
                   f"--harness-udp 127.0.0.1:5005 < /tmp/dial > {WSL_WORK}/clusterd.log 2>&1", wait=False)
    time.sleep(4)
    if not wsl("pgrep -x clusterd-bin").strip() or not wsl("pgrep -x harness").strip():
        raise SystemExit("record: clusterd or the harness did not start")

    # Windows and WSL keep their own wall clocks: the harness names its frames with WSL's
    t0 = time.time()
    wsl_ms = int(wsl("date +%s%3N").strip())
    t1 = time.time()
    marks["wsl_minus_windows_ms"] = wsl_ms - int((t0 + t1) / 2 * 1000)
    print(f"record: WSL clock - Windows clock = {marks['wsl_minus_windows_ms']} ms (+/- {int((t1 - t0) * 500)} ms)", flush=True)

    stop = threading.Event()
    marks["start"] = time.time()
    rec = threading.Thread(target=record_centre, args=(stop, centre_dir), daemon=True)
    rec.start()
    gps_stop = threading.Event()
    relay = None
    try:
        time.sleep(1.5)
        caption("Our speedometer on the round centre", "Linux + LIVI on the centre screen; the four small gauges are the real firmware drawing code")
        time.sleep(8)
        caption("The dial: hold for Settings", "every setting lives on the centre screen")
        dial("h")
        time.sleep(1.5)
        caption("Gauge theme: turn the dial", "all five screens follow")
        dial("c")
        caption("CarPlay-inspired", "")      # each look's caption as its edit starts, so it never lags behind
        dial("d", 2.5)                       # Modern -> CarPlay-inspired
        dial("c")
        dial("h")
        time.sleep(6)
        caption("Factory: the 1966 Mustang speedometer", "")
        dial("hc")
        dial("d", 2.0)                       # -> Factory 1966
        dial("ch")
        time.sleep(6)
        caption("Classic: needles", "")
        dial("hc")
        dial("d", 2.0)                       # -> Classic
        dial("ch")
        time.sleep(6)
        caption("Modern", "")
        dial("hcdch")                        # back to Modern for the phone part
        time.sleep(3)

        caption("A phone connects: Android Auto", "the phone's real Android Auto, projected by LIVI (open source) inside the circle")
        adb("emu", "geo", "fix", f"{ROUTE[0][1]:.6f}", f"{ROUTE[0][0]:.6f}")
        gps = None
        t_wait = time.time()
        # adb's forward accepts a TCP connection before the phone's server is ready, and a session dropped early wedges
        # the server; so: let it settle, relay one session at a time, and on failure start a fresh server and retry.
        # The emulator runs the arm64 Android Auto through ARM translation, and its car process sometimes crashes
        # (SIGSEGV in gearhead:car) seconds after connecting; so a session counts once it has stayed up for 8 s.
        for attempt in range(4):
            log = wsl(f"cat {WSL_WORK}/livi.log")
            n_conn, n_over = log.count("session connected"), log.count("session over")
            start_head_unit_server()
            # Maps in the foreground first, so Android Auto opens on the map rather than wherever it was last (its app
            # grid, on some runs). Navigation starts once the session is up (see below).
            adb("shell", "am", "start", "-n", "com.google.android.apps.maps/com.google.android.maps.MapsActivity")
            time.sleep(5)
            relay = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                      os.path.join(REPO, "software", "linux", "aa-bench", "relay.ps1"), "-Once"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            ok = False
            for _ in range(25):
                if wsl(f"cat {WSL_WORK}/livi.log").count("session connected") > n_conn:
                    time.sleep(8)
                    ok = wsl(f"cat {WSL_WORK}/livi.log").count("session over") == n_over
                    break
                time.sleep(1)
            if ok:
                break
            print(f"record: Android Auto attempt {attempt + 1} did not stay up, retrying", flush=True)
            relay.kill()
        else:
            raise SystemExit("record: Android Auto did not connect")
        marks["phone"] = time.time()
        marks["cuts"] = [[t_wait + 3.0, marks["phone"] - 10.0]]     # waiting for a session that stays up
        gps = threading.Thread(target=gps_drive, args=(gps_stop,), daemon=True)
        gps.start()
        caption("Google Maps on the round centre", "the phone's Android Auto, laid out inside the circle")
        time.sleep(5)
        # Maps on the emulator often crashes once as navigation starts (SIGSEGV in its car map renderer, ARM
        # translation) and comes back by itself; the picture is black meanwhile. Wait for Android Auto's green
        # navigation banner, and cut the wait.
        t_nav = time.time()
        nav = ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "'google.navigation:q=Shoreline+Amphitheatre&mode=d'"]   # quoted: adb runs it through the phone's shell
        adb(*nav)                  # mode=d: driving (Maps picked walking on one run and never found a route)
        h = find_window("LIVI")
        for i in range(120):
            img = capture(h).astype(int)
            b, g, r = img[..., 0], img[..., 1], img[..., 2]
            if ((g > r + 40) & (g > b + 15) & (g > 70) & (g < 150)).mean() > 0.02:
                break
            if i == 60:
                adb(*nav)
            time.sleep(0.5)
        else:
            raise SystemExit("record: no navigation banner on the centre")
        if time.time() - t_nav > 4.0:
            marks["cuts"].append([t_nav + 1.0, time.time() - 1.0])
        caption("Google Maps navigation on the round centre", "speed moves back to the small gauges while the map is up")
        time.sleep(16)
        caption("Hold the dial 1.5 s: our speedometer, even with a phone", "")
        dial("m")
        time.sleep(3)
        caption("Back to the map", "a click on the speedometer")
        dial("c")
        time.sleep(6)
        marks["end"] = time.time()
    finally:
        stop.set()
        gps_stop.set()
        rec.join(5)
        if relay:
            relay.kill()
        json.dump({"timeline": timeline, "marks": marks, "harness_dir": f"\\\\wsl.localhost\\{DISTRO}{WSL_WORK}/hf".replace("/", "\\")},
                  open(os.path.join(WORK, "timeline.json"), "w"), indent=1)
        print(f"record: {marks.get('centre_frames')} centre frames; timeline in {WORK}", flush=True)
    del livi, harness, clusterd   # they keep running: the bench stays up for stills


if __name__ == "__main__":
    main()
