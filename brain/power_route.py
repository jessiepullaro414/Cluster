"""
Planned power copper on the brain board (2026-11-06). Pure geometry, no KiCad imports, so
build_pcb.py can write the fences and route_board.py can add the copper after the autorouter,
the same way as fan_route.py and usb_route.py.

Why it isn't autorouted: every autorouted +5V track is 0.2 mm, and until now all of the buck's
output left L1 pad 2 on one of them, 10 mm to the first via into the In3 pour: 1021 K by IPC-2221
at the Alfa's 5.7 A peak. J1's five supply pins hung on 26 mm of the same track at 2 A. The In3
pour itself was never the problem: solved as a sheet, it loses 93 mW at 5.7 A
(review/power_sheet.py). What was missing is copper between the parts and the pour.

So each place that carries real current gets copper of its own, fenced from the autorouter:

* SW_5V, U2 pin 10 to L1: 1.5 mm between U2's PGND pads, 2.4 mm after them.
* U2's PGND pins to the input capacitors' GND pads on F.Cu, then GND vias beside them. Pin 9 and
  pin 11 each carry half of what the low-side switch conducts, about 2.2 A RMS at 5.7 A out, and
  had 0.2 mm stubs. It also shortens the input loop, which TI SNVSB70 asks for.
* The output capacitors' GND pads to one large via each.
* L1 pad 2 and the output capacitors onto one bar with four 1.0/0.5 mm vias into In3. Nothing
  fits inside the pad (no via in pad), but the 1.4 mm gap beside it holds them.
* J1's supply pins 251-259 onto a bar with two vias into In3.
* The port switches' IN pins (U6, U7, U11) with their capacitors onto a bar with two vias each,
  on the far side of the switch's own pin row. U16 sits right under the buck, so it gets a
  direct F.Cu run instead, and that run carries on past C89 to two more vias below U16. In3 is
  busiest round U16, and this puts the current for U11, U6 and U7 onto the pour past it.

The rest of +5V carries milliamps and stays autorouted at 0.2 mm. J1 pin 259 is left in the
router's input as the tie: it's on the planned copper, nothing else is near its free side, and the
router brings every other +5V pad to it. All the other pads the plan connects are dropped from the
router's input. (C89, under the buck, was the first tie. That strip is the board's most crowded and
the tree boxed in USB1_OC_N.)

In3 is shared with signals, so wire fences keep them off the pour right round the vias, between
the buck and J1, and along the bottom edge to U6. review/power_sheet.py solves the result; a route
it fails is a failed attempt.
"""
import math

VIA_5V = (1.0, 0.5)      # pad, drill: the battery path's size, about 2.6 A per via at 17 K
VIA_GND = (0.8, 0.4)
MARGIN = 0.05            # fence beyond the copper. The router keeps its 0.2 mm clearance from the fence
# Vias on one bar stay this far apart, centre to centre. Each cuts a 1.4 mm hole in the GND planes (1.0 mm plus 0.2 mm
# clearance a side), and the pour keeps nothing narrower than 0.2 mm: closer than 1.6 mm and the holes merge into a slot. The
# first version's five vias at 1.4 mm cut a 7 mm slot in In1 and In4, the longest on the board, across the output loop's return.
VIA_PITCH_MIN = 1.7


def _box_round(a, b, half):
    """A rectangle round the segment a-b, grown by half on every side, ends included."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 1e-9 else (1.0, 0.0)
    nx, ny = -uy, ux
    return [(a[0] - ux * half + nx * half, a[1] - uy * half + ny * half),
            (b[0] + ux * half + nx * half, b[1] + uy * half + ny * half),
            (b[0] + ux * half - nx * half, b[1] + uy * half - ny * half),
            (a[0] - ux * half - nx * half, a[1] - uy * half - ny * half)]


class _Plan:
    def __init__(self):
        self.items, self.corridors, self.corridor_nets = [], {}, {}
        self.n = 0

    def _fence(self, net, poly, suffix=""):
        self.n += 1
        name = f"PWR{self.n}{suffix}"
        self.corridors[name] = poly
        self.corridor_nets[name] = [net]

    def seg(self, net, width, *pts, fence=True):
        """F.Cu track through pts. fence=False for a stub that ends on a pad: the pad is the
        fence, and a box round it would crowd the next pin's escape."""
        self.items.append(("seg", "F.Cu", net, width, list(pts)))
        if fence:
            for a, b in zip(pts, pts[1:]):
                self._fence(net, _box_round(a, b, width / 2 + MARGIN))

    def via(self, net, x, y, size):
        self.items.append(("via", net, x, y, size[0], size[1]))
        r = size[0] / 2 + MARGIN
        self._fence(net, [(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r)], "_VIAS")

    def in3(self, name, poly):
        """Keep other nets' tracks off a stretch of the In3 pour. Vias may still pass."""
        self.corridors[f"PWR_{name}_IN3"] = poly
        self.corridor_nets[f"PWR_{name}_IN3"] = ["+5V"]


