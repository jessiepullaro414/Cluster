"""
Generates ClusterDisplay.kicad_pcb from ClusterDisplay.kicad_sch: real
footprints (loaded from their actual .kicad_mod files, not reinvented)
placed in non-overlapping, section-grouped positions, with every pad
assigned the net name kicad-cli's own netlist export says it should
have.

What this does NOT do: route copper (that's route_board.py). Placement
groups parts sensibly so a human has a sane starting point, but this is
a netlist-correct *unrouted* board - same state "Update PCB from
Schematic" leaves you in before you route it yourself.

*** ADAPTED FROM gauges/build_pcb.py / the original cluster-pcb
build_pcb.py (2026-09-25) *** The generic machinery (footprint loading,
bbox computation, the skyline bin-packer, net assignment, overlap/net-
count self-checks, board-outline drawing, the Reference-label bare-
property patch, the real DRC-verify loop) is reused near-verbatim -
none of it needed to change.

WHAT IS GENUINELY NEW, not a copy of any sibling board's own layout:
this board has no real fixed target width the way gauges/ does (that
board's width is pinned by 4 real, unmoving dash holes; this board's
real job is just to sit somewhere behind the center opening, and
nothing here dictates its footprint size the way the dash-opening did
for the original 5-connector board). Instead, this board's real shape
is driven by ONE big, unavoidable mechanical fact: the Toradex Verdin
iMX95 module itself is 69.6 x 47mm (real, confirmed spec - Verdin
Family Specification), plugging into the SODIMM-260 socket (U1) and
lying flat over a real keepout zone that nothing else on the board can
occupy. That keepout is sized GENEROUSLY (90 x 90mm) rather than
precisely, because the socket's own real courtyard geometry (pulled
directly from its bundled footprint: an irregular ~27 x 76.5mm outline,
not a plain rectangle - real SODIMM sockets have an angled ejector-latch
cutout) doesn't by itself say which direction the module extends once
inserted, and neither fascia-pcb (the sibling that already uses this
exact same SoM) nor this project has laid out a real Verdin carrier
board before to reuse a proven answer from. This is flagged HONESTLY as
a first-pass reservation, not a precisely modeled mechanical fact - a
real follow-up pass should pull Toradex's own carrier-board design
guide (module overhang direction, the real S1-S4 standoff positions)
before this keepout is trusted for a real enclosure fit.

Layout strategy: the module keepout (top-left) and the panel connector
J4 (top-right, toward the board's real "front" edge facing the round
panel) occupy a top band; the 5 real circuit zones (POWER, CAN0/1V8,
PANEL_VSN, PANEL_BACKLIGHT, CONTROL) pack left-to-right in a band below
that, same skyline-per-zone approach gauges/'s own CORE_ZONES uses.
Board size is DERIVED from what's actually packed (same "don't inflate
past real content" discipline the original cluster-pcb board's own
height-shrink established), with the real dash-opening hard limit
(116.69mm height) checked as a final sanity ceiling, not a target.
"""
import json
import math
import os
import re
import shutil
import subprocess
import uuid as uuid_module

from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.items.common import Net, Position, Effects, Font, Justify
from kiutils.items.brditems import LayerToken
from kiutils.items.gritems import GrLine, GrCircle, GrArc, GrText

HERE = os.path.dirname(os.path.abspath(__file__))
SCH = os.path.join(HERE, "ClusterDisplay.kicad_sch")
PCB = os.path.join(HERE, "ClusterDisplay.kicad_pcb")
KICAD_FOOTPRINTS = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
PROJECT_FOOTPRINTS = os.path.join(HERE, "footprints")


def find_kicad_cli():
    exe = shutil.which("kicad-cli")
    if exe:
        return exe
    for candidate in [
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


KICAD_CLI = find_kicad_cli()
if not KICAD_CLI:
    raise SystemExit("kicad-cli not found - needed for netlist export and pcb upgrade")

# ---------------------------------------------------------------------------
# 1. Ground truth: real ref/footprint list from the schematic, real net
#    assignments from kicad-cli's own netlist export.
# ---------------------------------------------------------------------------
from kiutils.schematic import Schematic
from kiutils.utils import sexpr

sch = Schematic.from_sexpr(sexpr.parse_sexp(open(SCH, encoding="utf-8").read()))
parts = {}  # ref -> {"footprint": "lib:name", "value": str, "uuid": str}
for inst in sch.schematicSymbols:
    ref = next(p.value for p in inst.properties if p.key == "Reference")
    if ref.startswith("#"):
        continue  # power-flag symbols aren't physical parts
    if ref in parts:
        continue  # multi-unit symbol (e.g. J1, the Verdin X1 connector) - one footprint instance covers all units
    fp = next((p.value for p in inst.properties if p.key == "Footprint"), "")
    val = next((p.value for p in inst.properties if p.key == "Value"), "")
    parts[ref] = {"footprint": fp, "value": val, "uuid": inst.uuid}

NETLIST_PATH = os.path.join(os.environ.get("TEMP", HERE), "clusterdisplay_netlist_for_pcb.net")
result = subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr",
                         "--output", NETLIST_PATH, SCH], capture_output=True, text=True)
