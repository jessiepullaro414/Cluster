"""
Floorplan for the display carrier: arranges the finished cells (cells.py)
around the Verdin module keepout.

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
  LEFT end = the JTAG header (JTAG pins sit at that end of the odd row);
  RIGHT end = the ignition-wake network (next to the power input).

Everything is computed from real footprint geometry; nothing is hand-placed
in millimetres except the gaps below.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "tools"))
from cellplace import rot_xy, rotate_cell as _rotate_cell

GAP = 3.0           # clearance between neighbouring cells, mm
KEEP_GAP = 3.0      # between the module keepout and the strips
INPUT_ROT = 270     # J2 pins along the right board edge


def pad_xy(parts, placed, ref, number):
    from cellplace import pad_abs
    return pad_abs(parts, placed, ref, number)


def floorplan(parts, res, j1_bbox, j1_dsi_y, keep_w, keep_h, margin, j4_dsi_pads,
              j4_first_pad):
    """res: {cell: (placed, bbox)} from cells.plan_cells.
    j1_bbox: local bbox of the J1 footprint (unrotated).
    j1_dsi_y: local y coordinates (unrotated frame) of J1's DSI pads.
    Returns dict with placements {ref: (ox, oy, rot)} in board coordinates
    (origin at board top-left), board size, keepout rectangle and J1 origin."""
    cells = {}
    for name, (placed, bbox) in res.items():
        cells[name] = (placed, bbox)

    # J4 must have its pins ascending left to right with the DSI pads on the
    # keepout-facing (top) row, so the panel lanes run straight down from J1:
    # pick the cell rotation that does that.
    best_r = None
    for r in (0, 90, 180, 270):
        p, b = _rotate_cell(*cells["PANEL"], r)
        x24 = pad_xy(parts, p, "J4", j4_dsi_pads[0])
        x38 = pad_xy(parts, p, "J4", j4_dsi_pads[-1])
        x1 = pad_xy(parts, p, "J4", j4_first_pad)
        # DSI pads share one row; the other row (odd pins) must be BELOW it
        ok = (x38[0] > x24[0]) and (x24[1] < x1[1] - 0.5)
        if ok:
            best_r = r
            cells["PANEL"] = (p, b)
            break
    if best_r is None:
        raise RuntimeError("floorplan: no J4 rotation puts DSI pins ascending with the DSI row on top")

    # Harness power terminal: rotate so its pins run along the board's right
    # edge (wire entry toward the edge is checked on the render, see
    # CELL_ROT in this module).
    cells["INPUT"] = _rotate_cell(*cells["INPUT"], INPUT_ROT)

    def size(name):
        b = cells[name][1]
        return b[2] - b[0], b[3] - b[1]

    top_row = ["DIAL", "CAN", "RTC", "LDO", "IGN", "BUTTONS"]
    bottom_row = ["BACKLIGHT", "BIAS", "PANEL", "USBUART", "BUCK", "FRONT"]
    left_end, right_end = "JTAG", ("INPUT",)

    M = margin
    E_L = size(left_end)[0] + GAP
    E_R = max(size(n)[0] for n in right_end) + GAP

    # J1 DSI pad x-centre relative to J1 origin once rotated by 90: x = ox + y
    dsi_cx_local = sum(j1_dsi_y) / len(j1_dsi_y)
    j1_cx = (j1_bbox[0] + j1_bbox[2]) / 2
    j1_cy = (j1_bbox[1] + j1_bbox[3]) / 2
    # rotated 90: (x, y) -> (y, -x); bbox centre moves to (j1_cy, -j1_cx)
    top_h = max(size(n)[1] for n in top_row)
    bot_h = max(size(n)[1] for n in bottom_row)

    # J4's DSI pad centre x inside the PANEL cell, relative to the cell's left edge
    p4, b4 = cells["PANEL"]
    j4_dsi_cx = (pad_xy(parts, p4, "J4", j4_dsi_pads[0])[0] +
                 pad_xy(parts, p4, "J4", j4_dsi_pads[-1])[0]) / 2 - b4[0]

    # Bottom row: left of PANEL are BACKLIGHT and BIAS. Choose the keepout's
    # left edge so PANEL's DSI end sits under J1's DSI pads, but not so far left
    # that the converters before it do not fit.
    left_of_panel = sum(size(n)[0] + GAP for n in ("BACKLIGHT", "BIAS"))
    # board-x of J1's DSI centre = KX + keep_w/2 + (dsi_cx_local - j1_cy_rot...)
    # J1 centre (after rotation) is at the keepout centre; dsi offset from that
    # centre along x is (dsi_cx_local - j1_cy)
    dsi_off = dsi_cx_local - j1_cy
    # panel left = KX + keep_w/2 + dsi_off - j4_dsi_cx  >= M + left_of_panel
    KX_min_by_panel = M + left_of_panel - (keep_w / 2 + dsi_off - j4_dsi_cx)
    KX = max(M + E_L, KX_min_by_panel)
    KY = M + top_h + KEEP_GAP

    ox = KX + keep_w / 2 - j1_cy
    oy = KY + keep_h / 2 + j1_cx
    j1 = (round(ox, 3), round(oy, 3), 90)

    out = {"J1": j1}

    def put(name, left, top):
        placed, bbox = cells[name]
        for ref, (cx, cy, a) in placed.items():
            out[ref] = (round(left - bbox[0] + cx, 3), round(top - bbox[1] + cy, 3), a)

    bottom_top = KY + keep_h + KEEP_GAP
    panel_left = KX + keep_w / 2 + dsi_off - j4_dsi_cx
    x = panel_left - left_of_panel
    for n in ("BACKLIGHT", "BIAS"):
        put(n, x, bottom_top)
        x += size(n)[0] + GAP
    put("PANEL", panel_left, bottom_top)
    x = panel_left + size("PANEL")[0] + GAP
    for n in ("USBUART", "BUCK", "FRONT"):
        put(n, x, bottom_top)
        x += size(n)[0] + GAP
    bottom_end = x - GAP

    W = max(KX + keep_w + E_R + M, bottom_end + M)
    # top row: spread the slack evenly (capped) between the cells
    tw = sum(size(n)[0] for n in top_row)
    slack = W - 2 * M - tw
    gap_t = min(max(GAP, slack / max(len(top_row) - 1, 1)), 14.0)
    x = M
    for n in top_row:
        put(n, x, KY - KEEP_GAP - size(n)[1])
        x += size(n)[0] + gap_t
    # end strips, vertically centred on the keepout band
    put(left_end, M, KY + keep_h / 2 - size(left_end)[1] / 2)
    # right strip: stack INPUT (harness power) and IGN, centred on the keepout band
    stack_h = sum(size(n)[1] for n in right_end) + GAP * (len(right_end) - 1)
    y = KY + keep_h / 2 - stack_h / 2
    for n in right_end:
        put(n, KX + keep_w + KEEP_GAP, y)
        y += size(n)[1] + GAP

    H = bottom_top + bot_h + M
    return dict(placed=out, width=W, height=H, keepout=(KX, KY, KX + keep_w, KY + keep_h),
                j4_rot=best_r)
