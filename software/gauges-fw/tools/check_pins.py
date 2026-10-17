#!/usr/bin/env python3
"""Check that the pin tables in the register drivers (src/*_s32k.c) match inc/gauges_pins.h.

gauges_pins.h carries each claim as `#define PIN_NAME  <package pin>  /* PTxN ... */` (the port
names come from NXP's IO table via gauges/build_schematic.py). The HAL repeats the port and
pin number in code, tagged with the macro name in a comment; a typo there would drive the wrong
physical pin, so this compares every tagged entry.

Run: python tools/check_pins.py   (exit status 1 on any mismatch)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)

header = open(os.path.join(FW, "inc", "gauges_pins.h"), encoding="utf-8").read()
import glob
hal = "\n".join(open(f, encoding="utf-8").read() for f in sorted(glob.glob(os.path.join(FW, "src", "*_s32k.c"))))

# PIN_AUX_CS0  13  /* PTE3, ... */
want = {}
for m in re.finditer(r"#define\s+(PIN_\w+)\s+\d+\s*/\*\s*PT([A-E])(\d+)", header):
    want[m.group(1)] = (m.group(2), int(m.group(3)))

# { PORTE, 3 },  /* PIN_AUX_CS0 */     and     = { PORTB, 13 };  /* PIN_AUX_RST */
got = {}
for m in re.finditer(r"\{\s*PORT([A-E]),\s*(\d+)\s*\}[,;]?\s*/\*\s*(PIN_\w+)", hal):
    got[m.group(3)] = (m.group(1), int(m.group(2)))

bad = 0
for name, (port, pin) in sorted(got.items()):
    if name not in want:
        print(f"{name}: not in gauges_pins.h or has no PTxN comment")
        bad += 1
    elif want[name] != (port, pin):
        print(f"{name}: HAL says PT{port}{pin}, gauges_pins.h says PT{want[name][0]}{want[name][1]}")
        bad += 1

needed = ["PIN_AUX_CS0", "PIN_AUX_CS1", "PIN_AUX_CS2", "PIN_AUX_CS3", "PIN_AUX_DC0", "PIN_AUX_DC1",
          "PIN_AUX_DC2", "PIN_AUX_DC3", "PIN_AUX_RST", "PIN_BL_EN", "PIN_LPSPI2_SCK", "PIN_LPSPI2_SOUT",
          "PIN_LAMP_TURN_L", "PIN_LAMP_TURN_R", "PIN_LAMP_HIGH_BEAM", "PIN_LAMP_BRAKE", "PIN_LAMP_ALT", "PIN_LAMP_OIL",
          "PIN_IGN_SENSE", "PIN_SPEED_IN", "PIN_TACH_IN"]
for n in needed:
    if n not in got:
        print(f"{n}: missing from the HAL table")
        bad += 1

print(f"check_pins: {len(got)} HAL pins checked against gauges_pins.h, {bad} problem(s)")
sys.exit(1 if bad else 0)
