"""
Verified pinouts for the display carrier's active parts.

Trimmed from fascia-pcb's own parts.py: this board is a dedicated bar-
display carrier (Verdin iMX95 + SN65DSI85-Q1 + power tree + CAN), not a
touchscreen/infotainment head unit, so PCM3168A-Q1 (audio codec),
SN74AXC4T245-Q1 (audio level shifters) and TPS2557-Q1 (USB-C power
switch) are dropped along with their footprints - real parts this board
has no use for, not parts awaiting a later stage.

Every remaining entry here was read out of the part's own datasheet, not
recalled - see fascia-pcb/parts.py for the original source citations
(same real parts, same real pin tables; this file only removes rows, it
does not re-derive anything). Pin tuples are:

    (pin_number, pin_name, electrical_type)

using KiCad's electrical-type vocabulary, so build_schematic.py can hand
them straight to the symbol factory.

Notes marked GOTCHA are things that will destroy a board or silently not
work, and that contradict the obvious default.
"""

# ---------------------------------------------------------------------------
# LM74930-Q1 - automotive ideal diode surge stopper with circuit breaker,
# overvoltage protection and fault output.
# Source: TI SNOSDF6, October 2023. VQFN-24 (RGE).
#
# GOTCHA: the exposed thermal pad (RTN) must be left FLOATING. The
# datasheet says explicitly "Leave exposed pad floating. Do Not connect to
# GND plane." That is the opposite of the usual VQFN convention, so the
# footprint and any ground-stitching pass need a deliberate exception.
#
# GOTCHA: OVCLAMP (16) tied to OV (5) selects overvoltage CLAMP with
# circuit-breaker timing, i.e. the part regulates through a surge instead
# of just disconnecting. Tied to GND instead, that behaviour is disabled.
# ---------------------------------------------------------------------------
LM74930_Q1 = [
    (1,  "DGATE",   "output"),      # ideal-diode FET gate
    (2,  "A",       "passive"),     # ideal-diode anode (that FET's source)
    (3,  "SW",      "passive"),     # battery-sense disconnect switch; may float
    (4,  "UVLO",    "input"),       # tie to VS or EN if unused
    (5,  "OV",      "input"),       # tie to GND if unused
    (6,  "EN",      "input"),       # tie to VS for always-on
    (7,  "MODE",    "input"),       # low disables reverse blocking; tie EN/VS
    (8,  "NC1",     "no_connect"),
    (9,  "TMR",     "passive"),     # fault/clamp timer cap; GND disables OCP
    (10, "IMON",    "output"),      # analog current monitor; may float
    (11, "ILIM",    "passive"),     # overcurrent threshold resistor
    (12, "FLT",     "open_collector"),
    (13, "GND",     "power_in"),
    (14, "HGATE",   "output"),      # pass (load switch) FET gate
    (15, "OUT",     "passive"),     # common source rail
    (16, "OVCLAMP", "input"),       # tie to OV to enable clamp; GND disables
    (17, "NC2",     "no_connect"),
    (18, "ISCP",    "input"),       # tie to C for internal 20 mV SCP threshold
    (19, "CS-",     "input"),
    (20, "CS+",     "input"),       # 50R to the sense resistor
    (21, "NC3",     "no_connect"),
    (22, "VS",      "power_in"),    # 100 nF to GND
    (23, "CAP",     "passive"),     # charge pump; 100 nF across CAP and VS
    (24, "C",       "passive"),     # ideal-diode cathode (that FET's drain)
    # Pad 25 is the exposed pad. It MUST be left floating on this part -
    # see the GOTCHA above. It exists here so the schematic can carry a
    # deliberate NoConnect rather than leaving a netless pad by omission.
    (25, "EP",      "passive"),
]

# ---------------------------------------------------------------------------
# TCAN1044V-Q1 - automotive CAN FD transceiver with 1.8 V I/O support.
# Source: TI SLLSF17D, August 2019, revised March 2025. SOIC-8 (D),
# SOT-8 (DDF) and VSON-8 (DRB) share this pinout.
#
# GOTCHA: the "V" suffix is load bearing. Per the datasheet's own device
# comparison table, TCAN1044-Q1 has pin 5 as a No-Connect while
# TCAN1044V-Q1 has it as VIO. The Verdin's I/O is 1.8 V logic, so ordering
# the non-V part yields a board that assembles perfectly and never talks.
#
# GOTCHA: VCC wants 4.5-5.5 V (so the 5 V rail), while VIO wants the 1.8 V
# rail to match the module. They are different supplies, each needing its
# own 100 nF close to the pin.
# ---------------------------------------------------------------------------
TCAN1044V_Q1 = [
    (1, "TXD",  "input"),
    (2, "GND",  "power_in"),
    (3, "VCC",  "power_in"),        # 4.5-5.5 V
    (4, "RXD",  "output"),
    (5, "VIO",  "power_in"),        # 1.7-5.5 V; 1.8 V here
    (6, "CANL", "bidirectional"),
    (7, "CANH", "bidirectional"),
    (8, "STB",  "input"),           # standby, integrated pull-up
]