if result.returncode != 0:
    raise SystemExit(f"netlist export failed: {result.stderr}")

netlist_txt = open(NETLIST_PATH, encoding="utf-8").read()
pad_net = {}  # (ref, pin) -> net_name
net_names = []
for block in re.split(r"\(net\s", netlist_txt)[1:]:
    name = re.search(r'\(name "([^"]+)"\)', block).group(1).lstrip("/")
    nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)
    if len(nodes) < 2:
        continue
    net_names.append(name)
    for ref, pin in nodes:
        pad_net[(ref, pin)] = name

print(f"Loaded {len(parts)} real parts and {len(net_names)} nets from the schematic/netlist.")

# ---------------------------------------------------------------------------
# 2. Footprint loading
# ---------------------------------------------------------------------------
def load_footprint(lib_colon_name):
    lib, _, name = lib_colon_name.partition(":")
    project_path = os.path.join(PROJECT_FOOTPRINTS, f"{lib}.pretty", f"{name}.kicad_mod")
    if os.path.isfile(project_path):
        path = project_path
    else:
        path = os.path.join(KICAD_FOOTPRINTS, f"{lib}.pretty", f"{name}.kicad_mod")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"footprint file not found: {path}")
    fp = Footprint.from_file(path)
    fp.libId = lib_colon_name
    return fp


def footprint_bbox(fp):
    """Bounding box from this footprint's pads AND silkscreen/courtyard
    graphics, in its own local (unplaced) coordinate frame."""
    xs, ys = [], []
    for pad in fp.pads:
        hw, hh = pad.size.X / 2, pad.size.Y / 2
        xs += [pad.position.X - hw, pad.position.X + hw]
        ys += [pad.position.Y - hh, pad.position.Y + hh]
    for item in fp.graphicItems:
        if hasattr(item, "start") and hasattr(item, "end"):
            xs += [item.start.X, item.end.X]
            ys += [item.start.Y, item.end.Y]
        elif hasattr(item, "coordinates"):
            xs += [p.X for p in item.coordinates]
            ys += [p.Y for p in item.coordinates]
        elif hasattr(item, "center"):
            r = ((item.end.X - item.center.X) ** 2 + (item.end.Y - item.center.Y) ** 2) ** 0.5
            xs += [item.center.X - r, item.center.X + r]
            ys += [item.center.Y - r, item.center.Y + r]
    if not xs:
        return (-2, -2, 2, 2)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# 3. Board scaffold
# ---------------------------------------------------------------------------
board = Board.create_new()
board.layers.insert(1, LayerToken(ordinal=1, name='In1.Cu', type='signal'))
board.layers.insert(2, LayerToken(ordinal=2, name='In2.Cu', type='signal'))

net_registry = {}
def net_number(name):
    if name not in net_registry:
        n = len(net_registry) + 1
        net_registry[name] = n
        board.nets.append(Net(number=n, name=name))
    return net_registry[name]


# ---------------------------------------------------------------------------
# 4. Placement
# ---------------------------------------------------------------------------
MARGIN = 2.0

