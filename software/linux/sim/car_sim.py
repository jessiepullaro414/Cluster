#!/usr/bin/env python3
"""The car, on a PC: a control panel that drives the cluster bench as if you were sitting in the 1966 Mustang.

  * the rotary dial (Piher PSC-360 + push button) -> SIMULATED GPIO: the files DIR/adc (raw 12-bit angle) and
    DIR/click (0/1) that clusterd reads with --sim-gpio DIR, exactly where the Verdin's ADC and gpio-keys would be
  * speed, rpm, fuel, coolant, oil, volts, the six lamps, headlights + dimmer, ignition -> the private CAN link,
    playing the gauges board: VehicleMotion, VehicleFluids, Indicators and PowerState, packed from the DBC with the
    rolling counter and CRC-8 (can_replay.PrivateEncoder), sent to clusterd's SIMULATED CAN bus (--can-udp PORT)
  * the phone -> Android Auto from the emulator, through software/linux/sim/phone.py on Windows

    python3 car_sim.py [--gpio /tmp/carsim] [--can-port 5101]

Started by start_car_sim.sh together with LIVI, clusterd and the small-gauge harness. Keys: Left/Right turn the dial,
Space is the dial's push button (hold it for a long press), I toggles the ignition.
"""
import argparse
import json
import math
import os
import socket
import struct
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "software", "tools"))
sys.path.insert(0, os.path.join(REPO, "protocol"))
import cantools  # noqa: E402
from can_replay import PrivateEncoder, periods  # noqa: E402

DETENTS = 12                       # clusterd-sim.conf dial_detents: one step per 30 degrees (one wheel notch)
WIN_PY = "/mnt/c/Users/root/AppData/Local/Python/bin/python.exe"
PHONE = os.path.join(HERE, "phone.py")

BG, PANEL, FG, DIM, ACCENT = "#121216", "#1c1c22", "#f2eee6", "#8c8c96", "#e0884a"


def win_path(p):
    """/mnt/c/Users/... -> C:\\Users\\... for Windows programs started from WSL."""
    return "C:" + p[len("/mnt/c"):].replace("/", "\\") if p.startswith("/mnt/c/") else p


