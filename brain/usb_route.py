"""
Planned route for Verdin USB_1's pair (brain board, 2026-11-06), from the socket J1 to
the second USB-C port J19 and the bench header J13. Pure geometry, no KiCad imports, so
build_pcb.py can report it and route_board.py can apply it after the autorouter, the
same way as fan_route.py.

Why it isn't autorouted: the first route of this board left the pair 54 and 67 mm long
(12.5 mm of skew) on In2 and In3, where a 0.2 mm track sits 0.11 mm from the next
layer's pour. USB 2.0 wants 90 ohm +/-15 %, and the same pair also has to serve as the
recovery port.

* Main run: both tracks on F.Cu over the solid In1 GND plane, 0.5 mm apart all the way,
  which is the pad pitch at J1, at the ESD array and at the receptacle. 0.19 mm wide with
  a 0.31 mm gap over 0.0994 mm of 3313 prepreg comes to 90.3 ohm differential
  (review/dsi_impedance.py's field solve).
* Two left bends and two right bends, so the bends' length differences cancel.
* The ESD array U17 is turned so its channels line up with the tracks, which run
  straight over pins 2 and 9 and pins 1 and 10: TI SLVSCO7C keeps those NC pins for this.
  Its layout guidance also asks for the array close to the connector, with the protected
  tracks straight, which they are.
* At J19, D- on B7 and D+ on A6 go straight in. A6 joins B6 over the top of the pad row
  and B7 joins A7 under it, as the autorouter did on J17, on F.Cu with no vias.
* The bench header J13 is a branch near J1 on B.Cu over In4 GND, the same stack-up mirrored,
  through one via per track. With J13 empty that branch is the only stub on the pair.

Everything planned is fenced from the autorouter (F.Cu corridors, with vias, and B.Cu along
the branch), and every far end of the pair is dropped from its input.
"""
import math

W = 0.19                 # pair track width, mm (about 90 ohm differential, see docstring)
W_BRANCH = 0.2           # the J13 branch, on B.Cu
PITCH = 0.5              # track centre to track centre, mm
VIA_DIA, VIA_DRILL = 0.6, 0.3
STUB = 0.4               # tracks start this far inside the J1 pad, mm
PAD_IN = 0.3             # tracks end this far inside the receptacle's pads, mm
CHAMFER = 1.0            # 45 degree corners, on the pair's centre line, mm
MARGIN = 0.05            # fence beyond the copper. The router keeps its 0.2 mm clearance from the fence
# Where the run goes, relative to pads it serves
RUN_BELOW_J1 = 4.7       # the first run east, below J1's pad centres: under the 3 mm strip other nets' vias need
CHANNEL_LEFT_OF_J19 = 5.3   # the run south, between the USBC cell and the buck cell
ESD_ABOVE_J19 = 7.53     # U17's centre above J19's origin (floorplan.py uses this too)
U17_X_FROM_J19 = -1.25   # U17's centre from J19's origin: pin 2 over B7 (-0.75), pin 1 over A6 (-0.25)
RUN_ABOVE_ESD = 2.6      # the second run east, above U17's centre
# The J13 branch, its vias beside the main run
VIA_OFF = 0.6            # via centre to its track's centre
VIA_Y_DN, VIA_Y_DP = 2.82, 3.42   # via centres below J1's pad centres. Stepped so the two branches don't cross
ARCH_ABOVE_PAD = 0.525   # the A6-B6 link's centre above the pad row's top edge
LOOP_BELOW_PAD = 0.375   # the B7-A7 link's centre below the pad row's bottom edge
LINK_CHAMFER = 0.2