# ---------------------------------------------------------------------------
# LM61460-Q1 - automotive 3-36 V, 6 A low-EMI synchronous buck.
# Source: TI SNVSB70F, May 2019, revised June 2021. VQFN-HR-14 (RJR).
#
# GOTCHA: BIAS (1) is not a bypass pin. It feeds the internal LDO and
# should be tied to the OUTPUT rail to improve efficiency - but only while
# Vout is at or below 12 V. Above that the datasheet says tie it to
# ground. At our 5 V output it goes to the output.
#
# GOTCHA: three pins must not float AND must not be grounded - FB (4),
# RT (6) and EN/SYNC (7). Grounding RT is a particularly easy mistake
# since most "set with a resistor to ground" pins tolerate it.
#
# GOTCHA: AGND (3) must connect to BOTH PGND1 (9) and PGND2 (11) on the
# PCB, and VIN1/VIN2 and PGND1/PGND2 each need a low-impedance connection
# to their pair. These are one net electrically but a real layout
# constraint, not something the schematic alone captures.
#
# RBOOT (13) sets the SW-node rise time, so it is the EMI knob on this
# part - relevant here given LVDS shares the enclosure.
# ---------------------------------------------------------------------------
LM61460_Q1 = [
    (1,  "BIAS",     "power_in"),
    (2,  "VCC",      "power_out"),   # internal LDO; 1 uF to AGND, no ext load
    (3,  "AGND",     "power_in"),
    (4,  "FB",       "input"),       # do not float or ground
    (5,  "PGOOD",    "open_collector"),
    (6,  "RT",       "passive"),     # 5.76k-66.5k to GND -> 200k-2200 kHz
    (7,  "EN/SYNC",  "input"),       # do not float; doubles as sync input
    (8,  "VIN1",     "power_in"),
    (9,  "PGND1",    "power_in"),
    (10, "SW",       "output"),
    (11, "PGND2",    "power_in"),
    (12, "VIN2",     "power_in"),
    (13, "RBOOT",    "passive"),     # SW rise time / EMI
    (14, "CBOOT",    "passive"),     # 100 nF to SW
]


# ---------------------------------------------------------------------------
# TLV767-Q1 - automotive 16 V, 1 A linear regulator, adjustable version.
# Source: TI SBVS381A, April 2020, revised December 2020. 8-pin WSON (DRB).
#
# Chosen as an LDO rather than a buck deliberately: the 1.8 V rail feeds
# the DSI-to-LVDS bridge and the CAN transceiver's VIO, the load is small,
# and a linear regulator contributes no switching noise to a board that
# already has LVDS sharing an enclosure.
#
# GOTCHA: pin 3 differs between versions - FB on the adjustable part,
# SNS on the fixed part. This design uses the ADJUSTABLE version, so
# pin 3 is FB and drives the output through an external divider. Neither
# may float.
#
# NOTE (contrast with the LM74930-Q1 above): this thermal pad MAY be
# grounded - "connect this pad to ground or leave floating", and a large
# ground plane is preferred for thermals. Do not generalise either part's
# pad rule to the other.
# ---------------------------------------------------------------------------
TLV767_Q1 = [
    (1, "OUT", "power_out"),
    (2, "NC1", "no_connect"),   # not internally connected; may tie to GND
    (3, "FB",  "input"),        # adjustable version; do not float
    (4, "GND", "power_in"),
    (5, "EN",  "input"),        # internal pull-up; may float to enable
    (6, "GND2", "power_in"),
    (7, "NC2", "no_connect"),
    (8, "IN",  "power_in"),
    (9, "EP",  "passive"),      # exposed pad; grounded on this part
]