def skyline_pack(refs, max_width, margin, sort_key=None, initial_skyline=None):
    """Same real algorithm as every sibling project's build_pcb.py."""
    sized = []
    for ref in refs:
        fp = load_footprint(parts[ref]["footprint"])
        x0, y0, x1, y1 = footprint_bbox(fp)
        sized.append((ref, x1 - x0, y1 - y0, x0, y0, x1, y1))
    sized.sort(key=sort_key or (lambda t: t[1] * t[2]), reverse=True)

    skyline = initial_skyline if initial_skyline is not None else [(0.0, max_width, 0.0)]

    def profile_height(x, w):
        h = 0.0
        for sx, sw, sh in skyline:
            if sx + sw <= x + 1e-9 or sx >= x + w - 1e-9:
                continue
            h = max(h, sh)
        return h

    def best_position(w):
        best = None
        candidates = set()
        for sx, sw, sh in skyline:
            candidates.add(sx)
            candidates.add(sx + sw - w)
        for x in candidates:
            if x < -1e-9 or x + w > max_width + 1e-9:
                continue
            y = profile_height(x, w)
            if best is None or (y, x) < (best[0], best[1]):
                best = (y, x)
        return best

    def update_skyline(x, w, top):
        x_end = x + w
        segs = []
        for sx, sw, sh in skyline:
            s_end = sx + sw
            if s_end <= x + 1e-9 or sx >= x_end - 1e-9:
                segs.append((sx, sw, sh))
                continue
            if sx < x:
                segs.append((sx, x - sx, sh))
            if s_end > x_end:
                segs.append((x_end, s_end - x_end, sh))
        segs.append((x, w, top))
        segs.sort(key=lambda t: t[0])
        merged = []
        for seg in segs:
            if merged and abs(merged[-1][0] + merged[-1][1] - seg[0]) < 1e-6 \
                    and abs(merged[-1][2] - seg[2]) < 1e-6:
                merged[-1] = (merged[-1][0], merged[-1][1] + seg[1], merged[-1][2])
            else:
                merged.append(seg)
        return merged

    placed = {}
    rotated = set()
    for ref, w, h, x0, y0, x1, y1 in sized:
        options = []
        pos0 = best_position(w + margin)
        if pos0 is not None:
            y, x = pos0
            options.append((y + h + margin, x, False))
        pos90 = best_position(h + margin)
        if pos90 is not None:
            y, x = pos90
            options.append((y + w + margin, x, True))
        if not options:
            raise RuntimeError(f"skyline_pack: {ref} ({w:.1f}x{h:.1f}mm) doesn't "
                                f"fit in max_width={max_width:.1f}mm even alone")
        options.sort(key=lambda o: (o[0], o[1]))
        top, x, is_rot = options[0]
        if is_rot:
            rw, rh = h + margin, w + margin
            skyline = update_skyline(x, rw, top)
            placed[ref] = (x - y0, (top - rh) + x1)
            rotated.add(ref)
        else:
            rw, rh = w + margin, h + margin
            skyline = update_skyline(x, rw, top)
            placed[ref] = (x - x0, (top - rh) - y0)

    used_w, used_h = 0.0, 0.0
    for ref, w, h, x0, y0, x1, y1 in sized:
        px, py = placed[ref]
        if ref in rotated:
            used_w = max(used_w, px + y1)
            used_h = max(used_h, py - x0)
        else:
            used_w = max(used_w, px + x1)
            used_h = max(used_h, py + y1)
    return placed, rotated, used_w, used_h


def best_skyline_pack(refs, max_width, margin, initial_skyline=None):
    strategies = {
        "area-desc": lambda t: t[1] * t[2],
        "max-side-desc": lambda t: max(t[1], t[2]),
        "height-desc": lambda t: t[2],
        "width-desc": lambda t: t[1],
        "perimeter-desc": lambda t: t[1] + t[2],
    }
    best_name, best_result = None, None
    for name, key in strategies.items():
        result = skyline_pack(refs, max_width, margin, sort_key=key, initial_skyline=initial_skyline)
        used_w, used_h = result[2], result[3]
        if best_result is None or (used_h, used_w) < (best_result[3], best_result[2]):
            best_name, best_result = name, result
    print(f"skyline pack: tried {len(strategies)} orderings, best was "
          f"'{best_name}' ({best_result[2]:.1f}x{best_result[3]:.1f}mm used)")
    return best_result


BOARD_MARGIN = 3.0

# --- Real dash-opening hard limit (same real user-supplied dimension
# every sibling board checks against) - a sanity ceiling here, not a
# target, since this board's own real shape is driven by the module
# keepout + zone content, not the dash width. ---
DASH_OPENING_W = 457.2   # 18.00in
DASH_OPENING_H = 116.69  # 4.594in

