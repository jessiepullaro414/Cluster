#!/usr/bin/env python3
"""Generate src/face_data.c: the printed faces of the "factory" theme, drawn after the 1966 Mustang gauges.

The factory theme is mostly printing: radial numerals, tick marks, "FUEL", "E" "F", the oil and temperature
brackets. Those are drawn once, here, at 4x size with Pillow, squeezed to a condensed look, rotated where the
original is rotated, scaled down (this is the anti-aliasing) and stored as 240x240 pictures with 4 bits per pixel
(a ramp from the face colour to the print colour). Each row is run-length coded (a byte is value<<4 | (run-1),
runs of up to 16 pixels) and a table gives the start of every row, so the renderer can decode a row cheaply
without a frame buffer. The needles, hubs and the small volts text are drawn by the firmware over it.

Letters are Inter (SIL OFL 1.1, see ../docs/fonts/OFL-Inter.txt) squeezed in width: Ford's own type is not used.
The faces are drawn from photographs of a 1966 Mustang cluster, by eye. They are a first pass to tune:
every position and size is a constant at the top of this file.

Run: python tools/gen_faces.py    (needs Pillow; the generated file is committed)
"""
import math
import os
import sys
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
TTF = os.path.join(os.path.dirname(FW), "refs", "fonts", "Inter.ttf")
OUT = os.path.join(FW, "src", "face_data.c")
PREVIEW = os.path.join(FW, "docs", "screens", "factory_faces.png")

N = 240                     # face size in pixels
S = 4                       # supersampling
FACE_RGB = (0x08, 0x08, 0x08)         # multiples of 8 stay neutral in RGB565
PRINT_RGB = (0xF2, 0xEF, 0xE6)

# speedometer, measured on the owner's photo of a real one (scaled so the face fills the round panel): the needle
# rests at the lower left (151 degrees clockwise from 3 o'clock, y down) and ends at the lower right (389.5, i.e.
# 29.5 degrees) at 140 mph: 1.704 degrees per mph. The numerals are large, bold and narrow, their tops pointing
# outwards, on a ring just inside the edge; the ticks sit between them and the hub.
SPEED_PIVOT = (120.0, 126.0)
SPEED_START, SPEED_SWEEP = 151.0, 238.5
SPEED_LABEL_R = 77.0
SPEED_TICK_R_LONG = (47.0, 61.0)            # at the numbered speeds
SPEED_TICK_R_SHORT = (52.0, 60.0)           # between them

# small gauges: the needle hangs from a pivot near the top and swings between E/L/C and F/H
FUEL_PIVOT = (120.0, 104.0)
OIL_PIVOT = (120.0, 84.0)
SWING_FROM, SWING_TO = 122.0, 58.0          # needle angle at E / L / C and at F / H


def font(px, weight=800):
    f = ImageFont.truetype(TTF, int(px * S))
    f.set_variation_by_axes([max(14, min(32, px)), weight])
    return f


def text_img(s, px, weight=800, squeeze=0.72, tracking=0.0):
    """Condensed text as an 'L' image at S x scale, tight around the ink."""
    f = font(px, weight)
    widths = [f.getlength(c) for c in s]
    total = sum(widths) + tracking * S * (len(s) - 1)
    pad = 6 * S
    img = Image.new("L", (int(total) + 2 * pad, int(px * S * 1.5) + 2 * pad), 0)
    d = ImageDraw.Draw(img)
    x = pad
    for c, w in zip(s, widths):
        d.text((x, pad + px * S * 1.1), c, font=f, fill=255, anchor="ls")
        x += w + tracking * S
    bbox = img.getbbox()
    img = img.crop(bbox)
    return img.resize((max(1, int(img.width * squeeze)), img.height), Image.LANCZOS)


def put(canvas, img, cx, cy, rot_cw=0.0):
    """Paste img centred at (cx, cy) in face pixels, rotated clockwise by rot_cw degrees."""
    if rot_cw:
        img = img.rotate(-rot_cw, resample=Image.BICUBIC, expand=True)
    x = int(round(cx * S - img.width / 2.0))
    y = int(round(cy * S - img.height / 2.0))
    layer = Image.new("L", canvas.size, 0)
    layer.paste(img, (x, y))
    return ImageChops.lighter(canvas, layer)


