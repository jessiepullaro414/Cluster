#!/usr/bin/env python3
"""The Python update tool against the C bootloader core: mkimage.py makes an image, can_flash.py --emit writes its frames, and
build/boot_replay feeds them to bootcore.c over the flash model. The flash must then hold exactly the image and every answer must be OK.
Run from software/gauges-fw after `make build/boot_replay` (make test does both)."""
import os
import random
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import can_flash  # noqa: E402
import mkimage  # noqa: E402

REPLAY = os.path.join(os.path.dirname(HERE), "build", "boot_replay")
failures = 0


def check(cond, msg):
    global failures
    if not cond:
        print("FAIL", msg)
        failures += 1


def raw_app(length, seed):
    rnd = random.Random(seed)
    raw = bytearray(rnd.randrange(256) for _ in range(length))
    struct.pack_into("<II", raw, 0, 0x20006FE0, (mkimage.APP_BASE + 0x420) | 1)
    struct.pack_into("<IHHHHIIIII", raw, mkimage.HEADER_OFFSET, mkimage.MAGIC, 1, 1, 0, 1, 0xFFFFFFFF, 0xFFFFFFFF, 1, 0, 0xFFFFFFFF)   # as src/app_header.c
    return bytes(raw)


def replay(frames_text, tmp):
    fp = os.path.join(tmp, "frames.txt")
    dp = os.path.join(tmp, "dump.bin")
    open(fp, "w").write(frames_text)
    out = subprocess.run([REPLAY, fp, dp], capture_output=True, text=True, check=True).stdout
    return out, open(dp, "rb").read()


def main():
    if not os.path.exists(REPLAY):
        raise SystemExit("build/boot_replay is missing: run `make build/boot_replay`")
    with tempfile.TemporaryDirectory() as tmp:
        for length, seed in ((1100, 1), (4096, 2), (4103, 3), (30001, 4), (0x1E000 + 3, 5)):
            img = mkimage.finish(raw_app(length, seed))
            path = os.path.join(tmp, "img.bin")
            open(path, "wb").write(img)
            emitted = os.path.join(tmp, "emit.txt")
            can_flash.emit(emitted, img)
            out, dump = replay(open(emitted).read(), tmp)
            last = [l for l in out.splitlines() if l.startswith("STATE")][0].split()
            check(dump[:len(img)] == img, f"length {length}: the flash does not hold the image")
            check(all(b == 0xFF for b in dump[len(img):len(img) + 64]), f"length {length}: bytes after the image are not erased")
            check("BAD_RESPONSES" in last and last[last.index("BAD_RESPONSES") + 1] == "0", f"length {length}: a response was not OK:\n{out[-400:]}")
            check(last[last.index("BOOT_REQUESTED") + 1] == "1", f"length {length}: BOOT was not accepted")
            check(last[last.index("VIOLATIONS") + 1] == "0" and last[last.index("BOOT_TOUCHED") + 1] == "0", f"length {length}: flash rule violated")
            nresp = sum(1 for l in out.splitlines() if l.startswith("R "))
            check(nresp == 2 + (len(img) + 6) // 7 + 2, f"length {length}: {nresp} answers")
            print(f"ok: {len(img)} bytes, {(len(img) + 6) // 7} data frames, flash == image, CRC {can_flash.parse_image(img)[4]:08X}")
        # the image the toolchain really produced (make image), if it has been built: header offset, vector table and CRC as linked
        real = os.path.join(os.path.dirname(HERE), "build", "gauges-app.bin")
        if os.path.exists(real):
            img = open(real, "rb").read()
            emitted = os.path.join(tmp, "emit.txt")
            can_flash.emit(emitted, img)
            out, dump = replay(open(emitted).read(), tmp)
            last = [l for l in out.splitlines() if l.startswith("STATE")][0].split()
            check(dump[:len(img)] == img and last[last.index("BAD_RESPONSES") + 1] == "0" and last[last.index("BOOT_REQUESTED") + 1] == "1",
                  "the real application image was not accepted by the bootloader core")
            print(f"ok: the real application image ({len(img)} bytes, build/gauges-app.bin) passes the bootloader core's checks")
        # the tool refuses an image that was not finished by mkimage.py
        raw = raw_app(2000, 9)
        try:
            can_flash.parse_image(raw)
            check(False, "an unfinished image was accepted")
        except SystemExit:
            pass
        img = bytearray(mkimage.finish(raw)); img[1500] ^= 1
        try:
            can_flash.parse_image(bytes(img))
            check(False, "a corrupted image was accepted")
        except SystemExit:
            pass
        # a flipped bit in the frames (an error CAN's own CRC missed): the bootloader must refuse to boot it
        img = mkimage.finish(raw_app(5000, 11))
        emitted = os.path.join(tmp, "emit.txt")
        can_flash.emit(emitted, img)
        lines = open(emitted).read().splitlines()
        lines[100] = lines[100][:6] + "%02X" % (int(lines[100][6:8], 16) ^ 0x04) + lines[100][8:]
        out, dump = replay("\n".join(lines) + "\n", tmp)
        check(any(l.startswith("R 7C8 83 04") for l in out.splitlines()), "a corrupted frame was not caught by FINISH:\n" + out[-300:])
        check(any(l.startswith("R 7C8 85 01") for l in out.splitlines()), "BOOT was not refused after a failed FINISH")
        print("ok: a corrupted data frame is caught by FINISH (CRC mismatch) and BOOT is refused")
    if failures:
        print(f"test_can_flash: {failures} FAILED")
        sys.exit(1)
    print("test_can_flash: ok")


if __name__ == "__main__":
    main()