# --- U1 (Verdin X1 SODIMM-260 socket) + the real 69.6x47mm module that
# plugs into it - pulled out of the general packer, real mechanical
# reason (see this file's own header for the honest flag on exact
# orientation). Reserved as a generous keepout, not tightly fitted. ---
CONNECTOR_REFS = ["J1"]
_conn_fp = {ref: load_footprint(parts[ref]["footprint"]) for ref in CONNECTOR_REFS}
_conn_bbox = {ref: footprint_bbox(fp) for ref, fp in _conn_fp.items()}
MODULE_KEEPOUT_W = 90.0   # real 69.6mm module + real margin for
MODULE_KEEPOUT_H = 90.0   # standoffs/overhang in an unconfirmed direction

# --- J4 (panel connector) - also pulled out, real mechanical reason:
# it needs to sit toward the board's "front" edge (facing the round
# panel), same as U1/the module, not buried in the middle of a packed
# zone. ---
PANEL_CONN_REFS = ["J4"]
_panel_conn_fp = {ref: load_footprint(parts[ref]["footprint"]) for ref in PANEL_CONN_REFS}
_panel_conn_bbox = {ref: footprint_bbox(fp) for ref, fp in _panel_conn_fp.items()}

placed_rel = {}

# --- Everything else: 5 real functional zones, same "keep a real
# relationship short" reasoning as gauges/'s own CORE_ZONES. ---
CORE_ZONES = [
    ("POWER", ["J2", "F1", "D1", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
               "L1", "Q1", "Q2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
               "R9", "R10", "R11", "R12", "R13", "R14", "R15", "R16", "U1", "U2"]),
    ("CAN0_1V8", ["C9", "C10", "C11", "C12", "C13", "J3", "R17", "R18", "R19",
                  "R20", "R21", "U3", "U4"]),
    ("PANEL_VSN", ["C40", "C41", "C42", "U6"]),
    ("PANEL_BACKLIGHT", ["C43", "C44", "C45", "D2", "L2", "Q3", "R37", "R38",
                          "R39", "R40", "U7"]),
    ("CONTROL", ["C39", "J8", "J9", "J10", "R44", "R45", "R46", "R47", "R48", "R49"]),
]

_accounted = set(CONNECTOR_REFS) | set(PANEL_CONN_REFS)
for _, refs in CORE_ZONES:
    _accounted.update(refs)
_missing = set(parts.keys()) - _accounted
_extra = _accounted - set(parts.keys())
assert not _missing, f"parts in the schematic but not assigned to any zone: {sorted(_missing)}"
assert not _extra, f"zone refs that don't exist in the schematic: {sorted(_extra)}"

rotated_refs = set()

# 1. Pack each core zone first (don't place yet - real board size not
# known until every zone's been packed).
ZONE_MAX_W = 90.0
zone_packed = []
for name, refs in CORE_ZONES:
    z_placed, z_rot, z_w, z_h = best_skyline_pack(refs, max_width=ZONE_MAX_W, margin=MARGIN)
    rotated_refs |= z_rot
    zone_packed.append((name, refs, z_placed, z_w, z_h))
    print(f"  core zone {name}: {len(refs)} parts, {z_w:.1f}x{z_h:.1f}mm")

ZONE_GAP = 8.0
zone_total_w = sum(z_w for _, _, _, z_w, _ in zone_packed) + ZONE_GAP * (len(zone_packed) - 1)
zone_max_h = max(z_h for _, _, _, _, z_h in zone_packed)

# --- Top band: module keepout (left) + panel connector (right) ---
_conn_x0, _conn_y0, _conn_x1, _conn_y1 = _conn_bbox["J1"]
_pconn_x0, _pconn_y0, _pconn_x1, _pconn_y1 = _panel_conn_bbox["J4"]
_pconn_w = _pconn_x1 - _pconn_x0
_pconn_h = _pconn_y1 - _pconn_y0

TOP_BAND_GAP = 10.0
top_band_w = MODULE_KEEPOUT_W + TOP_BAND_GAP + max(_pconn_w, 40.0)
top_band_h = max(MODULE_KEEPOUT_H, _pconn_h)

board_width = max(top_band_w, zone_total_w) + 2 * BOARD_MARGIN
ZONE_BAND_GAP = 8.0
board_height = top_band_h + ZONE_BAND_GAP + zone_max_h + 2 * BOARD_MARGIN

print(f"Real minimal board size: {board_width:.1f} x {board_height:.1f}mm "
      f"(module keepout {MODULE_KEEPOUT_W:.0f}x{MODULE_KEEPOUT_H:.0f}mm is the "
      f"single biggest driver - see this file's own header on why it's a "
      f"generous first-pass reservation, not a precise mechanical fact)")

