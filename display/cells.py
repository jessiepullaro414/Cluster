"""
Cell definitions for the display carrier (see cellplace.py for the method).

Each cell is one functional circuit built around an anchor part. build_pcb.py
places every cell with cellplace.place_cell(), then floorplans the finished
cells around the Verdin module keepout. Run this file directly for a picture
of every cell (cells_preview.png) and its measured critical distances.

Net weights and pulls come from the datasheet layout guidance cited in
parts.py/build_schematic.py: the buck's input capacitors go at VIN/PGND, the
inductor at SW, the boot capacitor across CBOOT/SW; the boost and inverter
inductors and diodes at their SW pins; feedback dividers at FB.
"""
import os
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "tools"))
from cellplace import Part, place_cell, pad_abs, pull, make_parts, plan_cells as _plan_cells, rotate_cell  # noqa: F401

# Weak weights for plane/rail nets (GND is a plane reached by vias, so it must
# not drag parts around), strong weights for switching nodes.
NET_WEIGHT = {
    "GND": 0.15, "+5V": 0.4, "+12V_PROT": 0.4, "+1V8": 0.3, "VBAT_F": 0.5,
    "SW_5V": 8, "BOOT_C": 4, "BOOT_R": 3, "FB_5V": 3, "VCC_LDO": 3, "RT_5V": 3,
    "EN_5V": 2,
    "PANEL_BOOST_SW": 8, "PANEL_INV_SW": 8, "BL_SW": 8,
    "PANEL_FBP": 3, "PANEL_FBN": 3, "PANEL_VREF": 3, "BL_COMP": 3, "FB_1V8": 3,
    "PANEL_CP": 2, "PANEL_CN": 2, "PANEL_VSP": 2, "PANEL_VSN": 2,
    "DGATE": 3, "HGATE": 3, "COMMON": 3, "CS_PLUS": 2, "SENSE_OUT": 2,
    "CAP_CP": 2, "TMR": 2,
}


