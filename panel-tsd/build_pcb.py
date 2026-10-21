#!/usr/bin/env python3
"""
build_pcb.py - generates ClusterPanelTSD.kicad_pcb, the panel board for the TSD
TST040HDBC-42 round panel (2026-10-20).

The panel board carries the panel's own circuits that used to sit on display/:
the FPC connector J4, the TPS65131-Q1 bias supply with its polarity jumpers,
and the TPS61165-Q1 backlight. It plugs into the brain board's screen port A
through J1 (Hirose FH12-40S, ../tools/screen_ports.py). The parts, values and
converter cells are display/'s (build_schematic.py, cells.py); this script
only arranges them:

    top row:     BIAS cell | PANEL cell (J4, the FPC enters from the top edge) | BACKLIGHT cell
    bottom row:  PORTCAP | PORT (J1, the ribbon to the brain board enters from the bottom edge)

J4's DSI row faces down, toward J1, with J4's DSI pads centred over J1's DSI
contacts; ROW_GAP between the rows leaves room for the four pairs, which the
autorouter routes (route_board.py) on F.Cu and B.Cu only, over the solid In1
and In4 GND planes. The pairs cross each other on the way (the port carries
each pair N then P in the Verdin's lane order, the panel FPC P then N in its
own), which at about 250 Mbit/s per lane over a 10-20 mm run is harmless:
on 0.0994 mm prepreg each 0.16 mm leg is about 52 ohm on its own, so a pair
stays near 100 ohm differential even where its legs separate.

Same six-layer stack-up as the brain board (JLC06161H-3313), so the same
DSI geometry holds on both boards. Everything is generated; never hand-edit
the .kicad_pcb.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid as uuid_module

from kiutils.board import Board
from kiutils.items.common import Net, Position
from kiutils.items.brditems import LayerToken
from kiutils.items.gritems import GrLine

from fpgeom import load_footprint, footprint_bbox, load_schematic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from cellplace import rotate_cell, pad_abs  # noqa: E402
import cells as _cells                       # noqa: E402

SCH = os.path.join(HERE, "ClusterPanelTSD.kicad_sch")
PCB = os.path.join(HERE, "ClusterPanelTSD.kicad_pcb")
KICAD_CLI = shutil.which("kicad-cli") or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

GAP = 3.0            # between neighbouring cells, mm
ROW_GAP = 8.0        # between the panel row and the port row (DSI routing room)
M = 7.5              # board margin (clears the corner M3 holes)
MOUNTING_HOLE_INSET = 3.8
MIN_TRACK_WIDTH_MM = 0.15      # the 0.16 mm DSI tracks (see brain/build_pcb.py)
# converter switch nodes and the backlight's LED anode are widened by
# route_board.py's widen_trunks() wherever there is room
TRUNK_WIDTH_LADDER = [0.8, 0.6, 0.5, 0.4, 0.3]
TRUNK_NETS = ["PANEL_BOOST_SW", "PANEL_INV_SW", "BL_SW", "+5V"]

# ---------------------------------------------------------------------------
# 1. Ground truth from the schematic
# ---------------------------------------------------------------------------
NETLIST_PATH = os.path.join(os.environ.get("TEMP", HERE), "clusterpaneltsd_netlist_for_pcb.net")
parts, pad_net, net_names = load_schematic(SCH, KICAD_CLI, NETLIST_PATH)
print(f"Loaded {len(parts)} real parts and {len(net_names)} nets from the schematic/netlist.")

# ---------------------------------------------------------------------------
# 2. Board scaffold: six layers, In1/In4 GND planes (same as the brain board)
# ---------------------------------------------------------------------------
board = Board.create_new()
board.layers.insert(1, LayerToken(ordinal=1, name='In1.Cu', type='power'))
board.layers.insert(2, LayerToken(ordinal=2, name='In2.Cu', type='signal'))
board.layers.insert(3, LayerToken(ordinal=3, name='In3.Cu', type='signal'))
board.layers.insert(4, LayerToken(ordinal=4, name='In4.Cu', type='power'))
net_registry = {}


def net_number(name):
    if name not in net_registry:
        net_registry[name] = len(net_registry) + 1
        board.nets.append(Net(number=net_registry[name], name=name))
    return net_registry[name]


def _rot_xy(x, y, a):
    a %= 360
    if a == 0:
        return x, y
    if a == 90:
        return y, -x
    if a == 180:
        return -x, -y
    return -y, x


def _rot_bbox(bb, a):
    x0, y0, x1, y1 = bb
    pts = [_rot_xy(x, y, a) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


# ---------------------------------------------------------------------------
# 3. Cells and floorplan
# ---------------------------------------------------------------------------
cell_parts = _cells.make_parts(parts, pad_net, load_footprint, footprint_bbox)
res, used = _cells.plan_cells(cell_parts)
missing = set(parts) - used
assert not missing, f"parts in the schematic but not in any cell: {sorted(missing)}"
cells = dict(res)
for n, (pl, bb) in cells.items():
    print(f"  cell {n}: {len(pl)} parts, {bb[2] - bb[0]:.1f}x{bb[3] - bb[1]:.1f}mm")


def orient(cell, test):
    for r in (0, 90, 180, 270):
        pl, bb = rotate_cell(*cells[cell], r)
        if test(pl):
            cells[cell] = (pl, bb)
            return r
    raise RuntimeError(f"no rotation of {cell} passes its orientation test")


# J4: DSI row (even pins) BELOW the odd row, so it faces J1 underneath; the FPC
# then enters from the top edge (the FH26 body lies on the odd-row side).
rot_j4 = orient("PANEL", lambda pl: abs(pad_abs(cell_parts, pl, "J4", "24")[1] -
                                         pad_abs(cell_parts, pl, "J4", "38")[1]) < 0.01 and
                pad_abs(cell_parts, pl, "J4", "24")[1] > pad_abs(cell_parts, pl, "J4", "1")[1] + 1.0)
# J1: pad row on top (toward J4), ribbon entering from the bottom edge.
rot_j1 = orient("PORT", lambda pl: pad_abs(cell_parts, pl, "J1", "9")[0] <
                pad_abs(cell_parts, pl, "J1", "22")[0] - 1.0 and
                pad_abs(cell_parts, pl, "J1", "9")[1] < cells["PORT"][1][1] + 3.0)


def size(n):
    b = cells[n][1]
    return b[2] - b[0], b[3] - b[1]


def fan_cx(cell, ref, a, b):
    pl, bb = cells[cell]
    return (pad_abs(cell_parts, pl, ref, a)[0] + pad_abs(cell_parts, pl, ref, b)[0]) / 2 - bb[0]


placed = {}
part_rot = {}


def put(name, left, top):
    pl, bb = cells[name]
    for ref, (cx, cy, a) in pl.items():
        placed[ref] = (left - bb[0] + cx, top - bb[1] + cy)
        part_rot[ref] = a


X0 = 200.0                      # the DSI centre line, before the board is shifted into place
top_h = max(size(n)[1] for n in ("BIAS", "PANEL", "JUMPERS", "BACKLIGHT"))
panel_left = X0 - fan_cx("PANEL", "J4", "24", "38")
put("PANEL", panel_left, top_h - size("PANEL")[1])   # J4 at the bottom of its row, closest to J1
put("BIAS", panel_left - GAP - size("BIAS")[0], 0.0)
put("JUMPERS", panel_left + size("PANEL")[0] + GAP, 0.0)
put("BACKLIGHT", panel_left + size("PANEL")[0] + GAP + size("JUMPERS")[0] + GAP, 0.0)
row2 = top_h + ROW_GAP
port_left = X0 - fan_cx("PORT", "J1", "9", "22")
put("PORT", port_left, row2)
put("PORTCAP", port_left - GAP - size("PORTCAP")[0], row2)

# board extents from the placed footprints
xs0, ys0, xs1, ys1 = [], [], [], []
for ref, (x, y) in placed.items():
    fp = load_footprint(parts[ref]["footprint"])
    bx0, by0, bx1, by1 = _rot_bbox(footprint_bbox(fp), part_rot[ref])
    xs0.append(x + bx0); ys0.append(y + by0); xs1.append(x + bx1); ys1.append(y + by1)
min_x, min_y, max_x, max_y = min(xs0), min(ys0), max(xs1), max(ys1)
board_width = round(max_x - min_x + 2 * M, 2)
board_height = round(max_y - min_y + 2 * M, 2)
PAGE_W, PAGE_H = 297.0, 210.0
board.paper.paperSize = "A4"
BOARD_OFFSET_X = round((PAGE_W - board_width) / 2, 2)
BOARD_OFFSET_Y = round((PAGE_H - board_height) / 2, 2)
dx = BOARD_OFFSET_X + M - min_x
dy = BOARD_OFFSET_Y + M - min_y
placed = {r: (round(x + dx, 3), round(y + dy, 3)) for r, (x, y) in placed.items()}
print(f"Board {board_width:.1f} x {board_height:.1f} mm; J4 rotated {rot_j4} deg, J1 rotated {rot_j1} deg")

# ---------------------------------------------------------------------------
# 4. Footprint instances
# ---------------------------------------------------------------------------
ref_label_pos = {}
for ref, info in parts.items():
    fp = load_footprint(info["footprint"])
    x, y = placed[ref]
    angle = part_rot.get(ref, 0)
    fp.position = Position(round(x, 3), round(y, 3), angle)
    fp.path = f"/{info['uuid']}"
    if angle:
        for pad in fp.pads:
            pad.position.angle = ((pad.position.angle or 0) + angle) % 360
    lx0, ly0, lx1, ly1 = footprint_bbox(fp)
    _, _ry0, _, _ = _rot_bbox((lx0, ly0, lx1, ly1), angle)
    _lx, _ly = _rot_xy(0.0, _ry0 - 0.5, (-angle) % 360)
    ref_label_pos[ref] = (round(_lx, 2), round(_ly, 2))
    for item in fp.graphicItems:
        if getattr(item, "type", None) == "reference":
            item.text = ref
        elif getattr(item, "type", None) == "value":
            item.text = info["value"]
    fp.properties["Reference"] = ref
    fp.properties["Value"] = info["value"]
    fp.properties.pop("KiLib_Generator", None)
    for pad in fp.pads:
        key = (ref, str(pad.number))
        if key in pad_net:
            pad.net = Net(number=net_number(pad_net[key]), name=pad_net[key])
    board.footprints.append(fp)

MOUNTING_HOLE_FP = "MountingHole:MountingHole_3.2mm_M3"
_mh = [("MH1", MOUNTING_HOLE_INSET, MOUNTING_HOLE_INSET),
       ("MH2", board_width - MOUNTING_HOLE_INSET, MOUNTING_HOLE_INSET),
       ("MH3", MOUNTING_HOLE_INSET, board_height - MOUNTING_HOLE_INSET),
       ("MH4", board_width - MOUNTING_HOLE_INSET, board_height - MOUNTING_HOLE_INSET)]
for r, x, y in _mh:
    fp = load_footprint(MOUNTING_HOLE_FP)
    fp.position = Position(round(BOARD_OFFSET_X + x, 3), round(BOARD_OFFSET_Y + y, 3), 0)
    fp.path = f"/{uuid_module.uuid4()}"
    fp.properties["Reference"] = r
    ref_label_pos[r] = (0.0, -4.15)
    board.footprints.append(fp)

# ---------------------------------------------------------------------------
# 5. Outline
# ---------------------------------------------------------------------------
ox, oy = BOARD_OFFSET_X, BOARD_OFFSET_Y
ex, ey = ox + board_width, oy + board_height
for p1, p2 in [((ox, oy), (ex, oy)), ((ex, oy), (ex, ey)), ((ex, ey), (ox, ey)), ((ox, ey), (ox, oy))]:
    board.graphicItems.append(GrLine(start=Position(round(p1[0], 3), round(p1[1], 3)),
                                     end=Position(round(p2[0], 3), round(p2[1], 3)),
                                     layer="Edge.Cuts", width=0.1))

# ---------------------------------------------------------------------------
# 6. Verification on the in-memory board
# ---------------------------------------------------------------------------
assert len(board.footprints) == len(parts) + len(_mh)
boxes = []
for fp in board.footprints:
    x0, y0, x1, y1 = _rot_bbox(footprint_bbox(fp), fp.position.angle or 0)
    boxes.append((fp.properties.get("Reference"), fp.position.X + x0, fp.position.Y + y0,
                  fp.position.X + x1, fp.position.Y + y1))
overlaps = [(a[0], b[0]) for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]]
assert not overlaps, f"overlapping footprint bounding boxes: {overlaps}"
for r, x0, y0, x1, y1 in boxes:
    assert ox <= x0 and x1 <= ex and oy <= y0 and y1 <= ey, f"{r} runs off the board"
print("Placement OK: no overlapping footprint bounding boxes, everything on the board")
pcb_pins, seen = {}, set()
for fp in board.footprints:
    for pad in fp.pads:
        if pad.net and pad.net.name and (fp.properties.get("Reference"), pad.number) not in seen:
            seen.add((fp.properties.get("Reference"), pad.number))
            pcb_pins[pad.net.name] = pcb_pins.get(pad.net.name, 0) + 1
sch_pins = {}
for (_, _), name in pad_net.items():
    sch_pins[name] = sch_pins.get(name, 0) + 1
mism = {n: (sch_pins[n], pcb_pins.get(n, 0)) for n in sch_pins if sch_pins[n] != pcb_pins.get(n, 0)}
assert not mism, f"net pin-count mismatches: {mism}"
print(f"Net check OK: all {len(sch_pins)} nets have matching pin counts between schematic and PCB")

board.to_file(PCB)
text = open(PCB, encoding="utf-8").read()
for ref, (lx, ly) in ref_label_pos.items():
    old = f'(property "Reference" "{ref}")'
    layer = "F.SilkS" if ref[0] in "UJ" else "F.Fab"
    new = (f'(property "Reference" "{ref}" (at {lx} {ly} 0) (layer "{layer}") '
           f'(effects (font (size 1.0 1.0) (thickness 0.15))))')
    assert text.count(old) == 1, ref
    text = text.replace(old, new, 1)
open(PCB, "w", encoding="utf-8").write(text)
print("Wrote", PCB)

# ---------------------------------------------------------------------------
# 7. Project rule, upgrade, DRC
# ---------------------------------------------------------------------------
_pro = os.path.join(HERE, "ClusterPanelTSD.kicad_pro")
_t = open(_pro, encoding="utf-8").read()
_t2, _n = re.subn(r'"min_track_width": [0-9.]+,', f'"min_track_width": {MIN_TRACK_WIDTH_MM},', _t)
assert _n == 1
if _t2 != _t:
    open(_pro, "w", encoding="utf-8", newline="").write(_t2)
r = subprocess.run([KICAD_CLI, "pcb", "upgrade", PCB], capture_output=True, text=True)
print("Upgraded to current KiCad format" if r.returncode == 0 else "WARNING: upgrade failed")
drc_path = os.path.join(os.environ.get("TEMP", HERE), "clusterpaneltsd_pcb_drc.json")
subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--output", drc_path, PCB],
               capture_output=True, text=True)
viol = json.load(open(drc_path, encoding="utf-8")).get("violations", [])


def _on_jumpers(v):
    return v.get("type") == "solder_mask_bridge" and all(
        any(f" of {jp} " in it.get("description", "") or f"of {jp} on" in it.get("description", "")
            for jp in ("JP1", "JP2")) for it in v.get("items", []))


by = {}
for v in viol:
    if not _on_jumpers(v):
        by[v.get("type")] = by.get(v.get("type"), 0) + 1
print("DRC on the unrouted board (unconnected_items expected):", dict(sorted(by.items())))