assert board_height <= DASH_OPENING_H * 1.5, (
    f"board_height {board_height:.1f}mm is implausibly large even against "
    f"1.5x the real dash-opening hard limit ({DASH_OPENING_H:.1f}mm) - "
    f"something in the zone packing has gone wrong, not just \"needs a "
    f"bigger board\"")
# NOTE: board_height is NOT asserted against the bare DASH_OPENING_H the
# way gauges/'s own board is - this board's real installation depth in
# the dash (in front of/behind/beside gauges/) isn't resolved yet (see
# README's own note on the stacked/side-by-side/gap-based options all
# being viable), so a hard fail here would be asserting a constraint
# that isn't actually confirmed yet, not a real one.

# Place U1 (module keepout) at top-left.
_mod_cx = BOARD_MARGIN + MODULE_KEEPOUT_W / 2
_mod_cy = BOARD_MARGIN + MODULE_KEEPOUT_H / 2
placed_rel["J1"] = (_mod_cx - (_conn_x0 + _conn_x1) / 2, _mod_cy - (_conn_y0 + _conn_y1) / 2)

# Place J4 (panel connector) at top-right, vertically centered in the top band.
_pconn_cx = BOARD_MARGIN + MODULE_KEEPOUT_W + TOP_BAND_GAP + max(_pconn_w, 40.0) / 2
_pconn_cy = BOARD_MARGIN + top_band_h / 2
placed_rel["J4"] = (_pconn_cx - (_pconn_x0 + _pconn_x1) / 2, _pconn_cy - (_pconn_y0 + _pconn_y1) / 2)

# Place the 5 core zones left-to-right in the band below.
zone_y = BOARD_MARGIN + top_band_h + ZONE_BAND_GAP
zone_x = BOARD_MARGIN
zone_gap_centers = [zone_x + zone_max_h * 0]  # placeholder start; real centers built below
zone_gap_centers = []
_cursor = BOARD_MARGIN
for name, refs, z_placed, z_w, z_h in zone_packed:
    for ref, (x, y) in z_placed.items():
        placed_rel[ref] = (x + _cursor, y + zone_y)
    zone_gap_centers.append(_cursor - ZONE_GAP / 2)
    _cursor += z_w + ZONE_GAP
zone_gap_centers.append(_cursor - ZONE_GAP / 2)

PAGE_W, PAGE_H = 420.0, 297.0  # A3 landscape - this board is much
                                 # smaller than gauges/, no A2 needed
board.paper.paperSize = "A3"
if board_width > PAGE_W - 20 or board_height > PAGE_H - 20:
    PAGE_W, PAGE_H = 594.0, 420.0
    board.paper.paperSize = "A2"
BOARD_OFFSET_X = round((PAGE_W - board_width) / 2, 2)
BOARD_OFFSET_Y = round((PAGE_H - board_height) / 2, 2)
placed = {ref: (round(x + BOARD_OFFSET_X, 2), round(y + BOARD_OFFSET_Y, 2))
          for ref, (x, y) in placed_rel.items()}

# ---------------------------------------------------------------------------
# 5. Build footprint instances: real part, real pads, real nets, real position
# ---------------------------------------------------------------------------
ref_label_pos = {}
for ref, info in parts.items():
    fp = load_footprint(info["footprint"])
    x, y = placed[ref]
    angle = 90 if ref in rotated_refs else 0
    fp.position = Position(round(x, 3), round(y, 3), angle)
    fp.path = f"/{info['uuid']}"
    if angle:
        for pad in fp.pads:
            pad.position.angle = angle
    lx0, ly0, lx1, ly1 = footprint_bbox(fp)
    if angle == 90:
        ref_label_pos[ref] = (round(lx1 + 0.5, 2), 0.0)
    else:
        ref_label_pos[ref] = (0.0, round(ly0 - 0.5, 2))
    for item in fp.graphicItems:
        if getattr(item, "type", None) == "reference":
            item.text = ref
        elif getattr(item, "type", None) == "value":
            item.text = info["value"]
    fp.properties["Reference"] = ref
    fp.properties["Value"] = info["value"]
    fp.properties.pop("KiLib_Generator", None)
    unmatched = []
    for pad in fp.pads:
        key = (ref, str(pad.number))
        if key in pad_net:
            name = pad_net[key]
            pad.net = Net(number=net_number(name), name=name)
        else:
            unmatched.append(pad.number)
    if unmatched:
        print(f"  {ref}: {len(unmatched)} pad(s) with no schematic net "
              f"(spare/mechanical): {len(unmatched)} pads")
    board.footprints.append(fp)

