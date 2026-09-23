"""
Generates Cluster.kicad_pcb from Cluster.kicad_sch: real footprints
(loaded from their actual .kicad_mod files, not reinvented) placed in
non-overlapping, section-grouped positions, with every pad assigned the
net name kicad-cli's own netlist export says it should have.

What this does NOT do: route copper (that's route_board.py). Placement
groups parts sensibly so a human has a sane starting point, but this is
a netlist-correct *unrouted* board - same state "Update PCB from
Schematic" leaves you in before you route it yourself.

*** ADAPTED FROM thermo-pcb (2026-09-23) ***
The generic machinery (footprint loading, bbox computation, the skyline
bin-packer, net assignment, overlap/net-count self-checks, board-outline
drawing, the Reference-label bare-property patch) is reused close to
verbatim - it's already generic and needed no changes, same lineage as
every sibling project's own build_pcb.py.

ONE thing is genuinely new, not a copy of any sibling's board-sizing
model: Cluster has a REAL, FIXED target outline (not a free width sweep
like thermo-pcb, and not one oversized anchor connector like
manifold-pcb/ecu-pcb). The user supplied real dash-opening dimensions
(README.md, 2026-09-23): 18.00" x 4.594" (457.2x116.69mm) is the hard
outer limit the board has to fit through; 17.361" x 4.155"
(441.09x105.54mm) is the real inner usable dimension once inside it.
This board targets the INNER figure so it comfortably clears the outer
limit with margin. The 5 display connectors (J3 speedo + U6-U9 aux
gauges) are pulled out of the general packer and placed in a single row
at evenly-spaced X positions across that width - real hole-CENTER
spacing isn't individually dimensioned on the user's reference image
(only sizes), so this is an explicit, flagged estimate, not measured
fact - matching the family's own "distinguish a real distance from an
estimate" discipline (see ecu-pcb's own CAM_COUT honesty about a
similarly-unconfirmed pin). Everything else (MCU, BT817AQ, power stage,
CAN transceiver, all passives) packs into the remaining height above
that connector row, same skyline algorithm as every sibling board.

Simplifications versus thermo-pcb's own script, deliberate and flagged,
not oversights: no back-silkscreen logo, no rounded board corners, and
Value-text silkscreen uses a fixed offset rather than thermo-pcb's own
neighbor-aware lane assignment - all real cosmetic polish, not
electrical correctness, appropriate to defer to a follow-up pass once
the real floorplan (the genuinely new, unproven part of this file) is
confirmed to actually work.
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
from kiutils.items.common import Net, Position
from kiutils.items.brditems import LayerToken
from kiutils.items.gritems import GrLine

HERE = os.path.dirname(os.path.abspath(__file__))
SCH = os.path.join(HERE, "Cluster.kicad_sch")
PCB = os.path.join(HERE, "Cluster.kicad_pcb")
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
    fp = next((p.value for p in inst.properties if p.key == "Footprint"), "")
    val = next((p.value for p in inst.properties if p.key == "Value"), "")
    parts[ref] = {"footprint": fp, "value": val, "uuid": inst.uuid}

NETLIST_PATH = os.path.join(os.environ.get("TEMP", HERE), "cluster_netlist_for_pcb.net")
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
    graphics, in its own local (unplaced) coordinate frame - see
    thermo-pcb's own build_pcb.py for the original reasoning (a
    right-angle connector's real overhang isn't captured by pads alone)."""
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
    """Same real algorithm as every sibling project's build_pcb.py - see
    thermo-pcb's own copy for the full reasoning. Returns (placed_dict,
    rotated_set, used_width, used_height)."""
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

# --- Real, fixed target outline (see this file's own header for the real
# user-supplied dimensions this comes from) ---
DASH_OPENING_W = 457.2   # 18.00in, hard outer limit
DASH_OPENING_H = 116.69  # 4.594in, hard outer limit
TARGET_W = 441.09        # 17.361in, real inner usable dimension - board target
TARGET_H = 105.54        # 4.155in, real inner usable dimension - board target

# --- 5 display connectors, pulled out of the general packer (real
# mechanical reason: their positions have to roughly match the 5 real
# gauge holes, which the general area/clearance-only packer has no way
# to know about - same "pull the part with an outside-the-packer
# constraint" move every sibling board's own build_pcb.py already makes
# for at least one connector). ---
DISPLAY_REFS = ["U6", "U7", "J3", "U8", "U9"]  # real left-to-right order,
                                                 # matching the reference
                                                 # image: fuel, oil, speedo,
                                                 # coolant temp, battery
