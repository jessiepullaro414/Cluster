"""
Power-stage cells for the gauges board (see ../tools/cellplace.py for the
method; display/cells.py is the fuller example).

REVIEW FIX 2026-10-04: the LMR33630 buck was laid out with the zone packer
that knew nothing about it (switch node 26.8 mm long, input capacitor far from
the VIN pins). Each of these circuits is now built around its IC first, then
packed as a block into the POWER zone.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from cellplace import pull, plan_cells as _plan_cells  # noqa: E402

NET_WEIGHT = {
    "GND": 0.15, "+5V": 0.4, "+3V3": 0.3, "VIN_PROT": 0.4, "VIN_FUSED": 0.5,
    "SW": 8, "BOOT_CAP": 4, "FB": 3, "VCC_INT": 3,
    "DGATE": 3, "HGATE": 3, "COMMON": 3, "CS_PLUS": 2, "SENSE_OUT": 2,
    "CAP_CP": 2, "TMR": 2, "OV_DIV": 2, "UVLO_DIV": 2,
}

CELLS = {
    # LMR33630-Q1 (RNX0012C): VIN pins 2 and 9/10, PGND 1/11, SW 3/12, CBOOT 4,
    # VCC 5, FB 7. Input capacitors at VIN/PGND, inductor at SW.
    "BUCK": dict(
        anchor="U2",
        order=["L1", "C46", "C1", "C11", "C12", "C45", "C2", "R2", "R3"],
        pulls={
            "L1": {"SW": pull("U2", [3, 12], 10)},
            "C46": {"VIN_PROT": pull("U2", [2], 6), "GND": pull("U2", [1], 6)},
            "C1": {"VIN_PROT": pull("U2", [9, 10], 4), "GND": pull("U2", [11], 4)},
            "C11": {"BOOT_CAP": pull("U2", [4], 5), "SW": pull("U2", [3, 12], 5)},
            "C12": {"VCC_INT": pull("U2", [5], 5), "GND": pull("U2", [6], 4)},
            "C45": {"+5V": pull("L1", [2], 3)},
            "C2": {"+5V": pull("L1", [2], 3)},
            "R2": {"FB": pull("U2", [7], 4)},
            "R3": {"FB": pull("U2", [7], 4)},
        }),
    # LM74930-Q1 ideal diode / surge front end.
    "FRONT": dict(
        anchor="U3",
        order=["Q1", "Q3", "R49", "R48", "C48", "C49", "C47", "R50", "R51", "R52",
               "R53", "R54", "D1"],
        pulls={
            "R48": {"CS_PLUS": pull("U3", [20], 4)},
            "C48": {"CAP_CP": pull("U3", [23], 4)},
            "C49": {"TMR": pull("U3", [9], 4)},
            "C47": {"VIN_FUSED": pull("U3", [6, 7, 22], 3)},
            "R50": {"ILIM": pull("U3", [11], 3)},
        }),
    "INPUT": dict(anchor="J1", order=["F1"],
                  pulls={"F1": {"VIN": pull("J1", [1], 6)}}),
    "LDO": dict(anchor="U4", order=["C3"],
                pulls={"C3": {"+3V3": pull("U4", [5], 4)}}),
}


def plan_cells(parts):
    return _plan_cells(parts, CELLS, NET_WEIGHT)