def _chamfered(corners):
    """Centre line through corners, with each inner corner cut at 45 degrees."""
    out = [corners[0]]
    for a, b, c in zip(corners, corners[1:], corners[2:]):
        d1 = math.hypot(b[0] - a[0], b[1] - a[1])
        d2 = math.hypot(c[0] - b[0], c[1] - b[1])
        out.append((b[0] - (b[0] - a[0]) / d1 * CHAMFER, b[1] - (b[1] - a[1]) / d1 * CHAMFER))
        out.append((b[0] + (c[0] - b[0]) / d2 * CHAMFER, b[1] + (c[1] - b[1]) / d2 * CHAMFER))
    out.append(corners[-1])
    return out


def _normals(points):
    ns = []
    for a, b in zip(points, points[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        ns.append(((b[1] - a[1]) / L, -(b[0] - a[0]) / L))
    return ns


def offset(points, d):
    """The line parallel to points, d along (dy, -dx): heading south that is east, heading
    east north. So d > 0 is D+'s side and d < 0 is D-'s."""
    ns = _normals(points)
    out = []
    for i, p in enumerate(points):
        if i == 0:
            n = ns[0]
            k = 1.0
        elif i == len(points) - 1:
            n = ns[-1]
            k = 1.0
        else:
            a, b = ns[i - 1], ns[i]
            m = (a[0] + b[0], a[1] + b[1])
            L = math.hypot(*m)
            n = (m[0] / L, m[1] / L)
            k = 1.0 / (n[0] * a[0] + n[1] * a[1])     # a miter keeps the spacing through the corner
        out.append((p[0] + n[0] * d * k, p[1] + n[1] * d * k))
    return out


def length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _band(points, half):
    """A polygon round a line."""
    return offset(points, half) + offset(points, -half)[::-1]


def _with_points(line, ys):
    """line's last leg runs straight south: add a vertex at each y, so a junction or a pad
    on it is a real point on the track."""
    head, tail = line[:-1], line[-1]
    x = tail[0]
    last = head[-1]
    assert abs(last[0] - x) < 1e-6, "the last leg must run south"
    return head + [(x, y) for y in sorted(ys) if last[1] < y < tail[1]] + [tail]


def plan(pad):
    """pad(ref, number) -> (x, y, half_y) in board coordinates. Returns (items, report,
    corridors, dropped), as fan_route.plan() does: items are ("seg", layer, net, width,
    [(x, y), ...]) and ("via", net, x, y); corridors maps a name to a polygon, fenced on F.Cu,
    or on every signal layer if the name ends _VIAS, or on B.Cu only if it ends _BCU."""
    xn, yj, hj = pad("J1", "163")         # USB_1_D_N
    xp, _, _ = pad("J1", "165")           # USB_1_D_P
    assert abs((xp - xn) - PITCH) < 1e-3, "J1's USB_1 pins are not 0.5 mm apart"
    xb7, yr, hr = pad("J19", "B7")
    xa6 = pad("J19", "A6")[0]
    xa7 = pad("J19", "A7")[0]
    xb6 = pad("J19", "B6")[0]
    assert abs(xa6 - xb7 - PITCH) < 1e-3 and xb7 < xa6 < xa7 < xb6, "J19's D pads moved"
    jx = (xa6 + xa7) / 2                  # J19's origin
    top, bottom = yr - hr, yr + hr        # the pad row's edges
    xu_n, yu_top, _ = pad("U17", "2")
    xu_p = pad("U17", "1")[0]
    yu_bot = pad("U17", "9")[1]
    assert abs(xu_n - xb7) < 1e-3 and abs(xu_p - xa6) < 1e-3, "U17 isn't lined up with J19's contacts"
    assert yu_top < yu_bot, "U17's channel pads should face the module"

    y_run1 = yj + RUN_BELOW_J1
    x_chan = jx - CHANNEL_LEFT_OF_J19
    y_run2 = (yu_top + yu_bot) / 2 - RUN_ABOVE_ESD
    x_end = (xb7 + xa6) / 2
    start = yj + hj - STUB
    end = top + PAD_IN
    centre = _chamfered([((xn + xp) / 2, start), ((xn + xp) / 2, y_run1), (x_chan, y_run1),
                         (x_chan, y_run2), (x_end, y_run2), (x_end, end)])
    dn = offset(centre, -PITCH / 2)
    dp = offset(centre, PITCH / 2)

    # Junctions and pads along the tracks
    y_via_dn, y_via_dp = yj + VIA_Y_DN, yj + VIA_Y_DP
    y_arch = top - ARCH_ABOVE_PAD
    y_tee = y_arch + LINK_CHAMFER
    y_loop = bottom + LOOP_BELOW_PAD
    head_n = [dn[0], (dn[0][0], y_via_dn)] + dn[1:]
    head_p = [dp[0], (dp[0][0], y_via_dp)] + dp[1:]
    head_n = _with_points(head_n, [yu_top, yu_bot])
    head_p = _with_points(head_p, [yu_top, yu_bot, y_tee])

    items = [("seg", "F.Cu", "USB_DN", W, head_n), ("seg", "F.Cu", "USB_DP", W, head_p)]
    # A6 to B6 over the pad row, B7 to A7 under it
    c = LINK_CHAMFER
    items.append(("seg", "F.Cu", "USB_DP", W, [(xa6, y_tee), (xa6 + c, y_arch), (xb6 - c, y_arch), (xb6, y_tee), (xb6, top + PAD_IN)]))
    items.append(("seg", "F.Cu", "USB_DN", W, [(xb7, bottom - PAD_IN), (xb7, y_loop - c), (xb7 + c, y_loop), (xa7 - c, y_loop), (xa7, y_loop - c), (xa7, bottom - PAD_IN)]))

    # The J13 branch: one via beside each track, then B.Cu at 45 degrees to the header's pads
    vn = (xn - VIA_OFF, y_via_dn)
    vp = (xp + VIA_OFF, y_via_dp)
    jn = pad("J13", "2")
    jp = pad("J13", "3")
    branch_n = [vn, (vn[0] - (jn[1] - vn[1]), jn[1]), (jn[0], jn[1])]
    branch_p = [vp, (vp[0] - (jp[1] - vp[1]), jp[1]), (jp[0], jp[1])]
    items += [("seg", "F.Cu", "USB_DN", W, [(xn, y_via_dn), vn]), ("seg", "F.Cu", "USB_DP", W, [(xp, y_via_dp), vp]),
              ("via", "USB_DN", vn[0], vn[1]), ("via", "USB_DP", vp[0], vp[1]),
              ("seg", "B.Cu", "USB_DN", W_BRANCH, branch_n), ("seg", "B.Cu", "USB_DP", W_BRANCH, branch_p)]

    report = {"USB_1 J1 to J19": (length(head_n), length(head_p)),
              "USB_1 branch to J13": (VIA_OFF + length(branch_n), VIA_OFF + length(branch_p))}

    # Fences
    half = PITCH / 2 + W / 2 + MARGIN
    h_via = VIA_DIA / 2 + MARGIN
    h_br = W_BRANCH / 2 + MARGIN

    def box(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    corridors = {
        "USB1": _band(centre, half),
        "USB1_J19": box(xb7 - W / 2 - MARGIN, y_arch - W / 2 - MARGIN, xb6 + W / 2 + MARGIN, y_loop + W / 2 + MARGIN),
        "USB1N_VIAS": box(vn[0] - h_via, vn[1] - h_via, xn, vn[1] + h_via),
        "USB1P_VIAS": box(xp, vp[1] - h_via, vp[0] + h_via, vp[1] + h_via),
        "USB1N_BCU": _band(branch_n, h_br),
        "USB1P_BCU": _band(branch_p, h_br),
    }
    dropped = [("J13", "2"), ("J13", "3"), ("U17", "1"), ("U17", "2"), ("U17", "9"), ("U17", "10"),
               ("J19", "A6"), ("J19", "B6"), ("J19", "A7"), ("J19", "B7")]
    return items, report, corridors, dropped


def planned_nets():
    return ["USB_DP", "USB_DN"]