class CarSim:
    def __init__(self, root, gpio_dir, can_port, page_port):
        self.root = root
        self.gpio_dir = gpio_dir
        os.makedirs(gpio_dir, exist_ok=True)
        self.dest = ("127.0.0.1", can_port)
        self.page_url = f"http://127.0.0.1:{page_port}/state"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        db = cantools.database.load_file(os.path.join(REPO, "protocol", "cluster_private.dbc"))
        self.enc = PrivateEncoder(db)
        self.period = periods(db, "gauges")
        self.last_sent = {}
        self.angle = 0.0
        self.click = False
        self.phone_proc = None
        self.suspend_at = None
        self.write_gpio()

        root.title("Car (cluster bench): dial, pedals and switches")
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
        style.configure("TLabelframe", background=BG, foreground=ACCENT)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("DejaVu Sans", 10, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TButton", background=PANEL, foreground=FG)
        style.configure("Horizontal.TScale", background=BG)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, padx=12, pady=12, sticky="n")
        mid = ttk.Frame(root)
        mid.grid(row=0, column=1, padx=12, pady=12, sticky="n")
        right = ttk.Frame(root)
        right.grid(row=0, column=2, padx=12, pady=12, sticky="n")

        # ---- the dial
        dial = ttk.LabelFrame(left, text="Dial (simulated GPIO)")
        dial.pack(fill="x")
        self.cv = tk.Canvas(dial, width=240, height=240, bg=BG, highlightthickness=0)
        self.cv.pack(padx=8, pady=8)
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<MouseWheel>", lambda e: self.turn(1 if e.delta > 0 else -1))
        self.cv.bind("<Button-4>", lambda e: self.turn(1))
        self.cv.bind("<Button-5>", lambda e: self.turn(-1))
        ttk.Label(dial, text="drag the rim or scroll to turn; press the centre\n(hold 0.6 s: long press, 1.5 s with a phone: settings)",
                  foreground=DIM, justify="center").pack(pady=(0, 6))
        self.dial_label = ttk.Label(dial, text="", foreground=DIM)
        self.dial_label.pack(pady=(0, 6))
        self.draw_dial()

        # ---- ignition and phone
        key = ttk.LabelFrame(left, text="Ignition and phone")
        key.pack(fill="x", pady=(12, 0))
        self.ign = tk.BooleanVar(value=True)
        ttk.Checkbutton(key, text="Ignition ON  (I)", variable=self.ign, command=self.ignition_changed).pack(anchor="w", padx=8, pady=4)
        self.ign_label = ttk.Label(key, text="", foreground=DIM)
        self.ign_label.pack(anchor="w", padx=8)
        row = ttk.Frame(key)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Button(row, text="Connect Android Auto", command=lambda: self.phone("connect")).pack(side="left")
        ttk.Button(row, text="Disconnect", command=lambda: self.phone("disconnect")).pack(side="left", padx=6)
        self.phone_label = ttk.Label(key, text="", foreground=DIM, wraplength=250)
        self.phone_label.pack(anchor="w", padx=8, pady=(0, 6))

        # ---- driving and fluids
        drive = ttk.LabelFrame(mid, text="Driving")
        drive.pack(fill="x")
        self.speed = self.slider(drive, "Speed", 0, 200, 0, lambda v: f"{v:.0f} km/h  ({v / 1.609:.0f} mph)")
        self.rpm = self.slider(drive, "RPM", 0, 7000, 800, lambda v: f"{v:.0f} rpm")
        self.auto_rpm = tk.BooleanVar(value=True)
        ttk.Checkbutton(drive, text="RPM follows speed (3-speed auto feel)", variable=self.auto_rpm).pack(anchor="w", padx=8, pady=(0, 6))
        fluids = ttk.LabelFrame(mid, text="Senders")
        fluids.pack(fill="x", pady=(12, 0))
        self.fuel = self.slider(fluids, "Fuel", 0, 100, 68, lambda v: f"{v:.0f} %")
        self.cool = self.slider(fluids, "Coolant", 20, 130, 88, lambda v: f"{v:.0f} °C  ({v * 9 / 5 + 32:.0f} °F)")
        self.oil = self.slider(fluids, "Oil pressure", 0, 700, 300, lambda v: f"{v:.0f} kPa  ({v * 0.145:.0f} psi)")
        self.batt = self.slider(fluids, "Battery", 10, 15.5, 13.8, lambda v: f"{v:.1f} V")
        self.link = tk.BooleanVar(value=True)
        ttk.Checkbutton(fluids, text="Gauges board connected (untick: link lost)", variable=self.link).pack(anchor="w", padx=8, pady=(4, 6))

        # ---- lamps and lights
        lamps = ttk.LabelFrame(right, text="Lamps (12 V inputs on the gauges board)")
        lamps.pack(fill="x")
        self.lamp = {}
        for name, label in (("tl", "Left turn"), ("tr", "Right turn"), ("haz", "Hazards"), ("hb", "High beam"),
                            ("brake", "Brake warning"), ("alt", "Alternator warning"), ("oilw", "Oil warning")):
            self.lamp[name] = tk.BooleanVar(value=False)
            ttk.Checkbutton(lamps, text=label, variable=self.lamp[name]).pack(anchor="w", padx=8, pady=1)
        lights = ttk.LabelFrame(right, text="Headlights")
        lights.pack(fill="x", pady=(12, 0))
        self.head = tk.BooleanVar(value=False)
        ttk.Checkbutton(lights, text="Headlights on (night palette)", variable=self.head).pack(anchor="w", padx=8, pady=4)
        self.dimmer = self.slider(lights, "Dash dimmer", 0, 100, 70, lambda v: f"{v:.0f} %")

        # ---- what the cluster is doing
        status = ttk.LabelFrame(right, text="Centre screen (clusterd)")
        status.pack(fill="x", pady=(12, 0))
        self.status = ttk.Label(status, text="waiting for clusterd...", foreground=DIM, wraplength=280, justify="left")
        self.status.pack(anchor="w", padx=8, pady=6)

        root.bind("<Left>", lambda e: self.turn(-1))
        root.bind("<Right>", lambda e: self.turn(1))
        root.bind("<KeyPress-space>", lambda e: self.set_click(True))
        root.bind("<KeyRelease-space>", lambda e: self.set_click(False))
        root.bind("<KeyPress-i>", lambda e: (self.ign.set(not self.ign.get()), self.ignition_changed()))
        self.t0 = time.time()
        self.tick()
        self.poll_status()

    # ---- widgets
    def slider(self, parent, name, lo, hi, init, fmt):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=8, pady=3)
        var = tk.DoubleVar(value=init)
        lab = ttk.Label(f, text="", width=26)
        ttk.Label(f, text=name, width=12).pack(side="left")
        ttk.Scale(f, from_=lo, to=hi, variable=var, length=220, command=lambda v: lab.config(text=fmt(float(v)))).pack(side="left")
        lab.pack(side="left", padx=6)
        lab.config(text=fmt(init))
        return var

    # ---- the dial: simulated ADC and button
    def write_gpio(self):
        raw = int(self.angle % 360.0 / 360.0 * 4096) % 4096
        for name, val in (("adc", str(raw)), ("click", "1" if self.click else "0")):
            tmp = os.path.join(self.gpio_dir, name + ".tmp")
            with open(tmp, "w") as f:
                f.write(val + "\n")
            os.replace(tmp, os.path.join(self.gpio_dir, name))

    def draw_dial(self):
        c, r = 120, 100
        self.cv.delete("all")
        self.cv.create_oval(c - r, c - r, c + r, c + r, fill="#2a2a31", outline="#55555f", width=3)
        for i in range(DETENTS):
            a = math.radians(i * 360 / DETENTS)
            self.cv.create_line(c + math.sin(a) * (r - 4), c - math.cos(a) * (r - 4), c + math.sin(a) * (r - 14),
                                c - math.cos(a) * (r - 14), fill="#44444c", width=2)
        a = math.radians(self.angle)
        self.cv.create_oval(c + math.sin(a) * (r - 26) - 8, c - math.cos(a) * (r - 26) - 8, c + math.sin(a) * (r - 26) + 8,
                            c - math.cos(a) * (r - 26) + 8, fill=ACCENT, outline="")
        self.cv.create_oval(c - 40, c - 40, c + 40, c + 40, fill="#e0884a" if self.click else "#3a3a42", outline="#66666f", width=2)
        self.cv.create_text(c, c, text="PUSH", fill=FG, font=("DejaVu Sans", 10, "bold"))
        self.dial_label.config(text=f"angle {self.angle % 360:5.1f}°   adc {int(self.angle % 360 / 360 * 4096) % 4096:4d}   click {int(self.click)}")

    def turn(self, steps):
        self.angle += steps * 360.0 / DETENTS
        self.write_gpio()
        self.draw_dial()

    def set_click(self, down):
        if down != self.click:
            self.click = down
            self.write_gpio()
            self.draw_dial()

    def on_press(self, e):
        if math.hypot(e.x - 120, e.y - 120) <= 40:
            self.set_click(True)
            self.drag = None
        else:
            self.drag = math.degrees(math.atan2(e.x - 120, -(e.y - 120)))

    def on_drag(self, e):
        if self.drag is None:
            return
        a = math.degrees(math.atan2(e.x - 120, -(e.y - 120)))
        d = (a - self.drag + 540) % 360 - 180
        self.drag = a
        self.angle += d
        self.write_gpio()
        self.draw_dial()

    def on_release(self, e):
        self.set_click(False)
        self.drag = None

    # ---- the car
    def ignition_changed(self):
        if self.ign.get():
            self.suspend_at = None
        else:
            self.suspend_at = time.time() + 5.0      # gauges/ announces the suspend 5 s ahead

    def phone(self, what):
        if not os.path.exists(WIN_PY):
            self.phone_label.config(text=f"no Windows Python at {WIN_PY}")
            return
        if self.phone_proc and self.phone_proc.poll() is None:
            self.phone_proc.kill()
        self.phone_proc = subprocess.Popen([WIN_PY, win_path(PHONE), what], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.phone_label.config(text=f"phone: {what}...")

    def state(self):
        t = time.time() - self.t0
        v = self.speed.get()
        if self.auto_rpm.get():
            gear = 1 if v < 35 else 2 if v < 75 else 3
            ratio = {1: 95.0, 2: 55.0, 3: 35.0}[gear]
            self.rpm.set(max(700.0, min(6800.0, 750 + v * ratio + 30 * math.sin(t * 7))))
        blink = int(t * 3) % 2 == 0                  # 1.5 Hz flasher
        haz = self.lamp["haz"].get()
        return dict(speed=v, rpm=self.rpm.get(), batt=self.batt.get(), fuel=self.fuel.get(), cool=self.cool.get(),
                    oil=self.oil.get(), tl=(self.lamp["tl"].get() or haz) and blink,
                    tr=(self.lamp["tr"].get() or haz) and blink, hb=self.lamp["hb"].get(), brake=self.lamp["brake"].get(),
                    alt=self.lamp["alt"].get(), oilw=self.lamp["oilw"].get(), dash=self.head.get(), dim=self.dimmer.get())

    def frames(self, s):
        ign = self.ign.get()
        left = 0 if self.suspend_at is None else max(0, int(math.ceil(self.suspend_at - time.time())))
        return {
            "VehicleMotion": dict(SpeedKph=s["speed"], Rpm=s["rpm"] if ign else 0, BatteryV=s["batt"], SpeedValid=1,
                                  RpmValid=1, BatteryValid=1, SpeedFromHall=1),
            "VehicleFluids": dict(FuelPct=s["fuel"], CoolantC=s["cool"], OilKpa=s["oil"] if ign else 0,
                                  FuelValid=1, CoolantValid=1, OilValid=1),
            "Indicators": dict(TurnLeft=int(s["tl"]), TurnRight=int(s["tr"]), HighBeam=int(s["hb"]), BrakeWarning=int(s["brake"]),
                               AlternatorWarning=int(s["alt"]), OilWarning=int(s["oilw"]), DashLightsOn=int(s["dash"]),
                               DashDimmerPct=s["dim"] if s["dash"] else 0),
            "PowerState": dict(IgnitionOn=int(ign), SuspendRequest=int(not ign), SuspendInSeconds=left),
        }

    def tick(self):
        now = time.time()
        if self.link.get():
            s = self.state()
            for name, vals in self.frames(s).items():
                if now - self.last_sent.get(name, 0) >= self.period.get(name, 0.1):
                    self.last_sent[name] = now
                    _, fid, data = self.enc.frame(name, vals)
                    self.sock.sendto(struct.pack("<IB", fid, len(data)) + bytes(data).ljust(8, b"\0"), self.dest)
        if self.ign.get():
            self.ign_label.config(text="engine running")
        elif self.suspend_at is not None:
            left = self.suspend_at - now
            self.ign_label.config(text=f"key off: centre suspends in {left:.0f} s" if left > 0 else "key off: centre told to suspend")
        if self.phone_proc and self.phone_proc.poll() is not None:
            out = (self.phone_proc.stdout.read() or "").strip().splitlines()
            self.phone_label.config(text="phone: " + (out[-1] if out else "done"))
            self.phone_proc = None
        self.root.after(20, self.tick)

    def poll_status(self):
        try:
            with urllib.request.urlopen(self.page_url, timeout=0.3) as r:
                st = json.load(r)
            themes = ["Classic", "Modern", "CarPlay-inspired", "Factory"]
            phone = {"cp": "CarPlay", "aa": "Android Auto"}.get(st.get("phone"), "no phone")
            text = (f"showing: {st['view']}   ({phone})\n"
                    f"small gauges' look: {themes[st['theme']] if 0 <= st['theme'] < 4 else st['theme']}\n"
                    f"units: {'mph' if st['imperial'] else 'km/h'}   link from gauges board: {'yes' if st['veh']['link'] else 'NO'}")
            if st["view"] == "settings":
                row = st["rows"][st["row"]]
                text += f"\nsettings: {row[0]} = {row[1]}{'  (editing)' if st['editing'] else ''}"
            self.status.config(text=text)
        except Exception as e:  # noqa: BLE001 - clusterd starting or restarting
            self.status.config(text=f"clusterd not answering ({type(e).__name__})")
        self.root.after(300, self.poll_status)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gpio", default="/tmp/carsim")
    ap.add_argument("--can-port", type=int, default=5101)
    ap.add_argument("--page-port", type=int, default=4010)
    a = ap.parse_args()
    root = tk.Tk()
    CarSim(root, a.gpio, a.can_port, a.page_port)
    root.mainloop()


if __name__ == "__main__":
    main()