def _west_or_east_switch(P, pad, ref, bulk, ceramic, side):
    """A switch whose IN pins (2 and 3) face west (side -1) or east (side +1): a bar one via's
    width out from the pin row, a via at each end of it, the capacitors tied on."""
    xp, y2, _ = pad(ref, "2")
    _, y3, _ = pad(ref, "3")
    ym = (y2 + y3) / 2
    edge = xp + side * 0.3               # the pads' outer edge
    xb = edge + side * 0.9               # the bar. A via beside it clears the next pin by 0.4 mm
    xf = edge + side * 0.35              # where the feed's round end reaches into the pads
    P.seg("+5V", 0.97, (xb, ym), (xf, ym))
    P.seg("+5V", 0.31, (xf, y2), (xp, y2), fence=False)
    P.seg("+5V", 0.31, (xf, y3), (xp, y3), fence=False)
    v0, v1 = ym - 1.1, ym + 1.1
    P.seg("+5V", 1.0, (xb, v0), (xb, v1))
    P.via("+5V", xb, v0, VIA_5V)
    P.via("+5V", xb, v1, VIA_5V)
    xc, yc, _ = pad(*bulk)
    xd, yd, _ = pad(*ceramic)
    if side < 0:
        # U6, U7: the bulk capacitor is level with pin 2, the ceramic just below it
        P.seg("+5V", 1.2, (xc, yc), (xb, yc))
        P.seg("+5V", 0.6, (xd, yd), (xd + 0.98, yd), (xb, v1))
    else:
        # U11: the capacitors are 6 mm above and 5 mm below the pins
        P.seg("+5V", 0.6, (xb, v0), (xb, yc + 1.52), (xc + 0.24, yc + 0.12))
        P.seg("+5V", 0.6, (xb, v1), (xb, yd - 1.03), (xd + 0.17, yd - 0.03))
    return xb, ym


