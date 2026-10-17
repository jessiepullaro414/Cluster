#!/usr/bin/env python3
"""
layout_checks.py - routed-copper checks that need the .kicad_pcb.

    python review/layout_checks.py gauges
    python review/layout_checks.py display --pcb X.kicad_pcb

  1. slow or sensitive signals near a switching node (any layer, in plan view): a switch node
     radiates on every layer, and a track on the layer below or above it couples through the thin
     prepreg, so the distance is measured in plan view regardless of layer;
  2. long fast nets (SPI, CAN) and how many layers/vias they use, for the signal-integrity estimate;
  3. widths of the power nets against the currents they carry.
"""
import argparse
import collections
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kmodel import Layout, Netlist  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
CFG = {
    "gauges": dict(
        pcb=os.path.join(ROOT, "gauges", "ClusterGauges.kicad_pcb"),
        sch=os.path.join(ROOT, "gauges", "ClusterGauges.kicad_sch"),
        switch=["SW", "BOOT_CAP"],
        # nets that legitimately touch the switch cell (power parts of the same converter)
        own={"SW", "BOOT_CAP", "+5V", "GND", "VIN_PROT", "VCC_INT", "FB"},
        fast=["LPSPI2_SCK", "LPSPI2_SOUT", "CAN0_H", "CAN0_L", "CAN1_H", "CAN1_L", "AUX_RST"],
        slow_guard=1.5,
    ),
    "display": dict(
        pcb=os.path.join(ROOT, "display", "ClusterDisplay.kicad_pcb"),
        sch=os.path.join(ROOT, "display", "ClusterDisplay.kicad_sch"),
        switch=["SW_5V", "BOOT_C", "BOOT_R", "PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW"],
        own={"SW_5V", "BOOT_C", "BOOT_R", "+5V", "GND", "+12V_PROT", "VCC_LDO", "FB_5V", "PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW",
             "PANEL_VSP", "PANEL_VSN", "PANEL_BL_LEDA", "PANEL_BL_LEDK", "PANEL_FBP", "PANEL_FBN", "PANEL_VREF", "PANEL_CP", "PANEL_CN",
             "PANEL_BIAS_VIN", "BL_COMP"},
        fast=["DSI_D0_P", "DSI_D0_N", "CAN1_H", "CAN1_L"],
        slow_guard=1.5,
    ),
}


def seg_dist(a1, a2, b1, b2):
    def pt_seg(p, s1, s2):
        dx, dy = s2[0] - s1[0], s2[1] - s1[1]
        l2 = dx * dx + dy * dy
        u = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - s1[0]) * dx + (p[1] - s1[1]) * dy) / l2))
        return math.hypot(p[0] - (s1[0] + u * dx), p[1] - (s1[1] + u * dy))
    # segments intersect?
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])
    if ccw(a1, b1, b2) != ccw(a2, b1, b2) and ccw(a1, a2, b1) != ccw(a1, a2, b2):
        return 0.0
    return min(pt_seg(a1, b1, b2), pt_seg(a2, b1, b2), pt_seg(b1, a1, a2), pt_seg(b2, a1, a2))


# steady-state branch currents (A) the copper of each net must carry, with the reasoning.
# gauges: 5 V budget in thermal_derating.py; battery side = 5 V power / 0.85 / 5.8 V (UVLO edge).
# display: peak 5 V power 14.5 W (assumption, see thermal_derating.py) at the 6 V cranking edge, fuse 5 A.
NEEDS = {
    "gauges": {"VIN_FUSED": 0.40, "VIN_PROT": 0.40, "COMMON": 0.40, "SENSE_OUT": 0.40, "+5V": 0.45, "+3V3": 0.15, "AUX_VLED_RTN": 0.07},
    "display": {"VBAT_IN": 2.6, "VBAT_F": 2.6, "+12V_PROT": 2.6, "COMMON": 2.6, "SENSE_OUT": 2.6, "+5V": 3.0, "+1V8": 0.1,
                "PANEL_BL_LEDA": 0.2, "PANEL_VSP": 0.15, "PANEL_VSN": 0.15},
}
DT_LIMIT = 20.0      # K rise allowed for continuous current


def ipc2221_current(w_mm, oz, dt, internal):
    area = (w_mm / 0.0254) * (oz * 1.378)
    k = 0.024 if internal else 0.048
    return k * dt ** 0.44 * area ** 0.725


def rise_for(i, w_mm, oz, internal):
    area = (w_mm / 0.0254) * (oz * 1.378)
    k = 0.024 if internal else 0.048
    return (i / (k * area ** 0.725)) ** (1 / 0.44)


