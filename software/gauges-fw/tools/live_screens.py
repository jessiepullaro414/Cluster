#!/usr/bin/env python3
"""Show the four small screens live, driven by data from the Android app.

  Android emulator --UDP 10.0.2.2:5005--> this script --stdin--> screens_live (C, in WSL)
                                                       <--frames-- (the same code the firmware runs,
                                                                    into a mock GC9A01 panel)
  browser  <--HTTP-- this script (page + frames)

The data direction is a development convenience: in the car the gauges board is the source and
Android only reads. Standard library only. Run it on Windows:

  python tools/live_screens.py            # then open http://localhost:8765 and start the Android app
  python tools/live_screens.py --demo     # no Android: feed a built-in drive instead
  python tools/live_screens.py --build    # (re)build screens_live in WSL first

If no data arrives for one second the C program shows dashes, exactly as the firmware would.
"""
import argparse
import json
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
FRAME_BYTES = 4 * 240 * 240 * 2
HEADER = struct.Struct("<4s8I")          # "CLF1" + 8 x uint32 stats

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Small screens live</title>
<style>
  :root { --bg:#101216; --fg:#e8eaed; --dim:#8a95a3; --ok:#3ddc84; --bad:#ffb000; }
  body { margin:0; padding:16px; background:var(--bg); color:var(--fg); font:14px system-ui, sans-serif; }
  h1 { font-size:16px; margin:0 0 4px; font-weight:600; }
  p.sub { margin:0 0 14px; color:var(--dim); }
  .row { display:flex; gap:14px; flex-wrap:nowrap; justify-content:center; padding:6px; }
  figure { margin:0; text-align:center; }
  canvas { width:min(calc((100vw - 32px - 3 * 14px - 4 * 12px) / 4), 300px); aspect-ratio:1; height:auto; border-radius:50%; background:#000; box-shadow:0 0 0 6px #1b1f26; }
  figcaption { margin-top:10px; color:var(--dim); font-size:12px; }
  .stats { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:8px 20px; }
  .stats div { display:flex; justify-content:space-between; border-bottom:1px solid #20242c; padding:3px 0; }
  .stats b { font-variant-numeric:tabular-nums; }
  .live { color:var(--ok); } .dead { color:var(--bad); }
</style></head><body>
<h1>The four small screens, rendered by the firmware code</h1>
<p class="sub">Left to right on the board: fuel + volts, speed, rpm, coolant + oil. Data: the Android app. Pixels: the C renderer through a mock GC9A01 panel.</p>
<div class="row" id="row"></div>
<div class="stats" id="stats"></div>
<script>
const names = ["outer left: fuel + volts","inner left: speed","inner right: rpm","outer right: coolant + oil"];
const row = document.getElementById("row"), cv = [], ctx = [], img = [];
for (let i = 0; i < 4; i++) {
  const f = document.createElement("figure"), c = document.createElement("canvas");
  c.width = 240; c.height = 240; f.appendChild(c);
  const cap = document.createElement("figcaption"); cap.textContent = names[i]; f.appendChild(cap);
  row.appendChild(f); cv.push(c); ctx.push(c.getContext("2d")); img.push(ctx[i].createImageData(240, 240));
}
const st = document.getElementById("stats");
let frames = 0, t0 = performance.now(), fps = 0;
// RGB565 -> RGBA lookup, built once: the per-pixel work is then one array read and one write.
const lut = new Uint32Array(65536);
for (let p = 0; p < 65536; p++) {
  const r = Math.round(((p >> 11) & 31) * 255 / 31), g = Math.round(((p >> 5) & 63) * 255 / 63), b = Math.round((p & 31) * 255 / 31);
  lut[p] = (255 << 24) | (b << 16) | (g << 8) | r;          // little-endian RGBA
}
const out32 = img.map(im => new Uint32Array(im.data.buffer));
function draw(buf) {
  const w = new Uint16Array(buf);
  for (let s = 0; s < 4; s++) {
    const d = out32[s], o = s * 57600;
    for (let i = 0; i < 57600; i++) d[i] = lut[w[o + i]];
    ctx[s].putImageData(img[s], 0, 0);
  }
}
function row2(k, v, cls) { return `<div><span>${k}</span><b class="${cls||''}">${v}</b></div>`; }
async function tick() {
  try {
    const r = await fetch("/frame", {cache:"no-store"});
    const s = JSON.parse(r.headers.get("X-Stats"));
    draw(await r.arrayBuffer());
    frames++;
    const now = performance.now();
    if (now - t0 > 1000) { fps = frames * 1000 / (now - t0); frames = 0; t0 = now; }
    st.innerHTML =
      row2("Android feed", s.alive ? "live" : (s.rx_lines ? "lost (dashes shown)" : "waiting for data"), s.alive ? "live" : "dead") +
      row2("datagrams / s", s.rx_per_s.toFixed(1)) +
      row2("last data", s.rx_lines ? s.age_ms + " ms ago" : "never") +
      row2("panel bus (9.6 MHz)", s.bus_pct.toFixed(1) + " %") +
      row2("bytes to panels / s", Math.round(s.bytes_per_s).toLocaleString()) +
      row2("tiles waiting", s.pending_tiles) +
      row2("page frames / s", fps.toFixed(0)) +
      row2("firmware ticks", s.ticks.toLocaleString());
  } catch (e) {
    st.innerHTML = row2("bridge", "not reachable", "dead");
  }
  setTimeout(tick, 40);
}
tick();
</script></body></html>
"""


def wsl_path(win_path):
    p = os.path.abspath(win_path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/mnt/" + p[0].lower() + p[2:]
    return p


class Bridge:
    def __init__(self, distro):
        self.lock = threading.Lock()
        self.frame = bytes(FRAME_BYTES)
        self.stats = dict(bytes_total=0, runs=0, pending_tiles=0, rx_lines=0, alive=0, age_ms=0, ticks=0)
        self.rx_times = []
        self.byte_samples = []
        exe = wsl_path(os.path.join(FW, "build", "screens_live"))
        self.proc = subprocess.Popen(["wsl.exe", "-d", distro, "--", exe], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, bufsize=0)
        threading.Thread(target=self._read_frames, daemon=True).start()

    def feed(self, line):
        try:
            self.proc.stdin.write(line.encode("ascii", "replace") + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        now = time.monotonic()
        with self.lock:
            self.rx_times.append(now)
            self.rx_times = [t for t in self.rx_times if now - t < 2.0]

    def _read_exact(self, n):
        out = bytearray()
        while len(out) < n:
            chunk = self.proc.stdout.read(n - len(out))
            if not chunk:
                raise EOFError
            out += chunk
        return bytes(out)

    def _read_frames(self):
        try:
            while True:
                magic, blo, bhi, runs, pend, rx, alive, age, ticks = HEADER.unpack(self._read_exact(HEADER.size))
                if magic != b"CLF1":
                    raise ValueError("bad frame magic %r" % magic)
                data = self._read_exact(FRAME_BYTES)
                now = time.monotonic()
                total = blo | (bhi << 32)
                with self.lock:
                    self.frame = data
                    self.stats = dict(bytes_total=total, runs=runs, pending_tiles=pend, rx_lines=rx,
                                      alive=alive, age_ms=age, ticks=ticks)
                    self.byte_samples.append((now, total))
                    self.byte_samples = [s for s in self.byte_samples if now - s[0] < 2.0]
        except (EOFError, ValueError) as e:
            print("screens_live stopped:", e, file=sys.stderr)
            os._exit(1)

    def snapshot(self):
        with self.lock:
            s = dict(self.stats)
            bs = list(self.byte_samples)
            rx = list(self.rx_times)
            frame = self.frame
        bps = 0.0
        if len(bs) >= 2 and bs[-1][0] > bs[0][0]:
            bps = (bs[-1][1] - bs[0][1]) / (bs[-1][0] - bs[0][0])
        now = time.monotonic()
        recent = [t for t in rx if now - t < 1.0]
        s["bytes_per_s"] = bps
        s["bus_pct"] = 100.0 * bps * 8.0 / 9.6e6
        s["rx_per_s"] = float(len(recent))
        return frame, s


def udp_loop(bridge, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    while True:
        data, _ = sock.recvfrom(2048)
        try:
            bridge.feed(data.decode("ascii").strip())
        except UnicodeDecodeError:
            pass


def demo_loop(bridge):
    """The 30 s drive of DriveScenario, so the viewer can be tried without the emulator."""
    t0 = time.monotonic()
    while True:
        t = (time.monotonic() - t0) % 30.0
        kph = 0.0 if t < 3 else 90.0 * (t - 3) / 10 if t < 13 else 90.0 if t < 23 else 90.0 * (30 - t) / 7
        rpm = 800 + kph * 28 + 40 * math.sin(t * 6)
        line = "CL1 imperial=1 speed=%.2f rpm=%.0f batt=%.2f fuel=%.1f cool=%.1f oil=%.1f" % (
            kph, rpm, 13.8 if t > 1 else 12.4, 68 - 0.02 * t, min(92.0, 40 + 2 * t), min(380.0, 150 + rpm * 0.08))
        bridge.feed(line)
        time.sleep(0.05)


class Handler(BaseHTTPRequestHandler):
    bridge = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif self.path.startswith("/frame"):
            body, stats = self.bridge.snapshot()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("X-Stats", json.dumps(stats))
            self.send_header("Access-Control-Expose-Headers", "X-Stats")
        elif self.path.startswith("/stats"):
            _, stats = self.bridge.snapshot()
            body = json.dumps(stats).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            self.send_error(404)
            return
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--distro", default="Ubuntu-22.04")
    ap.add_argument("--demo", action="store_true", help="feed a built-in drive instead of waiting for Android")
    ap.add_argument("--build", action="store_true", help="build screens_live in WSL first")
    a = ap.parse_args()

    if a.build:
        subprocess.check_call(["wsl.exe", "-d", a.distro, "--", "make", "-C", wsl_path(FW), "live"])
    if not os.path.exists(os.path.join(FW, "build", "screens_live")):
        sys.exit("build/screens_live is missing: run with --build")

    bridge = Bridge(a.distro)
    Handler.bridge = bridge
    threading.Thread(target=udp_loop, args=(bridge, a.udp_port), daemon=True).start()
    if a.demo:
        threading.Thread(target=demo_loop, args=(bridge,), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.http_port), Handler)
    print("screens: http://localhost:%d   (Android sends UDP to 10.0.2.2:%d)%s" %
          (a.http_port, a.udp_port, "   [demo feed]" if a.demo else ""), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