# ---------------------------------------------------------------------------
# 5b. Standoff/mounting holes. Same real bundled part every sibling
#     board uses (MountingHole_3.2mm_M3). 4 corners - this board is
#     compact (not long/thin like gauges/), so 4 real support points is
#     enough, no extra holes needed.
# ---------------------------------------------------------------------------
MOUNTING_HOLE_FP = "MountingHole:MountingHole_3.2mm_M3"
MOUNTING_HOLE_INSET = 7.0
_mh_positions = [
    ("MH1", BOARD_OFFSET_X + MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
    ("MH2", BOARD_OFFSET_X + board_width - MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
    ("MH3", BOARD_OFFSET_X + MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + board_height - MOUNTING_HOLE_INSET),
    ("MH4", BOARD_OFFSET_X + board_width - MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + board_height - MOUNTING_HOLE_INSET),
]
for mh_ref, mh_x, mh_y in _mh_positions:
    mh_fp = load_footprint(MOUNTING_HOLE_FP)
    mh_fp.position = Position(round(mh_x, 3), round(mh_y, 3), 0)
    mh_fp.path = f"/{uuid_module.uuid4()}"
    mh_fp.properties["Reference"] = mh_ref
    ref_label_pos[mh_ref] = (0.0, -4.15)
    board.footprints.append(mh_fp)
print(f"Added {len(_mh_positions)} M3 mounting holes (4 corners - this "
      f"board is compact, not long/thin like gauges/)")

print(f"Board outline: {board_width:.1f} x {board_height:.1f} mm, "
      f"{len(board.footprints)} footprints, {len(net_registry)} nets")

# ---------------------------------------------------------------------------
# 6. Board outline: simple rectangle on Edge.Cuts
# ---------------------------------------------------------------------------
ox, oy = BOARD_OFFSET_X, BOARD_OFFSET_Y
ex, ey = BOARD_OFFSET_X + board_width, BOARD_OFFSET_Y + board_height
for p1, p2 in [((ox, oy), (ex, oy)), ((ex, oy), (ex, ey)),
               ((ex, ey), (ox, ey)), ((ox, ey), (ox, oy))]:
    board.graphicItems.append(GrLine(
        start=Position(round(p1[0], 3), round(p1[1], 3)),
        end=Position(round(p2[0], 3), round(p2[1], 3)),
        layer="Edge.Cuts", width=0.1))

# ---------------------------------------------------------------------------
# 6a. Module keepout outline (F.SilkS + F.Fab) - visual reminder that
#     this real estate is reserved for the Verdin module, not empty
#     board area a future edit might accidentally fill.
# ---------------------------------------------------------------------------
_kx0 = BOARD_OFFSET_X + BOARD_MARGIN
_ky0 = BOARD_OFFSET_Y + BOARD_MARGIN
_kx1 = _kx0 + MODULE_KEEPOUT_W
_ky1 = _ky0 + MODULE_KEEPOUT_H
for p1, p2 in [((_kx0, _ky0), (_kx1, _ky0)), ((_kx1, _ky0), (_kx1, _ky1)),
               ((_kx1, _ky1), (_kx0, _ky1)), ((_kx0, _ky1), (_kx0, _ky0))]:
    board.graphicItems.append(GrLine(
        start=Position(round(p1[0], 3), round(p1[1], 3)),
        end=Position(round(p2[0], 3), round(p2[1], 3)),
        layer="Dwgs.User", width=0.2))
board.graphicItems.append(GrText(
    text="VERDIN MODULE KEEPOUT (provisional, see build_pcb.py header)",
    position=Position(round(_kx0 + 3, 3), round(_ky0 + 5, 3), 0),
    layer="Dwgs.User",
    effects=Effects(font=Font(height=2.0, width=2.0, thickness=0.3))))
print("Added module keepout outline (Dwgs.User) - provisional, see this "
      "script's own header comment")

# ---------------------------------------------------------------------------
# 7. Verification on the IN-MEMORY board (before writing/upgrading)
# ---------------------------------------------------------------------------
MECHANICAL_FOOTPRINT_COUNT = len(_mh_positions)
assert len(board.footprints) == len(parts) + MECHANICAL_FOOTPRINT_COUNT, \
    (f"footprint count mismatch: {len(board.footprints)} vs {len(parts)} parts "
     f"+ {MECHANICAL_FOOTPRINT_COUNT} mechanical")

boxes = []
for fp in board.footprints:
    x0, y0, x1, y1 = footprint_bbox(fp)
    if fp.position.angle == 90:
        x0, y0, x1, y1 = y0, -x1, y1, -x0
    boxes.append((fp.properties.get("Reference", fp.path), fp.position.X + x0, fp.position.Y + y0,
                 fp.position.X + x1, fp.position.Y + y1))
overlaps = []
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        ra, ax0, ay0, ax1, ay1 = boxes[i]
        rb, bx0, by0, bx1, by1 = boxes[j]
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            overlaps.append((ra, (round(ax0,1),round(ay0,1),round(ax1,1),round(ay1,1)),
                              rb, (round(bx0,1),round(by0,1),round(bx1,1),round(by1,1))))
assert not overlaps, f"overlapping footprint bounding boxes: {overlaps}"
print("Placement OK: no overlapping footprint bounding boxes")

pcb_net_pins = {}
seen_logical_pins = set()
for fp in board.footprints:
    ref = fp.properties.get("Reference")
    for pad in fp.pads:
        if pad.net and pad.net.name:
            logical_pin = (ref, pad.number)
            if logical_pin in seen_logical_pins:
                continue
            seen_logical_pins.add(logical_pin)
            pcb_net_pins.setdefault(pad.net.name, 0)
            pcb_net_pins[pad.net.name] += 1
sch_net_pins = {}
for (ref, pin), name in pad_net.items():
    sch_net_pins[name] = sch_net_pins.get(name, 0) + 1
mismatches = {n: (sch_net_pins[n], pcb_net_pins.get(n, 0)) for n in sch_net_pins
              if sch_net_pins[n] != pcb_net_pins.get(n, 0)}
assert not mismatches, f"net pin-count mismatches (schematic vs PCB): {mismatches}"
print(f"Net check OK: all {len(sch_net_pins)} nets have matching pin "
      f"counts between schematic and PCB")

board.to_file(PCB)
print("Wrote", PCB)

text = open(PCB, encoding="utf-8").read()
for ref, (dx, dy) in ref_label_pos.items():
    old = f'(property "Reference" "{ref}")'
    new = (f'(property "Reference" "{ref}" (at {dx} {dy} 0) (layer "F.SilkS") '
           f'(effects (font (size 0.8 0.8) (thickness 0.12))))')
    count = text.count(old)
    assert count == 1, f"expected exactly 1 bare Reference property for {ref}, found {count}"
    text = text.replace(old, new, 1)
open(PCB, "w", encoding="utf-8").write(text)
print(f"Repositioned {len(ref_label_pos)} Reference labels clear of their own footprints")

# ---------------------------------------------------------------------------
# 8. Upgrade to current KiCad format, then run a real DRC
# ---------------------------------------------------------------------------
result = subprocess.run([KICAD_CLI, "pcb", "upgrade", PCB], capture_output=True, text=True)
print("Upgraded to current KiCad format:" if result.returncode == 0 else "WARNING: upgrade failed:",
      (result.stdout or result.stderr).strip())

drc_path = os.path.join(os.environ.get("TEMP", HERE), "clusterdisplay_pcb_drc.json")
result = subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json",
                         "--output", drc_path, "--exit-code-violations", PCB],
                        capture_output=True, text=True)
drc = json.load(open(drc_path, encoding="utf-8"))
violations = drc.get("violations", [])
by_type = {}
for v in violations:
    t = v.get("type", "unknown")
    by_type[t] = by_type.get(t, 0) + 1
print("DRC violation summary (unrouted board - 'unconnected_items' is EXPECTED "
      "for every net, everything else is worth a look):")
for t, count in sorted(by_type.items()):
    print(f"  {t}: {count}")
EXPECTED_TYPES = {"unconnected_items", "lib_footprint_mismatch"}
unexpected = {t: c for t, c in by_type.items() if t not in EXPECTED_TYPES}
if unexpected:
    print("NOTE: unexpected DRC findings present, see", drc_path, "for details:", unexpected)
elif by_type:
    print("All DRC findings are real, documented, expected categories - "
          "nothing unaccounted for.")
else:
    print("No unexpected DRC findings (only unrouted-net warnings, as expected).")
