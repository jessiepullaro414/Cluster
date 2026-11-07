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

The battery path gets the same (2026-11-06, when the shrink moved the front end): on the first routes
of the smaller board the autorouter left it 0.3 mm necks, 92 K by IPC-2221 at 2.65 A, where a track
hugged a pad and the widening step couldn't move it. So, on F.Cu all the way:

* J2 pin 1 to the fuse, the fuse to the TVS, a 2.4 mm strap past the TVS's GND pad to Q2's tab.
* Q2 and Q1 with their source pins facing, so COMMON is about 2 mm long.
* Q1's tab straight into the sense resistor, the sense resistor down to a bus over the buck's upper input
  capacitors, with a branch to the bulk capacitor C1.
* The buck has two input pins, top and bottom. C5 and C56 at the bottom one get the bulk supply over a
  1.5 mm strap on B.Cu, straight under the buck, through two large vias at each end. (A strap on F.Cu between
  L1's two pads fits too, but it boxes in U16's enable pin.)
* The boot capacitor's SW branch leaves pin 10 between pins 12 and 13, so it doesn't cross the feed to pin 12,
  and R9 sits right over pins 13 and 14. Pin 1 (BIAS) has its own via into a fenced stretch of the In3 pour.
* The TVS and the bulk capacitor get their GND vias.

And so do the two screen ports' switched 5 V, up to the switch's 1.98 A limit: on the same routes they came back with
0.4 mm necks at the switch and the connector, 21 to 29 K.

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

    def seg_b(self, net, width, *pts):
        """The same on B.Cu."""
        self.items.append(("seg", "B.Cu", net, width, list(pts)))
        for a, b in zip(pts, pts[1:]):
            self._fence(net, _box_round(a, b, width / 2 + MARGIN), "_BCU")

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

    battery_dropped = _battery(P, pad) + _ports(P, pad)

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
    # U7 gets a 3.8 mm strip up to the top edge, and a 3 mm strip along it to the free pour behind port B: on one route its
    # 1.98 A squeezed out between two tracks
    y_top = pad("J10", "1")[1] - 12.0        # 0.5 mm in from the top edge: the holder's courtyard is 11.8 mm, plus 0.7 mm
    x_portb = pad("J18", "1")[0]
    P.in3("U7", [(u7[0] - 2.0, y_top), (u7[0] + 1.8, y_top), (u7[0] + 1.8, u7[1] + 2.2), (u7[0] - 2.0, u7[1] + 2.2)])
    P.in3("U7_TOP", [(u7[0] + 1.8, y_top), (x_portb + 4.0, y_top), (x_portb + 4.0, y_top + 3.0), (u7[0] + 1.8, y_top + 3.0)])
    P.in3("U11", [(u11[0] - 1.8, u11[1] - 2.2), (u11[0] + 1.8, u11[1] - 2.2), (u11[0] + 1.8, y_band), (u11[0] - 1.8, y_band)])

    dropped = [("L1", "1"), ("L1", "2"),
               ("U2", "9"), ("U2", "9@1"), ("U2", "11"), ("U2", "11@1"),
               ("C56", "2"), ("C57", "2"), ("C5", "2"),
               ("C59", "1"), ("C54", "1"), ("C8", "1"), ("C59", "2"), ("C54", "2"), ("C8", "2"),
               ("U16", "2"), ("U16", "3"), ("C88", "1"), ("C89", "1"),
               ("J1", "251"), ("J1", "253"), ("J1", "255"), ("J1", "257"),
               ("U6", "2"), ("U6", "3"), ("C41", "1"), ("C40", "1"),
               ("U7", "2"), ("U7", "3"), ("C45", "1"), ("C44", "1"),
               ("U11", "2"), ("U11", "3"), ("C81", "1"), ("C80", "1")] + battery_dropped
    return P.items, {}, P.corridors, dropped, P.corridor_nets


def planned_nets():
    return ["+5V", "SW_5V", "GND"]


# Nets the plan connects completely: one pin of each stays in the router's input, alone, so the net has nothing to route and
# the fences over that pin don't matter.
LONE_NETS = ["VBAT_IN", "SW_5V", "+12V_PROT", "BOOT_C", "BOOT_R", "PORTA_5V", "PORTB_5V"]


def _switch_out(P, net, pad, ref, cap):
    """A port switch's OUT pins (6 and 7, on its east side) onto a short bar, and from there to its capacitor."""
    xp, y7, _ = pad(ref, "7")
    y6 = pad(ref, "6")[1]
    xb = xp + 0.9
    P.seg(net, 0.31, (xp, y7), (xb, y7), fence=False)
    P.seg(net, 0.31, (xp, y6), (xb, y6), fence=False)
    P.seg(net, 0.6, (xb, y7), (xb, y6))
    xc, yc, _ = pad(*cap)
    P.seg(net, 1.0, (xb + 0.1, y7 - 0.3), (xc - 0.1, yc + 0.3))
    P.seg(net, 0.6, (xb, y7), (xb + 0.1, y7 - 0.3), fence=False)
    return xc, yc


