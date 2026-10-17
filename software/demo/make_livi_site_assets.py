#!/usr/bin/env python3
"""Cut the website's stills out of the composed Linux-option demo (compose_livi_demo.py): one picture per gauge look (modern,
classic, CarPlay-inspired, factory) and one with Android Auto navigating on the round centre, without the caption box, plus a
poster for the video.

    py software/demo/make_livi_site_assets.py workdir outdir
"""
import bisect
import json
import os
import sys

from PIL import Image

CROP = (0, 0, 1920, 830)        # the dash, its labels, no caption box
WIDTH = 1600


def main():
    work, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    tl = json.load(open(os.path.join(work, "timeline.json")))
    info = json.load(open(os.path.join(work, "compose_info.json")))
    times, intro = info["times"], info["intro_frames"]
    ev = tl["timeline"]

    def frame_at(t):
        return intro + max(0, min(len(times) - 1, bisect.bisect_left(times, t)))

    def caption_time(prefix):
        return next(e["t"] for e in ev if e["title"].startswith(prefix))

    # Each look's caption comes up as its settings edit starts; its gauge is on screen in the last seconds before the
    # next caption, so the still is taken 1.5 s before that. Android Auto: just after the navigation banner appears.
    shots = {
        "style-modern": caption_time("Our speedometer") + 5.0,
        "style-carplay": caption_time("Factory") - 1.5,
        "style-factory": caption_time("Classic") - 1.5,
        "style-classic": caption_time("Modern") - 1.5,
        "android-auto": caption_time("Google Maps navigation") + 1.5,
    }
    for name, t in shots.items():
        k = frame_at(t)
        im = Image.open(os.path.join(work, "out_frames", f"{k:06d}.jpg")).crop(CROP)
        im = im.resize((WIDTH, int(WIDTH * im.height / im.width)), Image.LANCZOS)
        im.save(os.path.join(out, f"{name}.jpg"), quality=86, optimize=True)
        print(name, k, os.path.getsize(os.path.join(out, f"{name}.jpg")) // 1024, "KB")
    # the poster: the title card
    im = Image.open(os.path.join(work, "out_frames", "000075.jpg")).resize((1280, 720), Image.LANCZOS)
    im.save(os.path.join(out, "demo-poster.jpg"), quality=84, optimize=True)
    print("poster")


if __name__ == "__main__":
    main()
