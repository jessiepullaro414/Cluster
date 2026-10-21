"""
expected.py - what each IC's pins MUST connect to, written from the datasheets
rather than from the schematic generator.

Every IC block cites the datasheet and revision it was transcribed from. A pin
rule is a tuple:

    ("net", "GND")                  the pin sits on this exact net
    ("nets", ["+5V", "VIN_PROT"])   ... on any of these nets
    ("nc",)                         must be left unconnected (no other pin on the net)
    ("same", "16")                  same net as another pin of the same IC (pin number)
    ("r", NET, lo, hi)              a resistor of lo..hi ohms joins this pin's net to NET
    ("c", NET, lo)                  a capacitor >= lo farads joins this pin's net to NET
    ("fn", "CAN0_TX")               MCU only: the pin's alternate-function list must include this
    ("free",)                       signal pin; wiring is design intent, only the pin name is checked

"names" is the datasheet pin name for every pin number (a symbol whose pin NAMES
disagree with the datasheet is a wiring bug waiting to happen, so those are
checked too).  "decap" lists the datasheet's decoupling requirement per supply
pin: nominal capacitance (before DC-bias loss) and how close it must sit.

Status words used in the report:  READ = I read the pin table in the datasheet
text in this review (revision given);  PRIOR = only the earlier sessions'
transcription (parts.py) was available, flagged as unverified here.
"""

# ---------------------------------------------------------------------------
# gauges/
# ---------------------------------------------------------------------------
GAUGES = {}

GAUGES["U1"] = dict(
    part="NXP S32K144, LQFP-64", status="READ",
    ds="NXP S32K1xx Data Sheet Rev. 15 (5 Mar 2026) tables 1, 7 + S32K144 IO signal xlsx (RM 14.2 attachment) sheets Pinout/Supplies",
    mcu_json="s32k144_lqfp64.json",
    pins={
        # supplies and fixed pins
        7: ("VDD", [("net", "+3V3")]), 41: ("VDD", [("net", "+3V3")]),
        8: ("VDDA", [("net", "VDDA")]), 9: ("VREFH", [("same", "8")]),
        10: ("VSS", [("net", "GND")]), 40: ("VSS", [("net", "GND")]),
        11: ("EXTAL", [("net", "OSC_IN")]), 12: ("XTAL", [("net", "OSC_OUT")]),
        63: ("RESET_b", [("net", "RESET"), ("r", "+3V3", 4.7e3, 100e3)]),
        62: ("SWD_CLK", [("net", "SWCLK")]), 64: ("SWD_DIO", [("net", "SWDIO")]),
        # peripheral pins: net + required alternate function
        5: ("PTE5", [("net", "CAN0_TX"), ("fn", "CAN0_TX")]),
        6: ("PTE4", [("net", "CAN0_RX"), ("fn", "CAN0_RX")]),
        51: ("PTC7", [("net", "CAN1_TX"), ("fn", "CAN1_TX")]),
        52: ("PTC6", [("net", "CAN1_RX"), ("fn", "CAN1_RX")]),
        29: ("PTC15", [("net", "LPSPI2_SCK_MCU"), ("fn", "LPSPI2_SCK")]),   # 33 ohm series resistor R84 to the shared bus
        26: ("PTC0", [("net", "LPSPI2_SIN"), ("fn", "LPSPI2_SIN")]),
        25: ("PTC1", [("net", "LPSPI2_SOUT_MCU"), ("fn", "LPSPI2_SOUT")]),  # 33 ohm series resistor R85
        30: ("PTC14", [("nc",)]),
        50: ("PTA0", [("net", "ADC_FUEL"), ("fn", "ADC0_SE0")]),
        49: ("PTA1", [("net", "ADC_OIL"), ("fn", "ADC0_SE1")]),
        48: ("PTA2", [("net", "ADC_TEMP"), ("fn", "ADC1_SE0")]),
        47: ("PTA3", [("net", "ADC_BATT"), ("fn", "ADC1_SE1")]),
        31: ("PTB3", [("net", "DIM_ADC"), ("fn", "ADC0_SE7")]),
        58: ("PTA10", [("net", "SPEED_IN"), ("fn", "FTM1_CH4")]),
        57: ("PTA11", [("net", "TACH_IN"), ("fn", "FTM1_CH5")]),
        59: ("PTE1", [("net", "IGN_SENSE"), ("fn", "PTE1")]),
        60: ("PTE0", [("net", "CAN1_STB"), ("fn", "PTE0")]),
        13: ("PTE3", [("net", "AUX_CS0"), ("fn", "PTE3")]),
        14: ("PTD16", [("net", "AUX_CS1"), ("fn", "PTD16")]),
        15: ("PTD15", [("net", "AUX_CS2"), ("fn", "PTD15")]),
        16: ("PTE9", [("net", "AUX_CS3"), ("fn", "PTE9")]),
        17: ("PTE8", [("net", "AUX_DC0"), ("fn", "PTE8")]),
        22: ("PTD7", [("net", "AUX_DC1"), ("fn", "PTD7")]),
        23: ("PTD6", [("net", "AUX_DC2"), ("fn", "PTD6")]),
        24: ("PTD5", [("net", "AUX_DC3"), ("fn", "PTD5")]),
        42: ("PTB13", [("net", "AUX_RST"), ("fn", "PTB13")]),
        39: ("PTE7", [("net", "BL_EN"), ("fn", "PTE7")]),
        18: ("PTB5", [("net", "CAN0_EN"), ("fn", "PTB5")]),
        19: ("PTB4", [("net", "CAN0_STB_N"), ("fn", "PTB4")]),
        35: ("PTC9", [("net", "LAMP_TURN_L"), ("fn", "PTC9")]),
        36: ("PTC8", [("net", "LAMP_TURN_R"), ("fn", "PTC8")]),
        37: ("PTA7", [("net", "LAMP_HIGH_BEAM"), ("fn", "PTA7")]),
        38: ("PTA6", [("net", "LAMP_BRAKE"), ("fn", "PTA6")]),
        43: ("PTB12", [("net", "LAMP_ALT"), ("fn", "PTB12")]),
        44: ("PTD4", [("net", "LAMP_OIL"), ("fn", "PTD4")]),
    },
    # datasheet Table 7 + Figure 6 (64 LQFP): one CDEC per VDD pin, CREF on VREFH/VDDA,
    # >= 70 nF effective after aging/tolerance, placed within 2 mm of the pin
    decap=[
        dict(pin="7", net="+3V3", min_nom=100e-9, max_mm=4.0, why="CDEC per VDD pin (DS Table 7 note 7: <= 2 mm from the pin; max_mm here is pad centre to pad centre, which adds about 2 mm of pad geometry)"),
        dict(pin="41", net="+3V3", min_nom=100e-9, max_mm=4.0, why="CDEC per VDD pin"),
        dict(pin="8", net="VDDA", min_nom=100e-9, max_mm=4.5, why="CREF/CDEC on VDDA/VREFH (>= 70 nF; 10 uF + 0.1 uF + 1 nF recommended for the ADC reference)"),
        dict(pin="9", net="VDDA", min_nom=100e-9, max_mm=4.5, why="CREF on VREFH"),
    ],
)

