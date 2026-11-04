"""
Power-stage cells for the gauges board (see ../tools/cellplace.py for the
method; display/cells.py is the fuller example).

REVIEW FIX 2026-10-17: the review script (review/review_netlist.py) measured the real distances from every supply pin
to its decoupling capacitor: the S32K144 VDD capacitors were 19 and 30 mm from their pins, VDDA's 35 mm, the TJA1043 VBAT
capacitor 16 mm, the TLV733P input capacitor 18 mm (NXP's data sheet asks for 2 mm). The MCU, both CAN transceivers, the
connector TVS parts and the LDO are now cells too.

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
    "VDDA": 3, "OSC_IN": 3, "OSC_OUT": 3, "RESET": 1, "CAN0_SPLIT": 2, "CAN1_SPLIT": 2,
    "SW": 8, "BOOT_CAP": 4, "FB": 3, "VCC_INT": 3,
    "DGATE": 3, "HGATE": 3, "COMMON": 3, "CS_PLUS": 2, "SENSE_HI": 2, "LM_VS": 2, "HGATE_DVDT": 3, "SENSE_TAP": 3, "CS_MINUS": 3,
    "CAP_CP": 2, "TMR": 2, "OV_DIV": 2, "UVLO_DIV": 2,
}

CELLS = {
    # LMR33630-Q1 (RNX0012C): VIN pins 2 and 9/10, PGND 1/11, SW 3/12, CBOOT 4,
    # VCC 5, FB 7. Input capacitors at VIN/PGND, inductor at SW.
    "BUCK": dict(
        anchor="U2",
        order=["L1", "C46", "C1", "C59", "C60", "C11", "C12", "C45", "C2", "R2", "R3"],
        pulls={
            "L1": {"SW": pull("U2", [3, 12], 10)},
            "C46": {"VIN_PROT": pull("U2", [2], 6), "GND": pull("U2", [1], 6)},
            "C1": {"VIN_PROT": pull("U2", [9, 10], 4), "GND": pull("U2", [11], 4)},
            "C59": {"VIN_PROT": pull("U2", [9, 10], 3), "GND": pull("U2", [11], 3)},
            "C60": {"VIN_PROT": pull("U2", [2], 3), "GND": pull("U2", [1], 3)},
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
        order=["Q1", "Q3", "C47", "R49", "R48", "C48", "C49", "D34", "R89", "C61", "R50", "R51", "R52",
               "R53", "R54", "C62", "D1"],
        pulls={
            "R49": {"SENSE_TAP": pull("U3", [18], 3), "CS_MINUS": pull("U3", [19], 3)},   # review 2026-11-03: Kelvin taps at the IC
            "R48": {"CS_PLUS": pull("U3", [20], 4), "SENSE_TAP": pull("R49", [3], 4)},
            "C48": {"CAP_CP": pull("U3", [23], 4)},
            "C49": {"TMR": pull("U3", [9], 4)},
            # review 2026-11-03: VS (pin 22, with EN 6 and MODE 7) now comes through D34; C47 and D34 sit at the pin
            "C47": {"LM_VS": pull("U3", [22], 8)},     # placed right after the FETs: 7.5 mm from pin 22 otherwise
            "D34": {"LM_VS": pull("U3", [22], 4)},
            "R89": {"HGATE": pull("U3", [14], 4)},
            "C61": {"HGATE_DVDT": pull("R89", [2], 3)},
            "C62": {"VIN_FUSED": pull("Q3", [5], 5)},
            "R50": {"ILIM": pull("U3", [11], 3)},
            # 2026-10-19: the OV/UV dividers had no pull, so on six layers
            # FreeRouting left SW_SENSE (U3 pin 3) unrouted every attempt.
            # Pulling all four divider parts made the POWER zone pack 9.4 mm
            # taller (72.8 mm board); R51 alone keeps the 63.4 mm outline.
            "R51": {"SW_SENSE": pull("U3", [3], 4)},
        },
        # review 2026-11-03: the four new parts (D34, R89, C61, C62) stacked the cell to 17.9 mm and the board grew 5.5 mm;
        # a flat keep-in lays it out wider instead, and the POWER zone in build_pcb.py is allowed the width.
        keepin=(-22.0, -7.0, 22.0, 7.0)),
    # S32K144 (LQFP-64): VDD pins 7 and 41, VDDA 8, VREFH 9, VSS/VREFL 10 and 40, XTAL 11/12, RESET_b 63, SPI SCK 29, MOSI 25.
    "MCU": dict(
        anchor="U1",
        order=["C7", "C6", "C8", "L2", "R1", "Y1", "C4", "C5", "R84", "R85"],
        pulls={
            "C6": {"+3V3": pull("U1", [7], 6), "GND": pull("U1", [10], 5)},
            "C7": {"+3V3": pull("U1", [41], 6), "GND": pull("U1", [40], 5)},
            "C8": {"VDDA": pull("U1", [8, 9], 5), "GND": pull("U1", [10], 4)},
            "L2": {"+3V3": pull("U1", [7], 3), "VDDA": pull("U1", [8], 4)},
            "R1": {"RESET": pull("U1", [63], 3)},
            "Y1": {"OSC_IN": pull("U1", [11], 5), "OSC_OUT": pull("U1", [12], 5)},
            "C4": {"OSC_IN": pull("Y1", [1], 4)},
            "C5": {"OSC_OUT": pull("Y1", [3], 4)},
            "R84": {"LPSPI2_SCK_MCU": pull("U1", [29], 4)},
            "R85": {"LPSPI2_SOUT_MCU": pull("U1", [25], 4)},
        }),
    # TJA1043T: VCC 3, VIO 5, VBAT 10, SPLIT 11
    "CAN0": dict(
        anchor="U5",
        order=["C13", "C14", "C15", "C16", "R4", "R5", "R87", "R88"],
        pulls={
            "C13": {"+5V": pull("U5", [3], 5), "GND": pull("U5", [2], 4)},
            "C14": {"+3V3": pull("U5", [5], 5), "GND": pull("U5", [2], 4)},
            "C15": {"VIN_PROT": pull("U5", [10], 5), "GND": pull("U5", [2], 4)},
            "C16": {"CAN0_SPLIT": pull("U5", [11], 3)},
            "R87": {"CAN0_EN": pull("U5", [6], 3)},
            "R88": {"CAN0_STB_N": pull("U5", [14], 3)},
        }),
    # TCAN1044V: VCC 3, VIO 5, STB 8
    "CAN1": dict(
        anchor="U10",
        order=["C40", "C41", "R40", "R41", "R42", "C42"],
        pulls={
            "C40": {"+5V": pull("U10", [3], 5), "GND": pull("U10", [2], 4)},
            "C41": {"+3V3": pull("U10", [5], 5), "GND": pull("U10", [2], 4)},
            "R40": {"CAN1_STB": pull("U10", [8], 3)},
            "C42": {"CAN1_SPLIT": pull("R41", [2], 3)},
        }),
    # connector TVS arrays sit at the connector pins they protect
    "J7": dict(anchor="J7", order=["D28", "D29", "D30"], pulls={}),
    "J8": dict(anchor="J8", order=["D31"], pulls={}),
    "J9": dict(anchor="J9", order=["D32"], pulls={}),
    # review 2026-11-03: the sender excitation switch and the 12 V pull-up / sensor-supply switch, each with its parts
    "SENDEXC": dict(anchor="U11", order=["C65", "C66", "R94"],
                    pulls={"C65": {"+3V3": pull("U11", [1], 4), "GND": pull("U11", [2], 4)},
                           "C66": {"SENDER_EXC": pull("U11", [6], 4)},
                           "R94": {"SENDER_EXC_EN": pull("U11", [3], 4)}}),
    "VPULL": dict(anchor="U12", order=["C63", "R91", "R92", "R90", "C64"],
                  pulls={"C63": {"VIN_PROT": pull("U12", [8], 4), "GND": pull("U12", [6], 4)},
                         "R91": {"VPULL_CL": pull("U12", [4], 3)},
                         "R92": {"VPULL_DLY": pull("U12", [5], 3)},
                         "R90": {"VPULL_IN": pull("U12", [1], 3)},
                         "C64": {"VPULL": pull("U12", [7], 4)}}),
    # 2026-11-04: the VR speed input around its comparator. TLV7031-Q1: 1 OUT, 2 VEE, 3 IN+, 4 IN-, 5 VCC.
    "VRIN": dict(anchor="U13", order=["C70", "R101", "R102", "R103", "R104", "C69", "D36", "C68", "D35", "R99", "R100"],
                 pulls={"C70": {"+3V3": pull("U13", [5], 5), "GND": pull("U13", [2], 4)},
                        "R101": {"VR_P": pull("U13", [3], 4)},
                        "R102": {"VR_P": pull("U13", [3], 3), "VR_SPEED_IN": pull("U13", [1], 3)},
                        "R103": {"VR_N": pull("U13", [4], 3)},
                        "R104": {"VR_N": pull("U13", [4], 3)},
                        "C69": {"VR_N": pull("U13", [4], 3)},
                        "D36": {"VR_N": pull("U13", [4], 3)},
                        "C68": {"VR_FP": pull("R101", [1], 3)},
                        "D35": {"VR_FP": pull("R101", [1], 3)},
                        "R99": {"VR_FP": pull("R101", [1], 3)},
                        "R100": {"VR_N": pull("U13", [4], 3)}}),
    # 2026-11-04: the dash dimmer's pulsed test load. MMBT5551Q: 1 B, 2 E, 3 C.
    "DIMLOAD": dict(anchor="Q4", order=["R107", "R106", "R105", "D37"],
                    pulls={"R107": {"DIM_LOAD_B": pull("Q4", [1], 4)},
                           "R106": {"DIM_LOAD_B": pull("Q4", [1], 4)},
                           "R105": {"DIM_LOAD_C": pull("Q4", [3], 4)},
                           "D37": {"DIM_LOAD": pull("R105", [1], 4)}}),
    "INPUT": dict(anchor="J1", order=["F1"],
                  pulls={"F1": {"VIN": pull("J1", [1], 6)}}),
    "LDO": dict(anchor="U4", order=["C3", "C58"],
                pulls={"C3": {"+3V3": pull("U4", [5], 4)},
                       "C58": {"+5V": pull("U4", [1], 5), "GND": pull("U4", [2], 4)}}),
}


def plan_cells(parts):
    return _plan_cells(parts, CELLS, NET_WEIGHT)
