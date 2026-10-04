"""
DSI lane routing for the display carrier (pure geometry, no KiCad imports, so
build_pcb.py can report it and route_board.py can apply it).

J1 (Verdin SODIMM) lists every DSI pair N then P along its pad row; J4 (panel
FPC) lists the same pair P then N. So each pair has to swap once between the
two connectors. Per pair: the N leg runs on F.Cu the whole way (down, one 45
degree jog across, down); the P leg jogs away from N, drops through a via to
B.Cu, runs under N, and comes back to F.Cu through a second via on the other
side of N. Both legs are 0.25 mm wide on F.Cu over the unbroken In1 GND plane
(about 100 ohm differential by IPC-2141 for a 0.21 mm prepreg and a 0.25 mm gap;
that is an estimate, not a field-solver result).

Lanes are in order of increasing x on J1 and J4 (D2, CLK, D1, D0), so the
four pairs never cross each other.
"""
import math

W = 0.25                 # F.Cu / B.Cu track width, mm
VIA_DIA, VIA_DRILL = 0.6, 0.3
LANES = ["DSI_D2", "DSI_CLK", "DSI_D1", "DSI_D0"]
J1_PIN_NET = "J1"
STUB = 0.4               # how far inside the pad a track starts/ends, mm


def plan(pad):
    """pad(ref, net) -> (x, y, half_height) of the single pad of that net on
    that part (board coordinates, half_height = half the pad's extent along y).
    Returns (items, report, corridor): items are
    ("seg", layer, net, [(x, y), ...]) and ("via", net, x, y); report maps lane
    -> (lenN, lenP); corridor is (x0, y0, x1, y1) around all DSI copper."""
    items, report = [], {}
    xs, ys = [], []
    for lane in LANES:
        n1x, n1y, n1h = pad("J1", lane + "_N")
        p1x, p1y, _ = pad("J1", lane + "_P")
        n4x, n4y, n4h = pad("J4", lane + "_N")
        p4x, p4y, _ = pad("J4", lane + "_P")
        assert abs(n1y - p1y) < 1e-6 and abs(n4y - p4y) < 1e-6, "DSI pads not in one row"
        assert p1x > n1x and n4x > p4x, "pad order differs from the crossing template"
        y1_end = n1y + n1h
        y4_top = n4y - n4h
        y_via1 = y1_end + 0.6
        d_n = n4x - n1x
        ya = y_via1 + 1.0                     # N starts its jog below the P via
        yb = ya + abs(d_n)
        y_via2 = yb + 0.9
        if y_via2 >= y4_top - 0.5:
            raise RuntimeError("DSI corridor too short for the pair crossing")
        net_n, net_p = lane + "_N", lane + "_P"
        ptsN = [(n1x, n1y + STUB), (n1x, ya), (n4x, yb), (n4x, n4y - 0.1)]
        v1x = p1x + 0.3
        ptsP1 = [(p1x, p1y + STUB), (p1x, y1_end + 0.3), (v1x, y_via1)]
        dxb = v1x - p4x
        ptsPb = [(v1x, y_via1), (p4x, y_via1 + dxb), (p4x, y_via2)]
        ptsP2 = [(p4x, y_via2), (p4x, p4y - 0.1)]
        items.append(("seg", "F.Cu", net_n, ptsN))
        items.append(("seg", "F.Cu", net_p, ptsP1))
        items.append(("via", net_p, v1x, y_via1))
        items.append(("seg", "B.Cu", net_p, ptsPb))
        items.append(("via", net_p, p4x, y_via2))
        items.append(("seg", "F.Cu", net_p, ptsP2))

        def length(pts):
            return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))

        report[lane] = (round(length(ptsN), 2),
                        round(length(ptsP1) + length(ptsPb) + length(ptsP2), 2))
        xs += [n1x, p1x + 0.3, n4x, p4x, n4x, v1x]
        ys += [y1_end, y4_top]
    corridor = (min(xs) - 0.8, min(ys) + 0.1, max(xs) + 0.8, max(ys) - 0.0)
    return items, report, corridor