GAUGES["U2"] = dict(
    part="TI LMR33630BRNXRQ1 (1.4 MHz 'B' option), 12-pin VQFN-HR RNX", status="READ",
    ds="TI SNVSB26C (Oct 2020) section 5, tables 5-1, 6.1, 6.3, 8.2.2",
    pins={
        1: ("PGND", [("net", "GND")]), 11: ("PGND", [("net", "GND")]),
        2: ("VIN", [("net", "VIN_PROT")]), 10: ("VIN", [("net", "VIN_PROT")]),
        # datasheet: "On the VQFN package connect the SW pin to NC on the PCB"
        3: ("NC", [("net", "SW")]),
        12: ("SW", [("net", "SW")]),
        4: ("BOOT", [("c", "SW", 100e-9)]),
        5: ("VCC", [("c", "GND", 1e-6)]),            # 1 uF, 16 V ceramic, no external load
        6: ("AGND", [("net", "GND")]),
        7: ("FB", [("r", "GND", 1e3, 100e3)]),       # divider; never floated or grounded
        8: ("PG", [("nc",)]),                        # open drain, may be left open
        9: ("EN", [("net", "VIN_PROT")]),            # may be tied straight to VIN, never floated
    },
    decap=[
        dict(pin="2", net="VIN_PROT", min_nom=100e-9, max_mm=4.5, why="DS 8.2.2.6: 220 nF X7R 50 V HF bypass at VIN + split 10 uF bulk (one at each VIN/PGND location)"),
        dict(pin="10", net="VIN_PROT", min_nom=1e-6, max_mm=4.5, why="DS 8.2.2.6: >= 10 uF ceramic in total at VIN (split across both VIN pins)"),
        dict(pin="5", net="VCC_INT", min_nom=1e-6, max_mm=4.5, why="DS 8.2.2.8: 1 uF 16 V ceramic VCC to GND"),
    ],
)

