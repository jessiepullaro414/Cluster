"""
Floorplan for the brain board: arranges the finished cells (cells.py) around
the Verdin module keepout.

BRAIN BOARD (2026-10-20): the panel converters and panel connector of
display/ are gone. Screen port A (MIPI DSI, J4) takes the panel connector's
place in the bottom strip, its fan centred under J1's DSI pads, with its 5 V
switch cell (PORTA_PWR) to its left at the connector's 5 V contacts. Screen
port B (LVDS, J18) sits in the top strip, turned 180 degrees so its contacts
face the socket, centred over J1's LVDS pads (pins 88-144 on the even row);
its tracks run under the module (tracks are allowed there, components are
not). Its switch cell sits to its left. The notes below are display/'s.

The SODIMM socket J1 is rotated 90 degrees so its two pad rows run left-right.
That gives two sides to build against, matching where the Verdin pins are:

  BOTTOM side = the socket's odd-pin row: panel DSI lanes (pins 29-49), the
    JTAG pins at the low-number end, and the 5 V power pins (251-259) at the
    high-number end. So the bottom strip holds, left to right:
    backlight and panel-bias converters, the panel connector J4 (its DSI end
    right under the J1 DSI pins), then the 5 V buck and the power-input /
    protection cell at the power-pin end.
  TOP side = the even-pin row: dial ADC (pin 2), CAN1 TX/RX (pins 20/22),
    wake/sleep/reset controls (pins 252-260). The top strip holds the dial,
    CAN transceiver, RTC holder and the 1.8 V LDO.
  LEFT end = the JTAG header (JTAG pins sit at that end of the odd row) and,
    since 2026-10-16, the audio codec and its 3.3 V LDO: the I2S_1 / I2C_1
    pins (12-38) are on the even row near that same end. The codec column is
    top-aligned, as far from the panel-bias and backlight converters in the
    bottom strip as the band allows. The line-out / microphone connectors and
    their ESD arrays (AOUT) lead the top row, directly above the codec.
  RIGHT end = the ignition-wake network (next to the power input).
  USB-C host port: its pins (USB_2, 181-187) are on the odd row between the
    bring-up USB header and the power pins, so USBC sits in the bottom strip
    after USBUART, pushed down so the receptacle mouth is on the board edge.

Everything is computed from real footprint geometry; nothing is hand-placed
in millimetres except the gaps below.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "tools"))
from cellplace import rot_xy, rotate_cell as _rotate_cell

GAP = 3.0           # clearance between neighbouring cells, mm
KEEP_GAP = 3.0      # between the module keepout and the strips
INPUT_ROT = 270     # J2 pins along the right board edge
USBC_EDGE_OFFSET = 3.1   # PCB edge is 3.1 mm below the USB-C footprint origin (GCT USB4105 footprint)
# Left strip columns (cell names, vertical alignment in the keepout band).
LEFT_COLS = [(["JTAG", "MFI"], "center"), (["AUDIO", "LDO3V3"], "top")]


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


def floorplan(parts, res, j1_bbox, j1_dsi_y, keep_w, keep_h, margin, porta_pads,
              j1_local_x_hi=None, j1_lvds_y=None, portb_pads=None, porta_drop=0.0):
    """res: {cell: (placed, bbox)} from cells.plan_cells.
    j1_bbox: local bbox of the J1 footprint (unrotated).
    j1_dsi_y / j1_lvds_y: local y coordinates (unrotated frame) of J1's DSI
    and LVDS pads. porta_pads / portb_pads: the port contacts of each fan, in
    J1 order (left to right on the board). porta_drop: extra distance (mm)
    port A sits below the bottom strip's top, for the DSI fan's jog.
    Returns dict with placements {ref: (ox, oy, rot)} in board coordinates
    (origin at board top-left), board size, keepout rectangle and J1 origin.
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

    # Harness power terminal: rotate so its pins run along the board's right
    # edge (wire entry toward the edge is checked on the render, see
    # CELL_ROT in this module).
    cells["INPUT"] = _rotate_cell(*cells["INPUT"], INPUT_ROT)

    def size(name):
        if isinstance(name, tuple):      # a vertical stack of cells
            return (max(size(n)[0] for n in name),
                    sum(size(n)[1] for n in name) + GAP * (len(name) - 1))
        b = cells[name][1]
        return b[2] - b[0], b[3] - b[1]

    # Brain board: the top row also has to carry port B and its switch, so the
    # CAN cell moves to the empty bottom-left corner (its link is a slow
    # in-dash cable) and LDO / IGN stack in one top-row slot.
    top_left = ["AOUT", "DIAL", "PORTB_PWR"]
    top_right = ["RTC", ("LDO", "IGN"), "BUTTONS"]
    bottom_left = ["CAN"]
    top_row = top_left + ["PORTB", "RTC", "LDO", "IGN", "BUTTONS"]
    bottom_row = ["PORTA_PWR", "PORTA", "USBUART", "USBC", "BUCK", "FRONT", "CAN"]
    right_end = ("INPUT",)

    M = margin
    col_w = [max(size(n)[0] for n in names) for names, _ in LEFT_COLS]
    E_L = sum(col_w) + GAP * len(LEFT_COLS)
    E_R = max(size(n)[0] for n in right_end) + GAP

    # J1 DSI pad x-centre relative to J1 origin once rotated by 90: x = ox + y
    dsi_cx_local = sum(j1_dsi_y) / len(j1_dsi_y)
    j1_cx = (j1_bbox[0] + j1_bbox[2]) / 2
    j1_cy = (j1_bbox[1] + j1_bbox[3]) / 2
    # rotated 90: (x, y) -> (y, -x); bbox centre moves to (j1_cy, -j1_cx)
    top_h = max(size(n)[1] for n in top_left + ["PORTB"] + top_right)
    # USBC is pushed down to the board edge below, so it does not set the row height
    bot_h = max(size(n)[1] for n in bottom_row if n != "USBC")

    # Each port's fan centre x inside its cell, relative to the cell's left edge
    def fan_cx(cell, ref, pads):
        pl, bb = cells[cell]
        return (pad_xy(parts, pl, ref, pads[0])[0] + pad_xy(parts, pl, ref, pads[-1])[0]) / 2 - bb[0]
    j4_dsi_cx = fan_cx("PORTA", "J4", porta_pads)
    j18_cx = fan_cx("PORTB", "J18", portb_pads)

    # Bottom row: PORTA_PWR is left of PORTA. Choose the keepout's left edge so
    # port A's fan sits under J1's DSI pads, but not so far left that the cell
    # before it does not fit.
    left_of_panel = size("PORTA_PWR")[0] + GAP
    # board-x of J1's DSI centre = KX + keep_w/2 + (dsi_cx_local - j1_cy_rot...)
    # J1 centre (after rotation) is at the keepout centre; dsi offset from that
    # centre along x is (dsi_cx_local - j1_cy)
    dsi_off = dsi_cx_local - j1_cy
    # panel left = KX + keep_w/2 + dsi_off - j4_dsi_cx  >= M + left_of_panel
    KX_min_by_panel = M + left_of_panel - (keep_w / 2 + dsi_off - j4_dsi_cx)
    KX = max(M + E_L, KX_min_by_panel)
    # Top row: port B's fan sits over J1's LVDS pads; the cells left of it must fit.
    lvds_off = sum(j1_lvds_y) / len(j1_lvds_y) - j1_cy
    left_of_b = sum(size(n)[0] + GAP for n in top_left)
    KX_min_by_b = M + left_of_b - (keep_w / 2 + lvds_off - j18_cx)
    KX = max(KX, KX_min_by_b)
    KY = M + top_h + KEEP_GAP

    ox = KX + keep_w / 2 - j1_cy
    oy = KY + (j1_local_x_hi if j1_local_x_hi is not None else keep_h / 2 + j1_cx)
    j1 = (round(ox, 3), round(oy, 3), 90)

    out = {"J1": j1}

    def put(name, left, top):
        placed, bbox = cells[name]
        for ref, (cx, cy, a) in placed.items():
            out[ref] = (round(left - bbox[0] + cx, 3), round(top - bbox[1] + cy, 3), a)

    bottom_top = KY + keep_h + KEEP_GAP
    panel_left = KX + keep_w / 2 + dsi_off - j4_dsi_cx
    put("PORTA_PWR", panel_left - left_of_panel, bottom_top)
    x = panel_left - left_of_panel
    for n in reversed(bottom_left):
        x -= size(n)[0] + GAP
        put(n, x, bottom_top)
    assert x >= M - 1e-6, "bottom row: cells left of port A run off the board"
    put("PORTA", panel_left, bottom_top + porta_drop)
    x = panel_left + size("PORTA")[0] + GAP
    usbc_left = None
    for n in ("USBUART", "USBC", "BUCK", "FRONT"):
        if n == "USBC":
            usbc_left = x
        else:
            put(n, x, bottom_top)
        x += size(n)[0] + GAP
    bottom_end = x - GAP

    W = max(KX + keep_w + E_R + M, bottom_end + M)
    # top row: port B at its fixed x; the cells left of it packed against it,
    # the cells right of it spread over the remaining width (gap capped)
    portb_left = KX + keep_w / 2 + lvds_off - j18_cx
    x = portb_left
    for n in reversed(top_left):
        x -= size(n)[0] + GAP
        put(n, x, KY - KEEP_GAP - size(n)[1])
    assert x >= M - 1e-6, "top row: cells left of port B run off the board"
    put("PORTB", portb_left, KY - KEEP_GAP - size("PORTB")[1])
    x = portb_left + size("PORTB")[0]
    W = max(W, x + sum(size(n)[0] + GAP for n in top_right) + M)
    tw = sum(size(n)[0] for n in top_right)
    slack = W - M - x - tw
    gap_t = min(max(GAP, slack / len(top_right)), 14.0)
    for n in top_right:
        x += gap_t
        if isinstance(n, tuple):
            y = KY - KEEP_GAP - size(n)[1]
            for m in n:
                put(m, x, y)
                y += size(m)[1] + GAP
        else:
            put(n, x, KY - KEEP_GAP - size(n)[1])
        x += size(n)[0]
    # left strip: columns of stacked cells
    x = M
    for (names, align), w in zip(LEFT_COLS, col_w):
        stack_h = sum(size(n)[1] for n in names) + GAP * (len(names) - 1)
        y = KY + keep_h / 2 - stack_h / 2 if align == "center" else KY
        for n in names:
            put(n, x, y)
            y += size(n)[1] + GAP
        x += w + GAP
    # right strip: stack INPUT (harness power) and IGN, centred on the keepout band
    stack_h = sum(size(n)[1] for n in right_end) + GAP * (len(right_end) - 1)
    y = KY + keep_h / 2 - stack_h / 2
    for n in right_end:
        put(n, KX + keep_w + KEEP_GAP, y)
        y += size(n)[1] + GAP

    H = max(bottom_top + bot_h, bottom_top + porta_drop + size("PORTA")[1]) + M
    # USB-C cell: the receptacle origin sits USBC_EDGE_OFFSET above the board
    # bottom edge; everything else in the cell is above it (keepin in cells.py).
    placed_u, bbox_u = cells["USBC"]
    j17_below_top = placed_u["J17"][1] - bbox_u[1]
    usbc_top = H - USBC_EDGE_OFFSET - j17_below_top
    if usbc_top < bottom_top:          # cell taller than the row: grow the board
        H += bottom_top - usbc_top
        usbc_top = bottom_top
    put("USBC", usbc_left, usbc_top)
    return dict(placed=out, width=W, height=H, keepout=(KX, KY, KX + keep_w, KY + keep_h),
                j4_rot=rot_a, j18_rot=rot_b)
