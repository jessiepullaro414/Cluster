#!/usr/bin/env python3
"""
thermal_derating.py - dissipation, derating and current-capacity numbers for both boards.

    python review/thermal_derating.py [gauges|display|all] [--display-sch X --display-pcb Y]

Sections printed:
  A. rail current budgets (every number is labelled: datasheet / assumption)
  B. regulator and switch dissipation at worst-case input and load, and junction temperature
  C. capacitor DC-bias derating (effective capacitance on every cap on a regulated rail)
  D. resistor power in the sender / LED / divider networks, normal and fault
  E. track and fuse current capacity (from the routed copper)

Honesty notes. Murata/TDK DC-bias curves are not retrievable offline here, so capacitor derating
uses a bracketing class-II model (optimistic and pessimistic) instead of a per-part curve; the
report says so wherever it matters. Module currents that no datasheet gives (Verdin iMX95 power,
GC9A01 module VCI current) are explicit ASSUMPTIONS at the top of this file.
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from kmodel import Netlist, Layout, value_of  # noqa: E402
import passive_catalog  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))

# ---------------------------------------------------------------------------
# ASSUMPTIONS (flagged: no datasheet number exists for these)
# ---------------------------------------------------------------------------
ASSUME = dict(
    gc9a01_vci_ma=10.0,       # per GC9A01 module at 3.3 V incl. FPC; GC9A01A datasheet gives no IDD, Raystar gives only the touch IC (3-4.5 mA, unused)
    mcu_run_ma=45.0,          # S32K144 RUN 80 MHz, peripherals enabled, 85-105 C maximum (DS Table 13: 40 typ, 43.5-47 max)
    can_xcvr_dom_ma=70.0,     # TJA1043 / TCAN1044 dominant, 60 ohm bus (TCAN1044 DS 6.6: 45 typ / 70 max)
    verdin_w_typ=5.0,         # Verdin iMX95: Toradex datasheet Rev 0.7 section 6.3 says consumption data is not published yet
    verdin_w_peak=10.0,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def hot(r25, tj=125.0, tc=0.0039):
    """Copper/silicon RDS(on) rises ~0.39 %/K for a Trench MOSFET."""
    return r25 * (1 + tc * (tj - 25.0))


def bias_ratio(x, pessimistic):
    """Class-II MLCC capacitance retained at DC bias fraction x = V / V_rated.
    Two brackets standing in for the missing per-part curves (typical high-capacitance X7R/X7S MLCC:
    about 0.55-0.75 left at 50 % of rated voltage, 0.25-0.55 at 80 %)."""
    k = 1.65 if pessimistic else 0.90
    return max(0.10, 1.0 - k * x ** 1.6)


def rating_v(note):
    import re
    m = re.search(r"(\d+)\s*V", note)
    return float(m.group(1)) if m else None


def tab(rows, head):
    w = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
    print("  " + "  ".join(str(h).ljust(w[i]) for i, h in enumerate(head)))
    for r in rows:
        print("  " + "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))


# ---------------------------------------------------------------------------
# gauges/
# ---------------------------------------------------------------------------
def gauges():
    print("\n################ gauges/ ################")
    a = ASSUME
    # --- A. rail budget
    bl_ma = 4 * (5.15 - 3.0) / 120.0 * 1e3                    # R6-R9 120 ohm, LED Vf min 3.0 V (Raystar: 3.0-3.4 V)
    i3 = a["mcu_run_ma"] + 4 * a["gc9a01_vci_ma"] + 1.0
    i5_logic = i3 + 2 * a["can_xcvr_dom_ma"] + 1.0
    i5 = i5_logic + bl_ma
    print("\nA. Rail budget (mA)")
    tab([
        ["+3V3 (LDO out)", f"{i3:.0f}", f"MCU {a['mcu_run_ma']:.0f} (DS Table 13) + 4 x GC9A01 {a['gc9a01_vci_ma']:.0f} (ASSUMED) + VIO/clamps 1"],
        ["+5V (buck out)", f"{i5:.0f}", f"3V3 LDO {i3:.0f} + 2 CAN transceivers dominant {2 * a['can_xcvr_dom_ma']:.0f} (TCAN1044 DS 6.6) + backlights {bl_ma:.0f} (R6-R9, Vf 3.0 V)"],
    ], ["rail", "mA", "composition"])
    # --- B. dissipation
    print("\nB. Dissipation and junction temperature (TA 85 C)")
    rows = []
    # LMR33630: tON/RDS from DS 6.5 (75/50 mohm typ, 145/95 max at 125 C), fsw 1.4 MHz, L1 XAL5030-222MEC DCR 14.5 mohm max (was XAL5050-103ME 41 mohm before review G-14)
    for vin in (9.0, 13.8, 16.0, 29.9):
        for iout in (i5 / 1e3, 0.6):
            d = min(5.0 / vin, 0.95)
            r_hs, r_ls, dcr = 0.145, 0.095, 0.0145      # DS maxima at 125 C
            p_cond = iout ** 2 * (r_hs * d + r_ls * (1 - d) + dcr)
            p_sw = 0.5 * vin * iout * 10e-9 * 1.4e6 * 2          # 10 ns edges both transitions (estimate)
            p_q = vin * 34e-6 + 5.0 * 0.0                         # IQ 34 uA max
            p_gate = 5e-9 * 5.0 * 1.4e6 * 2                      # gate charge ~5 nC (estimate)
            p = p_cond + p_sw + p_q + p_gate
            eta = 5.0 * iout / (5.0 * iout + p)
            rows.append([f"{vin:.1f} V", f"{iout * 1e3:.0f} mA", f"{p * 1e3:.0f} mW", f"{eta * 100:.0f} %",
                         f"{85 + 72.5 * p:.0f} C", "DS RthJA 72.5 (JEDEC); a real board is lower"])
    print(" LMR33630-Q1 (U2), 5 V out:")
    tab(rows, ["VIN", "IOUT", "loss", "eff", "TJ", "note"])
    p_ldo = (5.15 - 3.3) * i3 / 1e3
    pmax = (150 - 85) / 198.3
    print(f"\n TLV733P-Q1 (U4): {p_ldo * 1e3:.0f} mW at {i3:.0f} mA (5.15 V in, 3.3 V out); TJ = {85 + 198.3 * p_ldo:.0f} C with RthJA 198 C/W (DS 6.4, JEDEC). "
          f"Limit at TA 85 C: {pmax * 1e3:.0f} mW = {pmax / 1.85 * 1e3:.0f} mA of 3V3 load; the part is rated 300 mA.")
    # fault: LDO output pumped is covered in the findings. Q1/Q3
    for load_i, label in ((0.35, "VIN 5.8 V, 5 V load 0.35 A"),):
        i_in = 5.0 * i5 / 1e3 / 0.85 / 5.8
        rds = 0.0145        # SQJ460AEP RDS(on) max at 125 C, VGS 10 V (Vishay S22-0167 Rev. D), since 2026-10-18
        print(f" LM74930 stage at the UVLO edge ({label}): input current {i_in:.2f} A, Q1/Q3 {i_in ** 2 * rds * 1e3:.0f} mW each, "
              f"R49 {i_in ** 2 * 5e-3 * 1e3:.1f} mW; breaker threshold 1.49 A -> margin x{1.49 / i_in:.1f}")
    # --- C/D/E use the netlist
    return i5, i3


def cap_table(nl, netvolts, label):
    print(f"\nC. Capacitor DC-bias derating, {label} (effective capacitance, optimistic .. pessimistic bracket)")
    rows = []
    for ref, c in sorted(nl.comps.items(), key=lambda kv: (len(kv[0]), kv[0])):
        if not ref.startswith("C"):
            continue
        n1, n2 = nl.net_of(ref, "1"), nl.net_of(ref, "2")
        v = max(netvolts.get(n1, (0, 0))[1], netvolts.get(n2, (0, 0))[1])
        vnom = max(netvolts.get(n1, (0, 0))[0], netvolts.get(n2, (0, 0))[0])
        if v < 2.5:
            continue
        val = value_of(c["value"])
        pk = passive_catalog.pkg_key(c["footprint"])
        cat = passive_catalog.lookup("C", c["value"].split()[0], c["footprint"])
        vr = rating_v(cat[2]) if cat else None
        if val is None or vr is None or val < 1e-6:
            continue
        lo_n, hi_n = bias_ratio(vnom / vr, True), bias_ratio(vnom / vr, False)
        lo_w, hi_w = bias_ratio(v / vr, True), bias_ratio(v / vr, False)
        rows.append([ref, c["value"].split()[0], pk, f"{vr:.0f} V", f"{vnom:.1f}/{v:.1f} V", f"{val * hi_n * 1e6:.1f}..{val * lo_n * 1e6:.1f} uF at nominal",
                     f"{val * hi_w * 1e6:.1f}..{val * lo_w * 1e6:.1f} uF at worst"])
    tab(rows, ["ref", "nominal", "case", "rated", "bias nom/worst", "effective (nominal bias)", "effective (worst bias)"])
    return rows


def gauges_netlist_parts():
    sch = os.path.join(ROOT, "gauges", "ClusterGauges.kicad_sch")
    pcb = os.path.join(ROOT, "gauges", "ClusterGauges.kicad_pcb")
    nl = Netlist(sch)
    lay = Layout(pcb)
    netvolts = {"+5V": (5.02, 5.2), "+3V3": (3.3, 3.35), "VIN_PROT": (13.8, 31.0), "VIN_FUSED": (13.8, 31.0), "VIN": (13.8, 31.0),
                "VCC_INT": (5.0, 5.25), "SW": (0, 0), "BOOT_CAP": (5.0, 5.5), "VDDA": (3.3, 3.35), "CAP_CP": (13.0, 14.0),
                "SPEED_IN": (3.3, 3.3), "TMR": (1.2, 1.2)}
    return nl, lay, netvolts


def resistor_power_gauges(nl):
    v = lambda r: value_of(nl.comps[r]["value"])
    print("\nD. Resistor power, normal and fault (rating: 0603 0.1 W, 1206 0.25 W at 70 C; derate linearly to 0 at 155 C -> x0.62 at 85 C)")
    rows = []

    def add(ref, scen, vdrop, note=""):
        r = v(ref)
        p = vdrop ** 2 / r
        pk = passive_catalog.pkg_key(nl.comps[ref]["footprint"])
        rated = {"0603": 0.1, "1206": 0.25, "0805": 0.125}.get(pk, 0.1) * 0.62
        rows.append([ref, scen, f"{vdrop:.1f} V", f"{p * 1e3:.0f} mW", f"{rated * 1e3:.0f} mW", "OVER" if p > rated else "ok", note])
    for ref in ("R16", "R17", "R18"):
        add(ref, "sender nominal, 10 ohm sender", 3.3 * 1000 / 1010)
        add(ref, "wire shorted to 14.4 V", 14.4 - 3.3, "current also flows into +3V3")
        add(ref, "wire shorted to 18 V", 18 - 3.3)
        add(ref, "wire shorted to 27 V", 27 - 3.3)
    for ref, led in (("R82", "D26"), ("R83", "D27")):
        add(ref, "LED on, 14.4 V", 14.4 - 3.0)
        add(ref, "24 V jump start", 24 - 3.0)
        add(ref, "27 V surge, clamped by nothing", 27 - 3.0)
    for ref in ("R6", "R7", "R8", "R9"):
        add(ref, "backlight, 5.2 V, Vf 3.0 V", 5.2 - 3.0)
    add("R43", "Hall sender shorted to GND, VIN 14.4 V", 14.4)
    add("R43", "same at the 29.9 V OV clamp", 29.9)
    add("R44", "SPEED_RAW at 14.4 V (33 k to the divider)", 14.4 - 3.9)
    for ref in ("R58", "R61", "R64", "R67", "R70", "R73"):
        add(ref, "lamp wire at 14.4 V (clamped node 3.9 V)", 14.4 - 3.9)
        break
    add("R46", "ignition 14.4 V", 14.4 - 3.9)
    add("R76", "tach 18 V", (18 - 3.9) / 2)
    add("R19", "battery divider at VIN_PROT 29.9 V", 29.9 * v("R19") / (v("R19") + v("R20")))
    add("R51", "OV ladder at 29.9 V", 29.9 * v("R51") / (v("R51") + v("R52")))
    tab(rows, ["ref", "scenario", "across", "power", "rating@85C", "", "note"])


def tracks_gauges(lay):
    print("\nE. Copper capacity (routed 1 oz outer / 0.5 oz inner, IPC-2221 external 10 K rise; the boards route planes and tracks together, so these are track-only floors)")
    import collections
    by = collections.defaultdict(lambda: collections.defaultdict(float))
    width = collections.defaultdict(set)
    for t in lay.tracks:
        ln = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        by[t["net"]][t["layer"]] += ln
        width[t["net"]].add(t["width"])

    def ipc2221(w_mm, oz, dT=10.0, internal=False):
        area_mil2 = (w_mm / 0.0254) * (oz * 1.378)
        k = 0.024 if internal else 0.048
        return k * dT ** 0.44 * area_mil2 ** 0.725

    rows = []
    for net, need, why in (("VIN_PROT", 0.40, "5 V buck input at 5.8 V UVLO edge 0.30 A, breaker 1.49 A"),
                           ("VIN_FUSED", 0.40, "same current, ahead of the LM74930"),
                           ("+5V", 0.42, "5 V budget"), ("+3V3", 0.10, "3.3 V budget"), ("AUX_VLED_RTN", 0.07, "4 backlights")):
        ws = sorted(width[net])
        lens = by[net]
        rows.append([net, f"{need:.2f} A", why, f"widths {ws} mm", ", ".join(f"{k} {v:.0f} mm" for k, v in sorted(lens.items())),
                     f"{ipc2221(min(ws), 1.0):.2f} A ext / {ipc2221(min(ws), 0.5, internal=True):.2f} A int at {min(ws)} mm"])
    tab(rows, ["net", "needs", "for", "track widths", "length by layer", "capacity of the thinnest piece"])
    return by


# ---------------------------------------------------------------------------
# display/
# ---------------------------------------------------------------------------
def display(sch=None, pcb=None):
    print("\n################ display/ (git HEAD copy unless --display-sch is given) ################")
    a = ASSUME
    # loads: panel backlight 15 V / 180 mA (TST040HDBC-42 datasheet as quoted in build_schematic.py)
    p_bl_out = 15.2 * 0.182
    eta_bl = 0.86
    p_bl_in = p_bl_out / eta_bl
    p_bias_out = 6.5 * 0.05 * 2                                  # panel analog current "TBD"; 50 mA per rail assumed (the datasheet value is TBD)
    p_bias_in = p_bias_out / 0.80
    p_verdin_typ, p_verdin_pk = a["verdin_w_typ"], a["verdin_w_peak"]
    p_misc = 0.5                                                  # CAN transceiver, dial sensor 8.5 mA x 5 V, 1.8 V LDO share, clamps
    p5_typ = p_bl_in + p_bias_in + p_verdin_typ + p_misc
    p5_pk = p_bl_in + p_bias_in + p_verdin_pk + p_misc
    print("\nA. 5 V rail budget (W)")
    tab([
        ["backlight boost input", f"{p_bl_in:.2f}", f"15.2 V x 182 mA = {p_bl_out:.2f} W out, 86 % efficiency (ASSUMED)"],
        ["panel bias converter input", f"{p_bias_in:.2f}", "+/-6.5 V x 50 mA (panel datasheet says TBD) / 80 %"],
        ["Verdin iMX95 module", f"{p_verdin_typ:.1f} typ / {p_verdin_pk:.1f} peak", "ASSUMED: Toradex datasheet Rev 0.7 6.3 'power consumption available soon'"],
        ["CAN, dial, 1V8, misc", f"{p_misc:.1f}", "estimate"],
        ["total on +5V", f"{p5_typ:.1f} typ / {p5_pk:.1f} peak", f"{p5_pk / 5.0:.1f} A peak at 5 V"],
    ], ["load", "W", "basis"])
    rows = []
    print("\nB. Dissipation (TA 85 C)")
    # LM61460: DS fig 10-3 at 2.1 MHz, RthJA 25 C/W EVM allows 4 A at 105 C ambient -> ~1.8 W; use P = 0.30 W + (Iout/4)^2 x 1.5 W
    for iout in (p5_typ / 5.0, p5_pk / 5.0):
        p = 0.30 + (iout / 4.0) ** 2 * 1.5
        for rth, lab in ((25.0, "TI EVM 100x80 mm 4-layer"), (45.0, "this board, estimate")):
            rows.append(["LM61460-Q1", f"{iout:.2f} A", f"{p:.2f} W", f"{85 + rth * p:.0f} C", f"RthJA {rth:.0f} ({lab}); loss from the 2.1 MHz derating curve (DS Fig 10-3)"])
    for iin_w, lab in ((p_bl_out, "backlight at 85 C panel load"),):
        for eta in (0.90, 0.86, 0.82):
            p = p_bl_out / eta - p_bl_out
            for rth in (100.0, 150.0, 210.1):
                rows.append(["TPS61165-Q1", lab, f"{p:.2f} W (eta {eta * 100:.0f} %)", f"{85 + rth * p:.0f} C", f"RthJA {rth} C/W (DS 210.1 JEDEC); shutdown 160 C"])
    p_bias_loss = p_bias_in - p_bias_out
    rows.append(["TPS65131-Q1", "2 x 50 mA", f"{p_bias_loss:.2f} W", f"{85 + 34.1 * p_bias_loss:.0f} C", "RthJA 34.1 (DS 6.4); TA max 105 C"])
    p_ldo = (5.0 - 1.8) * 0.020
    rows.append(["TLV767-Q1", "20 mA", f"{p_ldo * 1e3:.0f} mW", f"{85 + 51.9 * p_ldo:.0f} C", "RthJA 51.9 (DS)"])
    for i_in in (1.4, 2.0, 2.5):
        # Vishay SQJ460AEP since 2026-10-18 (review D-05): RDS(on) max 18.3 mohm at TJ 175 C (worst case,
        # datasheet page 2), RthJA 68 C/W on 1 in2 FR4 (page 1); 120 C/W bracket for the smaller copper here
        rds = 0.0183
        p = i_in ** 2 * rds
        for rth, lab in ((68, "DS 1 in2 FR4"), (120, "assumed: footprint pad only")):
            rows.append(["Q1 / Q2 SQJ460AEP (each)", f"{i_in:.1f} A input", f"{p * 1e3:.0f} mW", f"{85 + rth * p:.0f} C", f"RDS(on) {rds * 1e3:.1f} mohm at 175 C, Rth {rth} ({lab}); 175 C max"])
    tab(rows, ["part", "load", "loss", "TJ at TA 85 C", "basis"])
    return p5_typ, p5_pk


def run_display_tables(sch, pcb):
    nl = Netlist(sch)
    lay = Layout(pcb) if pcb and os.path.isfile(pcb) else None
    netvolts = {"+5V": (5.02, 5.2), "+1V8": (1.8, 1.85), "+12V_PROT": (13.8, 31.0), "VBAT_F": (13.8, 31.0), "VBAT_IN": (13.8, 31.0),
                "VCC_LDO": (5.0, 5.25), "PANEL_VSP": (6.5, 6.7), "PANEL_VSN": (6.5, 6.7), "PANEL_BL_LEDA": (15.2, 38.0),
                "DIAL_5V": (5.0, 5.5), "CAP_CP": (13.0, 14.0), "PANEL_BIAS_VIN": (5.0, 5.2), "BOOT_C": (5.0, 5.5)}
    cap_table(nl, netvolts, "display/")
    return nl, lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="?", default="all", choices=("gauges", "display", "all"))
    ap.add_argument("--display-sch")
    ap.add_argument("--display-pcb")
    a = ap.parse_args()
    if a.which in ("gauges", "all"):
        gauges()
        nl, lay, nv = gauges_netlist_parts()
        cap_table(nl, nv, "gauges/")
        resistor_power_gauges(nl)
        tracks_gauges(lay)
    if a.which in ("display", "all"):
        display()
        sch = a.display_sch or os.path.join(ROOT, "display", "ClusterDisplay.kicad_sch")
        pcb = a.display_pcb or os.path.join(ROOT, "display", "ClusterDisplay.kicad_pcb")
        run_display_tables(sch, pcb)


if __name__ == "__main__":
    main()