GAUGES["U3"] = dict(
    part="TI LM74930QRGERQ1, 24-pin VQFN + exposed pad", status="READ",
    ds="TI SNOSDF6 (Oct 2023) section 5, table 5-1, 6.1, 8.2",
    pins={
        1: ("DGATE", [("net", "DGATE")]), 2: ("A", [("net", "COMMON")]),
        3: ("SW", [("net", "SW_SENSE")]),
        4: ("UVLO", [("net", "UVLO_DIV")]), 5: ("OV", [("net", "OV_DIV")]),
        6: ("EN", [("net", "VIN_FUSED")]), 7: ("MODE", [("net", "VIN_FUSED")]),
        8: ("N.C", [("nc",)]),
        9: ("TMR", [("c", "GND", 10e-9)]),
        10: ("IMON", [("nc",)]),                      # "if unused, leave floating"
        11: ("ILIM", [("r", "GND", 10e3, 500e3)]),
        12: ("FLT", [("nc",)]),
        13: ("GND", [("net", "GND")]),
        14: ("HGATE", [("net", "HGATE")]), 15: ("OUT", [("net", "COMMON")]),
        16: ("OVCLAMP", [("same", "5")]),            # tied to OV = clamp with circuit breaker
        17: ("N.C", [("nc",)]),
        18: ("ISCP", [("same", "24")]),              # tied to C = internal 20 mV SCP threshold
        19: ("CS-", [("net", "SENSE_OUT")]),
        20: ("CS+", [("r", "VIN_FUSED", 49.9, 100)]),  # 50-100 ohm RSET to the sense resistor
        21: ("N.C", [("nc",)]),
        22: ("VS", [("net", "VIN_FUSED"), ("c", "GND", 100e-9)]),
        23: ("CAP", [("c", "VIN_FUSED", 100e-9)]),
        24: ("C", [("net", "VIN_PROT")]),
        25: ("RTN", [("nc",)]),                       # "Leave exposed pad floating. Do not connect to GND plane"
    },
    decap=[
        dict(pin="22", net="VIN_FUSED", min_nom=100e-9, max_mm=8.0, why="VS: 100 nF to GND (pin table); TI's 8.2.2.1 example asks for >= 1 uF (see findings)"),
    ],
)

GAUGES["U4"] = dict(
    part="TI TLV73333PQDBVRQ1 (3.3 V), SOT-23-5", status="READ",
    ds="TI SBVS283F (Oct 2020) table 5-1, 6.1",
    pins={
        1: ("IN", [("net", "+5V")]), 2: ("GND", [("net", "GND")]),
        3: ("EN", [("net", "+5V")]), 4: ("NC", [("nc",)]),
        5: ("OUT", [("net", "+3V3"), ("c", "GND", 1e-6)]),
    },
    decap=[
        dict(pin="1", net="+5V", min_nom=1e-6, max_mm=5.0, why="small input capacitor recommended (DS 8.1.1)"),
        dict(pin="5", net="+3V3", min_nom=1e-6, max_mm=5.0, why="1 uF ceramic on OUT (DS 8.1.1)"),
    ],
)

GAUGES["U5"] = dict(
    part="NXP TJA1043T/1J, SO-14", status="READ",
    ds="NXP TJA1043 Rev. 6 (10 Nov 2017) table 3, 6 (limiting values), 7.6",
    pins={
        1: ("TXD", [("net", "CAN0_TX")]), 2: ("GND", [("net", "GND")]),
        3: ("VCC", [("net", "+5V")]), 4: ("RXD", [("net", "CAN0_RX")]),
        5: ("VIO", [("net", "+3V3")]),                  # 2.8 V .. VCC
        6: ("EN", [("net", "CAN0_EN")]), 7: ("INH", [("nc",)]), 8: ("ERR_N", [("nc",)]),
        9: ("WAKE", [("nets", ["GND", "VIN_PROT"])]),   # unused: tie to VBAT or GND for EMC (7.6)
        10: ("VBAT", [("net", "VIN_PROT")]),
        11: ("SPLIT", [("net", "CAN0_SPLIT")]),
        12: ("CANL", [("net", "CAN0_L")]), 13: ("CANH", [("net", "CAN0_H")]),
        14: ("STB_N", [("net", "CAN0_STB_N")]),
    },
    decap=[
        dict(pin="3", net="+5V", min_nom=100e-9, max_mm=5.0, why="100 nF on VCC (typical application)"),
        dict(pin="5", net="+3V3", min_nom=100e-9, max_mm=5.0, why="100 nF on VIO"),
        dict(pin="10", net="VIN_PROT", min_nom=100e-9, max_mm=5.0, why="100 nF on VBAT"),
    ],
)

GAUGES["U10"] = dict(
    part="TI TCAN1044VDRQ1, SOIC-8 (V suffix = VIO pin)", status="READ",
    ds="TI SLLSF17D (Mar 2025) section 5, 6.1, 6.3, 6.4",
    pins={
        1: ("TXD", [("net", "CAN1_TX")]), 2: ("GND", [("net", "GND")]),
        3: ("VCC", [("net", "+5V")]), 4: ("RXD", [("net", "CAN1_RX")]),
        5: ("VIO", [("net", "+3V3")]),
        6: ("CANL", [("net", "CAN1_L")]), 7: ("CANH", [("net", "CAN1_H")]),
        8: ("STB", [("net", "CAN1_STB")]),
    },
    decap=[
        dict(pin="3", net="+5V", min_nom=100e-9, max_mm=5.0, why="100 nF on VCC (DS 9.4)"),
        dict(pin="5", net="+3V3", min_nom=100e-9, max_mm=5.0, why="100 nF on VIO"),
    ],
)