_disp_fp = {ref: load_footprint(parts[ref]["footprint"]) for ref in DISPLAY_REFS}
_disp_bbox = {ref: footprint_bbox(fp) for ref, fp in _disp_fp.items()}
_disp_w = {ref: x1 - x0 for ref, (x0, y0, x1, y1) in _disp_bbox.items()}
_disp_h = {ref: y1 - y0 for ref, (x0, y0, x1, y1) in _disp_bbox.items()}

# Real hole-center X spacing is NOT individually dimensioned on the user's
# reference image (only sizes were) - evenly-spaced estimate, explicitly
# confirmed with the user as the right way to proceed for now (2026-09-23)
# rather than blocking on exact numbers. Edge inset sized to comfortably
# clear the widest connector's own half-width plus real margin.
_edge_inset = max(_disp_w.values()) / 2 + 15.0
_row_span = TARGET_W - 2 * _edge_inset
_row_x = {ref: _edge_inset + i * (_row_span / (len(DISPLAY_REFS) - 1))
          for i, ref in enumerate(DISPLAY_REFS)}
# Connector row sits along the board's own bottom edge (the real-world
# "front" of the board, closest to the reprinted faceplate) - real
# support passives for each display (VLED resistors, decoupling caps,
# the backlight switch) get their own small reserve directly above each
# connector, same "keep a real thermal/signal-integrity relationship
# short" reasoning as thermo-pcb's own analog/motor column reserves,
# applied here to "keep each display's own support parts near it"
# instead.
# Real DRC finding (first run): BOARD_MARGIN (3mm) wasn't enough clearance
# for these connectors' own silkscreen outline against the board's bottom
# edge (10 real silk_edge_clearance hits, all 5 display connectors) - a
# bigger, dedicated bottom margin fixes it rather than guessing a small
# nudge.
DISPLAY_ROW_BOTTOM_MARGIN = 6.0
ROW_Y = TARGET_H - max(_disp_h.values()) / 2 - DISPLAY_ROW_BOTTOM_MARGIN
placed_rel = {}
for ref in DISPLAY_REFS:
    x0, y0, x1, y1 = _disp_bbox[ref]
    cx, cy = _row_x[ref], ROW_Y
    # Real coordinate-math bug caught by the first DRC run (silk clipped
    # past the board edge by ~0.56-0.95mm, unchanged no matter how much
    # margin got added - a dead giveaway the margin wasn't the actual
    # variable in play): placing a footprint's ORIGIN such that its bbox
    # CENTER lands at (cx, cy) is `origin = (cx, cy) - bbox_midpoint`, i.e.
    # `(cx - (x0+x1)/2, cy - (y0+y1)/2)`. The extra `- x0`/`- y0` terms
    # this line previously had belong to a DIFFERENT formula entirely
    # (placing the bbox's own (x0,y0) CORNER at a target, not its center)
    # - conflating the two put every display connector's real footprint
    # origin ~4mm further down/right than intended, silently eating into
    # the bottom-edge clearance this same section was trying to budget
    # for with DISPLAY_ROW_BOTTOM_MARGIN.
    placed_rel[ref] = (cx - (x0 + x1) / 2, cy - (y0 + y1) / 2)

print(f"Display row: {len(DISPLAY_REFS)} connectors at x="
      f"{sorted(round(v) for v in _row_x.values())}, y~{ROW_Y:.1f}mm "
      f"(evenly-spaced estimate, not real dimensioned hole-center data)")

# Everything else packs into the remaining height above the connector row
# via the same shared skyline algorithm every sibling board uses.
PACK_H_BUDGET = ROW_Y - max(_disp_h.values()) / 2 - BOARD_MARGIN - MARGIN
ORDER = [r for r in parts.keys() if r not in DISPLAY_REFS]

_total_area = 0.0
for _ref in ORDER:
    _fp = load_footprint(parts[_ref]["footprint"])
    _x0, _y0, _x1, _y1 = footprint_bbox(_fp)
    _total_area += (_x1 - _x0 + MARGIN) * (_y1 - _y0 + MARGIN)
print(f"Real total footprint area (non-display parts): {_total_area:.0f}mm^2, "
      f"budget at target width x remaining height: "
      f"{TARGET_W * PACK_H_BUDGET:.0f}mm^2")

placed_rest, rotated_refs, used_w, used_h = best_skyline_pack(
    ORDER, max_width=TARGET_W, margin=MARGIN)

