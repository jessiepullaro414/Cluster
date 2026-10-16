#!/usr/bin/env python3
"""Join build/screen_0..3.ppm (written by test/preview.c) into one PNG, 2x scaled, in board order.

Pure standard library (zlib + struct), so it needs no Pillow.
Usage: python montage.py [out.png] [scale]
"""
import struct
import sys
import zlib


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(b"\n", 3)
    assert parts[0] == b"P6"
    w, h = map(int, parts[1].split())
    return w, h, parts[3]


def write_png(path, w, h, rgb):
    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "build/screens.png"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    shots = [read_ppm(f"build/screen_{i}.ppm") for i in range(4)]
    gap, pad = 12, 12
    sw = 240 * k
    W = pad * 2 + 4 * sw + 3 * gap
    H = pad * 2 + sw
    bg = bytes((24, 24, 28))
    canvas = bytearray(bg * (W * H))
    for i, (w, h, px) in enumerate(shots):
        ox = pad + i * (sw + gap)
        for y in range(h):
            row = bytearray()
            for x in range(w):
                row += px[(y * w + x) * 3:(y * w + x) * 3 + 3] * k
            for dy in range(k):
                o = ((pad + y * k + dy) * W + ox) * 3
                canvas[o:o + len(row)] = row
    write_png(out, W, H, bytes(canvas))
    print("wrote", out, W, "x", H)


if __name__ == "__main__":
    main()