# Raystar RFA401280B-AYW-DNF1 18-pin FPC, the same table four times
_GC9A01 = {
    1: ("TP_INT", [("nc",)]), 2: ("TP_SDA", [("nc",)]), 3: ("TP_SCL", [("nc",)]),
    4: ("TP_RESET", [("nc",)]), 5: ("TP_GND", [("net", "GND")]), 6: ("TP_VDD3.3V", [("nc",)]),
    7: ("VLED+", [("r", "+5V", 50, 400)]), 8: ("VLED-", [("net", "AUX_VLED_RTN")]),
    9: ("GND", [("net", "GND")]), 10: ("CS", [("free",)]), 11: ("SCL", [("net", "LPSPI2_SCK")]),
    12: ("SDA", [("net", "LPSPI2_SOUT")]), 13: ("RS", [("free",)]), 14: ("TE", [("nc",)]),
    15: ("RESET", [("net", "AUX_RST")]), 16: ("VCI3.3V", [("net", "+3V3")]),
    17: ("NC", [("nc",)]), 18: ("GND", [("net", "GND")]),
}
for _u, _cs, _dc in (("U6", "AUX_CS0", "AUX_DC0"), ("U7", "AUX_CS1", "AUX_DC1"),
                     ("U8", "AUX_CS2", "AUX_DC2"), ("U9", "AUX_CS3", "AUX_DC3")):
    _pins = dict(_GC9A01)
    _pins[10] = ("CS", [("net", _cs)])
    _pins[13] = ("RS", [("net", _dc)])
    GAUGES[_u] = dict(part="Raystar RFA401280B-AYW-DNF1 module via Amphenol F32Q-1A7H1-11018 FPC", status="READ",
                      ds="Raystar RFA401280B-AYW-DNF1 datasheet p3 (pin table), p5 (ratings); GC9A01A datasheet 7.1",
                      pins=_pins,
                      decap=[dict(pin="16", net="+3V3", min_nom=100e-9, max_mm=8.0,
                                  why="100 nF at the VCI feed (module has its own on-FPC decoupling)")])

# Abracon ABM8AIG-8.000MHZ-12-2Z: "Pin #1: Crystal, Pin #2: GND, Pin #3: Crystal, Pin #4: GND" (Abracon ABM8AIG datasheet)
GAUGES["Y1"] = dict(
    part="Abracon ABM8AIG-8.000MHZ-12-2Z-T3, 3.2 x 2.5 mm", status="READ",
    ds="Abracon ABM8AIG datasheet, pad connections",
    pins={1: ("XTAL1", [("net", "OSC_IN")]), 2: ("GND", [("net", "GND")]),
          3: ("XTAL2", [("net", "OSC_OUT")]), 4: ("GND", [("net", "GND")])},
)

# connector TVS arrays: Littelfuse SM24CANB-02HTG, pins 1 and 2 are the lines, pin 3 the common (datasheet Rev 10/09/17)
for _d, _a, _b in (("D28", "CAN0_H", "CAN0_L"), ("D29", "SENDER_FUEL", "SENDER_OIL"), ("D30", "SENDER_TEMP", None),
                   ("D31", "CAN1_H", "CAN1_L"), ("D32", "SPEED_RAW", None)):
    GAUGES[_d] = dict(part="Littelfuse SM24CANB-02HTG dual 24 V TVS", status="READ",
                      ds="Littelfuse SM24CANB series datasheet Rev. 10/09/17 (pin 1 or 2 to pin 3; VRWM 24 V)",
                      pins={1: ("IO1", [("net", _a)]), 2: ("IO2", [("net", _b)] if _b else [("nc",)]), 3: ("COM", [("net", "GND")])})

# +3V3 rail clamp (G-08): onsemi SZMMSZ3V6T1G, SOD-123, pad 1 cathode (KiCad D_SOD-123), distributor-listed ratings only
GAUGES["D33"] = dict(
    part="onsemi SZMMSZ3V6T1G 3.6 V zener", status="PRIOR",
    ds="DigiKey listing (AEC-Q101, 500 mW, Zzt 90 ohm max, 5 uA at 1 V); onsemi datasheet not retrievable",
    pins={1: ("K", [("net", "+3V3")]), 2: ("A", [("net", "GND")])},
)

# Tag-Connect TC2030-IDC-NL: the cable the programmer plugs in expects exactly this order
# (Tag-Connect TC2030-CTX datasheet): 1 VCC, 2 SWDIO, 3 nRESET, 4 SWCLK, 5 GND, 6 SWO
GAUGES["J2"] = dict(
    part="Tag-Connect TC2030-IDC-NL footprint", status="READ",
    ds="Tag-Connect TC2030-CTX datasheet ('6-Pin TC2030 Footprint' column)",
    pins={
        1: ("VCC", [("net", "+3V3")]), 2: ("SWDIO", [("net", "SWDIO")]),
        3: ("nRESET", [("net", "RESET")]), 4: ("SWCLK", [("net", "SWCLK")]),
        5: ("GND", [("net", "GND")]), 6: ("SWO", [("nc",)]),
    },
)

