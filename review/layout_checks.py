#!/usr/bin/env python3
"""
layout_checks.py - routed-copper checks that need the .kicad_pcb.

    python review/layout_checks.py gauges
    python review/layout_checks.py display --pcb X.kicad_pcb

  1. slow or sensitive signals near a switching node (any layer, in plan view): a switch node
     radiates on every layer, and a track on the layer below or above it couples through the thin
     prepreg, so the distance is measured in plan view regardless of layer;
  2. long fast nets (SPI, CAN) and how many layers/vias they use, for the signal-integrity estimate;
  3. widths of the power nets against the currents they carry (nets in PATHS: along the path the
     current takes, counting same-net fill beside a track and the vias, with milliamp branches apart);
  4. (2026-10-19, six layers) the GND reference planes In1.Cu and In4.Cu carry no other net's
     track: exits 1 if they do, since a split plane under a fast net is the failure this guards.
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
        pcb=os.path.join(ROOT, "archive", "display-1966", "ClusterDisplay.kicad_pcb"),
        sch=os.path.join(ROOT, "archive", "display-1966", "ClusterDisplay.kicad_sch"),
        switch=["SW_5V", "BOOT_C", "BOOT_R", "PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW"],
        own={"SW_5V", "BOOT_C", "BOOT_R", "+5V", "GND", "+12V_PROT", "VCC_LDO", "FB_5V", "PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW",
             "PANEL_VSP", "PANEL_VSN", "PANEL_BL_LEDA", "PANEL_BL_LEDK", "PANEL_FBP", "PANEL_FBN", "PANEL_VREF", "PANEL_CP", "PANEL_CN",
             "PANEL_BIAS_VIN", "BL_COMP"},
        fast=["DSI_D0_P", "DSI_D0_N", "USB2_DP", "USB2_DN", "USB_DP", "USB_DN", "CAN1_H", "CAN1_L"],
        slow_guard=1.5,
    ),
}
# the RGB variant is display/ plus the LVDS-to-RGB bridge: same converters, same checks
CFG["display-rgb"] = dict(CFG["display"],
                          pcb=os.path.join(ROOT, "archive", "display-rgb", "ClusterDisplayRGB.kicad_pcb"),
                          sch=os.path.join(ROOT, "archive", "display-rgb", "ClusterDisplayRGB.kicad_sch"))
# the brain board (2026-10-20): display/ without the panel converters, plus two
# screen ports whose 5 V switches allow up to 1.98 A each
CFG["brain"] = dict(CFG["display"],
                    pcb=os.path.join(ROOT, "brain", "ClusterBrain.kicad_pcb"),
                    sch=os.path.join(ROOT, "brain", "ClusterBrain.kicad_sch"),
                    switch=["SW_5V", "BOOT_C", "BOOT_R"],
                    own={"SW_5V", "BOOT_C", "BOOT_R", "+5V", "GND", "+12V_PROT", "VCC_LDO", "FB_5V"},
                    fast=["DSI_D0_P", "DSI_D0_N", "DSI_CLK_P", "LVDS0_CLK_P", "LVDS0_CLK_N",
                          "LVDS1_D3_P", "USB2_DP", "USB2_DN", "CAN1_H", "CAN1_L"])
# the TSD panel board (2026-10-20): display/'s panel bias and backlight converters
CFG["panel-tsd"] = dict(
    pcb=os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_pcb"),
    sch=os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_sch"),
    switch=["PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW"],
    own={"PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW", "+5V", "GND", "PANEL_VSP", "PANEL_VSN",
         "PANEL_BL_LEDA", "PANEL_BL_LEDK", "PANEL_FBP", "PANEL_FBN", "PANEL_VREF", "PANEL_CP",
         "PANEL_CN", "PANEL_BIAS_VIN", "BL_COMP"},
    fast=["DSI_D0_P", "DSI_D0_N", "DSI_D1_P", "DSI_D1_N", "DSI_D2_P", "DSI_D2_N",
          "DSI_CLK_P", "DSI_CLK_N"],
    slow_guard=1.5,
)
PLANE_LAYERS = ("In1.Cu", "In4.Cu")


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
NEEDS["display-rgb"] = NEEDS["display"]   # same supply chain; the RGB receiver adds about 0.1 A on +5V
NEEDS["brain"] = {k: v for k, v in NEEDS["display"].items() if not k.startswith("PANEL_")}
NEEDS["brain"].update({"PORTA_5V": 1.98, "PORTB_5V": 1.98})
# the panel draws about 0.65 A at 5 V for its backlight (2.7 W / 0.88) plus the bias supply
NEEDS["panel-tsd"] = {"+5V": 1.0, "PANEL_BL_LEDA": 0.2, "PANEL_VSP": 0.15, "PANEL_VSN": 0.15}
# (2026-10-20) Where the current really flows. A net listed here is rated only along the copper
# between these pads (the union of the shortest track paths from the first pad to each of the
# others); its other copper goes to milliamp pins and is listed as a branch, not rated at the
# net's current. display/ battery path: J2 -> F1 -> R1 (2 mohm sense) -> Q2 -> Q1 -> the buck's VIN
# pins. Branches: the LM74930 (U1) sense, gate-supply and VS pins, C2/C3, R2, the D1 TVS
# (surge pulses only), the buck's input caps and EN divider.
# Each terminal is a list of pads: the SO-8L FET's three source pins are one terminal, the current
# divides between them.
PATHS = {
    "display": {"VBAT_IN": [[("J2", "1")], [("F1", "1")]],
                "VBAT_F": [[("F1", "2")], [("R1", "1")]],
                "SENSE_OUT": [[("R1", "2")], [("Q2", "5")]],
                "COMMON": [[("Q2", "1"), ("Q2", "2"), ("Q2", "3")], [("Q1", "1"), ("Q1", "2"), ("Q1", "3")]],
                "+12V_PROT": [[("Q1", "5")], [("U2", "8")], [("U2", "12")]]},
}
PATHS["display-rgb"] = PATHS["display"]
# the brain board keeps display/'s front end and buck with the same designators; each screen
# port's 5 V runs from its switch's OUT pins to the connector's 5 V contacts
PATHS["brain"] = dict(PATHS["display"],
                      PORTA_5V=[[("U6", "6"), ("U6", "7")], [("J4", "2"), ("J4", "3"), ("J4", "4"), ("J4", "5")]],
                      PORTB_5V=[[("U7", "6"), ("U7", "7")], [("J18", "45"), ("J18", "46"), ("J18", "47"),
                                                             ("J18", "48"), ("J18", "49")]])
DT_LIMIT = 20.0      # K rise allowed for continuous current
RHO_CU = 1.72e-5       # ohm mm, copper at 20 C
CU_OUTER_MM = 0.035    # 1 oz
VIA_PLATING_MM = 0.018   # JLCPCB's stated minimum via-wall plating; the barrel is rated as an outer conductor


def ipc2221_current(w_mm, oz, dt, internal):
    area = (w_mm / 0.0254) * (oz * 1.378)
    k = 0.024 if internal else 0.048
    return k * dt ** 0.44 * area ** 0.725


def rise_for(i, w_mm, oz, internal):
    area = (w_mm / 0.0254) * (oz * 1.378)
    k = 0.024 if internal else 0.048
    return (i / (k * area ** 0.725)) ** (1 / 0.44)


def via_rise(i, drill_mm):
    """A via barrel rated as an outer conductor as wide as its circumference, VIA_PLATING_MM thick."""
    return rise_for(i, math.pi * drill_mm, VIA_PLATING_MM / 0.0347, False)   # 1 oz = 0.0347 mm


def pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    u = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - (a[0] + u * dx), p[1] - (a[1] + u * dy))


def current_path(lay, net, terminals):
    """Track and via indices on the union of the shortest copper paths from the first terminal to
    each of the others, following tracks, vias and pads of `net` only. None if a terminal is not
    reached by track (it would then hang on a pour, which this does not follow)."""
    tr = [(i, t) for i, t in enumerate(lay.tracks) if t["net"] == net]
    vi = [(j, v) for j, v in enumerate(lay.vias) if v["net"] == net]
    pads = [((ref, pin), p) for (ref, pin), lst in lay.pads.items() for p in lst if p["net"] == net]
    adj = collections.defaultdict(set)

    def link(a, b):
        adj[a].add(b)
        adj[b].add(a)

    ends = {i: ((t["x1"], t["y1"]), (t["x2"], t["y2"])) for i, t in tr}
    for i, t in tr:
        for k, u in tr:
            if k <= i or u["layer"] != t["layer"]:
                continue
            # an end of either track on the other (end to end, or a T onto its middle)
            if (min(pt_seg(e, *ends[k]) for e in ends[i]) <= u["width"] / 2 + 0.01
                    or min(pt_seg(e, *ends[i]) for e in ends[k]) <= t["width"] / 2 + 0.01):
                link(("t", i), ("t", k))
        for j, v in vi:
            if pt_seg((v["x"], v["y"]), *ends[i]) <= v["size"] / 2:
                link(("t", i), ("v", j))
        for key, p in pads:
            on_layer = t["layer"] in p["layers"] or "*.Cu" in p["layers"]
            if on_layer and pt_seg((p["x"], p["y"]), *ends[i]) <= max(p["w"], p["h"]) / 2:
                link(("t", i), ("p",) + key)
    for j, v in vi:
        for key, p in pads:
            if math.hypot(v["x"] - p["x"], v["y"] - p["y"]) <= max(p["w"], p["h"]) / 2:
                link(("v", j), ("p",) + key)

    def cost(node):
        if node[0] != "t":
            return 0.0
        a, b = ends[node[1]]
        return math.hypot(b[0] - a[0], b[1] - a[1])

    import heapq
    start = [("p",) + key for key in terminals[0]]
    dist, prev, heap = {}, {}, []
    for s in start:
        dist[s] = 0.0
        heapq.heappush(heap, (0.0, s))
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist.get(n, 9e9):
            continue
        for m in adj[n]:
            nd = d + cost(m)
            if nd < dist.get(m, 9e9):
                dist[m], prev[m] = nd, n
                heapq.heappush(heap, (nd, m))
    on_path = set()
    for term in terminals[1:]:
        reached = [("p",) + key for key in term if ("p",) + key in dist]
        if not reached:
            return None
        n = min(reached, key=lambda x: dist[x])
        while n in prev:
            on_path.add(n)
            n = prev[n]
    return {n[1] for n in on_path if n[0] == "t"}, {n[1] for n in on_path if n[0] == "v"}


def cross_width(t, fills, reach=6.0):
    """Copper width across track t at its midpoint: the track plus any same-net fill on its layer,
    measured along the perpendicular through the midpoint as the one unbroken stretch of copper that
    contains the track (out to `reach` mm each side). Even-odd crossing count, which also handles the
    zero-width slits KiCad cuts to fracture a fill's holes into its outline."""
    dx, dy = t["x2"] - t["x1"], t["y2"] - t["y1"]
    ln = math.hypot(dx, dy)
    if ln == 0:
        return t["width"]
    d = (dx / ln, dy / ln)                     # along the track
    n = (-d[1], d[0])                          # across it
    m = ((t["x1"] + t["x2"]) / 2, (t["y1"] + t["y2"]) / 2)
    spans = [(-t["width"] / 2, t["width"] / 2)]
    for pts in fills:
        cuts = []
        for (px, py), (qx, qy) in zip(pts, pts[1:] + pts[:1]):
            vp = (px - m[0]) * d[0] + (py - m[1]) * d[1]
            vq = (qx - m[0]) * d[0] + (qy - m[1]) * d[1]
            if (vp > 0) != (vq > 0):
                up = (px - m[0]) * n[0] + (py - m[1]) * n[1]
                uq = (qx - m[0]) * n[0] + (qy - m[1]) * n[1]
                cuts.append(up + (uq - up) * vp / (vp - vq))
        cuts.sort()
        spans += [(a, b) for a, b in zip(cuts[0::2], cuts[1::2]) if b > -reach and a < reach]
    lo, hi = -t["width"] / 2, t["width"] / 2
    grew = True
    while grew:
        grew = False
        for a, b in spans:
            if a <= hi + 1e-6 and b >= lo - 1e-6 and (a < lo - 1e-6 or b > hi + 1e-6):
                lo, hi, grew = min(lo, a), max(hi, b), True
    return min(hi, reach) - max(lo, -reach)


