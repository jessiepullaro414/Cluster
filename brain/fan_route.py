"""
Planned routes from the Verdin socket J1 to the two screen ports (brain board,
2026-10-20). Pure geometry, no KiCad imports, so build_pcb.py can report it and
route_board.py can apply it after the autorouter. Replaces display/'s
dsi_route.py.

The port contact order (../tools/screen_ports.py) follows J1's pin order, so
no pair has to swap polarity and nothing crosses: every track runs straight
out of its J1 pad, takes one 45 degree jog to its connector contact's x, and
runs straight in. J1's pins on one pad row sit 1.0 mm apart and the FH12
contacts 0.5 mm apart, so the group fans in.

* Pairs: 0.16 mm on F.Cu over the solid In1 GND plane, 0.0994 mm of 3313
  prepreg below (6-layer JLC06161H-3313). review/dsi_impedance.py's 2-D
  field solve gives Z0 51.8 ohm and 96.4 to 103.1 ohm differential for any
  gap from 0.25 to 1.2 mm, which covers the 0.84 mm gap at J1 and the
  0.34 mm gap at the connector. MIPI DSI and LVDS both want 100 ohm.
* GND guards: where J1 has a GND pin between two pairs and the connector a
  GND contact between the same two pairs, a 0.2 mm GND track joins them, so
  the pairs run with ground on both sides.
* Every connector GND contact inside the fan gets a short stub to a via on
  the far side of the pad (under the connector body, tented), which is what
  ties those contacts, and the J1 GND pins guarded to them, to the planes.
* The corridor around each fan is fenced from the autorouter on F.Cu (and
  with it vias, which pass through F.Cu). In2, In3 and B.Cu may still cross
  under it: the In1 plane separates them from the pairs.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from verdin_pinout import X1_PINS       # noqa: E402
import screen_ports                     # noqa: E402

W = 0.16                 # pair track width, mm (100 ohm diff, see docstring)
W_GUARD = 0.2
W_STUB = 0.25
VIA_DIA, VIA_DRILL = 0.6, 0.3
STUB = 0.4               # tracks start this far inside the J1 pad, mm
ESCAPE = 0.6             # straight run out of the J1 pad row before the jog
END_CLEAR = 0.5          # straight run into the connector pad after the jog
VIA_OFFSET = 1.2         # GND stub via centre beyond the connector pad centre
# Corridor margins beyond the outermost fan copper. J1's pins on one pad row
# and the FH12's contacts are both 0.5 mm apart, so the pin right beside a fan
# is only 0.5 mm from its edge: at 0.15 mm its escape track (0.2 mm wide) still
# clears the fence by 0.25 mm, above the router's 0.2 mm clearance. (0.3-0.5 mm
# left +1V8 and the RESET lines unroutable, 2026-10-20.)
CORRIDOR_J1_MARGIN = 0.15
CORRIDOR_PORT_MARGIN = 0.15
EDGE_VIA_INSET = 0.25    # the outermost GND stub vias sit this far toward the fan's centre


def inside(poly, x, y):
    """Point-in-polygon (even-odd), for checking the corridors."""
    hit = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit

_PIN_OF = {name: pin for pin, name in X1_PINS.items()}

GROUPS = [
    # name, connector ref, port table, verdin-name prefix map
    ("DSI", "J4", screen_ports.PORT_A, lambda net: "DSI_1_" + net[len("DSI_"):]),
    ("LVDS", "J18", screen_ports.PORT_B, lambda net: net),
]


def _is_pair_net(net):
    return net.startswith(("DSI_D", "DSI_CLK", "LVDS"))


def signal_nets(group):
    _, _, table, _ = group
    return sorted({n for n in table.values() if _is_pair_net(n)})


def plan(pad):
    """pad(ref, number) -> (x, y, half_y) of that pad in board coordinates,
    half_y = half the pad's extent along y. Returns (items, report, corridors,
    dropped): items are ("seg", layer, net, width, [(x, y), ...]) and
    ("via", net, x, y); report maps pair -> (len_N, len_P); corridors maps
    group name -> a polygon [(x, y), ...] fenced on F.Cu, and name + "_VIAS"
    -> the stub-via strip, fenced on every signal layer; dropped lists (ref, pad number) the
    autorouter must not try to connect (every planned net's far end and every
    GND pad inside a fan)."""
    items, report, corridors, dropped = [], {}, {}, []
    for group in GROUPS:
        gname, cref, table, to_verdin = group
        contact_of = {net: c for c, net in table.items() if _is_pair_net(net)}
        links = []          # (j1_pin, contact, net, width)
        for net, c in contact_of.items():
            links.append((_PIN_OF[to_verdin(net)], c, net, W))
        # order by J1 x; the connector x order must agree (no crossings)
        links.sort(key=lambda l: pad("J1", str(l[0]))[0])
        cx = [pad(cref, str(l[1]))[0] for l in links]
        assert cx == sorted(cx), f"{gname}: connector order does not follow J1's"
        step_j1 = 2                                     # one J1 pad row
        step_c = 1 if cx[-1] > cx[0] and links[-1][1] > links[0][1] else -1

        # GND guards and stub vias, gap by gap (including both outer edges)
        def j1_between(a, b):
            lo, hi = sorted((a, b))
            return [p for p in range(lo + step_j1, hi, step_j1) if X1_PINS.get(p) == "GND"]

        def c_between(a, b):
            lo, hi = sorted((a, b))
            return [c for c in range(lo + 1, hi) if table.get(c) == "GND"]

        sig = list(links)
        port_gnd = []
        for k in range(len(sig) + 1):
            if k == 0:
                jc = [p for p in (sig[0][0] - step_j1,) if X1_PINS.get(p) == "GND"]
                cc = [c for c in (sig[0][1] - step_c,) if table.get(c) == "GND"]
            elif k == len(sig):
                jc = [p for p in (sig[-1][0] + step_j1,) if X1_PINS.get(p) == "GND"]
                cc = [c for c in (sig[-1][1] + step_c,) if table.get(c) == "GND"]
            else:
                jc = j1_between(sig[k - 1][0], sig[k][0])
                cc = c_between(sig[k - 1][1], sig[k][1])
            port_gnd += cc
            if len(jc) == 1 and len(cc) == 1:
                links.append((jc[0], cc[0], "GND", W_GUARD))
                dropped.append(("J1", str(jc[0])))
            elif jc:
                raise RuntimeError(f"{gname}: J1 GND pin(s) {jc} in the fan have no connector partner")
        links.sort(key=lambda l: pad("J1", str(l[0]))[0])

        # common jog start: just past the J1 pad row, toward the connector
        y1s = [pad("J1", str(l[0])) for l in links]
        y2s = [pad(cref, str(l[1])) for l in links]
        s = 1 if y2s[0][1] > y1s[0][1] else -1
        ya = (max if s > 0 else min)(y + s * h for _, y, h in y1s) + s * ESCAPE
        x1s, x2s, y_j1, y_far = [], [], [], []
        for (j1p, c, net, wid), (x1, y1, h1), (x2, y2, h2) in zip(links, y1s, y2s):
            dx = x2 - x1
            yb = ya + s * abs(dx)
            if s * ((y2 - s * h2) - yb) < END_CLEAR:
                raise RuntimeError(f"{gname}: fan too short for {net} (needs "
                                   f"{abs(dx) + ESCAPE + END_CLEAR:.1f} mm between the pad rows)")
            pts = [(x1, y1 + s * STUB), (x1, ya), (x2, yb), (x2, y2)]
            items.append(("seg", "F.Cu", net, wid, pts))
            if net != "GND":
                dropped.append((cref, str(c)))
                L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
                pair = net[:-2]
                n_len, p_len = report.get(pair, (None, None))
                report[pair] = (round(L, 2), p_len) if net.endswith("_N") else (n_len, round(L, 2))
            x1s.append(x1)
            x2s.append(x2)
            y_j1.append(y1 + s * (h1 + 0.1))
            # the fence runs on to just past the GND stub vias behind the
            # connector pads (added after the autorouter, so the router must be
            # kept out of that strip too)
            y_far.append(y2 + s * (VIA_OFFSET + VIA_DIA / 2 + 0.35))
        gx = {c: pad(cref, str(c))[0] for c in port_gnd}
        lo_c, hi_c = min(gx, key=gx.get), max(gx, key=gx.get)
        for c in port_gnd:
            x2, y2, h2 = pad(cref, str(c))
            vy = y2 + s * VIA_OFFSET
            # keep the outermost vias inside the narrow corridor (see the margins)
            vx = x2 + (EDGE_VIA_INSET if c == lo_c else -EDGE_VIA_INSET if c == hi_c else 0.0)
            items.append(("seg", "F.Cu", "GND", W_STUB, [(x2, y2), (x2, y2 + s * h2), (vx, vy)]))
            items.append(("via", "GND", vx, vy))
            dropped.append((cref, str(c)))
        x2s += list(gx.values())        # stub-only GND contacts are inside the fence too
        # The corridor follows the fan: as wide as J1's pads (plus 0.5 mm) up to
        # the jog, 45 degree sides parallel to the outer tracks, and only 0.3 mm
        # past the outer connector contacts at the connector end, so the
        # control contacts right beside the fan keep their escapes. (A plain
        # rectangle as wide as the J1 end covered them: 12 connections
        # unroutable, 2026-10-20.)
        jl, jr = min(x1s) - CORRIDOR_J1_MARGIN, max(x1s) + CORRIDOR_J1_MARGIN
        pl, pr = min(x2s) - CORRIDOR_PORT_MARGIN, max(x2s) + CORRIDOR_PORT_MARGIN
        yj = (min if s > 0 else max)(y_j1)
        yf = (max if s > 0 else min)(y_far)
        # 45 degree sides, whether the group narrows (fan-in) or widens toward
        # the connector
        corridors[gname] = [(jl, yj), (jr, yj), (jr, ya), (pr, ya + s * abs(jr - pr)), (pr, yf),
                            (pl, yf), (pl, ya + s * abs(pl - jl)), (jl, ya)]
        # The GND stub vias go through every layer, so the strip behind the
        # connector pads where they sit is fenced on all signal layers, not only
        # F.Cu (an In3 track ran under one, 2026-10-20).
        yv = y2s[0][1] + s * y2s[0][2]          # the connector pads' far edge
        corridors[gname + "_VIAS"] = [(pl, yv), (pr, yv), (pr, yf), (pl, yf)]
    return items, report, corridors, dropped


def planned_nets():
    return sorted({n for g in GROUPS for n in signal_nets(g)})