# LM74930 FET pair since 2026-10-18: Vishay SQJ460AEP, PowerPAK SO-8L, pins 1-3 source, 4 gate, 5 (tab) drain
SQJ460AEP_DS = "Vishay SQJ460AEP S22-0167 Rev. D 14-Feb-2022 page 1 (pinning, ratings)"
for _q, g, d in (("Q1", "DGATE", "VIN_PROT"), ("Q3", "HGATE", "SENSE_OUT")):
    GAUGES[_q] = dict(part="Vishay SQJ460AEP", status="READ", ds=SQJ460AEP_DS,
                      pins={1: ("S", [("net", "COMMON")]), 2: ("S", [("net", "COMMON")]),
                            3: ("S", [("net", "COMMON")]), 4: ("G", [("net", g)]), 5: ("D", [("net", d)])})
# PMV55ENEA (SOT23, Nexperia 21 Mar 2016 table 2): pin 1 = gate, 2 = source, 3 = drain; still display/ Q3
PMV55ENEA_DS = "Nexperia PMV55ENEA 21 Mar 2016 table 2, 5, 7"
GAUGES["Q2"] = dict(part="Nexperia PMV37ENEA", status="PRIOR",
                    ds="pin order assumed identical to PMV55ENEA (same SOT23 outline and series); datasheet not retrievable here",
                    pins={1: ("G", [("net", "BL_GATE")]), 2: ("S", [("net", "GND")]),
                          3: ("D", [("net", "AUX_VLED_RTN")])})
# BAV99-Q (SOT23): 1 = anode 1, 2 = cathode 2, 3 = common (Nexperia BAV99 series Rev 8, table 3)
for _d in (["D10", "D11", "D12", "D13", "D14", "D15"] + [f"D{n}" for n in range(16, 24)]):
    GAUGES[_d] = dict(part="Nexperia BAV99-Q clamp", status="READ",
                      ds="Nexperia BAV99 series Rev. 8: pin 1 anode D1, pin 2 cathode D2, pin 3 common",
                      pins={1: ("A1", [("net", "GND")]), 2: ("K2", [("net", "+3V3")]),
                            3: ("CA", [("free",)])})
for _d in ("D24", "D25"):
    GAUGES[_d] = dict(part="Nexperia BAV99-Q reverse clamp (arrow LED)", status="READ",
                      ds="Nexperia BAV99 series Rev. 8",
                      pins={1: ("A1", [("net", "GND")]), 2: ("K2", [("nc",)]), 3: ("CA", [("free",)])})
for _d in ("D26", "D27"):
    GAUGES[_d] = dict(part="ROHM CSL0902ET1C green LED", status="READ",
                      ds="ROHM CSL0902ET1(C) Rev.007 figure 1 (cathode index)",
                      pins={1: ("K", [("net", "GND")]), 2: ("A", [("free",)])})

# ---------------------------------------------------------------------------
# display/  (git HEAD while another session is editing the working tree)
# ---------------------------------------------------------------------------
DISPLAY = {}

DISPLAY["U1"] = dict(
    part="TI LM74930-Q1", status="READ", ds=GAUGES["U3"]["ds"],
    pins={
        1: ("DGATE", [("net", "DGATE")]), 2: ("A", [("net", "COMMON")]),
        3: ("SW", [("net", "SW_SENSE")]), 4: ("UVLO", [("net", "UVLO_DIV")]),
        5: ("OV", [("net", "OV_DIV")]), 6: ("EN", [("net", "VBAT_F")]),
        7: ("MODE", [("net", "VBAT_F")]), 8: ("N.C", [("nc",)]),
        9: ("TMR", [("c", "GND", 10e-9)]), 10: ("IMON", [("free",)]),
        11: ("ILIM", [("r", "GND", 10e3, 500e3)]), 12: ("FLT", [("free",)]),
        13: ("GND", [("net", "GND")]), 14: ("HGATE", [("net", "HGATE")]),
        15: ("OUT", [("net", "COMMON")]), 16: ("OVCLAMP", [("same", "5")]),
        17: ("N.C", [("nc",)]), 18: ("ISCP", [("same", "24")]),
        19: ("CS-", [("net", "SENSE_OUT")]), 20: ("CS+", [("r", "VBAT_F", 49.9, 100)]),
        21: ("N.C", [("nc",)]), 22: ("VS", [("net", "VBAT_F"), ("c", "GND", 100e-9)]),
        23: ("CAP", [("c", "VBAT_F", 100e-9)]), 24: ("C", [("net", "+12V_PROT")]),
        25: ("RTN", [("nc",)]),
    },
    decap=[dict(pin="22", net="VBAT_F", min_nom=100e-9, max_mm=5.0, why="VS 100 nF")],
)

