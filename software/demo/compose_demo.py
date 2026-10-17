#!/usr/bin/env python3
"""Compose the demo video frames from what record_demo.py captured: the emulator recording (the Android centre gauge) and the harness
panel dumps (the four small gauges), laid out like the dash (two small gauges, the centre gauge, two small gauges) with captions,
plus a title card and an end card. Writes numbered JPEGs; encode_demo.mjs turns them into an H.264 MP4 with the browser's encoder.

    python software/demo/compose_demo.py workdir [outdir]
"""
import bisect
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
PAD = 12
BG = (14, 14, 17)
FONT_DIR = r"C:\Windows\Fonts"


def font(name, size):
    for n in (name, "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, n), size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font("segoeuib.ttf", 46)
F_SUB = font("segoeui.ttf", 32)
F_SMALL = font("segoeui.ttf", 22)
F_BIG = font("segoeuib.ttf", 84)
F_MED = font("segoeui.ttf", 38)
F_TAG = font("consolab.ttf", 24)


def circle_mask(d, ss=4):
    m = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    return m.resize((d, d), Image.LANCZOS)


CENTER_D, SMALL_D = 640, 250
CENTER_XY = (W // 2, 440)
SMALL_X = [CENTER_XY[0] - 765, CENTER_XY[0] - 485, CENTER_XY[0] + 485, CENTER_XY[0] + 765]
SMALL_Y = 440
MASK_C, MASK_S = circle_mask(CENTER_D), circle_mask(SMALL_D)


def make_background():
    bg = np.zeros((H, W, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - 430) / (H * 0.75)) ** 2)
    v = np.clip(1.0 - r * 0.55, 0.25, 1.0)
    for c in range(3):
        bg[:, :, c] = BG[c] * 1.5 * v
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    # a faceplate band behind the five gauges, and a bezel ring around each
    d.rounded_rectangle((70, 440 - 190, W - 70, 440 + 190), radius=40, fill=(10, 10, 12), outline=(38, 38, 44), width=3)
    for (cx, cy, dia) in [(CENTER_XY[0], CENTER_XY[1], CENTER_D)] + [(x, SMALL_Y, SMALL_D) for x in SMALL_X]:
        for k, col in ((22, (30, 30, 34)), (14, (58, 58, 66)), (6, (22, 22, 25))):
            d.ellipse((cx - dia // 2 - k, cy - dia // 2 - k, cx + dia // 2 + k, cy + dia // 2 + k), fill=col)
    d.text((70, 36), "JESSIE'S CARS", font=F_TAG, fill=(224, 136, 74))
    d.text((70, 72), "1966 Mustang digital instrument cluster", font=F_SMALL, fill=(200, 192, 180))
    d.text((CENTER_XY[0], 440 + CENTER_D // 2 + 30), "centre gauge: Android Automotive app (emulator)", font=F_SMALL, fill=(150, 150, 160), anchor="ma")
    d.text(((SMALL_X[0] + SMALL_X[1]) // 2, SMALL_Y + SMALL_D // 2 + 30), "small gauges: S32K144 firmware drawing code", font=F_SMALL, fill=(150, 150, 160), anchor="ma")
    d.text(((SMALL_X[2] + SMALL_X[3]) // 2, SMALL_Y + SMALL_D // 2 + 30), "(simulated panels, same code as the board)", font=F_SMALL, fill=(150, 150, 160), anchor="ma")
    return im


def caption_layer(title, sub):
    im = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if title:
        d.rounded_rectangle((260, 20, W - 260, 230), radius=28, fill=(10, 10, 12, 215), outline=(60, 60, 68, 255), width=2)
        d.text((W // 2, 62), title, font=F_TITLE, fill=(250, 244, 232), anchor="mm")
        d.text((W // 2, 150), sub, font=F_SUB, fill=(224, 136, 74), anchor="mm")
    return im


def card(title, sub, note=""):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 330), "JESSIE'S CARS", font=F_TAG, fill=(224, 136, 74), anchor="mm")
    d.text((W // 2, 450), title, font=F_BIG, fill=(250, 244, 232), anchor="mm")
    d.text((W // 2, 570), sub, font=F_MED, fill=(205, 191, 169), anchor="mm")
    if note:
        for i, line in enumerate(note.split("\n")):
            d.text((W // 2, 760 + i * 36), line, font=F_SMALL, fill=(150, 150, 160), anchor="mm")
    return im


def read_ppm(path):
    with open(path, "rb") as f:
        assert f.readline().strip() == b"P6"
        w, h = map(int, f.readline().split())
        f.readline()
        return np.frombuffer(f.read(w * h * 3), np.uint8).reshape(h, w, 3)


def small_gray(img):
    return cv2.cvtColor(cv2.resize(img, (96, 96), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.int16)


def main():
    work = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(work, "out_frames")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    tl = json.load(open(os.path.join(work, "timeline.json")))
    marks, events = tl["marks"], tl["timeline"]

    # ---- the harness frames: epoch milliseconds in the file names
    hdir = os.path.join(work, "harness_frames")
    hnames = sorted(os.listdir(hdir), key=lambda n: int(n.split(".")[0]))
    hts = [int(n.split(".")[0]) / 1000.0 for n in hnames]
    print("harness frames", len(hnames), f"{hts[0]:.2f}..{hts[-1]:.2f}")

    # ---- the emulator video: presentation time of every frame, and where the big change (map to speedometer) happens
    cap = cv2.VideoCapture(os.path.join(work, "emulator.mp4"))
    pts, prev, big = [], None, []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        g = small_gray(fr)
        if prev is not None and np.mean(np.abs(g - prev) > 25) > 0.12:
            big.append(len(pts))
        prev = g
        pts.append(t)
    cap.release()
    print("emulator frames", len(pts), f"{pts[0]:.2f}..{pts[-1]:.2f}", "big changes at", [round(pts[i], 2) for i in big[:8]])
    sync = marks["sync"]
    # the same event in the harness: the first frame after the sync broadcast in which a panel changes by more than needle motion does
    prev, hflip = None, None
    for n, t in zip(hnames, hts):
        if t < sync - 0.5:
            continue
        img = read_ppm(os.path.join(hdir, n))
        g = [small_gray(cv2.cvtColor(np.ascontiguousarray(img[PAD:PAD + 240, PAD + s * 252:PAD + s * 252 + 240]), cv2.COLOR_RGB2BGR)) for s in range(4)]
        if prev is not None and t > sync and max(float(np.mean(np.abs(a - b) > 25)) for a, b in zip(g, prev)) > 0.06:
            hflip = t
            break
        prev = g
    if hflip is None:
        raise SystemExit("compose: the layout change after the sync broadcast was not found in the harness frames")
    # the emulator change closest after the sync broadcast
    e_flip = next(pts[i] for i in big if pts[i] > 1.0)
    print(f"flip: emulator video {e_flip:.2f} s, harness wall {hflip}, broadcast issued at {sync:.2f}")
    emu_wall0 = hflip - e_flip                        # wall time of emulator video time 0
    t_start, t_end = emu_wall0 + 0.2, marks["end"] + 0.5
    nframes = int((t_end - t_start) * FPS)
    emu_wall = [emu_wall0 + p for p in pts]

    bg = make_background()
    cap = cv2.VideoCapture(os.path.join(work, "emulator.mp4"))
    ev_t = [e["t"] + 0.25 for e in events]
    layers = {}
    cur_emu, emu_i = None, -1
    cur_h, h_i = None, -1
    cards = (card("Cluster", "a digital instrument cluster for a 1966 Mustang", "an Android centre gauge and four small gauges, on one CAN bus"),
             card("Cluster", "Android Automotive app + S32K144 firmware", "Prototype: the boards are designed but not built.\nThe app runs in an emulator; the small gauges are the real firmware drawing code on a simulated panel."))
    k = 0
    intro_n, outro_n = int(3.5 * FPS), int(5.0 * FPS)
    fade = int(0.5 * FPS)

    def save(img):
        nonlocal k
        img.save(os.path.join(out, f"{k:06d}.jpg"), quality=92)
        k += 1

    for i in range(intro_n):
        a = min(1.0, i / fade)
        save(Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), cards[0], a))

    prev_frame = None
    for f in range(nframes):
        t = t_start + f / FPS
        # advance to the newest emulator frame at or before t
        j = bisect.bisect_right(emu_wall, t) - 1
        while emu_i < j:
            ok, fr = cap.read()
            if not ok:
                break
            emu_i += 1
            cur_emu = fr
        h = max(0, bisect.bisect_right(hts, t) - 1)
        if h != h_i:
            cur_h = read_ppm(os.path.join(hdir, hnames[h]))
            h_i = h
        frame = bg.copy()
        if cur_emu is not None:
            em = Image.fromarray(cv2.cvtColor(cur_emu, cv2.COLOR_BGR2RGB)).resize((CENTER_D, CENTER_D), Image.LANCZOS)
            frame.paste(em, (CENTER_XY[0] - CENTER_D // 2, CENTER_XY[1] - CENTER_D // 2), MASK_C)
        for s in range(4):
            x0 = PAD + s * 252
            panel = Image.fromarray(np.ascontiguousarray(cur_h[PAD:PAD + 240, x0:x0 + 240])).resize((SMALL_D, SMALL_D), Image.LANCZOS)
            frame.paste(panel, (SMALL_X[s] - SMALL_D // 2, SMALL_Y - SMALL_D // 2), MASK_S)
        e = bisect.bisect_right(ev_t, t) - 1
        if e >= 0 and events[e]["title"]:
            key = (events[e]["title"], events[e]["sub"])
            if key not in layers:
                layers[key] = caption_layer(*key)
            frame.paste(layers[key], (0, H - 250), layers[key])
        save(frame)
        prev_frame = frame
        if f % 300 == 0:
            print(f"  {f}/{nframes}")

    for i in range(outro_n):
        a = min(1.0, i / fade)
        save(Image.blend(prev_frame, cards[1], a) if i < fade else cards[1])
    print(f"{k} frames = {k / FPS:.1f} s in {out}")


if __name__ == "__main__":
    main()