def line(d, x0, y0, x1, y1, w):
    d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=255, width=max(1, int(round(w * S))))
    r = w * S / 2.0
    for (x, y) in ((x0, y0), (x1, y1)):
        d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill=255)


def polar(pivot, r, deg):
    a = math.radians(deg)
    return pivot[0] + r * math.cos(a), pivot[1] + r * math.sin(a)


def new_canvas():
    return Image.new("L", (N * S, N * S), 0)


def speed_face(mph):
    c = new_canvas()
    d = ImageDraw.Draw(c)
    vmax, minor, label = (140, 5, 10) if mph else (220, 10, 20)
    for v in range(0, vmax + 1, minor):
        ang = SPEED_START + SPEED_SWEEP * v / vmax
        tens = v % label == 0
        r0, r1 = SPEED_TICK_R_LONG if tens else SPEED_TICK_R_SHORT
        x0, y0 = polar(SPEED_PIVOT, r0, ang)
        x1, y1 = polar(SPEED_PIVOT, r1, ang)
        line(d, x0, y0, x1, y1, 2.2 if tens else 1.6)
    for v in range(0, vmax + 1, label):                     # the 0 is printed too (the needle rests over it)
        ang = SPEED_START + SPEED_SWEEP * v / vmax
        cx, cy = polar(SPEED_PIVOT, SPEED_LABEL_R, ang)
        squeeze = 0.5 if len(str(v)) < 3 else 0.44
        c = put(c, text_img(str(v), 22, 560, squeeze, -0.4), cx, cy, ang + 90.0)     # the tops of the numerals point outwards
    c = put(c, text_img("MILES" if mph else "KM/H", 12, 800, 0.8, 1.4), 120, 21)
    d = ImageDraw.Draw(c)
    # the odometer: a window with six empty cells (no odometer data exists yet, so no digits)
    x0, y0, x1, y1 = 82.0, 147.0, 158.0, 162.0
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=1.5 * S, outline=150, width=int(1.4 * S), fill=0)
    for i in range(1, 6):
        x = x0 + (x1 - x0) * i / 6.0
        d.line([(x * S, (y0 + 1.5) * S), (x * S, (y1 - 1.5) * S)], fill=90, width=int(0.9 * S))
    return c


def swing_ticks(d, pivot, r0, r1, n, w):
    for i in range(n):
        ang = SWING_FROM + (SWING_TO - SWING_FROM) * i / (n - 1)
        x0, y0 = polar(pivot, r0, ang)
        x1, y1 = polar(pivot, r1, ang)
        line(d, x0, y0, x1, y1, w)


def fuel_face():
    c = new_canvas()
    d = ImageDraw.Draw(c)
    swing_ticks(d, FUEL_PIVOT, 92.0, 103.0, 5, 3.0)
    c = put(c, text_img("FUEL", 25, 800, 0.74, 2.0), 120, 54)
    c = put(c, text_img("E", 27, 800, 0.74), 40, 148)
    c = put(c, text_img("F", 27, 800, 0.74), 200, 148)
    return c


def bracket_face(low, high, name):
    c = new_canvas()
    d = ImageDraw.Draw(c)
    # the normal range: a flat bar with a slash falling away at each end
    line(d, 96, 148, 144, 148, 2.4)
    line(d, 96, 148, 78, 172, 2.4)
    line(d, 144, 148, 162, 172, 2.4)
    c = put(c, text_img(low, 27, 800, 0.74), 38, 150)
    c = put(c, text_img(high, 27, 800, 0.74), 202, 150)
    c = put(c, text_img(name, 21, 800, 0.74, 3.0), 120, 206)
    return c


def volts_face():
    """Ammeter-style: D and C, slashes at the ends, VOLTS (this car has a voltmeter signal, not a shunt)."""
    c = new_canvas()
    d = ImageDraw.Draw(c)
    for i, (ang, r0, r1, w) in enumerate([(122.0, 72.0, 96.0, 3.0), (106.0, 80.0, 92.0, 2.4), (90.0, 78.0, 94.0, 2.8),
                                          (74.0, 80.0, 92.0, 2.4), (58.0, 72.0, 96.0, 3.0)]):
        x0, y0 = polar(OIL_PIVOT, r0, ang)
        x1, y1 = polar(OIL_PIVOT, r1, ang)
        line(d, x0, y0, x1, y1, w)
    c = put(c, text_img("D", 27, 800, 0.74), 38, 150)
    c = put(c, text_img("C", 27, 800, 0.74), 202, 150)
    c = put(c, text_img("VOLTS", 21, 800, 0.74, 3.0), 120, 206)
    return c


