#!/usr/bin/env python3
"""Cut the website's stills out of the composed demo frames: one picture per gauge look (classic, modern, CarPlay-inspired, factory),
without the caption box, plus a poster for the video.

    python software/demo/make_site_assets.py workdir outdir
"""
import json
import os
import sys

from PIL import Image

FPS, INTRO = 30, int(3.5 * 30)
CROP = (0, 0, 1920, 830)        # the dash, its labels, no caption box
WIDTH = 1600


def main():
    work, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    tl = json.load(open(os.path.join(work, "timeline.json")))
    log = open(os.path.join(work, "..", "compose_t0.txt")).read().split() if os.path.exists(os.path.join(work, "..", "compose_t0.txt")) else None
    t_start = float(sys.argv[3]) if len(sys.argv) > 3 else float(log[0])
    ev = tl["timeline"]
    looks = {"classic": "Classic: needles", "modern": "Modern: progress", "carplay": "CarPlay-inspired", "factory": "Factory: the printed"}
    # seconds into each look at which to take the still (the drive is looping, so pick a moment with the needles up)
    delay = {"classic": 2.6, "modern": 2.4, "carplay": 0.8, "factory": 4.2}
    for name, key in looks.items():
        e = next(x for x in ev if x["sub"].startswith(key))
        k = INTRO + int((e["t"] + delay[name] - t_start) * FPS)
        im = Image.open(os.path.join(work, "out_frames", f"{k:06d}.jpg")).crop(CROP)
        im = im.resize((WIDTH, int(WIDTH * im.height / im.width)), Image.LANCZOS)
        im.save(os.path.join(out, f"style-{name}.jpg"), quality=86, optimize=True)
        print(name, k, os.path.getsize(os.path.join(out, f"style-{name}.jpg")) // 1024, "KB")
    # the poster: the title card, which is clean and says what the video is
    im = Image.open(os.path.join(work, "out_frames", "000075.jpg")).resize((1280, 720), Image.LANCZOS)
    im.save(os.path.join(out, "demo-poster.jpg"), quality=84, optimize=True)
    print("poster")


if __name__ == "__main__":
    main()
