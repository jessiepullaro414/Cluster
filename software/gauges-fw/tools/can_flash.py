#!/usr/bin/env python3
"""Send an update image (from mkimage.py) to gauges/ over the private CAN link. Protocol: inc/bootcore.h.

    can_flash.py --interface socketcan --channel can0 gauges-app.bin       # a real bus (needs python-can)
    can_flash.py --emit frames.txt gauges-app.bin                          # write the frames, candump style, without a bus

The tool sends ENTER repeatedly (the running application resets into the bootloader when the car is standing; a bootloader that is
already waiting answers at once), then BEGIN (which erases the application region and takes a moment), the image in stop-and-wait data
frames of seven bytes, FINISH with the CRC-32 and BOOT. Every answer is checked; a data frame that is not acknowledged within 100 ms is
sent again (the bootloader ignores a repeat). The old application stops being valid at BEGIN; an interrupted update just leaves the
bootloader waiting, so run the tool again.
"""
import argparse
import struct
import sys
import time

import mkimage

ID_CMD, ID_DATA, ID_RESP = 0x7C0, 0x7C1, 0x7C8
BOARD_GAUGES = 1
STATUS = {0: "ok", 1: "wrong state", 2: "bad argument", 3: "flash error", 4: "CRC mismatch", 5: "bad image", 6: "out of sequence"}


def parse_image(img: bytes):
    magic, hver, board, major, minor, length, crc = struct.unpack_from("<IHHHHII", img, mkimage.HEADER_OFFSET)
    if magic != mkimage.MAGIC:
        raise SystemExit("can_flash: this is not an application image (run it through mkimage.py)")
    if length != len(img) or length == 0xFFFFFFFF:
        raise SystemExit("can_flash: the image length in the header (%d) does not match the file (%d): run mkimage.py" % (length, len(img)))
    if crc != mkimage.image_crc(img):
        raise SystemExit("can_flash: the image CRC in the header is wrong: run mkimage.py")
    return board, major, minor, length, crc


def enter_frame(board):
    return (ID_CMD, bytes([0x01, ord("B"), ord("L"), board & 0xFF, board >> 8, 0, 0, 0]))


def command(cmd, arg=0):
    return (ID_CMD, bytes([cmd]) + struct.pack("<I", arg) + b"\x00\x00\x00")


def data_frames(img: bytes):
    """seq (8 bit, from 0) and seven image bytes, the last frame padded with 0xFF"""
    n = (len(img) + 6) // 7
    for i in range(n):
        chunk = img[i * 7:i * 7 + 7]
        yield (ID_DATA, bytes([i & 0xFF]) + chunk + b"\xFF" * (7 - len(chunk)))


def all_frames(img: bytes):
    board, major, minor, length, crc = parse_image(img)
    yield enter_frame(board)
    yield command(0x02, length)
    yield from data_frames(img)
    yield command(0x03, crc)
    yield command(0x05)


def emit(path, img):
    with open(path, "w") as f:
        for cid, d in all_frames(img):
            f.write("%03X#%s\n" % (cid, d.hex().upper()))


class Link:
    def __init__(self, interface, channel, bitrate):
        try:
            import can
        except ImportError:
            raise SystemExit("can_flash: python-can is not installed (pip install python-can), or use --emit")
        self.can = can
        self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)

    def send(self, cid, data):
        self.bus.send(self.can.Message(arbitration_id=cid, data=data, is_extended_id=False))

    def wait(self, timeout, want):
        end = time.time() + timeout
        while time.time() < end:
            m = self.bus.recv(max(0.001, end - time.time()))
            if m is not None and m.arbitration_id == ID_RESP and want(bytes(m.data)):
                return bytes(m.data)
        return None


def flash(link: Link, img: bytes, log=print):
    board, major, minor, length, crc = parse_image(img)
    log(f"firmware {major}.{minor}, {length} bytes, CRC-32 {crc:08X}")
    cid, d = enter_frame(board)
    r = None
    for _ in range(150):                                                   # up to ~3 s of knocking
        link.send(cid, d)
        r = link.wait(0.02, lambda m: m[0] == 0x81)
        if r is not None:
            break
    if r is None:
        raise SystemExit("can_flash: nothing answered ENTER (is the link connected, the bit rate 500 kbit/s, and the car standing still?)")
    if r[1] != 0:
        raise SystemExit("can_flash: ENTER refused: " + STATUS.get(r[1], str(r[1])))
    log(f"bootloader version {r[2]}, application at 0x{r[5] << 12:05X}")
    cid, d = command(0x02, length)
    link.send(cid, d)
    r = link.wait(10.0, lambda m: m[0] == 0x82)
    if r is None or r[1] != 0:
        raise SystemExit("can_flash: BEGIN failed: " + ("no answer" if r is None else STATUS.get(r[1], str(r[1]))))
    t0 = time.time()
    frames = list(data_frames(img))
    for n, (cid, d) in enumerate(frames):
        for attempt in range(6):
            link.send(cid, d)
            r = link.wait(0.1, lambda m: m[0] == 0x90)
            if r is not None and r[1] == 0 and r[2] == ((n + 1) & 0xFF):
                break
            if r is not None and r[1] not in (0, 6):
                raise SystemExit(f"can_flash: data frame {n}: " + STATUS.get(r[1], str(r[1])))
        else:
            raise SystemExit(f"can_flash: data frame {n} was never acknowledged")
        if n % 2000 == 0:
            log(f"  {100 * n // len(frames)} %")
    log(f"sent {len(img)} bytes in {time.time() - t0:.1f} s")
    for cmd, arg, name in ((0x03, crc, "FINISH"), (0x05, 0, "BOOT")):
        cid, d = command(cmd, arg)
        link.send(cid, d)
        r = link.wait(3.0, lambda m, c=cmd: m[0] == (c | 0x80))
        if r is None or r[1] != 0:
            raise SystemExit(f"can_flash: {name} failed: " + ("no answer" if r is None else STATUS.get(r[1], str(r[1]))))
    log("done: the application is verified and the board is restarting into it")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--emit", metavar="FILE", help="write the frames to FILE instead of sending them")
    a = ap.parse_args()
    img = open(a.image, "rb").read()
    if a.emit:
        emit(a.emit, img)
        print(f"can_flash: wrote {a.emit}")
        return
    flash(Link(a.interface, a.channel, a.bitrate), img)


if __name__ == "__main__":
    sys.exit(main())
