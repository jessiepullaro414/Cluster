#!/usr/bin/env python3
"""Compare the GC9A01 register tables in src/gc9a01.c with the open-source reference.

The "vendor block" of undocumented registers and the default power / gamma / frame-rate values
were taken from Zephyr's display_gc9x01x.c (Apache-2.0) and its devicetree binding
galaxycore,gc9x01x.yaml. This script re-derives both from those files and compares them byte for
byte, so a transcription error cannot hide. It needs the two reference files, which are not
committed (software/refs/ is git-ignored):

  software/refs/raystar/display_gc9x01x.c
  software/refs/raystar/gc9x01x.yaml
  (https://github.com/zephyrproject-rtos/zephyr, drivers/display and dts/bindings/display)

Run: python tools/check_vendor_block.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
REFS = os.path.join(os.path.dirname(FW), "refs", "raystar")

zc = os.path.join(REFS, "display_gc9x01x.c")
zy = os.path.join(REFS, "gc9x01x.yaml")
if not (os.path.exists(zc) and os.path.exists(zy)):
    print("reference files not present (see the docstring); nothing checked")
    sys.exit(2)

ref_c = open(zc, encoding="utf-8").read()
ref_y = open(zy, encoding="utf-8").read()
mine = open(os.path.join(FW, "src", "gc9a01.c"), encoding="utf-8").read()

# Zephyr: .cmd = 0xEBU, .len = 1U, .data = {0x14U},
zephyr = []
for m in re.finditer(r"\.cmd\s*=\s*0x([0-9A-Fa-f]+)U?,\s*\.len\s*=\s*(\d+)U?,\s*\.data\s*=\s*\{([^}]*)\}", ref_c):
    data = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)U?", m.group(3))]
    zephyr.append((int(m.group(1), 16), int(m.group(2)), data))

# ours: { 0xEB, 1, { 0x14 } },
start = mine.index("vendor_block[]")
end = mine.index("};", start)
ours = []
for m in re.finditer(r"\{\s*0x([0-9A-Fa-f]+),\s*(\d+),\s*\{([^}]*)\}\s*\}", mine[start:end]):
    data = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", m.group(3))]
    ours.append((int(m.group(1), 16), int(m.group(2)), data))

bad = 0
if len(zephyr) != len(ours):
    print(f"vendor block: Zephyr has {len(zephyr)} registers, gc9a01.c has {len(ours)}")
    bad += 1
for i, (z, o) in enumerate(zip(zephyr, ours)):
    if z != o or z[1] != len(z[2]):
        print(f"vendor block entry {i}: Zephyr {z[0]:#04x} {z[2]} vs ours {o[0]:#04x} {o[2]}")
        bad += 1


def yaml_default(name):
    m = re.search(r"\n  %s:\s*\n\s*type: uint8-array\s*\n\s*default: \[([^\]]*)\]" % name, ref_y)
    return [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", m.group(1))]


def c_array(name):
    m = re.search(r"%s\[\d*\]\s*=\s*\{([^}]*)\}" % name, mine)
    return [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", m.group(1))]


def c_scalar(name):
    m = re.search(r"\b%s\s*=\s*0x([0-9A-Fa-f]+)" % name, mine)
    return [int(m.group(1), 16)]


checks = [("pwrctrl2", c_scalar("PWR2")), ("pwrctrl3", c_scalar("PWR3")), ("pwrctrl4", c_scalar("PWR4")),
          ("framerate", c_scalar("FRAMERATE")),
          ("gamma1", c_array("GAMMA_NEG")), ("gamma3", c_array("GAMMA_NEG")),
          ("gamma2", c_array("GAMMA_POS")), ("gamma4", c_array("GAMMA_POS"))]
for name, have in checks:
    want = yaml_default(name)
    if want != have:
        print(f"{name}: Zephyr default {want} vs ours {have}")
        bad += 1

print(f"check_vendor_block: {len(ours)} vendor registers and {len(checks)} documented-register defaults compared, {bad} problem(s)")
sys.exit(1 if bad else 0)