FACES = [
    ("SPEED_MPH", lambda: speed_face(True)),
    ("SPEED_KPH", lambda: speed_face(False)),
    ("FUEL", fuel_face),
    ("OIL", lambda: bracket_face("L", "H", "OIL")),
    ("TEMP", lambda: bracket_face("C", "H", "TEMP")),
    ("VOLTS", volts_face),
]


def to_levels(canvas):
    small = canvas.resize((N, N), Image.LANCZOS)
    return [min(15, (p + 8) // 17) for p in small.tobytes()]


def rle_rows(levels):
    blob, offs = bytearray(), []
    for y in range(N):
        offs.append(len(blob))
        row = levels[y * N:(y + 1) * N]
        x = 0
        while x < N:
            v, run = row[x], 1
            while x + run < N and row[x + run] == v and run < 16:
                run += 1
            blob.append((v << 4) | (run - 1))
            x += run
    return blob, offs


def palette():
    out = []
    for i in range(16):
        t = i / 15.0
        out.append(tuple(int(round(f + (p - f) * t)) for f, p in zip(FACE_RGB, PRINT_RGB)))
    return out


def main():
    if not os.path.exists(TTF):
        sys.exit("missing %s (see tools/gen_font.py)" % TTF)
    pal = palette()
    lines = ["""/* GENERATED by tools/gen_faces.py. Do not edit.
 *
 * Printed faces of the factory theme, run-length coded 4-bit pictures (see the generator for the format).
 * Letters are rasterisations of Inter, Copyright 2020 The Inter Project Authors (https://github.com/rsms/inter),
 * SIL Open Font License 1.1 (text in docs/fonts/OFL-Inter.txt).
 */
#include "face.h"
""", "static const uint32_t FACE_PAL[16] = {"]
    lines.append("    " + ", ".join("0x%02X%02X%02X" % c for c in pal) + ",")
    lines.append("};\n")
    sheet = Image.new("RGB", (N * len(FACES), N), (0, 0, 0))
    total = 0
    checks = []
    for i, (name, make) in enumerate(FACES):
        levels = to_levels(make())
        blob, offs = rle_rows(levels)
        assert len(blob) < 65536
        total += len(blob) + 2 * N
        checks.append(zlib.crc32(bytes(levels)))
        lines.append("static const uint8_t %s_RLE[%d] = {" % (name, len(blob)))
        for k in range(0, len(blob), 24):
            lines.append("    " + ", ".join("0x%02X" % b for b in blob[k:k + 24]) + ",")
        lines.append("};\n")
        lines.append("static const uint16_t %s_ROWS[%d] = {" % (name, N))
        for k in range(0, N, 16):
            lines.append("    " + ", ".join("%d" % o for o in offs[k:k + 16]) + ",")
        lines.append("};\n")
        lines.append("const face_t FACE_%s = { %s_RLE, %s_ROWS, FACE_PAL };\n" % (name, name, name))
        img = Image.new("RGB", (N, N))
        img.putdata([pal[v] for v in levels])
        # round mask, as the panel shows it
        mask = Image.new("L", (N, N), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, N - 1, N - 1], fill=255)
        black = Image.new("RGB", (N, N), (0, 0, 0))
        sheet.paste(Image.composite(img, black, mask), (i * N, 0))
    lines.append("/* CRC-32 of the decoded 4-bit pixels of each face (one byte per pixel, row-major), for the host test. */")
    lines.append("const uint32_t FACE_CHECKS[FACE_COUNT] = { %s };" % ", ".join("0x%08Xu" % c for c in checks))
    lines.append("const char *const FACE_NAMES[FACE_COUNT] = { %s };" % ", ".join('"%s"' % n for n, _ in FACES))
    lines.append("const face_t *const FACE_LIST[FACE_COUNT] = { %s };" % ", ".join("&FACE_%s" % n for n, _ in FACES))
    open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    sheet.save(PREVIEW)
    print("wrote %s (about %d bytes of flash) and %s" % (OUT, total, PREVIEW))


if __name__ == "__main__":
    main()
