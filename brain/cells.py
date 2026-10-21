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
    "FB_1V8": 3,
    "PORTA_ILIM": 3, "PORTB_ILIM": 3, "PORTA_5V": 1, "PORTB_5V": 1,
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
        order=["Q1", "Q2", "R1", "C3", "R2", "C4", "C2", "R3", "R4", "R5", "R6",
               "R7", "R8", "R15", "D1", "C1"],
        pulls={
            # 2026-10-20: R2's VBAT_F end to R1's input pad (the Kelvin point
            # RSET wants anyway). With only the CS_PLUS pull R2 sat on R1's
            # output side, and the router threaded SENSE_OUT (2.6 A) between
            # its two pads at 0.3 mm.
            "R2": {"CS_PLUS": pull("U1", [20], 4), "VBAT_F": pull("R1", [1], 6)},
            # C3 between CAP (pin 23) and VS (pin 22), not on the R1 -> Q2 line either
            "C3": {"CAP_CP": pull("U1", [23], 4), "VBAT_F": pull("U1", [22], 4)},
            "C4": {"TMR": pull("U1", [9], 4)},
            "C2": {"VBAT_F": pull("U1", [6, 7, 22], 3)},
            "R3": {"ILIM": pull("U1", [11], 3)},
            "R4": {"IMON": pull("U1", [10], 3)},
            "R15": {"PWR_FLT": pull("U1", [12], 2)},
            # 2026-10-19: the OV/UV dividers had no pull; on six layers
            # FreeRouting left SW_SENSE (U1 pin 3) unrouted. Pulling R7 too
            # (or all four) packs the board 3.6-7.2 mm taller than 105 mm.
            "R5": {"SW_SENSE": pull("U1", [3], 4)},
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
    # Screen ports (brain board, 2026-10-20). Each FH12 connector is a cell of
    # its own, so nothing sits in the fan where the planned DSI / LVDS pairs
    # arrive (fan_route.py); its 5 V switch and the control-line pulls are a
    # second cell next to the connector's 5 V contacts.
    "PORTA": dict(anchor="J4", order=[], pulls={}),
    "PORTA_PWR": dict(
        anchor="U6",
        order=["C41", "C40", "R37", "R38", "R39", "C42", "R40", "C43", "R41", "R42",
               "R43", "R50", "R75", "R76"],
        pulls={
            "C40": {"+5V": pull("U6", [2, 3], 4)},
            "C41": {"+5V": pull("U6", [2, 3], 3)},
            "R37": {"PORTA_ILIM": pull("U6", [5], 4)},
            "R38": {"PORTA_PWR_EN": pull("U6", [4], 3)},
            "R39": {"PORTA_FLT_N": pull("U6", [8], 3)},
            "C42": {"PORTA_5V": pull("U6", [6, 7], 4)},
        }),
    "PORTB": dict(anchor="J18", order=[], pulls={}),
    "PORTB_PWR": dict(
        anchor="U7",
        order=["C45", "C44", "R77", "R78", "R79", "C46", "R80", "C47", "R81", "R82",
               "R83", "R84", "R85", "R86"],
        pulls={
            "C44": {"+5V": pull("U7", [2, 3], 4)},
            "C45": {"+5V": pull("U7", [2, 3], 3)},
            "R77": {"PORTB_ILIM": pull("U7", [5], 4)},
            "R78": {"PORTB_PWR_EN": pull("U7", [4], 3)},
            "R79": {"PORTB_FLT_N": pull("U7", [8], 3)},
            "C46": {"PORTB_5V": pull("U7", [6, 7], 4)},
        }),
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
    # --- Audio and USB host (2026-10-16) --------------------------------
    # 3.3 V AVDD LDO, kept as its own small cell so the floorplan can put it
    # beside the codec.
    "LDO3V3": dict(
        anchor="U10",
        order=["C64", "C65", "R59", "R60"],
        pulls={
            "C64": {"+5V": pull("U10", [8], 4)},
            "C65": {"+3V3": pull("U10", [1], 4)},
            "R59": {"FB_3V3": pull("U10", [3], 4)},
            "R60": {"FB_3V3": pull("U10", [3], 4)},
        }),
    # Codec with its decoupling (datasheet Figure 8-1 / layout guidance 8.4.1:
    # supply capacitors close to the pins, VREF and MICBIAS capacitors with a
    # direct ground return), the microphone input network and the line-out
    # series resistors and DC-blocking capacitors at the OUT pins.
    "AUDIO": dict(
        anchor="U9",
        anchor_gap=3.5,
        order=["C66", "C67", "C68", "C69", "C70", "C71", "C72", "C73",
               "R63", "C74", "C75", "R64", "R61", "R62",
               "R65", "R66", "R67", "R68", "C76", "C77", "C78", "C79"],
        pulls={
            "C66": {"+3V3": pull("U9", [31], 4)},
            "C67": {"+3V3": pull("U9", [31], 4)},
            "C68": {"CODEC_DREG": pull("U9", [2], 4)},
            "C69": {"CODEC_DREG": pull("U9", [2], 4)},
            "C70": {"+1V8": pull("U9", [7], 4)},
            "C71": {"+1V8": pull("U9", [7], 4)},
            "C72": {"CODEC_VREF": pull("U9", [32], 5)},
            "C73": {"CODEC_MICBIAS": pull("U9", [17], 5)},
            "R63": {"CODEC_MICBIAS": pull("U9", [17], 2)},
            "C74": {"MIC_IN_P": pull("U9", [18], 4)},
            "C75": {"MIC_IN_N": pull("U9", [19], 4)},
            "R61": {"I2C1_SDA": pull("U9", [10], 2)},
            "R62": {"I2C1_SCL": pull("U9", [9], 2)},
            "R65": {"AOUT_L_P": pull("U9", [28], 4)},
            "R66": {"AOUT_L_N": pull("U9", [27], 4)},
            "R67": {"AOUT_R_P": pull("U9", [29], 4)},
            "R68": {"AOUT_R_N": pull("U9", [30], 4)},
            "C76": {"AOUT_L_P_R": pull("R65", [2], 3)},
            "C77": {"AOUT_L_N_R": pull("R66", [2], 3)},
            "C78": {"AOUT_R_P_R": pull("R67", [2], 3)},
            "C79": {"AOUT_R_N_R": pull("R68", [2], 3)},
        }),
    # External audio connectors with their ESD arrays right at the connector
    # (TI: place the array as close to the connector as possible).
    "AOUT": dict(
        anchor="J14",
        order=["U12", "J15", "U13"],
        pulls={
            "U12": {"LINE_L_P": pull("J14", [1], 4), "LINE_L_N": pull("J14", [2], 4),
                    "LINE_R_P": pull("J14", [3], 4), "LINE_R_N": pull("J14", [4], 4)},
            "U13": {"MIC_P": pull("J15", [1], 4), "MIC_N": pull("J15", [2], 4)},
        }),
    # Reserved MFi coprocessor access point (DNP header), by itself.
    "MFI": dict(anchor="J16", order=["U15", "C83", "C84", "R74"], pulls={}),
    # USB-C host port. The receptacle sits on the board edge, with the edge
    # 3.1 mm below its origin (GCT USB4105 footprint "PCB Edge" line), so every
    # other part stays above y = 2.6 mm in the cell frame. The cell is kept
    # narrow (26 mm) and tall (up to 26 mm above the receptacle origin, which
    # the bottom strip's height allows) because the bottom strip's WIDTH is what
    # sets the board width.
    "USBC": dict(
        anchor="J17",
        order=["U14", "D8", "C82", "U11", "R69", "R70", "R73", "C80", "C81", "R71", "R72"],
        keepin=(-13.0, -26.0, 13.0, 2.6),
        anchor_gap=3.5,
        pulls={
            "U14": {"USB2_DP": pull("J17", ["A6", "B6"], 4),
                    "USB2_DN": pull("J17", ["A7", "B7"], 4),
                    "USB2_CC1": pull("J17", ["A5"], 3),
                    "USB2_CC2": pull("J17", ["B5"], 3)},
            "D8": {"USB2_VBUS": pull("J17", ["A9", "B4"], 3)},
            "C82": {"USB2_VBUS": pull("J17", ["A9", "B4"], 2)},
            "U11": {"USB2_VBUS": pull("J17", ["A9", "B4"], 4)},
            "R69": {"USB2_ILIM": pull("U11", [5], 4)},
            "R70": {"USB2_OC_N": pull("U11", [8], 3)},
            "R73": {"USB2_EN": pull("U11", [4], 3)},
            "C80": {"+5V": pull("U11", [2, 3], 4)},
            "C81": {"+5V": pull("U11", [2, 3], 4)},
            "R71": {"USB2_CC1": pull("J17", ["A5"], 2)},
            "R72": {"USB2_CC2": pull("J17", ["B5"], 2)},
        }),
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
    info, pad_net, _ = load_schematic(os.path.join(here, "ClusterBrain.kicad_sch"), cli,
                                      os.path.join(os.environ.get("TEMP", here), "cells_preview_" + os.path.basename(here) + ".net"))
    info = {r: v for r, v in info.items() if r != "J1"}
    parts = make_parts(info, pad_net, load_footprint, footprint_bbox)
    res, used = plan_cells(parts)
    missing = set(info) - used
    print("parts not in any cell:", sorted(missing))
    n = len(res)
    fig, axes = plt.subplots(4, 5, figsize=(26, 20))
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