# name -> dict(anchor, order, pulls, rot) . pulls: ref -> {net: (target, pads, w)}
CELLS = {
    "BUCK": dict(
        anchor="U2",
        # SW inductor first (largest, claims its side), then the HF input caps
        order=["L1", "C56", "C57", "C5", "C55", "C7", "R9", "C6", "C54", "C59",
               "C8", "R10", "R11", "C58", "R12", "R13", "R14", "R16"],
        pulls={
            "L1": {"SW_5V": pull("U2", [10], 10)},
            "C56": {"+12V_PROT": pull("U2", [8], 6), "GND": pull("U2", [9], 6)},
            "C57": {"+12V_PROT": pull("U2", [12], 6), "GND": pull("U2", [11], 6)},
            "C5": {"+12V_PROT": pull("U2", [8], 4), "GND": pull("U2", [9], 4)},
            "C55": {"+12V_PROT": pull("U2", [12], 4), "GND": pull("U2", [11], 4)},
            "C7": {"BOOT_C": pull("U2", [14], 5), "SW_5V": pull("U2", [10], 5)},
            "R9": {"BOOT_R": pull("U2", [13], 5), "BOOT_C": pull("U2", [14], 3)},
            "C6": {"VCC_LDO": pull("U2", [2], 5), "GND": pull("U2", [3], 4)},
            "C54": {"+5V": pull("L1", [2], 3)},
            "C59": {"+5V": pull("L1", [2], 3)},
            "C8": {"+5V": pull("L1", [2], 3)},
            "R10": {"FB_5V": pull("U2", [4], 4), "+5V": pull("L1", [2], 0.3)},
            "R11": {"FB_5V": pull("U2", [4], 4)},
            "C58": {"FB_5V": pull("U2", [4], 4)},
            "R12": {"RT_5V": pull("U2", [6], 4), "GND": pull("U2", [3], 1)},
            "R13": {"EN_5V": pull("U2", [7], 3)},
            "R14": {"EN_5V": pull("U2", [7], 3)},
            "R16": {"PG_5V": pull("U2", [5], 2)},
        }),
    "FRONT": dict(
        anchor="U1",
        order=["Q1", "Q2", "R1", "R2", "C3", "C4", "C2", "R3", "R4", "R5", "R6",
               "R7", "R8", "R15", "D1", "C1"],
        pulls={
            "R2": {"CS_PLUS": pull("U1", [20], 4)},
            "C3": {"CAP_CP": pull("U1", [23], 4)},
            "C4": {"TMR": pull("U1", [9], 4)},
            "C2": {"VBAT_F": pull("U1", [6, 7, 22], 3)},
            "R3": {"ILIM": pull("U1", [11], 3)},
            "R4": {"IMON": pull("U1", [10], 3)},
            "R15": {"PWR_FLT": pull("U1", [12], 2)},
        }),
    "BIAS": dict(
        anchor="U6",
        order=["L2", "D2", "C46", "L3", "D3", "C47", "C40", "C41", "R37", "C42",
               "C43", "C44", "C45", "R38", "R39", "C48", "R40", "R41", "C49", "R43"],
        pulls={
            "L2": {"PANEL_BOOST_SW": pull("U6", [1, 24], 10)},
            "D2": {"PANEL_BOOST_SW": pull("U6", [1, 24], 8)},
            "C46": {"PANEL_VSP": pull("D2", [1], 6)},
            "L3": {"PANEL_INV_SW": pull("U6", [13, 14], 10)},
            "D3": {"PANEL_INV_SW": pull("U6", [13, 14], 8)},
            "C47": {"PANEL_VSN": pull("D3", [2], 6)},
            "C40": {"+5V": pull("L2", [1], 4)},
            "C41": {"+5V": pull("L3", [1], 0.5)},
            "R37": {"PANEL_BIAS_VIN": pull("U6", [4], 3)},
            "C42": {"PANEL_BIAS_VIN": pull("U6", [4], 4)},
            "C43": {"PANEL_VREF": pull("U6", [17], 4)},
            "C44": {"PANEL_CP": pull("U6", [21], 4)},
            "C45": {"PANEL_CN": pull("U6", [18], 4)},
            "R38": {"PANEL_FBP": pull("U6", [22], 4)},
            "R39": {"PANEL_FBP": pull("U6", [22], 4)},
            "C48": {"PANEL_FBP": pull("U6", [22], 4)},
            "R40": {"PANEL_FBN": pull("U6", [16], 4)},
            "R41": {"PANEL_FBN": pull("U6", [16], 4)},
            "C49": {"PANEL_FBN": pull("U6", [16], 4)},
            "R43": {"PANEL_BIAS_EN": pull("U6", [8, 10], 2)},
        }),
    "BACKLIGHT": dict(
        anchor="U7",
        order=["L4", "D4", "C52", "C50", "C51", "R42"],
        pulls={
            "L4": {"BL_SW": pull("U7", [3], 10)},
            "D4": {"BL_SW": pull("U7", [3], 8)},
            "C52": {"PANEL_BL_LEDA": pull("D4", [1], 6)},
            "C50": {"+5V": pull("U7", [1], 4)},
            "C51": {"BL_COMP": pull("U7", [5], 4)},
            "R42": {"PANEL_BL_LEDK": pull("U7", [6], 4)},
        }),
    "LDO": dict(
        anchor="U3",
        order=["C9", "C10", "R17", "R18"],
        pulls={
            "C9": {"+5V": pull("U3", [8], 4)},
            "C10": {"+1V8": pull("U3", [1], 4)},
            "R17": {"FB_1V8": pull("U3", [3], 4)},
            "R18": {"FB_1V8": pull("U3", [3], 4)},
        }),
    "CAN": dict(
        anchor="U4",
        order=["C11", "C12", "R19", "R20", "C13", "R21", "J3"],
        pulls={
            "C11": {"+5V": pull("U4", [3], 4)},
            "C12": {"+1V8": pull("U4", [5], 4)},
            "R19": {"CAN1_H": pull("U4", [7], 4)},
            "R20": {"CAN1_L": pull("U4", [6], 4)},
            "R21": {"CAN1_STB": pull("U4", [8], 3)},
        }),
    # Harness power input: terminal block and fuse holder, kept together at a
    # board edge; the protected path then runs to the FRONT cell.
    "INPUT": dict(
        anchor="J2",
        order=["F1"],
        pulls={"F1": {"VBAT_IN": pull("J2", [1], 6)}}),
    "IGN": dict(
        anchor="Q3",
        order=["R52", "C53", "R51", "D5", "R53"],
        pulls={}),
    "DIAL": dict(
        anchor="U8",
        order=["C60", "C63", "R54", "R58", "R55", "C61", "D6", "R56", "R57",
               "C62", "D7", "J11"],
        pulls={
            "C60": {"+5V": pull("U8", [1], 4)},
            "C63": {"DIAL_5V": pull("U8", [6], 4)},
        }),
    "PANEL": dict(
        anchor="J4",
        order=["R50", "JP1", "JP2"],
        pulls={}),
    # JTAG header sits at the low-pin-number end of the Verdin odd row (its
    # JTAG pins are 1-13); the button header and its pull-ups go with the
    # reset/recovery/power pins at the other end (246-260).
    # Bring-up headers sit with the Verdin pins they serve (UART_3 pins 147/149
    # and USB_1 pins 159-165, middle of the odd row), in the bottom strip.
    "USBUART": dict(
        anchor="J13",
        order=["J12"],
        pulls={}),
    "JTAG": dict(
        anchor="J8",
        order=["R48"],
        pulls={}),
    "BUTTONS": dict(
        anchor="J9",
        order=["R44", "R45", "R46", "R47"],
        pulls={}),
    "RTC": dict(
        anchor="J10",
        order=["R49", "C39"],
        pulls={}),
}