# skyline_pack's own internal frame starts flush at (0, 0) - it only
# spaces PARTS apart from each other by `margin`, it has no notion of the
# board's own edge. Real bug caught by the first DRC run: without adding
# BOARD_MARGIN here, every one of these parts landed with ZERO clearance
# to the board's top edge (155 real copper_edge_clearance violations) -
# same class of bug thermo-pcb's own build_pcb.py already fixed once
# (see BOARD_OFFSET_X/Y's own history there), just missed on this fresh
# port until a real DRC run caught it again.
for ref, (x, y) in placed_rest.items():
    placed_rel[ref] = (x + BOARD_MARGIN, y + BOARD_MARGIN)

board_width = max(used_w, TARGET_W) + 2 * BOARD_MARGIN
board_height = max(used_h + MARGIN, ROW_Y + max(_disp_h.values()) / 2) + BOARD_MARGIN
if used_h > PACK_H_BUDGET:
    print(f"NOTE: non-display parts used {used_h:.1f}mm of height, "
          f"more than the {PACK_H_BUDGET:.1f}mm budgeted above the display "
          f"row - board grew to {board_height:.1f}mm, past the real "
          f"{TARGET_H:.1f}mm target (still comfortably under the "
          f"{DASH_OPENING_H:.1f}mm hard outer opening limit if so - check "
          f"the printed height below against that limit).")

print(f"Board outline target: {board_width:.1f} x {board_height:.1f}mm "
      f"(real dash-opening hard limit: {DASH_OPENING_W:.1f} x {DASH_OPENING_H:.1f}mm)")
assert board_width <= DASH_OPENING_W, (
    f"board_width {board_width:.1f}mm exceeds the real {DASH_OPENING_W:.1f}mm "
    f"dash-opening hard limit - the part mix doesn't fit this board class "
    f"at all, needs a real design change, not a bigger board")
assert board_height <= DASH_OPENING_H, (
    f"board_height {board_height:.1f}mm exceeds the real {DASH_OPENING_H:.1f}mm "
    f"dash-opening hard limit - the part mix doesn't fit this board class "
    f"at all, needs a real design change, not a bigger board")

PAGE_W, PAGE_H = 594.0, 420.0  # A2 landscape - A3 (420x297) turned out
                                # SMALLER than the real board (447mm wide),
                                # which drove BOARD_OFFSET_X negative (a
                                # real bug caught by the first DRC run's
                                # edge-clearance findings citing an
                                # Edge.Cuts segment at x=-13.5)
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
              f"(spare/mechanical): {unmatched}")
    board.footprints.append(fp)

print(f"Board outline: {board_width:.1f} x {board_height:.1f} mm, "
      f"{len(board.footprints)} footprints, {len(net_registry)} nets")

# ---------------------------------------------------------------------------
# 6. Board outline: simple rectangle on Edge.Cuts (rounded corners deferred
#    to a polish pass, see this file's own header)
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
# 7. Verification on the IN-MEMORY board (before writing/upgrading)
# ---------------------------------------------------------------------------
assert len(board.footprints) == len(parts), \
    f"footprint count mismatch: {len(board.footprints)} vs {len(parts)} parts"

boxes = []
for fp in board.footprints:
    x0, y0, x1, y1 = footprint_bbox(fp)
    if fp.position.angle == 90:
        x0, y0, x1, y1 = y0, -x1, y1, -x0
    boxes.append((fp.path, fp.position.X + x0, fp.position.Y + y0,
                 fp.position.X + x1, fp.position.Y + y1))
overlaps = []
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        _, ax0, ay0, ax1, ay1 = boxes[i]
        _, bx0, by0, bx1, by1 = boxes[j]
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            overlaps.append((boxes[i][0], boxes[j][0]))
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

# Bare-Reference-property patch (see thermo-pcb's own build_pcb.py for the
# full reasoning: kiutils can't write a position for this property, so
# KiCad's own `pcb upgrade` would otherwise default every one to (0,0,0),
# dead center on the part).
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

drc_path = os.path.join(os.environ.get("TEMP", HERE), "cluster_pcb_drc.json")
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
unexpected = {t: c for t, c in by_type.items() if t != "unconnected_items"}
if unexpected:
    print("NOTE: non-routing DRC findings present, see", drc_path, "for details:", unexpected)
else:
    print("No unexpected DRC findings (only unrouted-net warnings, as expected).")