# ---------------------------------------------------------------------------
# SN65DSI85-Q1 - automotive dual-channel MIPI DSI to dual-link LVDS bridge.
# Source: TI SLLSEJ4B, July 2016, revised June 2018. HTQFP-64 (PAP).
#
# This board uses datasheet Table 5 mode "Single DSI Input to Dual-Link
# LVDS": DSI channel A only, four lanes, out to both LVDS links with odd
# pixels on A and even on B - same mode fascia-pcb uses, kept as a known-
# good default here even though this board's real target (a ~1920x540
# bar panel, meaningfully lower total pixel throughput than fascia's
# 1920x1200) may not actually need dual-link. Whether the real panel
# (cluster-pcb README's Step 1: STARTEK KD167FHFLA001, no public
# datasheet yet) needs single- or dual-link LVDS is a real open item -
# see README's "Real open risks".
#
# GOTCHA: VCORE (31) is an OUTPUT, not a supply input - it is the 1.1 V
# internal regulator rail and needs a 1 uF capacitor to ground. Feeding
# it would destroy the part.
#
# GOTCHA: RSVD1 (34) and RSVD2 (1) "must be left unconnected for normal
# operation". Not grounded, not pulled - unconnected.
#
# GOTCHA: the unused DSI channel B inputs must ALSO be left unconnected.
# The datasheet states it twice: in the pin table and again under
# CHA_DSI_LANES ("Unused DSI input pins ... must be left unconnected").
#
# GOTCHA: REFCLK (17) is optional - the pixel clock can come from the
# free-running D-PHY clock - but if unused it must be pulled to ground
# through a resistor, not left floating.
#
# GOTCHA: ADDR (64), when strapped high, must tie to the SAME 1.8 V rail
# that feeds VCC, not to any other 1.8 V source.
#
# NOTE: PowerPAD is reference ground here, so it DOES get grounded -
# unlike the LM74930-Q1 pad above. Check each part; do not generalise.
# ---------------------------------------------------------------------------
SN65DSI85_Q1 = [
    (1,  "RSVD2",  "no_connect"),
    (2,  "EN",     "input"),
    (3,  "VCC1",   "power_in"),
    (4,  "DB0P",   "input"),  (5,  "DB0N",  "input"),
    (6,  "DB1P",   "input"),  (7,  "DB1N",  "input"),
    (8,  "DBCP",   "input"),  (9,  "DBCN",  "input"),
    (10, "DB2P",   "input"),  (11, "DB2N",  "input"),
    (12, "DB3P",   "input"),  (13, "DB3N",  "input"),
    (14, "VCC2",   "power_in"),
    (15, "SCL",    "input"),
    (16, "SDA",    "bidirectional"),
    (17, "REFCLK", "input"),
    (18, "VCC3",   "power_in"),
    (19, "DA0P",   "input"),  (20, "DA0N",  "input"),
    (21, "DA1P",   "input"),  (22, "DA1N",  "input"),
    (23, "GND1",   "power_in"),
    (24, "DACP",   "input"),  (25, "DACN",  "input"),
    (26, "GND2",   "power_in"),
    (27, "DA2P",   "input"),  (28, "DA2N",  "input"),
    (29, "DA3P",   "input"),  (30, "DA3N",  "input"),
    (31, "VCORE",  "power_out"),   # 1.1 V regulator OUTPUT; 1 uF to GND
    (32, "VCC4",   "power_in"),
    (33, "IRQ",    "output"),
    (34, "RSVD1",  "no_connect"),
    (35, "VCC5",   "power_in"),
    (36, "A_Y3P",  "output"), (37, "A_Y3N", "output"),
    (38, "A_CLKP", "output"), (39, "A_CLKN", "output"),
    (40, "VCC6",   "power_in"),
    (41, "A_Y2P",  "output"), (42, "A_Y2N", "output"),
    (43, "VCC7",   "power_in"),
    (44, "A_Y1P",  "output"), (45, "A_Y1N", "output"),
    (46, "A_Y0P",  "output"), (47, "A_Y0N", "output"),
    (48, "VCC8",   "power_in"),
    (49, "VCC9",   "power_in"),
    (50, "B_Y3P",  "output"), (51, "B_Y3N", "output"),
    (52, "GND3",   "power_in"),
    (53, "B_CLKP", "output"), (54, "B_CLKN", "output"),
    (55, "VCC10",  "power_in"),
    (56, "B_Y2P",  "output"), (57, "B_Y2N", "output"),
    (58, "VCC11",  "power_in"),
    (59, "B_Y1P",  "output"), (60, "B_Y1N", "output"),
    (61, "B_Y0P",  "output"), (62, "B_Y0N", "output"),
    (63, "VCC12",  "power_in"),
    (64, "ADDR",   "input"),
    (65, "EP",     "passive"),      # PowerPAD is reference ground here
]