DISPLAY["U2"] = dict(
    part="TI LM61460-Q1 (RJR VQFN-HR-14), 2.1 MHz, 5 V", status="READ",
    ds="TI SNVSB70F (Jun 2021) table 7-1, 8.1, 8.3",
    pins={
        1: ("BIAS", [("net", "+5V")]),                       # Vout <= 12 V: tie to output
        2: ("VCC", [("c", "GND", 1e-6)]),
        3: ("AGND", [("net", "GND")]),
        4: ("FB", [("r", "GND", 1e3, 1e6)]),
        5: ("PGOOD", [("r", "+5V", 10e3, 1e6)]),
        6: ("RT", [("r", "GND", 5.76e3, 66.5e3)]),           # never floated or grounded
        7: ("EN/SYNC", [("r", "GND", 1e3, 1e6)]),            # never floated
        8: ("VIN1", [("net", "+12V_PROT")]), 12: ("VIN2", [("net", "+12V_PROT")]),
        9: ("PGND1", [("net", "GND")]), 11: ("PGND2", [("net", "GND")]),
        10: ("SW", [("net", "SW_5V")]),
        13: ("RBOOT", [("r", "BOOT_C", 0, 1e3)]),
        14: ("CBOOT", [("c", "SW_5V", 100e-9)]),
    },
    decap=[
        dict(pin="8", net="+12V_PROT", min_nom=4.7e-6, max_mm=3.0, why="DS: bypass at VIN1/PGND1"),
        dict(pin="12", net="+12V_PROT", min_nom=4.7e-6, max_mm=3.0, why="DS: bypass at VIN2/PGND2"),
        dict(pin="2", net="VCC_LDO", min_nom=1e-6, max_mm=3.0, why="1 uF VCC to AGND"),
    ],
)

DISPLAY["U3"] = dict(
    part="TI TLV767-Q1 adjustable, DRB WSON-8", status="READ",
    ds="TI SBVS381A (Dec 2020) table 5-1, 6.1",
    pins={
        1: ("OUT", [("net", "+1V8"), ("c", "GND", 1e-6)]), 2: ("NC", [("nc",)]),
        3: ("FB", [("r", "GND", 1e3, 1e6)]), 4: ("GND", [("net", "GND")]),
        5: ("EN", [("free",)]), 6: ("GND", [("net", "GND")]), 7: ("NC", [("nc",)]),
        8: ("IN", [("net", "+5V"), ("c", "GND", 1e-6)]), 9: ("EP", [("nets", ["GND"])]),
    },
    decap=[dict(pin="8", net="+5V", min_nom=1e-6, max_mm=5.0, why="CIN >= 1 uF"),
           dict(pin="1", net="+1V8", min_nom=1e-6, max_mm=5.0, why="COUT >= 1 uF")],
)

DISPLAY["U4"] = dict(
    part="TI TCAN1044VDRQ1", status="READ", ds=GAUGES["U10"]["ds"],
    pins={
        1: ("TXD", [("net", "CAN1_TXD")]), 2: ("GND", [("net", "GND")]),
        3: ("VCC", [("net", "+5V")]), 4: ("RXD", [("net", "CAN1_RXD")]),
        5: ("VIO", [("net", "+1V8")]), 6: ("CANL", [("net", "CAN1_L")]),
        7: ("CANH", [("net", "CAN1_H")]), 8: ("STB", [("net", "CAN1_STB")]),
    },
    decap=[dict(pin="3", net="+5V", min_nom=100e-9, max_mm=5.0, why="100 nF VCC"),
           dict(pin="5", net="+1V8", min_nom=100e-9, max_mm=5.0, why="100 nF VIO")],
)

DISPLAY["U6"] = dict(
    part="TI TPS65131-Q1, RGE VQFN-24", status="READ",
    ds="TI SLVSBB2F (Aug 2024) table 5-1, 6.1, 6.3",
    pins={
        1: ("INP", [("net", "PANEL_BOOST_SW")]), 24: ("INP", [("net", "PANEL_BOOST_SW")]),
        2: ("PGND", [("net", "GND")]), 3: ("PGND", [("net", "GND")]),
        4: ("VIN", [("c", "GND", 10e-9)]),
        5: ("INN", [("net", "+5V")]), 6: ("INN", [("net", "+5V")]),
        7: ("BSW", [("nc",)]),                               # leave floating when unused
        8: ("ENP", [("same", "10")]), 10: ("ENN", [("same", "8")]),
        9: ("PSP", [("net", "GND")]), 11: ("PSN", [("net", "GND")]),   # 0 V = power save disabled (forced PWM)
        12: ("NC", [("nc",)]), 20: ("NC", [("nc",)]),
        13: ("OUTN", [("net", "PANEL_INV_SW")]), 14: ("OUTN", [("net", "PANEL_INV_SW")]),
        15: ("VNEG", [("net", "PANEL_VSN")]),
        16: ("FBN", [("r", "PANEL_VREF", 10e3, 1e6)]),       # lower divider resistor goes to VREF, not GND
        17: ("VREF", [("c", "GND", 220e-9)]),
        18: ("CN", [("c", "GND", 1e-9)]), 21: ("CP", [("c", "GND", 1e-9)]),
        19: ("AGND", [("net", "GND")]),
        22: ("FBP", [("r", "GND", 10e3, 1e6)]),
        23: ("VPOS", [("net", "PANEL_VSP")]),
        25: ("PowerPAD", [("net", "GND")]),
    },
    decap=[dict(pin="5", net="+5V", min_nom=4.7e-6, max_mm=3.0, why="4.7 uF at INN (Fig 8-1)"),
           dict(pin="1", net="PANEL_BOOST_SW", min_nom=0, max_mm=99, why="")],
)