def _ports(P, pad):
    """Each screen port's 5 V, switch to connector."""
    # Port A: C42 up and to the right, under J4's pad row, stubs up to its four contacts
    xc, yc = _switch_out(P, "PORTA_5V", pad, "U6", ("C42", "1"))
    xj = [pad("J4", str(n))[0] for n in (2, 3, 4, 5)]
    yj, hj = pad("J4", "3")[1], pad("J4", "3")[2]
    ys = yj + hj + 0.2 + 0.4              # 0.8 mm where it runs between J4's contacts and its mounting pad
    x0, y0 = xc + 0.2, yc - 0.7
    xm = pad("J4", "MP", 0)[0] - 1.4 - 0.6 - 0.2
    P.seg("PORTA_5V", 1.2, (xc, yc), (x0, y0), (x0 + y0 - ys, ys), (xm, ys))
    P.seg("PORTA_5V", 0.8, (xm, ys), (xj[-1], ys))
    for x in xj:
        P.seg("PORTA_5V", 0.3, (x, ys), (x, yj), fence=False)
    # Port B: C46 down and to the right, past R77 and C46's GND pad where there's only room for 0.6 mm, then over J18's five contacts.
    # J18 is turned 180 degrees, so its pads' free side is the one away from the socket.
    xc, yc = _switch_out(P, "PORTB_5V", pad, "U7", ("C46", "1"))
    xj = [pad("J18", str(n))[0] for n in (45, 46, 47, 48, 49)]
    yj, hj = pad("J18", "47")[1], pad("J18", "47")[2]
    yn = yj - hj - 0.2 - 0.5
    x1, y1 = xc + 2.4, yc + 2.4
    P.seg("PORTB_5V", 0.6, (xc, yc), (x1, y1))
    y2 = y1 + 0.3
    xm = min(xj)                                    # J18's mounting pad is just left of this run
    yv = y2 + 2.0
    P.seg("PORTB_5V", 1.2, (x1, y1), (x1 + 0.3, y2), (xm - (yv - y2), y2), (xm, yv), (xm, yn))
    P.seg("PORTB_5V", 1.0, (xm, yn), (max(xj), yn))
    for x in xj:
        P.seg("PORTB_5V", 0.3, (x, yn), (x, yj), fence=False)
    return [("U6", "7"), ("C42", "1"), ("J4", "2"), ("J4", "3"), ("J4", "4"), ("J4", "5"),     # U6 pin 6 stays as PORTA_5V's lone pin
            ("U7", "7"), ("C46", "1"), ("J18", "45"), ("J18", "46"), ("J18", "47"), ("J18", "48"), ("J18", "49")]


