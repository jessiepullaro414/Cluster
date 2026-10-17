#!/usr/bin/env python3
"""Turn the raw application binary (linked at 0x8000 by link/s32k144_app.ld) into the update image.

The application carries a 32-byte header at +0x400 (src/app_header.c) whose length and CRC fields are placeholders. This fills them in:

    0  u32 magic 'CLAP'          4  u16 header version     6  u16 board id
    8  u16 fw major             10  u16 fw minor           12  u32 image length
   16  u32 image CRC-32        20  u32 min bootloader     24  u32 reserved     28  u32 header CRC-32 (of bytes 0..27)

The image CRC is the zlib CRC-32 of the whole image with the image-CRC field and the header-CRC field read as zero; the bootloader
(src/bootcore.c app_image_crc) computes the same. The image is padded with 0xFF to a multiple of 8 bytes (the flash is programmed by
8-byte phrases).

    mkimage.py app.raw.bin gauges-app.bin [--boot boot.raw.bin --flash gauges-flash.bin]

--flash writes bootloader + application as one 512 KB-aligned file for a programmer (the bootloader padded with 0xFF to 0x8000).
"""
import argparse
import struct
import sys
import zlib

APP_BASE = 0x8000
HEADER_OFFSET = 0x400
HEADER_BYTES = 32
MAGIC = 0x50414C43
APP_SIZE = 0x80000 - APP_BASE


def image_crc(img: bytes) -> int:
    h = HEADER_OFFSET
    z = b"\x00\x00\x00\x00"
    c = zlib.crc32(img[:h + 16])
    c = zlib.crc32(z, c)
    c = zlib.crc32(img[h + 20:h + 28], c)
    c = zlib.crc32(z, c)
    c = zlib.crc32(img[h + HEADER_BYTES:], c)
    return c & 0xFFFFFFFF


def finish(raw: bytes) -> bytes:
    if len(raw) < HEADER_OFFSET + HEADER_BYTES:
        raise SystemExit("mkimage: the binary is shorter than the header offset: is it the application, linked with s32k144_app.ld?")
    img = bytearray(raw)
    while len(img) % 8:
        img.append(0xFF)
    if len(img) > APP_SIZE:
        raise SystemExit(f"mkimage: {len(img)} bytes do not fit the {APP_SIZE} byte application region")
    magic, hver, board, major, minor, _len, _crc, minboot, reserved, _hcrc = struct.unpack_from("<IHHHHIIIII", img, HEADER_OFFSET)
    if magic != MAGIC:
        raise SystemExit("mkimage: no application header at +0x400 (magic %08X)" % magic)
    sp, pc = struct.unpack_from("<II", img, 0)
    if not (0x1FFF8000 <= sp <= 0x20007000) or not (pc & 1) or not (APP_BASE <= (pc & ~1) < APP_BASE + len(img)):
        raise SystemExit("mkimage: the vector table does not look like an application linked at 0x8000 (sp %08X, reset %08X)" % (sp, pc))
    struct.pack_into("<I", img, HEADER_OFFSET + 12, len(img))
    struct.pack_into("<I", img, HEADER_OFFSET + 16, 0)
    struct.pack_into("<I", img, HEADER_OFFSET + 28, 0)
    struct.pack_into("<I", img, HEADER_OFFSET + 16, image_crc(bytes(img)))
    struct.pack_into("<I", img, HEADER_OFFSET + 28, zlib.crc32(bytes(img[HEADER_OFFSET:HEADER_OFFSET + 28])) & 0xFFFFFFFF)
    return bytes(img)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--boot", help="raw bootloader binary (linked at 0)")
    ap.add_argument("--flash", help="write bootloader + application as one file")
    a = ap.parse_args()
    img = finish(open(a.raw, "rb").read())
    open(a.out, "wb").write(img)
    major, minor, length, crc = struct.unpack_from("<HHII", img, HEADER_OFFSET + 8)
    print(f"mkimage: {a.out}: firmware {major}.{minor}, {length} bytes, CRC-32 {crc:08X}")
    if a.flash:
        if not a.boot:
            raise SystemExit("mkimage: --flash needs --boot")
        boot = open(a.boot, "rb").read()
        if len(boot) > APP_BASE:
            raise SystemExit(f"mkimage: the bootloader is {len(boot)} bytes, it has {APP_BASE}")
        open(a.flash, "wb").write(boot + b"\xFF" * (APP_BASE - len(boot)) + img)
        print(f"mkimage: {a.flash}: bootloader {len(boot)} bytes + application")


if __name__ == "__main__":
    sys.exit(main())