DISPLAY["U7"] = dict(
    part="TI TPS61165QDBVRQ1, SOT-23-6", status="READ",
    ds="TI SLVSB73B (May 2015) pin functions, 6.1",
    pins={
        1: ("VIN", [("net", "+5V")]), 2: ("CTRL", [("free",)]), 3: ("SW", [("net", "BL_SW")]),
        4: ("GND", [("net", "GND")]), 5: ("COMP", [("c", "GND", 100e-9)]),
        6: ("FB", [("r", "GND", 0.5, 5)]),
    },
    decap=[dict(pin="1", net="+5V", min_nom=4.7e-6, max_mm=3.0, why="CIN 4.7 uF+ at VIN")],
)

DISPLAY["U8"] = dict(
    part="TI TPS22918QDBVRQ1, SOT-23-6", status="READ",
    ds="TI SLVSCZ8B (Dec 2019) pin functions, 6.1",
    pins={
        1: ("VIN", [("net", "+5V")]), 2: ("GND", [("net", "GND")]),
        3: ("ON", [("free",)]), 4: ("CT", [("nc",)]), 5: ("QOD", [("nc",)]),
        6: ("VOUT", [("net", "DIAL_5V")]),
    },
    decap=[dict(pin="1", net="+5V", min_nom=1e-6, max_mm=5.0, why="CIN >= 1 uF")],
)
# U15 (2026-10-18): the same part switching the MFi daughterboard's 5 V on J16, ON from Verdin GPIO_3
DISPLAY["U15"] = dict(
    part="TI TPS22918QDBVRQ1, SOT-23-6", status="READ",
    ds="TI SLVSCZ8B (Dec 2019) pin functions, 6.1",
    pins={
        1: ("VIN", [("net", "+5V")]), 2: ("GND", [("net", "GND")]),
        3: ("ON", [("net", "MFI_PWR_EN"), ("r", "GND", 10e3, 1e6)]), 4: ("CT", [("nc",)]), 5: ("QOD", [("nc",)]),
        6: ("VOUT", [("net", "MFI_5V")]),
    },
    decap=[dict(pin="1", net="+5V", min_nom=1e-6, max_mm=5.0, why="CIN >= 1 uF")],
)

for _q, g, d in (("Q1", "DGATE", "+12V_PROT"), ("Q2", "HGATE", "SENSE_OUT")):
    DISPLAY[_q] = dict(part="Vishay SQJ460AEP", status="READ", ds=SQJ460AEP_DS,
                       pins={1: ("S1", [("net", "COMMON")]), 2: ("S2", [("net", "COMMON")]),
                             3: ("S3", [("net", "COMMON")]), 4: ("G", [("net", g)]), 5: ("D", [("net", d)])})
DISPLAY["Q3"] = dict(part="Nexperia PMV55ENEA", status="READ", ds=PMV55ENEA_DS,
                     pins={1: ("G", [("free",)]), 2: ("S", [("net", "GND")]), 3: ("D", [("free",)])})
for _d in ("D5", "D6", "D7"):
    DISPLAY[_d] = dict(part="Nexperia BAV99-Q clamp", status="READ", ds=GAUGES["D10"]["ds"],
                       pins={1: ("A1", [("net", "GND")]), 2: ("K2", [("free",)]), 3: ("CA", [("free",)])})

