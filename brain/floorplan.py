"""
Floorplan for the brain board: arranges the finished cells (cells.py) around
the Verdin module keepout.

SHRUNK 2026-11-06, from 184.9 x 104.9 mm (the owner: "a lot of dead space"). The old
floorplan kept an 8 mm margin all round for the corner holes and laid the front end out
along the bottom row, which set the width and left a 39 x 32 mm hole on the right. Now:

  * The margin is only as much as the board edge needs. The holes keep their own corners.
  * Everything right of the module flows from the top down: J2 on the right edge with its
    wire mouth facing out, then the fuse, the TVS, the two FETs one above the other, the sense
    resistor, and so into the buck, which hasn't moved, with the bulk capacitor beside that run.
    All of it is on planned copper (power_route.py). (J2's mouth used to face the module. The 3D
    model's wire entry is on the footprint's +y side, so it has to be turned 90 degrees, not 270.)
  * The coin cell sits top right, and it alone sets the top strip's height.
  * The two corners of the keepout outside the module take small cells: the module is
    69.6 mm long against 86.3 mm of keepout, and the socket's latches stop 14 mm short of
    the module's far edge (footprint courtyard; Design Guide figure 114 only forbids parts
    under the module itself).

The socket and every part whose copper is planned keep their places relative to each other:
port A, the bench headers, the USB-C cell, the buck and the second USB-C port are the same chain
along the bottom edge as before, so usb_route.py and power_route.py still fit.

The space behind each ribbon connector stays empty on purpose: the FFC leaves that way.

The SODIMM socket J1 is rotated 90 degrees so its two pad rows run left-right.
That gives two sides to build against, matching where the Verdin pins are:

  BOTTOM side = the socket's odd-pin row: DSI lanes (pins 29-49), the JTAG pins at the
    low-number end, UART and USB_1 in the middle, USB_2 (181-187), and the 5 V power
    pins (251-259) at the high-number end. So the bottom strip holds, left to right:
    port A's switch, J4 with its fan right under the J1 DSI pins, the bench headers,
    the USB-C cell, then the buck with the second USB-C port under it.
  TOP side = the even-pin row: dial ADC (pin 2), I2S_1 / I2C_1 (12-38) and the LVDS
    pins (88-144). J18 sits centred over the LVDS pads, turned 180 degrees so its contacts
    face the socket, its tracks under the module (tracks are allowed there, components
    aren't), with its switch cell to its left at J18's 5 V contacts.
  LEFT end = the audio codec and its connectors, the JTAG header, CAN and MFi.

Everything is computed from real footprint geometry; nothing is hand-placed
in millimetres except the gaps below.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "tools"))
from cellplace import rot_xy, rotate_cell as _rotate_cell
import cells as _cells
import usb_route as _usb_route

GAP = 3.0           # the old cell gap, still between the cells of the bottom chain, mm
CELL_GAP = 1.0      # between cells elsewhere, mm. Each cell has its own 0.35 mm gaps inside
TIGHT = 0.4         # between single large parts in the column right of the module
KEEP_GAP = 3.0      # between the module keepout and the strips along the socket's pads
SIDE_GAP = 1.2      # between the module keepout and the columns at its ends
BOTTOM_STRIP = 25.8    # keepout + KEEP_GAP to the bottom edge: the buck over the second USB-C port needs all of it
TOP_EDGE = 0.7         # the coin cell's courtyard to the top edge
EDGE = 1.2             # any other part's bounding box to the board edge
HOLE_INSET = 3.6       # M3 hole centre from both edges: the courtyard's 3.45 mm radius fits, 2 mm of board round the hole
J10_COURT = 11.8       # the holder's courtyard is round, radius 11.8; footprint_bbox only sees the arcs' ends
J2_BODY_FRONT = 4.6    # J2's wire mouth, footprint origin to the body's face (KiCad's own 3D model, 2026-11-06)
USBC_EDGE_OFFSET = 3.1   # PCB edge is 3.1 mm below the USB-C footprint origin (GCT USB4105 footprint)
USBC2_GAP = 1.5          # second USB-C port: USBC cell to J19's courtyard, mm
USBC2_PWR_GAP = 0.5      # J19's courtyard to its power parts, mm
USBC2_TVS_COLUMN = 3.85  # D12 upright (3.5 mm wide) and its gap to C90, mm
USBC2_BOTTOM = 0.45      # lowest power part to the board edge, mm
# The keepout's corners outside the module, x from its near end and y from its far edge
CORNER_H = 14.1
STANDOFF_END = 7.6       # S1/S2's outline, from the keepout's end (the module's own end is 8.35 mm in)


LENIENT = False     # scratch previews draw a bad floorplan instead of stopping


def pad_xy(parts, placed, ref, number):
    from cellplace import pad_abs
    return pad_abs(parts, placed, ref, number)


def _orient_port(parts, cells, cell, ref, lo_pad, hi_pad, pads_up):
    """Turn a port cell so contact lo_pad is left of hi_pad and the pad row
    faces the socket (pads_up: pads on the cell's top side)."""
    for r in (0, 90, 180, 270):
        p, b = _rotate_cell(*cells[cell], r)
        a = pad_xy(parts, p, ref, lo_pad)
        z = pad_xy(parts, p, ref, hi_pad)
        mid = (b[1] + b[3]) / 2
        if a[0] < z[0] - 1.0 and abs(a[1] - z[1]) < 0.01 and ((a[1] < mid) == pads_up):
            cells[cell] = (p, b)
            return r
    raise RuntimeError(f"floorplan: no rotation of {ref} puts {lo_pad}..{hi_pad} left to right facing the socket")


def floorplan(parts, res, j1_bbox, j1_dsi_y, keep_w, keep_h, porta_pads,
              j1_local_x_hi=None, j1_lvds_y=None, portb_pads=None, porta_drop=0.0):
    """res: {cell: (placed, bbox)} from cells.plan_cells.
    j1_bbox: local bbox of the J1 footprint (unrotated).
    j1_dsi_y / j1_lvds_y: local y coordinates (unrotated frame) of J1's DSI
    and LVDS pads. porta_pads / portb_pads: the port contacts of each fan, in
    J1 order (left to right on the board). porta_drop: extra distance (mm)
    port A sits below the bottom strip's top, for the DSI fan's jog.
    Returns dict with placements {ref: (ox, oy, rot)} in board coordinates
    (origin at board top-left), board size, keepout rectangle, J1 origin and
    the mounting holes.
    j1_local_x_hi: if given, the keepout's top edge is this far along J1's
    local +x (the side the module lies on) from J1's origin, instead of the
    keepout being centred on J1's bounding box. The module is NOT centred
    on the socket: it reaches 35 mm from the locating pegs on the latch side
    (Toradex Verdin Carrier Board Design Guide V1.2, Fig 110 and 113)."""
    cells = {}
    for name, (placed, bbox) in res.items():
        cells[name] = (placed, bbox)

    rot_a = _orient_port(parts, cells, "PORTA", "J4", porta_pads[0], porta_pads[-1], True)
    rot_b = _orient_port(parts, cells, "PORTB", "J18", portb_pads[0], portb_pads[-1], False)

    # The front end comes in from the top and leaves at the bottom: reverse-blocking FET first
    cells["FRONT"] = _rotate_cell(*cells["FRONT"], 180)   # cells.py gives the FETs' places with this turn in mind
    cells["LDO3V3"] = _rotate_cell(*cells["LDO3V3"], 90)
    cells["CAN"] = _rotate_cell(*cells["CAN"], 90)

    def size(name):
        b = cells[name][1]
        return b[2] - b[0], b[3] - b[1]

    # ---- Everything below is first worked out with the keepout's top left corner at (0, 0)
    dsi_cx_local = sum(j1_dsi_y) / len(j1_dsi_y)
    j1_cx = (j1_bbox[0] + j1_bbox[2]) / 2
    j1_cy = (j1_bbox[1] + j1_bbox[3]) / 2

    # Each port's fan centre x inside its cell, relative to the cell's left edge
    def fan_cx(cell, ref, pads):
        pl, bb = cells[cell]
        return (pad_xy(parts, pl, ref, pads[0])[0] + pad_xy(parts, pl, ref, pads[-1])[0]) / 2 - bb[0]
    j4_dsi_cx = fan_cx("PORTA", "J4", porta_pads)
    j18_cx = fan_cx("PORTB", "J18", portb_pads)
    dsi_off = dsi_cx_local - j1_cy
    lvds_off = sum(j1_lvds_y) / len(j1_lvds_y) - j1_cy

    ox = keep_w / 2 - j1_cy
    oy = j1_local_x_hi if j1_local_x_hi is not None else keep_h / 2 + j1_cx
    out = {"J1": (round(ox, 3), round(oy, 3), 90)}

    def put(name, left, top):
        placed, bbox = cells[name]
        for ref, (cx, cy, a) in placed.items():
            out[ref] = (round(left - bbox[0] + cx, 3), round(top - bbox[1] + cy, 3), a)

    def box(ref):
        ox_, oy_, a_ = out[ref]
        x0_, y0_, x1_, y1_ = parts[ref].rbbox(a_)
        return ox_ + x0_, oy_ + y0_, ox_ + x1_, oy_ + y1_

    # ---- The bottom chain, unchanged relative to the socket
    bottom_top = keep_h + KEEP_GAP
    y_b = bottom_top + BOTTOM_STRIP
    panel_left = keep_w / 2 + dsi_off - j4_dsi_cx
    x_portapwr = panel_left - size("PORTA_PWR")[0] - GAP
    put("PORTA_PWR", x_portapwr, bottom_top)
    put("PORTA", panel_left, bottom_top + porta_drop)
    x = panel_left + size("PORTA")[0] + GAP
    usbc_left = None
    for n in ("USBUART", "USBC", "BUCK"):
        if n == "USBC":
            usbc_left = x
        else:
            put(n, x, bottom_top)
        x += size(n)[0] + GAP
    # USB-C cell: the receptacle origin sits USBC_EDGE_OFFSET above the board
    # bottom edge; everything else in the cell is above it (keepin in cells.py).
    placed_u, bbox_u = cells["USBC"]
    j17_below_top = placed_u["J17"][1] - bbox_u[1]
    usbc_top = y_b - USBC_EDGE_OFFSET - j17_below_top
    assert usbc_top >= bottom_top, "the USB-C cell is taller than the bottom strip"
    put("USBC", usbc_left, usbc_top)
    # L2, this pair's choke, just left of the ESD array and its CC resistor, connector side toward them
    r71 = box("R71")
    out["L2"] = (round(r71[0] - 0.35 - 1.3, 3), round((r71[1] + r71[3]) / 2, 3), 180)
    # Second USB-C port (2026-11-06): on the same bottom edge, in the strip under
    # the buck. J19 is about 20 mm from J17, so two plugs fit side by side
    # (a USB-C overmold can be 12.35 mm wide).
    placed_2, bbox_2 = cells["USBC2"]
    usbc2_left = usbc_left + size("USBC")[0] + USBC2_GAP
    # The cell's left edge is J19's: its CC resistors are all to the right of the origin.
    put("USBC2", usbc2_left, y_b - USBC_EDGE_OFFSET - (placed_2["J19"][1] - bbox_2[1]))
    # U17 lines up with J19's contacts, D- over B7 and D+ over A6, so the pair runs straight
    # through it (usb_route.py). Turned 270 degrees, pin 1 is to the right of pin 2.
    out["U17"] = (round(out["J19"][0] + _usb_route.U17_X_FROM_J19, 3),
                  round(out["J19"][1] - _usb_route.ESD_ABOVE_J19, 3), 270)
    # L3, the pair's choke, sits on the run south, in the channel between the USBC and buck cells:
    # turned 90 degrees its lines run north to south 0.5 mm apart, right on the pair's two tracks.
    out["L3"] = (round(out["J19"][0] - _usb_route.CHANNEL_LEFT_OF_J19, 3),
                 round(out["J1"][1] + _usb_route.L3_BELOW_J1, 3), 90)
    # USBC2_PWR is placed by its anchor, C90 (keep-in and blocked box in cells.py): its
    # left side touches the column kept for the TVS, its bottom the board-edge margin.
    c90_x0, c90_y0, c90_x1, c90_y1 = parts["C90"].rbbox(0)
    c90_x = out["J19"][0] + parts["J19"].rbbox(0)[2] + USBC2_PWR_GAP + USBC2_TVS_COLUMN - c90_x0
    c90_y = y_b - USBC2_BOTTOM - c90_y1
    for ref, (cx, cy, a) in cells["USBC2_PWR"][0].items():
        out[ref] = (round(c90_x + cx, 3), round(c90_y + cy, 3), a)

    # ---- Top strip: port B and its switch, then the coin cell right of it
    portb_left = keep_w / 2 + lvds_off - j18_cx
    put("PORTB", portb_left, -KEEP_GAP - size("PORTB")[1])
    x_portbpwr = portb_left - GAP - size("PORTB_PWR")[0]
    put("PORTB_PWR", x_portbpwr, -KEEP_GAP - size("PORTB_PWR")[1])
    j10_cy = -CELL_GAP - J10_COURT
    y_t = j10_cy - J10_COURT - TOP_EDGE
    j10_x = portb_left + size("PORTB")[0] + TIGHT - parts["J10"].rbbox(0)[0]
    out["J10"] = (round(j10_x, 3), round(j10_cy, 3), 0)

    # ---- The keepout's far corners. Right: the button header, its pull-up and the RTC feed beside it.
    x_b = keep_w - STANDOFF_END + 0.1
    j9_x0, j9_y0, j9_x1, j9_y1 = parts["J9"].rbbox(0)
    out["J9"] = (round(x_b - j9_x0, 3), round(0.3 - j9_y0, 3), 0)
    r_x = box("J9")[2] + TIGHT + 0.73
    for k, ref in enumerate(("R47", "R49", "C39")):
        out[ref] = (round(r_x, 3), round(0.3 + 1.48 + k * 3.31, 3), 90)
    # Left: the codec's 3.3 V LDO, turned upright, right beside the codec
    put("LDO3V3", STANDOFF_END - size("LDO3V3")[0] - 0.05, 0.0)

    # ---- The column right of the module, top to bottom. The fuse holder is its widest part, J2 sets the right edge.
    x0 = keep_w + SIDE_GAP
    f1_x0, f1_y0, f1_x1, f1_y1 = parts["F1"].rbbox(180)
    x_r = x0 + (f1_x1 - f1_x0) + 0.7
    # Pads run north to south, pin 1 (battery) lowest, mouth to the east
    j2_x0, j2_y0, j2_x1, j2_y1 = parts["J2"].rbbox(90)
    j2_x = x_r - J2_BODY_FRONT
    j2_y = y_t + 2 * HOLE_INSET - 0.1 - j2_y0
    out["J2"] = (round(j2_x, 3), round(j2_y, 3), 90)
    # The ignition network beside J2, its pin 3 at the top, under the coin cell's end
    put("IGN", max(x0, box("J10")[2] + 0.1), y_t + EDGE)
    # The fuse under J2, its input end next to pin 1
    y = j2_y + j2_y1 + TIGHT
    out["F1"] = (round(x0 - f1_x0, 3), round(y - f1_y0, 3), 180)
    y += f1_y1 - f1_y0 + TIGHT
    # Then the TVS straight under the fuse's output end, pad 1 toward it, on the FETs' centre line
    x_fet = x0 + 3.38
    d1_x0, d1_y0, d1_x1, d1_y1 = parts["D1"].rbbox(270)
    out["D1"] = (round(x_fet, 3), round(y - d1_y0, 3), 270)
    y += d1_y1 - d1_y0 + 0.1
    # The front end, placed by U1: the FETs' courtyards start right under the TVS
    y_u1 = y + 2 * _cells.FET_Y
    x_u1 = x_fet - _cells.FET_X
    assert x_u1 + _cells.FRONT_RIGHT <= x_r - EDGE + 1e-6, "the front end's keep-in is past the right edge"
    placed_f = cells["FRONT"][0]
    for ref, (cx, cy, a) in placed_f.items():
        out[ref] = (round(x_u1 + cx, 3), round(y_u1 + cy, 3), a)
    # The bulk capacitor under the front end's small parts, pad 1 toward the sense resistor, just above the buck's top edge
    c1_x0, c1_y0, c1_x1, c1_y1 = parts["C1"].rbbox(0)
    y = y_u1 + _cells.FRONT_BOTTOM
    out["C1"] = (round(x_r - 0.9 - c1_x1, 3), round(y - c1_y0, 3), 0)
    assert y + c1_y1 - c1_y0 <= bottom_top + 1e-6, "C1 runs into the buck"

    # ---- Under the bench headers, clear of the ribbon: the +1V8 LDO
    x12 = box("J12")[0]
    put("LDO", x12 - 3.0, y_b - EDGE - size("LDO")[1])

    # ---- The left end. The codec sets its width, as close to the keepout as it can go.
    x_col = -SIDE_GAP - size("AUDIO")[0]
    x_l = x_col - EDGE
    # Audio connectors at the top, J15 just under the corner hole; port B's switch and the CAN cell along the top to their right
    placed_ao, bbox_ao = cells["AOUT"]
    put("AOUT", x_col, 0.0)
    j15_top = box("J15")[1]
    put("AOUT", x_col, y_t + 2 * HOLE_INSET - 0.1 - j15_top)
    put("CAN", box("J14")[2] + CELL_GAP, -KEEP_GAP - size("CAN")[1])
    y = box("J14")[3] + CELL_GAP
    put("AUDIO", x_col, y)
    y += size("AUDIO")[1] + CELL_GAP
    # Under the codec: the JTAG header against the edge, the dial cell beside it
    put("JTAG", x_col, y)
    put("DIAL", -SIDE_GAP - size("DIAL")[0], y)
    y = box("J8")[3] + CELL_GAP
    # Bottom left, above the corner hole
    put("MFI", x_col, y)

    # ---- Shift to board coordinates
    W, H = x_r - x_l, y_b - y_t
    placed = {r: (round(a - x_l, 3), round(b - y_t, 3), c) for r, (a, b, c) in out.items()}
    holes = [("MH1", HOLE_INSET, HOLE_INSET), ("MH2", W - HOLE_INSET, HOLE_INSET),
             ("MH3", HOLE_INSET, H - HOLE_INSET), ("MH4", W - HOLE_INSET, H - HOLE_INSET)]

    # ---- Check it part by part: nothing here is a plain rectangle any more
    def pbox(ref):
        ox_, oy_, a_ = placed[ref]
        x0_, y0_, x1_, y1_ = parts[ref].rbbox(a_)
        return ox_ + x0_, oy_ + y0_, ox_ + x1_, oy_ + y1_
    refs = [r for r in placed if r != "J1"]
    problems = []
    for i, ra in enumerate(refs):
        a_ = pbox(ra)
        if ra not in ("J17", "J19", "J2"):     # the USB-C mouths overhang the edge, and J2's courtyard runs past its body
            if not (a_[0] >= -1e-6 and a_[1] >= -1e-6 and a_[2] <= W + 1e-6 and a_[3] <= H + 1e-6):
                problems.append(f"{ra} is off the board")
        for rb in refs[i + 1:]:
            b_ = pbox(rb)
            if not (a_[2] <= b_[0] or b_[2] <= a_[0] or a_[3] <= b_[1] or b_[3] <= a_[1]):
                problems.append(f"{ra} overlaps {rb}")
        for name, hx, hy in holes:
            nx, ny = max(a_[0], min(hx, a_[2])), max(a_[1], min(hy, a_[3]))
            if (nx - hx) ** 2 + (ny - hy) ** 2 < 3.45 ** 2:
                problems.append(f"{ra} is on {name}")
    keep = (-x_l, -y_t, keep_w - x_l, keep_h - y_t)
    for ra in refs:
        a_ = pbox(ra)
        kx0, ky0, kx1, ky1 = keep
        corner = ((a_[2] <= kx0 + STANDOFF_END or a_[0] >= kx1 - STANDOFF_END) and a_[3] <= ky0 + CORNER_H)
        if not corner:
            if not (a_[2] <= kx0 or a_[0] >= kx1 or a_[3] <= ky0 or a_[1] >= ky1):
                problems.append(f"{ra} is in the module keepout")
    if problems and not LENIENT:
        raise SystemExit("floorplan: " + "; ".join(problems))
    return dict(problems=problems, placed=placed, width=W, height=H, keepout=keep, j4_rot=rot_a, j18_rot=rot_b, holes=holes)