def check_path(lay, net, need, terms):
    names = " -> ".join("/".join(f"{r}.{p}" for r, p in term) for term in terms)
    res = current_path(lay, net, terms)
    if res is None:
        print(f"      {net:<12} {need:4.2f} A  path {names}: a terminal is not reached by track  [FAIL]")
        return
    on_t, on_v = res
    fills = collections.defaultdict(list)       # layer -> filled polygons of this net
    for z in lay.zones:
        if z["net"] == net:
            for layer, pts in z.get("filled", []):
                fills[layer].append(pts)
    worst, short, total, branch, by_fill = None, 0.0, 0.0, 0.0, 0.0
    necks = []
    for i, t in enumerate(lay.tracks):
        if t["net"] != net:
            continue
        ln = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        if i not in on_t:
            branch += ln
            continue
        internal = t["layer"].startswith("In")
        w = cross_width(t, fills[t["layer"]]) if fills[t["layer"]] else t["width"]
        dt = rise_for(need, w, 0.5 if internal else 1.0, internal)
        total += ln
        if rise_for(need, t["width"], 0.5 if internal else 1.0, internal) > DT_LIMIT >= dt:
            by_fill += ln
        if dt > DT_LIMIT:
            short += ln
            necks.append((round(w, 2), t["layer"], round(t["x1"], 1), round(t["y1"], 1), round(ln, 2)))
        if worst is None or dt > worst[0]:
            worst = (dt, round(w, 2), t["layer"], (round(t["x1"], 1), round(t["y1"], 1)))
    via_dt = [via_rise(need, lay.vias[j]["drill"]) for j in sorted(on_v)]
    bad_vias = sum(1 for d in via_dt if d > DT_LIMIT)
    shown = f"{worst[0]:.0f}" if worst[0] < 500 else ">500"
    status = "ok" if short == 0 and bad_vias == 0 else "FAIL"
    print(f"      {net:<12} {need:4.2f} A  path {names}: {short:4.1f} of {total:5.1f} mm under-width; worst {worst[1]} mm of copper on {worst[2]} "
          f"-> {shown} K near {worst[3]}; {len(on_v)} via(s)" + (f", {bad_vias} over {DT_LIMIT:.0f} K" if bad_vias else "")
          + (f"; {by_fill:.1f} mm narrow track carried by its F.Cu fill" if by_fill else "")
          + f"; {branch:.0f} mm of branch track to milliamp pins, not rated  [{status}]")
    groups = collections.defaultdict(list)       # (width, layer) -> [(x, y, length)]
    for w, layer, x, y, ln in necks:
        groups[(w, layer)].append((x, y, ln))
    # IPC-2221 rates a long uniform conductor; a short neck between wide copper sheds its heat into
    # that copper. Its resistance and dissipation at the full current put a number on how much.
    for (w, layer), pieces in sorted(groups.items()):
        xs, ys = [p[0] for p in pieces], [p[1] for p in pieces]
        ln = sum(p[2] for p in pieces)
        r = RHO_CU * ln / (w * (CU_OUTER_MM if not layer.startswith("In") else CU_OUTER_MM / 2))
        print(f"          under-width: {w} mm on {layer}, {ln:.1f} mm in x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}"
              f" ({r * 1000:.1f} mohm, {need * need * r * 1000:.0f} mW)")
    for j, d in zip(sorted(on_v), via_dt):
        if d > DT_LIMIT:
            v = lay.vias[j]
            print(f"          via {v['drill']} mm drill at ({v['x']:.1f}, {v['y']:.1f}): {d:.0f} K")


