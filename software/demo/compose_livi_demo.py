#!/usr/bin/env python3
"""Compose the Linux-option demo video frames from what record_livi_demo.py captured: LIVI's window (the round centre: our
speedometer, the settings, real Android Auto) and the harness panel dumps (the four small gauges), laid out like the dash with
captions, a title card and an end card. Same look as compose_demo.py, whose helpers it uses. Writes numbered JPEGs for
encode_demo.mjs.

    py software/demo/compose_livi_demo.py workdir [outdir]
"""
import bisect
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compose_demo import (BG, CENTER_D, CENTER_XY, F_SMALL, F_TAG, FPS, H, MASK_C, MASK_S, PAD, SMALL_D,  # noqa: E402
                          SMALL_X, SMALL_Y, W, caption_layer, card, read_ppm)

# LIVI's window as PrintWindow returns it: a 32 px title strip, then the 720 px page drawn 752 px wide at this display scale.
CROP = (0, 32, 752, 784)


def background():
    bg = np.zeros((H, W, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - 430) / (H * 0.75)) ** 2)
    v = np.clip(1.0 - r * 0.55, 0.25, 1.0)
    for c in range(3):
        bg[:, :, c] = BG[c] * 1.5 * v
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((70, 440 - 190, W - 70, 440 + 190), radius=40, fill=(10, 10, 12), outline=(38, 38, 44), width=3)
    for (cx, cy, dia) in [(CENTER_XY[0], CENTER_XY[1], CENTER_D)] + [(x, SMALL_Y, SMALL_D) for x in SMALL_X]:
        for k, col in ((22, (30, 30, 34)), (14, (58, 58, 66)), (6, (22, 22, 25))):
            d.ellipse((cx - dia // 2 - k, cy - dia // 2 - k, cx + dia // 2 + k, cy + dia // 2 + k), fill=col)
    d.text((70, 36), "JESSIE'S CARS", font=F_TAG, fill=(224, 136, 74))
    d.text((70, 72), "1966 Mustang digital instrument cluster", font=F_SMALL, fill=(200, 192, 180))
    d.text((CENTER_XY[0], 440 + CENTER_D // 2 + 30), "centre: Linux + LIVI, round 720 px screen (on a PC)", font=F_SMALL,
           fill=(150, 150, 160), anchor="ma")
    d.text(((SMALL_X[0] + SMALL_X[1]) // 2, SMALL_Y + SMALL_D // 2 + 30), "small gauges: S32K144 firmware drawing code",
           font=F_SMALL, fill=(150, 150, 160), anchor="ma")
    d.text(((SMALL_X[2] + SMALL_X[3]) // 2, SMALL_Y + SMALL_D // 2 + 30), "(simulated panels, same code as the board)",
           font=F_SMALL, fill=(150, 150, 160), anchor="ma")
    return im


def main():
    work = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(work, "out_frames")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    tl = json.load(open(os.path.join(work, "timeline.json")))
    marks, events = tl["marks"], tl["timeline"]
    offset = marks["wsl_minus_windows_ms"] / 1000.0

    cdir = os.path.join(work, "centre")
    cnames = sorted(os.listdir(cdir), key=lambda n: int(n.split(".")[0]))
    cts = [int(n.split(".")[0]) / 1000.0 for n in cnames]
    hdir = tl["harness_dir"]
    hnames = sorted((n for n in os.listdir(hdir) if n.endswith(".ppm")), key=lambda n: int(n.split(".")[0]))
    hts = [int(n.split(".")[0]) / 1000.0 - offset for n in hnames]          # on the Windows clock
    print(f"centre frames {len(cnames)}, harness frames {len(hnames)}, clock offset {offset * 1000:.0f} ms")

    t_start, t_end = marks["start"] + 0.5, marks["end"]
    # End on our speedometer over the phone (the 1.5 s hold): back on the map, the emulator's Maps tends to crash its
    # car renderer again.
    back = next((e["t"] for e in events if e["title"].startswith("Back to the map")), None)
    if back is not None:
        t_end = min(t_end, back - 0.3)
    # Wall times to show, minus the cuts the recorder marked: waiting for a phone session that stays up, and Maps
    # recovering from its crash as navigation starts (a black centre).
    times = [t_start + f / FPS for f in range(int((t_end - t_start) * FPS))]
    for cut0, cut1 in marks.get("cuts", []):
        if cut1 > cut0:
            times = [t for t in times if not cut0 <= t < cut1]
            print(f"cut {cut1 - cut0:.1f} s")
    nframes = len(times)
    bg = background()
    ev_t = [e["t"] + 0.25 for e in events]
    layers = {}
    cards = (card("Cluster", "a digital instrument cluster for a 1966 Mustang",
                  "now with real Android Auto on the round centre screen"),
             card("Cluster", "Linux + LIVI centre, S32K144 firmware gauges",
                  "Prototype, running on a PC: the boards are designed but not built yet."))
    k = 0
    intro_n, outro_n, fade = int(3.5 * FPS), int(6.0 * FPS), int(0.5 * FPS)

    def save(img):
        nonlocal k
        img.save(os.path.join(out, f"{k:06d}.jpg"), quality=92)
        k += 1

    for i in range(intro_n):
        save(Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), cards[0], min(1.0, i / fade)))

    ci = hi = -1
    cur_c = cur_h = None
    prev = None
    for f, t in enumerate(times):
        j = max(0, bisect.bisect_right(cts, t) - 1)
        if j != ci:
            im = Image.open(os.path.join(cdir, cnames[j])).convert("RGB").crop(CROP)
            cur_c = im.resize((CENTER_D, CENTER_D), Image.LANCZOS)
            ci = j
        h = max(0, bisect.bisect_right(hts, t) - 1)
        if h != hi:
            cur_h = read_ppm(os.path.join(hdir, hnames[h]))
            hi = h
        frame = bg.copy()
        frame.paste(cur_c, (CENTER_XY[0] - CENTER_D // 2, CENTER_XY[1] - CENTER_D // 2), MASK_C)
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
        prev = frame
        if f % 300 == 0:
            print(f"  {f}/{nframes}")

    for i in range(outro_n):
        save(Image.blend(prev, cards[1], i / fade) if i < fade else cards[1])
    json.dump({"times": times, "fps": FPS, "intro_frames": intro_n}, open(os.path.join(work, "compose_info.json"), "w"))
    print(f"{k} frames = {k / FPS:.1f} s in {out}")


if __name__ == "__main__":
    main()