def plan(pad):
    """pad(ref, number) -> (x, y, half_y) in board coordinates. Returns (items, report, corridors,
    dropped, corridor_nets). Items as in usb_route.plan(), except that a via also carries its
    pad and drill: ("via", net, x, y, dia, drill). Each corridor is fenced on F.Cu, or on every
    signal layer if its name ends _VIAS, or against In3 tracks only if it ends _IN3."""
    P = _Plan()

    # --- SW_5V: U2 pin 10 to L1 pad 1
    xs, ys, _ = pad("U2", "10")
    xl1, _, _ = pad("L1", "1")
    e = xs + 1.2                         # pin 10's east end
    P.seg("SW_5V", 0.4, (e - 0.2, ys), (e + 0.18, ys))
    P.seg("SW_5V", 1.5, (e + 0.18, ys), (e + 1.13, ys))
    P.seg("SW_5V", 2.4, (e + 1.13, ys), (xl1 - 0.58, ys))   # its round end stops at the pad's far edge: +12V_PROT runs just past it

    # --- U2's PGND pins (they're symmetric about pin 10) to the input capacitors and GND vias
    xa = xs + 0.6                        # the pins' inner tabs
    for s, cap in ((+1, ("C56", "2")), (-1, ("C57", "2"))):
        ya, yb, yv, yw = ys + s * 1.675, ys + s * 1.88, ys + s * 2.63, ys + s * 3.73
        P.seg("GND", 0.5, (xa, ya), (xa + 0.28, yb))
        P.seg("GND", 0.7, (xa + 0.28, yb), (xa + 2.38, yb))
        x1, x2 = xa + 1.28, xa + 2.38
        P.seg("GND", 0.6, (x1, yb), (x1, yv))
        P.seg("GND", 0.6, (x2, yb), (x2, yv))
        P.seg("GND", 0.6, (x1, yv), (x1 + 0.1, yw))
        P.via("GND", x1, yv, VIA_GND)
        P.via("GND", x2, yv, VIA_GND)
        P.via("GND", x1 + 0.1, yw, VIA_GND)
        xc, yc, _ = pad(*cap)
        P.seg("GND", 0.8, (xa + 0.08, yb), (xc - 0.035, yc))
    # C5 sits below C56 and joins it, with one more via beside them
    xc, yc, _ = pad("C56", "2")
    x5, y5, _ = pad("C5", "2")
    P.seg("GND", 0.8, (xc, yc + 0.38), (x5, y5 - 0.82), (x5, y5))
    P.seg("GND", 0.6, (xc, yc), (xc + 1.265, yc + 0.43))
    P.via("GND", xc + 1.265, yc + 0.43, VIA_GND)

    # --- the output capacitors' GND pads, one large via each
    for ref in ("C59", "C54", "C8"):
        x, y, _ = pad(ref, "2")
        P.seg("GND", 1.2, (x, y), (x + 1.365, y))
        P.via("GND", x + 1.365, y, VIA_GND)

    # --- L1 pad 2 and the output capacitors onto a bar in the gap between them, vias into In3
    xl, yl, _ = pad("L1", "2")
    xc54, _, _ = pad("C54", "1")
    xb = (xl + 0.59 + xc54 - 0.575) / 2
    P.seg("+5V", 1.42, (xb, yl - 2.8), (xb, yl + 2.8))     # touches L1's pad all along its height, and the capacitors'
    bar_vias = (-2.8, -2.8 / 3, 2.8 / 3, 2.8)
    assert min(b - a for a, b in zip(bar_vias, bar_vias[1:])) >= VIA_PITCH_MIN
    for d in bar_vias:
        P.via("+5V", xb, yl + d, VIA_5V)
    P.seg("+5V", 1.2, (xl, yl), (xb, yl))                  # 1.2 mm: a wider round end would stick out of the pad's near side
    P.seg("+5V", 1.2, (xl, yl - 1.6), (xb, yl - 1.6))
    P.seg("+5V", 1.2, (xl, yl + 1.6), (xb, yl + 1.6))
    for ref in ("C59", "C54", "C8"):
        x, y, _ = pad(ref, "1")
        P.seg("+5V", 1.2, (x, y), (xb, y))

    # --- U16's IN pins and its capacitors, straight down from the bar on F.Cu
    x2, yu, _ = pad("U16", "2")
    x3, _, _ = pad("U16", "3")
    yr = yu - 1.08
    P.seg("+5V", 1.0, (xb, yl + 2.8), (xb, yr))
    P.seg("+5V", 0.8, (xb, yr), (x3 - 0.1, yr))
    P.seg("+5V", 0.31, (x2, yr), (x2, yu), fence=False)
    P.seg("+5V", 0.31, (x3, yr), (x3, yu), fence=False)
    x88, y88, _ = pad("C88", "1")
    x89, y89, _ = pad("C89", "1")
    P.seg("+5V", 1.0, (xb, yr), (x88, y88 - 0.38), (x88, y88))
    P.seg("+5V", 1.0, (x88, y88), (x89, y89))
    yd = y89 + 1.65                      # below C89, on the way to the bottom edge
    P.seg("+5V", 1.0, (x89, y89), (x89, yd))
    d = VIA_PITCH_MIN / 2
    P.seg("+5V", 1.0, (x89 - d, yd), (x89 + d, yd))
    P.via("+5V", x89 - d, yd, VIA_5V)
    P.via("+5V", x89 + d, yd, VIA_5V)

    # --- J1's supply pins onto a bar, vias into In3
    xj = [pad("J1", str(p))[0] for p in (251, 253, 255, 257, 259)]
    yj = pad("J1", "255")[1]
    ybar = yj + 1.17
    for x in xj:
        P.seg("+5V", 0.3, (x, yj + 0.42), (x, ybar), fence=False)
    P.seg("+5V", 1.0, (xj[0] + 0.39, ybar), (xj[-1] + 0.39, ybar))
    xm = xj[2] + 0.39
    yv = ybar + 1.55
    P.seg("+5V", 2.0, (xm, ybar), (xm, yv))
    d = VIA_PITCH_MIN / 2
    P.seg("+5V", 1.0, (xm - d, yv), (xm + d, yv))
    P.via("+5V", xm - d, yv, VIA_5V)
    P.via("+5V", xm + d, yv, VIA_5V)

    # --- the port switches
    u6 = _west_or_east_switch(P, pad, "U6", ("C41", "1"), ("C40", "1"), -1)
    u7 = _west_or_east_switch(P, pad, "U7", ("C45", "1"), ("C44", "1"), -1)
    u11 = _west_or_east_switch(P, pad, "U11", ("C81", "1"), ("C80", "1"), +1)

    # --- In3: no other net's tracks right round the vias, between the buck and J1, or along the bottom edge.
    # Three full routes with fences over the whole strip under the buck left the USB-C ports' control lines
    # unrouted every time: they need In3 there, so the way down to the bottom edge is a 3.4 mm strip.
    # The rest of the pour is left to review/power_sheet.py.
    P.in3("BUCK", [(xb - 2.2, yl - 4.6), (xb + 2.6, yl - 4.6), (xb + 2.6, yl + 4.6), (xb - 2.2, yl + 4.6)])
    P.in3("BUCK_J1", [(xm - 2.5, yj + 1.0), (xm + 2.5, yj + 1.0), (xb + 2.6, yl - 7.5), (xb + 2.6, yl - 4.6),
                      (xb - 2.2, yl - 4.6), (xm - 2.5, yv + 2.2)])
    bottom = pad("J19", "A9")[1] + 6.25    # 0.5 mm in from the board's bottom edge
    y_band = bottom - 4.4
    P.in3("BOTTOM", [(u6[0] - 2.0, y_band), (xb + 1.9, y_band), (xb + 1.9, bottom), (u6[0] - 2.0, bottom)])
    P.in3("BUCK_DOWN", [(xb - 1.5, yl + 4.6), (xb + 1.9, yl + 4.6), (xb + 1.9, y_band), (xb - 1.5, y_band)])
    P.in3("U6", [(u6[0] - 2.0, u6[1] - 2.2), (u6[0] + 1.8, u6[1] - 2.2), (u6[0] + 1.8, y_band), (u6[0] - 2.0, y_band)])
    # U7 gets a 3.8 mm strip up to the open pour along the top edge: on one route its 1.98 A squeezed out between two tracks
    P.in3("U7", [(u7[0] - 2.0, u7[1] - 17.5), (u7[0] + 1.8, u7[1] - 17.5), (u7[0] + 1.8, u7[1] + 2.2), (u7[0] - 2.0, u7[1] + 2.2)])
    P.in3("U11", [(u11[0] - 1.8, u11[1] - 2.2), (u11[0] + 1.8, u11[1] - 2.2), (u11[0] + 1.8, y_band), (u11[0] - 1.8, y_band)])

    dropped = [("L1", "1"), ("L1", "2"),
               ("U2", "9"), ("U2", "9@1"), ("U2", "11"), ("U2", "11@1"),
               ("C56", "2"), ("C57", "2"), ("C5", "2"),
               ("C59", "1"), ("C54", "1"), ("C8", "1"), ("C59", "2"), ("C54", "2"), ("C8", "2"),
               ("U16", "2"), ("U16", "3"), ("C88", "1"), ("C89", "1"),
               ("J1", "251"), ("J1", "253"), ("J1", "255"), ("J1", "257"),
               ("U6", "2"), ("U6", "3"), ("C41", "1"), ("C40", "1"),
               ("U7", "2"), ("U7", "3"), ("C45", "1"), ("C44", "1"),
               ("U11", "2"), ("U11", "3"), ("C81", "1"), ("C80", "1")]
    return P.items, {}, P.corridors, dropped, P.corridor_nets


def planned_nets():
    return ["+5V", "SW_5V", "GND"]