def check_current(board, lay):
    print(f"\n    current capacity (IPC-2221, outer 1 oz / inner 0.5 oz, limit {DT_LIMIT:.0f} K rise); nets with a copper pour are carried by the pour:")
    zone_layers = collections.defaultdict(set)
    for z in lay.zones:
        ls = z["layers"] or []
        for l in (ls if isinstance(ls, list) else [ls]):
            zone_layers[z["net"]].add(l)
    for net, need in NEEDS[board].items():
        terms = PATHS.get(board, {}).get(net)
        if terms:
            check_path(lay, net, need, terms)
            continue
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
    ap.add_argument("board", choices=tuple(CFG))
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

    # GND reference planes
    print("\n    GND plane layers (only GND copper allowed):")
    bad = 0
    for layer in PLANE_LAYERS:
        per = collections.defaultdict(float)
        for t in lay.tracks:
            if t["layer"] == layer:
                per[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        foreign = {n: v for n, v in per.items() if n != "GND"}
        bad += len(foreign)
        print(f"      {layer}: GND tracks {per.get('GND', 0.0):.1f} mm, other nets "
              + (", ".join(f"{n} {v:.1f} mm" for n, v in sorted(foreign.items())) if foreign else "none"))
    if bad:
        raise SystemExit(f"FAIL: {bad} non-GND net(s) routed on a plane layer")


if __name__ == "__main__":
    main()