def plan_cells(parts):
    """Place every display cell. Returns ({cell: (placed, bbox)}, refs used)."""
    return _plan_cells(parts, CELLS, NET_WEIGHT)


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    import shutil
    from fpgeom import load_footprint, footprint_bbox, load_schematic
    from cellplace import rot_xy

    cli = shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
    here = os.path.dirname(os.path.abspath(__file__))
    info, pad_net, _ = load_schematic(os.path.join(here, "ClusterDisplay.kicad_sch"), cli,
                                      os.path.join(os.environ.get("TEMP", here), "cells_preview.net"))
    info = {r: v for r, v in info.items() if r != "J1"}
    parts = make_parts(info, pad_net, load_footprint, footprint_bbox)
    res, used = plan_cells(parts)
    missing = set(info) - used
    print("parts not in any cell:", sorted(missing))
    n = len(res)
    fig, axes = plt.subplots(3, 5, figsize=(26, 15))
    for ax, (name, (placed, bbox)) in zip(axes.flat, res.items()):
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print(f"{name:10s} {len(placed):3d} parts  {w:5.1f} x {h:5.1f} mm")
        for ref, (ox, oy, a) in placed.items():
            x0, y0, x1, y1 = parts[ref].rbbox(a)
            ax.add_patch(Rectangle((ox + x0, oy + y0), x1 - x0, y1 - y0, fill=False, lw=0.6, ec="gray"))
            for num, px, py, net in parts[ref].rpads(a):
                ax.plot(ox + px, oy + py, ".", ms=3,
                        color="tab:red" if net and "SW" in net else "tab:blue")
            ax.text(ox, oy, ref, fontsize=7, ha="center", va="center")
        ax.set_xlim(bbox[0] - 1, bbox[2] + 1)
        ax.set_ylim(bbox[3] + 1, bbox[1] - 1)
        ax.set_aspect("equal")
        ax.set_title(f"{name} {w:.1f}x{h:.1f}")
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.savefig(os.path.join(here, "cells_preview.png"), dpi=80)
    # critical distances
    def d(cell, a, pa, b, pb):
        placed = res[cell][0]
        (x1, y1), (x2, y2) = pad_abs(parts, placed, a, pa), pad_abs(parts, placed, b, pb)
        return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
    print("BUCK  L1.1 -> U2.10 (SW):", round(d("BUCK", "L1", "1", "U2", "10"), 2))
    print("BUCK  C56.1 -> U2.8 (VIN1):", round(d("BUCK", "C56", "1", "U2", "8"), 2),
          " C57.1 -> U2.12:", round(d("BUCK", "C57", "1", "U2", "12"), 2))
    print("BUCK  C5.1 -> U2.8:", round(d("BUCK", "C5", "1", "U2", "8"), 2),
          " C55.1 -> U2.12:", round(d("BUCK", "C55", "1", "U2", "12"), 2))
    print("BUCK  C7.1 -> U2.14:", round(d("BUCK", "C7", "1", "U2", "14"), 2))
    print("BIAS  L2.2 -> U6.1:", round(d("BIAS", "L2", "2", "U6", "1"), 2),
          " L3.1 -> U6.13:", round(d("BIAS", "L3", "1", "U6", "13"), 2))
    print("BL    L4.2 -> U7.3:", round(d("BACKLIGHT", "L4", "2", "U7", "3"), 2))