def check_current(board, lay):
    print(f"\n    current capacity (IPC-2221, outer 1 oz / inner 0.5 oz, limit {DT_LIMIT:.0f} K rise); nets with a copper pour are carried by the pour:")
    zone_layers = collections.defaultdict(set)
    for z in lay.zones:
        ls = z["layers"] or []
        for l in (ls if isinstance(ls, list) else [ls]):
            zone_layers[z["net"]].add(l)
    for net, need in NEEDS[board].items():
        worst, short, total = None, 0.0, 0.0
        for t in lay.tracks:
            if t["net"] != net:
                continue
            ln = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
            internal = t["layer"].startswith("In")
            dt = rise_for(need, t["width"], 0.5 if internal else 1.0, internal)
            total += ln
            if dt > DT_LIMIT:
                short += ln
            if worst is None or dt > worst[0]:
                worst = (dt, t["width"], t["layer"], (round(t["x1"], 1), round(t["y1"], 1)))
        zl = sorted(zone_layers.get(net, []))
        if worst is None:
            print(f"      {net:<12} {need:4.2f} A  no track pieces" + (f" (pour on {zl})" if zl else ""))
            continue
        # a rise above ~500 K is a burn-through, not a number to trust: cap the print
        shown = f"{worst[0]:.0f}" if worst[0] < 500 else ">500"
        status = "ok" if short == 0 else ("pour-carried?" if zl else "FAIL")
        print(f"      {net:<12} {need:4.2f} A  {short:5.0f} of {total:5.0f} mm of track under-width (limit {DT_LIMIT:.0f} K); "
              f"worst {worst[1]} mm on {worst[2]} -> {shown} K near {worst[3]}  [{status}]" + (f" pour on {zl}" if zl else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("gauges", "display"))
    ap.add_argument("--pcb")
    ap.add_argument("--sch")
    a = ap.parse_args()
    cfg = CFG[a.board]
    lay = Layout(a.pcb or cfg["pcb"])
    nl = Netlist(a.sch or cfg["sch"])
    sw_set = set(cfg["switch"])
    print(f"=== {a.board}: switch-node nets {sorted(sw_set)}")

    # copper of the switch nets: tracks, vias and pads
    sw_segs = [(t, (t["x1"], t["y1"]), (t["x2"], t["y2"])) for t in lay.tracks if t["net"] in sw_set]
    sw_pts = [(v["x"], v["y"]) for v in lay.vias if v["net"] in sw_set]
    for (ref, pin), plist in lay.pads.items():
        for p in plist:
            if p["net"] in sw_set:
                sw_pts.append((p["x"], p["y"]))
    sw_all = [(s, e) for _, s, e in sw_segs] + [(p, p) for p in sw_pts]
    print(f"    {len(sw_segs)} switch-node track segments, {len(sw_pts)} pads/vias")

    offenders = collections.defaultdict(lambda: [9e9, None, None])
    guard = cfg["slow_guard"]
    # other nets' tracks
    for t in lay.tracks:
        n = t["net"]
        if n in cfg["own"] or n is None:
            continue
        s, e = (t["x1"], t["y1"]), (t["x2"], t["y2"])
        for (a1, a2) in sw_all:
            d = seg_dist(s, e, a1, a2) - t["width"] / 2 - 0.1
            if d < guard and d < offenders[n][0]:
                offenders[n] = [d, t["layer"], (round(s[0], 1), round(s[1], 1))]
    if offenders:
        print(f"    signal tracks within {guard} mm (plan view, any layer) of a switching node:")
        for n, (d, layer, where) in sorted(offenders.items(), key=lambda kv: kv[1][0]):
            print(f"      {n:<22} closest {max(d, 0):.2f} mm on {layer} near {where}")
    else:
        print(f"    no foreign track within {guard} mm of a switching node on any layer")

    # fast nets
    print("\n    fast-net length and layer use:")
    for net in cfg["fast"]:
        per = collections.defaultdict(float)
        for t in lay.tracks:
            if t["net"] == net:
                per[t["layer"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        nv = sum(1 for v in lay.vias if v["net"] == net)
        tot = sum(per.values())
        print(f"      {net:<14} {tot:6.1f} mm  " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(per.items())) + f"  vias {nv}")

    # power net widths
    check_current(a.board, lay)
    print("\n    power-net track widths (mm) by layer:")
    for net in sorted({"+5V", "+3V3", "VIN_PROT", "VIN_FUSED", "+12V_PROT", "VBAT_F", "VBAT_IN", "COMMON", "SENSE_OUT"} & set(nl.nets)):
        w = collections.defaultdict(lambda: collections.defaultdict(float))
        for t in lay.tracks:
            if t["net"] == net:
                w[round(t["width"], 2)][t["layer"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        if not w:
            continue
        print(f"      {net:<10} " + "; ".join(f"{k} mm: " + ", ".join(f"{l} {v:.0f}" for l, v in sorted(d.items())) for k, d in sorted(w.items())))


if __name__ == "__main__":
    main()