def verify():
    """Sanity-check the tables before anything builds symbols from them."""
    problems = []
    for name, pins in (("LM74930_Q1", LM74930_Q1),
                       ("TCAN1044V_Q1", TCAN1044V_Q1),
                       ("LM61460_Q1", LM61460_Q1),
                       ("TLV767_Q1", TLV767_Q1),
                       ("SN65DSI85_Q1", SN65DSI85_Q1)):
        numbers = [p[0] for p in pins]
        if numbers != list(range(1, len(pins) + 1)):
            problems.append(f"{name}: pin numbers are not 1..{len(pins)} "
                            f"contiguous: {numbers}")
        if len(set(p[1] for p in pins)) != len(pins):
            problems.append(f"{name}: duplicate pin names")

    # Both parts are known-size packages; assert the counts so a careless
    # edit that drops a pin is caught here rather than in the netlist.
    if len(LM74930_Q1) != 25:
        problems.append(f"LM74930_Q1 should have 25 pins (24 + exposed pad), has {len(LM74930_Q1)}")
    if len(TCAN1044V_Q1) != 8:
        problems.append(f"TCAN1044V_Q1 should have 8 pins, "
                        f"has {len(TCAN1044V_Q1)}")
    if len(LM61460_Q1) != 14:
        problems.append(f"LM61460_Q1 should have 14 pins, "
                        f"has {len(LM61460_Q1)}")
    if len(TLV767_Q1) != 9:
        problems.append(f"TLV767_Q1 should have 9 pins (8 + EP), has {len(TLV767_Q1)}")
    if len(SN65DSI85_Q1) != 65:
        problems.append(f"SN65DSI85_Q1 should have 65 pins (64 + EP), "
                        f"has {len(SN65DSI85_Q1)}")
    # The bridge has twelve separate VCC pins and they must all reach the
    # 1.8 V rail; a dropped one is a brownout nobody sees on the drawing.
    ncc = sum(1 for _, n, _ in SN65DSI85_Q1 if n.startswith("VCC"))
    if ncc != 12:
        problems.append(f"SN65DSI85_Q1 should have 12 VCC pins, has {ncc}")
    return problems


if __name__ == "__main__":
    import sys

    problems = verify()
    for name, pins in (("LM74930-Q1 (VQFN-24)", LM74930_Q1),
                       ("TCAN1044V-Q1 (SOIC-8)", TCAN1044V_Q1),
                       ("LM61460-Q1 (VQFN-HR-14)", LM61460_Q1),
                       ("TLV767-Q1 (WSON-8)", TLV767_Q1),
                       ("SN65DSI85-Q1 (HTQFP-64)", SN65DSI85_Q1)):
        print(f"\n=== {name}: {len(pins)} pins ===")
        for num, pname, etype in pins:
            print(f"   {num:2d}  {pname:<8s} {etype}")
    print()
    if problems:
        print("PART TABLES INVALID:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("part tables OK")


# ---------------------------------------------------------------------------
# Footprint assignments.
#
# All but one come from KiCad's own libraries, and build_schematic.py
# verifies at build time that every file named here actually exists -
# a typo in a footprint name is otherwise invisible until the netlist is
# imported into the PCB editor.
#
# Exposed pads are pad N+1 in every one of these footprints (65 on the
# TQFP-64, 25 on the VQFN-24), which is why the pin tables above carry an
# explicit EP pin.
# ---------------------------------------------------------------------------
FOOTPRINTS = {
    # The Verdin module plugs into a standard DDR4 SODIMM socket, and
    # KiCad's footprint has exactly 260 pads numbered 1-260 - a direct
    # match for the extracted pinout.
    "Verdin_iMX95_X1": "Connector_PCBEdge:SODIMM-260_DDR4_H4.0-5.2_OrientationStd_Socket",
    "LM74930-Q1":      "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm",
    "TLV767-Q1":       "Package_DFN_QFN:Texas_DRB0008A",
    "TCAN1044V-Q1":    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SN65DSI85-Q1":    "Package_QFP:Texas_TQFP-64-1EP_10x10mm_P0.5mm_EP8x8mm_Mask4.44x4.44mm",
    # Generated rather than from a KiCad library: the RJR (VQFN-HR-14)
    # package has no stock footprint. See fascia-pcb/tools/build_lm61460_footprint.py
    # (reused verbatim - same real part, same real package).
    "LM61460-Q1":      "TI_RJR0014A_VQFN-HR:TI_RJR0014A_VQFN-HR-14_4x3.5mm",
    "R":    "Resistor_SMD:R_0603_1608Metric",
    "C":    "Capacitor_SMD:C_0603_1608Metric",
    "L":    "Inductor_SMD:L_1210_3225Metric",
    "TVS":  "Diode_SMD:D_SMB",
    "FUSE": "Fuse:Fuse_Bourns_MF-RG300",
    "NFET": "Package_TO_SOT_SMD:SOT-23",

    # Connectors. These are PROVISIONAL - 2.54 mm pin headers standing in
    # so the board can be placed and routed end to end, same convention
    # fascia-pcb uses for its own not-yet-finalised connectors.
    # CONN_PANEL waits on the real STARTEK KD167FHFLA001 datasheet (or
    # whichever bar panel is finally ordered) - real pin count/pitch
    # unconfirmed, same open item as fascia-pcb's own CONN_PANEL was at
    # this stage.
    "CONN3":      "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "CONN_CAN":   "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "CONN_PANEL": "Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical",
    "CONN_JTAG":  "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
    "CONN_BTN":   "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "CONN_CELL":  "Battery:BatteryHolder_Keystone_1058_1x2032",
}