# --- display/ audio and USB host (commit c307bf5), read against their datasheets 2026-10-17 ---
DISPLAY["U9"] = dict(
    part="TI TAC5112-Q1 audio codec, 32-pin QFN", status="READ",
    ds="TI SLASFC2A (Mar 2025) table 4-1, 5.1 (AVDD and IOVDD abs max 3.9 V)",
    pins={1: ("VSS", [("net", "GND")]), 2: ("DREG", [("c", "GND", 1e-6)]), 3: ("BCLK", [("free",)]),
          4: ("FSYNC", [("free",)]), 5: ("DOUT", [("free",)]), 6: ("DIN", [("free",)]),
          7: ("IOVDD", [("net", "+1V8")]), 8: ("VSS", [("net", "GND")]), 9: ("SCL", [("free",)]),
          10: ("SDA", [("free",)]), 11: ("GPIO1", [("free",)]), 12: ("GPIO2", [("free",)]),
          13: ("GPO1", [("free",)]), 14: ("GPI1", [("free",)]), 15: ("VSS", [("net", "GND")]),
          16: ("ADDR", [("nets", ["GND", "+1V8"])]), 17: ("MICBIAS", [("c", "GND", 100e-9)]),
          18: ("IN1P", [("free",)]), 19: ("IN1M", [("free",)]), 20: ("IN2P", [("free",)]), 21: ("IN2M", [("free",)]),
          22: ("VSSI", [("net", "GND")]), 23: ("VSSI", [("net", "GND")]), 24: ("VSSI", [("net", "GND")]),
          25: ("VSSI", [("net", "GND")]), 26: ("VSS", [("net", "GND")]),
          27: ("OUT1M", [("free",)]), 28: ("OUT1P", [("free",)]), 29: ("OUT2P", [("free",)]), 30: ("OUT2M", [("free",)]),
          31: ("AVDD", [("net", "+3V3")]), 32: ("VREF", [("c", "GND", 1e-6)]), 33: ("EP", [("net", "GND")])},   # thermal pad = VSS
    decap=[dict(pin="31", net="+3V3", min_nom=100e-9, max_mm=5.0, why="AVDD decoupling"),
           dict(pin="7", net="+1V8", min_nom=100e-9, max_mm=5.0, why="IOVDD decoupling")],
)
DISPLAY["U10"] = dict(
    part="TI TLV767-Q1 adjustable, 3.3 V audio AVDD", status="READ", ds=DISPLAY["U3"]["ds"],
    pins={1: ("OUT", [("net", "+3V3"), ("c", "GND", 1e-6)]), 2: ("NC", [("nc",)]), 3: ("FB", [("r", "GND", 1e3, 1e6)]),
          4: ("GND", [("net", "GND")]), 5: ("EN", [("free",)]), 6: ("GND", [("net", "GND")]), 7: ("NC", [("nc",)]),
          8: ("IN", [("net", "+5V"), ("c", "GND", 1e-6)]), 9: ("EP", [("nets", ["GND"])])},
)
DISPLAY["U11"] = dict(
    part="TI TPS2557-Q1 USB power switch, DRB", status="READ",
    ds="TI SLVSC97B (Sep 2020) terminal functions, 7.1, IOS table (61.9 k -> 1.61-1.98 A)",
    pins={1: ("GND", [("net", "GND")]), 2: ("IN", [("net", "+5V")]), 3: ("IN", [("net", "+5V")]),
          4: ("EN", [("free",)]), 5: ("ILIM", [("r", "GND", 20e3, 187e3)]), 6: ("OUT", [("net", "USB2_VBUS")]),
          7: ("OUT", [("net", "USB2_VBUS")]), 8: ("FAULT", [("free",)]), 9: ("EP", [("net", "GND")])},
    decap=[dict(pin="2", net="+5V", min_nom=100e-9, max_mm=5.0, why="0.1 uF or more at IN, as close as possible")],
)
for _u, _chs in (("U12", ["LINE_L_P", "LINE_L_N", "LINE_R_P", "LINE_R_N"]), ("U13", ["MIC_P", "MIC_N", None, None]),
                 ("U14", ["USB2_DP", "USB2_DN", "USB2_CC1", "USB2_CC2"])):
    _p = {3: ("GND", [("net", "GND")]), 8: ("GND", [("net", "GND")])}
    # datasheet names pins 1, 2, 4, 5 D1+, D1-, D2+, D2-; the symbol calls them CH1-CH4 (same pins)
    for _k, (_n, _net) in enumerate(zip((1, 2, 4, 5), _chs)):
        _p[_n] = (f"CH{_k + 1}", [("net", _net)] if _net else [("free",)])
    for _n in (6, 7, 9, 10):
        _p[_n] = ("NC", [("nc",)])
    DISPLAY[_u] = dict(part="TI TPD4E05U06-Q1 4-channel ESD, USON-10", status="READ",
                       ds="TI SLVSCO7C pin functions (DQA): 1,2,4,5 channels, 3,8 GND, 6,7,9,10 NC; VRWM 5.5 V, unidirectional (-0.6 V)",
                       pins=_p)
DISPLAY["U12"].update(part="TI TPD4E02B04-Q1 4-channel bidirectional ESD, USON-10",
                      ds="TI SLVSDZ2A pin functions (DQA): 1,2,4,5 IO, 3,8 GND, 6,7,9,10 NC; VRWM +-3.6 V bidirectional")

# Brain board (2026-10-20): display/ without the panel converters; U6 and U7 are
# now the two screen ports' TPS2557-Q1 switches (same datasheet table as U11).
BRAIN = {k: v for k, v in DISPLAY.items() if k not in ("U6", "U7")}
for _u, _p in (("U6", "PORTA"), ("U7", "PORTB")):
    _pins = dict(DISPLAY["U11"]["pins"])
    _pins.update({6: ("OUT", [("net", _p + "_5V")]), 7: ("OUT", [("net", _p + "_5V")])})
    BRAIN[_u] = dict(DISPLAY["U11"], part="TI TPS2557-Q1 screen-port 5 V switch, DRB", pins=_pins)
# TSD panel board: the panel converters moved there with their designators.
PANEL_TSD = {k: DISPLAY[k] for k in ("U6", "U7")}

BOARDS = {"gauges": GAUGES, "display": DISPLAY, "brain": BRAIN, "panel-tsd": PANEL_TSD}