def _battery(P, pad):
    """The battery path, J2 to both of the buck's input pins. Returns the pads it connects, as dropped pins."""
    # --- J2 pin 1 to the fuse, the fuse's two pins per side
    xj, yj, _ = pad("J2", "1")
    xf1, yf1b, _ = pad("F1", "1", 0)      # each pair of pins, upper and lower
    _, yf1a, _ = pad("F1", "1", 1)
    P.seg("VBAT_IN", 2.0, (xj, yj), (xf1, yf1b), (xf1, yf1a))
    xf2, yf2b, _ = pad("F1", "2", 0)
    _, yf2a, _ = pad("F1", "2", 1)
    P.seg("VBAT_F", 2.0, (xf2, yf2b), (xf2, yf2a))

    # --- the TVS, pad 1 straight under the fuse, then round its GND pad to Q2's tab
    xd, yd1, _ = pad("D1", "1")
    _, yd2, _ = pad("D1", "2")
    P.seg("VBAT_F", 2.0, (xf2, yf2a), (xd, yd1))
    xq, row2, _ = pad("Q2", "2")          # the FETs' centre line is half a pin pitch from pins 2 and 3
    xq = (xq + pad("Q2", "3")[0]) / 2
    row1 = pad("Q1", "2")[1]
    y2tab = row2 - 3.795                  # the tab's centre, from the footprint: pins at -2.715 and the tab at +1.08 along its x
    y1tab = row1 + 3.795
    xs = xd - 1.65 - 0.25 - 1.2           # the strap: 0.25 mm from the GND pad's edge (its pads are 3.3 mm across the part)
    P.seg("VBAT_F", 2.4, (xd, yd1), (xs, yd1), (xs, y2tab - 1.3))
    P.seg("VBAT_F", 2.0, (xs, y2tab - 1.3), (xq, y2tab - 0.9), fence=False)
    # D1's GND pad: two large vias on its right, 1.8 mm apart
    xv = xd + 1.65 + 0.2 + 0.6
    P.seg("GND", 2.0, (xd, yd2), (xv, yd2))
    P.seg("GND", 1.0, (xv, yd2 - 0.9), (xv, yd2 + 0.9))
    P.via("GND", xv, yd2 - 0.9, VIA_5V)
    P.via("GND", xv, yd2 + 0.9, VIA_5V)

    # --- COMMON: Q2's source pins straight down to a bar, Q1's straight up to it, overlapping in the middle
    xa = [pad("Q2", str(n))[0] for n in (1, 2, 3)]
    xb = [pad("Q1", str(n))[0] for n in (1, 2, 3)]
    P.seg("COMMON", 0.9, (min(xa), row2 + 0.76), (max(xa), row2 + 0.76))
    P.seg("COMMON", 0.9, (min(xb), row1 - 0.76), (max(xb), row1 - 0.76))
    P.seg("COMMON", 1.0, (xq, row2 + 0.76), (xq, row1 - 0.76))
    for x in xa:
        P.seg("COMMON", 0.41, (x, row2), (x, row2 + 0.76), fence=False)
    for x in xb:
        P.seg("COMMON", 0.41, (x, row1), (x, row1 - 0.76), fence=False)

    # --- Q1's tab into the sense resistor
    xr1, yr1, _ = pad("R1", "1")
    P.seg("SENSE_HI", 1.75, (xq, y1tab + 1.2), (xr1, yr1))

    # --- the sense resistor down to a bus over C55 and C57
    xr2, yr2, _ = pad("R1", "2")
    x55, y55, _ = pad("C55", "1")
    x57, y57, _ = pad("C57", "1")
    y_bus = y55 - 0.9 - 0.2 - 0.5 - 0.05  # 1 mm wide, clear of C55's GND pad
    P.seg("+12V_PROT", 1.75, (xr2, yr2), (xr2, yr2 + 1.5))
    P.seg("+12V_PROT", 2.0, (xr2, yr2 + 1.5), (x55, yr2 + 1.5 + (xr2 - x55)), (x55, y_bus - 0.5))
    P.seg("+12V_PROT", 1.15, (x55, y_bus - 0.5), (x55, y55))
    d = VIA_PITCH_MIN / 2
    P.seg("+12V_PROT", 1.0, (x55, y_bus), (x57 - d - 0.2, y_bus))
    P.seg("+12V_PROT", 0.9, (x57, y_bus), (x57, y57), fence=False)
    # C1, off to the right of the sense resistor
    xc1, yc1, _ = pad("C1", "1")
    P.seg("+12V_PROT", 1.5, (xr2, yr2 + 1.5), (xc1 - 1.2, yr2 + 1.5), (xc1, yc1))
    xc2, yc2, _ = pad("C1", "2")
    P.seg("GND", 2.0, (xc2, yc2), (xc2, yc2 - 1.9))
    P.seg("GND", 1.0, (xc2 - 0.9, yc2 - 1.9), (xc2 + 0.9, yc2 - 1.9))
    P.via("GND", xc2 - 0.9, yc2 - 1.9, VIA_5V)
    P.via("GND", xc2 + 0.9, yc2 - 1.9, VIA_5V)

    # --- the top input pin, straight up from pin 12 to C57
    x12, y12, _ = pad("U2", "12")
    P.seg("+12V_PROT", 0.8, (x12 + 0.2, y57 + 0.2), (x12 + 0.2, y12 - 0.3))
    # --- C55's GND pad: a via between its two pads, under the part, right beside the bus
    x552_, y552, _ = pad("C55", "2")
    xv55 = (x55 + x552_) / 2
    P.seg("GND", 1.0, (x552_, y552), (xv55, y552))
    P.via("GND", xv55, y552, VIA_GND)

    # --- the bottom input pin: from the bus on B.Cu, straight under the buck, to C5, then up through C56 to pin 8.
    # R13's milliamps come off the same strap, through a via of their own.
    x5, y5, _ = pad("C5", "1")
    x56, y56, _ = pad("C56", "1")
    x8, y8, _ = pad("U2", "8")
    y_low = y5 + 2.3                     # the vias, under C5
    P.via("+12V_PROT", x5 - d, y_bus, VIA_5V)
    P.via("+12V_PROT", x5 + d, y_bus, VIA_5V)
    P.seg_b("+12V_PROT", 1.0, (x5 - d, y_bus), (x5 + d, y_bus))
    P.seg_b("+12V_PROT", 1.5, (x5, y_bus), (x5, y_low))
    P.seg_b("+12V_PROT", 1.0, (x5 - d, y_low), (x5 + d, y_low))
    P.via("+12V_PROT", x5 - d, y_low, VIA_5V)
    P.via("+12V_PROT", x5 + d, y_low, VIA_5V)
    P.seg("+12V_PROT", 1.0, (x5 - d, y_low), (x5 + d, y_low))
    P.seg("+12V_PROT", 1.0, (x5, y_low), (x5, y5 + 0.85))
    P.seg("+12V_PROT", 1.0, (x56, y56), (x5 + 0.2, y5 - 0.85))
    P.seg("+12V_PROT", 0.9, (x56, y56), (x8, y8 + 0.1))
    x13, y13, _ = pad("R13", "1")
    P.seg("+12V_PROT", 0.4, (x13, y13), (x13, y13 + 1.05), fence=False)
    P.via("+12V_PROT", x13, y13 + 1.05, (0.6, 0.3))
    P.seg_b("+12V_PROT", 0.4, (x13, y13 + 1.05), (x5 + 0.7, y13 + 1.05))

    # --- the boot capacitor's SW branch, out of pin 10's west end between pins 12 and 13
    xp10, yp10, _ = pad("U2", "10")
    x_sw = pad("U2", "13")[0] + 0.125 + 0.2 + 0.15
    x7, y7, _ = pad("C7", "2")
    P.seg("SW_5V", 0.3, (x_sw, yp10), (x_sw, y7 + 1.1), (x7, y7))
    # --- R9, right over pins 13 and 14: pin 13 up to R9's pad 1, pin 14 under it to pad 2 and on to C7
    x_13, y_13, _ = pad("U2", "13")
    x_14, y_14, _ = pad("U2", "14")
    xr91, yr9, _ = pad("R9", "1")
    xr92, _, _ = pad("R9", "2")
    xc71, yc71, _ = pad("C7", "1")
    y_t = y_13 - 0.2                     # inside the pins' pads, near their top
    P.seg("BOOT_R", 0.25, (x_13, y_t), (x_13, yr9 + 0.6), (xr91 + 0.25, yr9 + 0.25))
    P.seg("BOOT_C", 0.25, (x_14, y_t), (x_14, yr9 + 1.15), (x_14 - 0.4, yr9 + 0.92), (xr92 + 0.45, yr9 + 0.92), (xr92 + 0.1, yr9 + 0.2))
    P.seg("BOOT_C", 0.3, (xc71 + 0.1, yc71), (xr92 - 0.1, yr9))
    # --- pin 1 (BIAS): its own via, tied to the In3 pour by a fence up to the fenced stretch over the buck
    x_1, y_1, _ = pad("U2", "1", 0)        # the pin's upper pad: that leaves pin 2's way out clear
    xv1 = x_1 - 1.0
    P.seg("+5V", 0.3, (x_1, y_1), (xv1, y_1), fence=False)
    P.via("+5V", xv1, y_1, (0.6, 0.3))
    P.in3("U2_BIAS", [(xv1 - 0.8, y_bus + 0.5), (xv1 + 0.8, y_bus + 0.5), (xv1 + 0.8, y_1 + 0.6), (xv1 - 0.8, y_1 + 0.6)])

    return [("J2", "1"), ("F1", "1"), ("F1", "1@1"), ("F1", "2"), ("F1", "2@1"),
            ("D1", "1"), ("D1", "2"), ("C1", "2"), ("C55", "2"),
            ("Q2", "5"), ("Q2", "5@2"), ("Q2", "5@3"), ("Q2", "5@4"),      # 5@1, the small pad on its east side, stays for the milliamp branches
            ("Q2", "1"), ("Q2", "2"), ("Q2", "3"), ("Q1", "2"), ("Q1", "3"),   # Q1 pin 1 stays, for U1's sense pins
            ("Q1", "5@1"), ("Q1", "5@2"), ("Q1", "5@3"), ("Q1", "5@4"),    # 5, the small pad on its east side, stays for U1's C pin
            ("R1", "1"), ("R1", "2"), ("C1", "1"), ("C5", "1"), ("C55", "1"), ("C57", "1"), ("C56", "1"),
            ("U2", "8"), ("U2", "12"), ("C7", "2"), ("C7", "1"), ("R9", "2"), ("U2", "14"), ("U2", "13"),   # R9 pad 1 stays, BOOT_R's lone pin; R13 pad 1 likewise
            ("U2", "1"), ("U2", "1@1")]
