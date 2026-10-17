"""
Verified pinouts for the display carrier's active parts.

Trimmed from fascia-pcb's own parts.py: this board is a dedicated round-
panel Android carrier (Verdin iMX95 + power tree + CAN). It first dropped
PCM3168A-Q1, SN74AXC4T245-Q1 and TPS2557-Q1; on 2026-10-16 the owner
required wireless Android Auto / CarPlay with sound, so the audio path
(TAC5112-Q1, a smaller 1.8 V-I/O codec instead of fascia's PCM3168A-Q1 +
level shifters) and a USB-C host port (TPS2557-Q1) came back, with their
own tables below. SN65DSI85-Q1 (DSI-to-
LVDS bridge) was here too at one point but is gone as of 2026-09-25:
the real target panel (DisplayModule DM-TFTR50-413) speaks MIPI-DSI
natively, so there's no LVDS anywhere in this board's real requirement
and no bridge chip needed - see build_schematic.py's build_panel().

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
# TPS65131-Q1 - automotive dual-output (positive boost + inverting) LCD
# bias supply: VIN 2.7-5.5 V, VPOS 3.2-15 V, VNEG -15 to -2 V, ~200 mA,
# AEC-Q100 Grade 2. Source: TI SLVSBB2F (Aug 2024), Table 5-1, RGE
# package (VQFN-24, 4x4 mm; package outline RGE0024B, thermal pad 2.45 mm).
# Powers the TST040HDBC-42 panel's +6.5 V / -6.5 V analog rails from +5V.
#
# GOTCHA: VPOS/VNEG are datasheet-typed as sense INPUTS. They are modelled
# as power_out here because they are the nets these converters regulate;
# without a power_out on the net ERC reports the panel's supply pins as
# undriven.
# GOTCHA: BSW (7) is the gate drive for an OPTIONAL external load-disconnect
# PMOS. The datasheet says to leave it floating when unused.
# GOTCHA: the datasheet's own duplicated pins (INP 1/24, PGND 2/3, INN 5/6,
# OUTN 13/14) get distinct names here only so verify() can keep names unique.
# ---------------------------------------------------------------------------
TPS65131_Q1 = [
    (1,  "INP1",  "passive"),      # boost switch pin
    (2,  "PGND1", "power_in"),
    (3,  "PGND2", "power_in"),
    (4,  "VIN",   "power_in"),     # control supply, RC filtered from +5V
    (5,  "INN1",  "power_in"),     # inverter input
    (6,  "INN2",  "power_in"),
    (7,  "BSW",   "output"),       # optional load-disconnect PMOS gate
    (8,  "ENP",   "input"),        # boost enable, VIH 1.4 V min
    (9,  "PSP",   "input"),        # boost power-save (0 V = forced PWM)
    (10, "ENN",   "input"),        # inverter enable
    (11, "PSN",   "input"),        # inverter power-save
    (12, "NC1",   "no_connect"),
    (13, "OUTN1", "passive"),      # inverter switch output
    (14, "OUTN2", "passive"),
    (15, "VNEG",  "power_out"),    # -6.5 V output / sense
    (16, "FBN",   "input"),        # divider to VREF, not GND
    (17, "VREF",  "output"),       # 220 nF to GND
    (18, "CN",    "passive"),      # 4.7 nF comp cap, inverter
    (19, "AGND",  "power_in"),
    (20, "NC2",   "no_connect"),
    (21, "CP",    "passive"),      # 10 nF comp cap, boost
    (22, "FBP",   "input"),        # divider to GND, VFB = 1.213 V
    (23, "VPOS",  "power_out"),    # +6.5 V output / sense
    (24, "INP2",  "passive"),
    (25, "EP",    "power_in"),     # thermal pad -> PGND
]


# ---------------------------------------------------------------------------
# TPS61165-Q1 - automotive boost white-LED driver: VIN 3-18 V, up to 38 V
# out, 1.2 A switch (0.96-1.44 A over temperature), 1.2 MHz, VFB = 0.2 V,
# CTRL = enable + PWM dimming (5-100 kHz), AEC-Q100. Source: TI SLVSB73B
# (May 2015), DBV (SOT-23-6) pin table.
# Drives the TST040HDBC-42 backlight (15 V / 180 mA) from +5V.
# ---------------------------------------------------------------------------
TPS61165_Q1 = [
    (1, "VIN",  "power_in"),
    (2, "CTRL", "input"),          # enable + PWM dimming; ~800k pulldown
    (3, "SW",   "passive"),
    (4, "GND",  "power_in"),
    (5, "COMP", "passive"),        # 220 nF to GND
    (6, "FB",   "input"),          # 0.2 V across the sense resistor
]


# ---------------------------------------------------------------------------
# TPS22918-Q1 - AEC-Q100 Grade 2 load switch, 1-5.5 V, 2 A, 52 mohm. Source:
# TI SLVSCZ8B, DBV (SOT-23-6) pin table. ON is active high with VIH 1.0 V min
# and VIL 0.5 V max, so the Verdin's 1.8 V CTRL_SLEEP_MOCI# drives it
# directly; CIN must be at least 1 uF. Switches the rotary dial's 5 V supply
# off in sleep.
# ---------------------------------------------------------------------------
TPS22918_Q1 = [
    (1, "VIN",  "power_in"),
    (2, "GND",  "power_in"),
    (3, "ON",   "input"),        # active high, do not float
    (4, "CT",   "passive"),      # slew control, may float
    (5, "QOD",  "passive"),      # quick output discharge, left open
    (6, "VOUT", "power_out"),
]


# ---------------------------------------------------------------------------
# TAC5112-Q1 - AEC-Q100 Grade 1 stereo audio codec (2-ch ADC, 2-ch DAC),
# WQFN-32 RTV0032L 5 x 5 mm. Source: TI SLASFC2A (March 2025), Table 4-1 and
# section 8. Replaces the PCM3168A-Q1 + SN74AXC4T245-Q1 + 3.3 V-domain port
# of fascia-pcb: this part's digital I/O (IOVDD) runs from 1.8 V directly, so
# the module's 1.8 V I2S/I2C connect WITHOUT level shifters, and there is no
# MCLK pin (the PLL locks to BCLK).
#
# GOTCHA: AVDD is 1.8 V OR 3.3 V. At 3.3 V the line outputs are 2 Vrms
# differential and MICBIAS can be 2.75 V; at 1.8 V they drop to 1 Vrms and
# 1.375 V. This board runs AVDD from its own 3.3 V LDO for that reason.
# GOTCHA: at 1.8 V I/O the FIRST I2C write after every power-up must set
# IOVDD_IO_MODE (P0_R2 bit 1) = 1, else bus speed is limited (section 8.3.2).
# Supplies may come up in any order but must ramp slower than 0.1 V/us, and a
# supply cycle needs at least 100 ms between power-down and power-up.
# GOTCHA: ADDR sets the control port: ground = I2C address 0x50, 4.7 k to
# ground 0x51, 22 k to AVDD 0x52, 4.7 k to AVDD 0x53, tied to AVDD = SPI.
# NOTE: pins 22-25 (VSSI) and 1/8/15/26 (VSS) all go to the board ground plane;
# the thermal pad is VSS. DREG (1.5 V) is an on-chip regulator output that
# only wants its 10 uF + 100 nF; nothing else may load it.
# NOTE: the datasheet table gives pin types only as Digital I/O, Analog Input
# and so on; the electrical types below are this project's mapping of those.
# ---------------------------------------------------------------------------
TAC5112_Q1 = [
    (1,  "VSS1",    "power_in"),
    (2,  "DREG",    "power_out"),     # 1.5 V on-chip digital regulator; 10 uF + 100 nF only
    (3,  "BCLK",    "bidirectional"),
    (4,  "FSYNC",   "bidirectional"),
    (5,  "DOUT",    "output"),
    (6,  "DIN",     "input"),
    (7,  "IOVDD",   "power_in"),      # 1.2 / 1.8 / 3.3 V; 1.8 V here
    (8,  "VSS2",    "power_in"),
    (9,  "SCL",     "input"),
    (10, "SDA",     "bidirectional"),
    (11, "GPIO1",   "bidirectional"), # unused; reset default is an active-low/Hi-Z output
    (12, "GPIO2",   "bidirectional"),
    (13, "GPO1",    "output"),
    (14, "GPI1",    "input"),
    (15, "VSS3",    "power_in"),
    (16, "ADDR",    "input"),         # ground = I2C 0x50
    (17, "MICBIAS", "output"),        # 2.75 V at AVDD 3.3 V; 1 uF to ground; max 5 mA
    (18, "IN1P",    "input"),
    (19, "IN1M",    "input"),
    (20, "IN2P",    "input"),
    (21, "IN2M",    "input"),
    (22, "VSSI1",   "power_in"),
    (23, "VSSI2",   "power_in"),
    (24, "VSSI3",   "power_in"),
    (25, "VSSI4",   "power_in"),
    (26, "VSS4",    "power_in"),
    (27, "OUT1M",   "output"),
    (28, "OUT1P",   "output"),
    (29, "OUT2P",   "output"),
    (30, "OUT2M",   "output"),
    (31, "AVDD",    "power_in"),      # 3.0-3.6 V here
    (32, "VREF",    "output"),        # 1 uF to ground
    (33, "EP",      "power_in"),      # thermal pad = VSS
]


# ---------------------------------------------------------------------------
# TPD4E05U06-Q1 - AEC-Q101 4-channel ESD array, 0.5 pF, 5.5 V max signal
# voltage, IEC 61000-4-2 +/-12 kV contact. Source: TI SLVSCO7C, DQA package
# (10-pin USON, 2.5 x 1.0 mm) pin table. Channels are pins 1, 2, 4, 5 (D1+,
# D1-, D2+, D2-); 3 and 8 are ground; 6, 7, 9 and 10 are NC, kept for the
# optional straight-through routing and used here only as no-connects.
# GOTCHA: the channels are not polarised or directional - any of the four
# may sit on any line that stays between 0 and 5.5 V.
# ---------------------------------------------------------------------------
TPD4E05U06_Q1 = [
    (1,  "CH1", "passive"),
    (2,  "CH2", "passive"),
    (3,  "GND1", "power_in"),
    (4,  "CH3", "passive"),
    (5,  "CH4", "passive"),
    (6,  "NC1", "no_connect"),
    (7,  "NC2", "no_connect"),
    (8,  "GND2", "power_in"),
    (9,  "NC3", "no_connect"),
    (10, "NC4", "no_connect"),
]


# ---------------------------------------------------------------------------
# TPS2557-Q1 - automotive adjustable current-limited power-distribution
# switch. Source: TI SLVSC97B (March 2014, revised September 2020),
# S-PVSON-8 (DRB), Table "Terminal Functions".
#
# GOTCHA: EN polarity is the ONLY difference between two otherwise identical
# parts. TPS2557-Q1 is enable-active-HIGH; TPS2556-Q1 is active-low.
# EN VIH is 1.1 V max, so the module's 1.8 V USB_2_EN drives it directly.
# FAULT is active-low open drain and needs a pull-up (to 1.8 V here so it
# stays inside the module's input rating).
# Current limit: IOS(min) = 125477 / R(ILIM[kohm])^1.058 mA, IOS(typ) =
# 113849 / R^1.0049, IOS(max) = 101810 / R^0.9538; 61.9 k gives the
# datasheet's table row 1610 / 1805 / 1980 mA.
# NOTE: thermal pad is internally GND and must also be connected externally.
# ---------------------------------------------------------------------------
TPS2557_Q1 = [
    (1, "GND",   "power_in"),
    (2, "IN1",   "power_in"),
    (3, "IN2",   "power_in"),
    (4, "EN",    "input"),          # active HIGH on this variant
    (5, "ILIM",  "passive"),        # 20k - 187k sets the limit
    # OUT1/OUT2 (and IN1/IN2) are the SAME internal node on two pins; only one
    # is typed as a driver, otherwise ERC reports a power-output conflict
    # against what is physically one pin.
    (6, "OUT1",  "power_out"),
    (7, "OUT2",  "passive"),
    (8, "FAULT", "open_collector"),
    (9, "EP",    "passive"),        # internally GND, must also connect
]


# NOTE: this file previously carried SN65DSI85-Q1 (DSI-to-LVDS bridge),
# removed 2026-09-25 when the board's target panel changed to a real
# native-MIPI-DSI round panel (DisplayModule DM-TFTR50-413) - see
# build_schematic.py's build_panel() docstring. No bridge chip on this
# board anymore; the Verdin's own DSI output goes straight to the panel.


def verify():
    """Sanity-check the tables before anything builds symbols from them."""
    problems = []
    for name, pins in (("LM74930_Q1", LM74930_Q1),
                       ("TCAN1044V_Q1", TCAN1044V_Q1),
                       ("LM61460_Q1", LM61460_Q1),
                       ("TLV767_Q1", TLV767_Q1),
                       ("TPS65131_Q1", TPS65131_Q1),
                       ("TPS61165_Q1", TPS61165_Q1),
                       ("TPS22918_Q1", TPS22918_Q1),
                       ("TAC5112_Q1", TAC5112_Q1),
                       ("TPD4E05U06_Q1", TPD4E05U06_Q1),
                       ("TPS2557_Q1", TPS2557_Q1)):
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
    if len(TPS65131_Q1) != 25:
        problems.append(f"TPS65131_Q1 should have 25 pins (24 + thermal pad), has {len(TPS65131_Q1)}")
    if len(TPS22918_Q1) != 6:
        problems.append(f"TPS22918_Q1 should have 6 pins, has {len(TPS22918_Q1)}")
    if len(TPS61165_Q1) != 6:
        problems.append(f"TPS61165_Q1 should have 6 pins, has {len(TPS61165_Q1)}")
    if len(TAC5112_Q1) != 33:
        problems.append(f"TAC5112_Q1 should have 33 pins (32 + thermal pad), has {len(TAC5112_Q1)}")
    if len(TPD4E05U06_Q1) != 10:
        problems.append(f"TPD4E05U06_Q1 should have 10 pins, has {len(TPD4E05U06_Q1)}")
    if len(TPS2557_Q1) != 9:
        problems.append(f"TPS2557_Q1 should have 9 pins (8 + thermal pad), has {len(TPS2557_Q1)}")
    return problems


if __name__ == "__main__":
    import sys

    problems = verify()
    for name, pins in (("LM74930-Q1 (VQFN-24)", LM74930_Q1),
                       ("TCAN1044V-Q1 (SOIC-8)", TCAN1044V_Q1),
                       ("LM61460-Q1 (VQFN-HR-14)", LM61460_Q1),
                       ("TLV767-Q1 (WSON-8)", TLV767_Q1),
                       ("TPS65131-Q1 (VQFN-24)", TPS65131_Q1),
                       ("TPS61165-Q1 (SOT-23-6)", TPS61165_Q1),
                       ("TAC5112-Q1 (WQFN-32)", TAC5112_Q1),
                       ("TPD4E05U06-Q1 (USON-10)", TPD4E05U06_Q1),
                       ("TPS2557-Q1 (S-PVSON-8)", TPS2557_Q1)):
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
    # Generated rather than from a KiCad library: the RJR (VQFN-HR-14)
    # package has no stock footprint. See fascia-pcb/tools/build_lm61460_footprint.py
    # (reused verbatim - same real part, same real package).
    "LM61460-Q1":      "TI_RJR0014A_VQFN-HR:TI_RJR0014A_VQFN-HR-14_4x3.5mm",
    "R":    "Resistor_SMD:R_0603_1608Metric",
    "C":    "Capacitor_SMD:C_0603_1608Metric",
    "L":    "Inductor_SMD:L_1210_3225Metric",
    # REVIEW FIX 2026-10-17 (docs/electrical-review.md D-01): D1 is ordered as an SMCJ33A (1500 W, DO-214AB / SMC),
    # so it needs the SMC land pattern; the D_SMB footprint it had fits only a 600 W SMBJ-class part.
    "TVS":  "Diode_SMD:D_SMC",
    # Real part MF-RG500 (5.0A hold, matching F1's own real "5A" target -
    # see build_schematic.py's own comment on F1). MF-RG300 (3.0A hold)
    # was the wrong footprint AND the wrong real part - Bourns' MF-RG
    # family's numeric suffix is the hold current, and each member has
    # its own real, different physical package size, not a shared one.
    "FUSE": "Fuse:Fuseholder_Blade_Mini_Keystone_3568",
    "NFET": "Package_TO_SOT_SMD:SOT-23",
    # RGE0024B: 4x4 mm, 24 pins at 0.5 mm, thermal pad 2.45 mm per TI's own
    # package drawing. KiCad's stock HVQFN-24 4x4/0.5mm footprint carries a
    # 2.5 mm pad - the closest bundled match, 0.05 mm larger than TI's
    # land pattern example.
    "TPS65131-Q1": "Package_DFN_QFN:HVQFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm",
    "TPS61165-Q1": "Package_TO_SOT_SMD:SOT-23-6",
    "TPS22918-Q1": "Package_TO_SOT_SMD:SOT-23-6",
    # Coilcraft XAL, AEC-Q200 125C shielded molded inductors (datasheet
    # Document 806-1): XAL4030-472ME 4.7 uH / Isat 4.6 A / 40 mOhm typ and
    # XAL4040-103ME 10 uH / Isat 3.0 A / 84 mOhm typ.
    "L_4U7": "Inductor_SMD:L_Coilcraft_XAL4030-XXX",
    "L_10U": "Inductor_SMD:L_Coilcraft_XAL4040-XXX",
    "SCHOTTKY_SOD123W": "Diode_SMD:Nexperia_CFP3_SOD-123W",
    "D_BAV99": "Package_TO_SOT_SMD:SOT-23",
    "CONN_DIAL": "Connector_Molex:Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical",
    "C_0805": "Capacitor_SMD:C_0805_2012Metric",
    # Power-stage packages (2026-10-02 audit): XEL5030 shares the XAL5030
    # land pattern (pads 1.18 x 4.70 mm, both datasheets), 2 mohm sense
    # resistor in 1206, and the 8 x 10.2 mm hybrid polymer can.
    "L_5030": "Inductor_SMD:L_Coilcraft_XAL5030-XXX",
    "R_1206": "Resistor_SMD:R_1206_3216Metric",
    "CP_HYBRID": "Capacitor_SMD:CP_Elec_8x10",
    "C_1206": "Capacitor_SMD:C_1206_3216Metric",
    # Open 3-pad solder jumpers for the panel's +/-6.5 V pin-group polarity.
    "SOLDERJUMPER3": "Jumper:SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm",

    # Connectors. J2/J3 are real harness parts (see below); J8 (JTAG) and
    # J9 (buttons) are bench/service-only 2.54 mm headers (Samtec
    # TSW-108-07-G-S / TSW-104-07-G-S) that never enter the vehicle harness.
    # J2 (12V/GND/IGN in): real Phoenix MKDS 1,5/3-5,08 (order no. 1715734,
    # 17.5 A / 400 V nominal) - same MKDS 5.08 family gauges/'s own J1 power
    # input uses. J3 (CAN): real Molex KK 254 22-27-2031, 3 circuits, 4 A /
    # 250 V per contact - same KK 254 family gauges/'s own J7 uses.
    "CONN3":      "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal",
    "CONN_CAN":   "Connector_Molex:Molex_KK-254_AE-6410-03A_1x03_P2.54mm_Vertical",
    # Real: Hirose FH26 0.3 mm-pitch 39-position FPC connector for the
    # TST040HDBC-42's 39-pin FPC (KiCad bundled footprint, 2 rows staggered).
    "CONN_PANEL": "Connector_FFC-FPC:Hirose_FH26-39S-0.3SHW_2Rows-39Pins-1MP_P0.60mm_Horizontal",
    "CONN_JTAG":  "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
    "CONN_BTN":   "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "CONN_UART":  "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "CONN_USB":   "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
    "CONN_CELL":  "Battery:BatteryHolder_Keystone_1058_1x2032",
    # Audio and USB parts (2026-10). RTV0032L land pattern has a 3.7 mm pad.
    "TAC5112-Q1": "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.7x3.7mm_ThermalVias",
    "TPS2557-Q1": "Package_DFN_QFN:Texas_DRB0008A",
    "TPD4E05U06-Q1": "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
    "TVS_SMA": "Diode_SMD:D_SMA",
    # JST XH (2.5 mm) for the in-cabin audio harness, deliberately a different
    # family from the KK 254 CAN/dial headers so they cannot be cross-mated.
    "CONN_LINEOUT": "Connector_JST:JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical",
    "CONN_MIC": "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
    "CONN_MFI": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    # GCT USB4105 USB-C 2.0 receptacle (KiCad's footprint carries the
    # datasheet geometry; PCB edge is 3.1 mm below the footprint origin).
    "CONN_USBC": "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
}
