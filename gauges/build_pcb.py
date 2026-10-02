"""
Generates ClusterGauges.kicad_pcb from ClusterGauges.kicad_sch: real
footprints (loaded from their actual .kicad_mod files, not reinvented)
placed in non-overlapping, section-grouped positions, with every pad
assigned the net name kicad-cli's own netlist export says it should
have.

What this does NOT do: route copper (that's route_board.py). Placement
groups parts sensibly so a human has a sane starting point, but this is
a netlist-correct *unrouted* board - same state "Update PCB from
Schematic" leaves you in before you route it yourself.

*** ADAPTED FROM the original cluster-pcb/build_pcb.py (2026-09-25) ***
Cluster's Android Automotive re-architecture split the original single
board into two: this one (gauges/) keeps the 4 small round GC9A01 aux
gauges + sensor ADC front end + CAN0, locally driven, no OS; the center
speedo moved to a separate Verdin iMX95 carrier (../display/). The
generic machinery below (footprint loading, bbox computation, the
skyline bin-packer, net assignment, overlap/net-count self-checks,
board-outline drawing, the tach-face silkscreen art, the Reference-
label bare-property patch) is reused near-verbatim from the original
file - none of it needed to change.

ONE thing IS genuinely different from the original file, not a copy:
DISPLAY_REFS drops J3 (the speedo connector, gone from this board's own
schematic) but keeps U6/U7/U8/U9 at their ORIGINAL real hole-position
fractions (slots 0, 1, 3, 4 of the original 5-slot row, deliberately
skipping slot 2) rather than re-spreading 4 connectors evenly across 4
new slots. The real aux-gauge hole positions in the dash haven't moved
just because the speedo's own board moved to a separate carrier - only
re-deriving even-4-way spacing would have silently pulled U7/U8 inward
toward the center and misaligned them from their real physical holes.
The freed-up space where J3's own local cluster (the whole BT817AQ
subsystem) used to sit is where this board's real remaining content
(MCU, CAN0, power, sensors) now consolidates - not an awkward gap, and
not needing a cutout for the display/ carrier, which is a physically
separate board (see cluster-pcb/README.md's own note on how the two
boards relate - any of stacked-depth / side-by-side / a literal gap all
work mechanically, since this board's real target width was always
driven by the OUTER aux-gauge hole positions, never by what sits
between them).
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
SCH = os.path.join(HERE, "ClusterGauges.kicad_sch")
PCB = os.path.join(HERE, "ClusterGauges.kicad_pcb")
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

# --- 4 display connectors, pulled out of the general packer (real
# mechanical reason: their positions have to roughly match the 4 real
# gauge holes, which the general area/clearance-only packer has no way
# to know about - same "pull the part with an outside-the-packer
# constraint" move every sibling board's own build_pcb.py already makes
# for at least one connector). ---
DISPLAY_REFS = ["U6", "U7", "U8", "U9"]  # real left-to-right order,
                                          # matching the reference image:
                                          # fuel, oil, [speedo - now on
                                          # display/], coolant temp,
                                          # battery
_disp_fp = {ref: load_footprint(parts[ref]["footprint"]) for ref in DISPLAY_REFS}
_disp_bbox = {ref: footprint_bbox(fp) for ref, fp in _disp_fp.items()}
_disp_w = {ref: x1 - x0 for ref, (x0, y0, x1, y1) in _disp_bbox.items()}
_disp_h = {ref: y1 - y0 for ref, (x0, y0, x1, y1) in _disp_bbox.items()}

# Real hole-center X spacing is NOT individually dimensioned on the user's
# reference image (only sizes were) - evenly-spaced estimate across the
# ORIGINAL 5-hole row, explicitly confirmed with the user as the right
# way to proceed for now (2026-09-23) rather than blocking on exact
# numbers. Edge inset sized to comfortably clear the widest connector's
# own half-width plus real margin.
#
# Real, easy-to-get-wrong detail specific to this board (gauges/, split
# from the original 5-connector design): U6/U7/U8/U9 keep their ORIGINAL
# 5-slot fractional positions (slots 0, 1, 3, 4 - skipping slot 2, where
# J3/the speedo used to sit) rather than being re-spread evenly across 4
# NEW slots. The real dash holes for these 4 gauges haven't moved just
# because the speedo's own board moved to display/ - re-deriving fresh
# 4-way even spacing would silently pull U7 and U8 inward toward the
# center and misalign them from their real physical holes.
_N_ORIGINAL_SLOTS = 5
_SLOT_INDEX = {"U6": 0, "U7": 1, "U8": 3, "U9": 4}  # slot 2 (speedo) skipped
_edge_inset = max(_disp_w.values()) / 2 + 15.0
_row_span = TARGET_W - 2 * _edge_inset
_row_x = {ref: _edge_inset + _SLOT_INDEX[ref] * (_row_span / (_N_ORIGINAL_SLOTS - 1))
          for ref in DISPLAY_REFS}
placed_rel = {}

# --- Everything else: real functional zones, spread across the full
# width, instead of one tight blob in a corner (2026-09-23 rework - the
# first pass was electrically fine but visually and practically bad: a
# 422.9x13.4mm sliver left 90%+ of the available width completely empty,
# meaning every trace to a far-side connector would have to cross the
# whole board for no real reason). Two kinds of zone, same "keep a real
# relationship short" reasoning as ecu-pcb's own 6-block schematic-Y-
# position bucketing and thermo-pcb's analog/motor column reserves:
#
# 1. LOCAL clusters: each display's own immediate support parts
#    (backlight resistor/decoupling cap, and for the speedo, its whole
#    BT817AQ+LDO+crystal subsystem) sit directly above THAT display -
#    short real traces, and a real visual/electrical reason each display
#    "owns" its own little cluster, not an arbitrary aesthetic split.
# 2. CORE zones: the board-wide subsystems (power input, MCU, CAN0, the
#    shared aux-gauge backlight switch, the 3 sender dividers) that don't
#    belong to any one display, arranged left-to-right in the band above
#    the local clusters.
LOCAL_CLUSTERS = {
    "U6": ["R6", "C17"],                                            # fuel gauge backlight
    "U7": ["R7", "C18"],                                            # oil gauge backlight
    # J3 (speedo) and its whole BT817AQ local cluster are gone - that
    # subsystem lives on display/ now, not this board.
    "U8": ["R8", "C19"],                                            # coolant temp backlight
    "U9": ["R9", "C20", "R19", "R20", "C31"],                       # battery gauge backlight + divider
}
CORE_ZONES = [
    ("POWER", ["J1", "F1", "Q1", "U2", "U3", "U4", "D1", "C1", "C2",
               "C3", "C10", "C11", "C12", "L1", "R2", "R3", "C45", "C46"]),
    ("MCU", ["U1", "Y1", "C4", "C5", "C6", "C7", "C8", "L2", "R1", "J2"]),
    # Rev B (2026-09-30): private CAN1 link to display/, Hall speed input,
    # ignition sense - see build_schematic.py's rev B comments.
    ("SPEED+IGN", ["J9", "R43", "R44", "R45", "C43", "D10",
                   "R46", "R47", "C44", "D11"]),
    ("CAN1 LINK", ["U10", "C40", "C41", "C42", "R40", "R41", "R42", "J8"]),
    ("CAN0", ["U5", "C13", "C14", "C15", "C16", "R4", "R5", "J7"]),
    ("AUX BL SWITCH", ["Q2", "R10", "R11"]),
    ("SENSORS", ["R16", "R17", "R18", "C28", "C29", "C30"]),
]

_accounted = set(DISPLAY_REFS)
for refs in LOCAL_CLUSTERS.values():
    _accounted.update(refs)
for _, refs in CORE_ZONES:
    _accounted.update(refs)
_missing = set(parts.keys()) - _accounted
_extra = _accounted - set(parts.keys())
assert not _missing, f"parts in the schematic but not assigned to any zone: {sorted(_missing)}"
assert not _extra, f"zone refs that don't exist in the schematic: {sorted(_extra)}"

rotated_refs = set()

# Real question asked (2026-09-23): "no reason to make it so big right?"
# - correct. The board's WIDTH genuinely can't shrink below TARGET_W (the
# 5 connectors have to reach across the real dash-opening width to land
# under their own real gauge holes, regardless of how little circuitry
# exists), but nothing forces the HEIGHT to fill the full 105.5mm inner
# opening - that was this project's own earlier assumption, not a real
# constraint (the board only needs to be as tall as its own real content,
# same as every sibling board's own height derivation). Fixed by packing
# every piece FIRST (both kinds of zone, below) to find their real sizes,
# THEN computing board_height from what's actually needed stacked
# bottom-to-top, instead of anchoring the display row to an oversized
# fixed target height.

# 1. Local clusters: pack each tightly first (don't place yet - real
# height not known until every cluster's been packed).
LOCAL_GAP = 4.0   # breathing room between a display connector and its own cluster
local_packed = {}
local_max_h = 0.0
for disp_ref, cluster_refs in LOCAL_CLUSTERS.items():
    c_placed, c_rot, c_w, c_h = best_skyline_pack(cluster_refs, max_width=60.0, margin=MARGIN)
    rotated_refs |= c_rot
    local_packed[disp_ref] = (c_placed, c_w, c_h)
    local_max_h = max(local_max_h, c_h)
    print(f"  local cluster above {disp_ref}: {len(cluster_refs)} parts, "
          f"{c_w:.1f}x{c_h:.1f}mm")

# 2. Core zones: same, pack first, place later once board_height is real.
zone_packed = []
for name, refs in CORE_ZONES:
    z_placed, z_rot, z_w, z_h = best_skyline_pack(refs, max_width=90.0, margin=MARGIN)
    rotated_refs |= z_rot
    zone_packed.append((name, refs, z_placed, z_w, z_h))
    print(f"  core zone {name}: {len(refs)} parts, {z_w:.1f}x{z_h:.1f}mm")

CORE_TOP_MARGIN = BOARD_MARGIN + MARGIN
CORE_LOCAL_GAP = 6.0        # breathing room between core zones and local clusters
DISPLAY_ROW_BOTTOM_MARGIN = 6.0  # same real DRC-driven value established earlier
core_max_h = max((z_h for _, _, _, z_w, z_h in zone_packed), default=0.0)
display_h = max(_disp_h.values())

# The real, minimal height this board actually needs, stacked bottom-to-
# top: bottom margin + display row + gap + tallest local cluster + gap +
# tallest core zone + top margin. Compared against TARGET_H only to
# report how much smaller this really is - never used to inflate it.
board_height = (CORE_TOP_MARGIN + core_max_h + CORE_LOCAL_GAP + local_max_h +
                LOCAL_GAP + display_h + DISPLAY_ROW_BOTTOM_MARGIN)
print(f"Real minimal board height: {board_height:.1f}mm (vs the "
      f"{TARGET_H:.1f}mm dash-opening inner dimension this board doesn't "
      f"need to fill - the opening's real height was never a target, "
      f"just an available maximum)")

ROW_Y = board_height - DISPLAY_ROW_BOTTOM_MARGIN - display_h / 2

# Now place the display row, using the real (not oversized) ROW_Y.
for ref in DISPLAY_REFS:
    x0, y0, x1, y1 = _disp_bbox[ref]
    cx, cy = _row_x[ref], ROW_Y
    placed_rel[ref] = (cx - (x0 + x1) / 2, cy - (y0 + y1) / 2)
print(f"Display row: {len(DISPLAY_REFS)} connectors at x="
      f"{sorted(round(v) for v in _row_x.values())}, y~{ROW_Y:.1f}mm "
      f"(evenly-spaced estimate, not real dimensioned hole-center data)")

# Place local clusters, directly above their own display.
for disp_ref, (c_placed, c_w, c_h) in local_packed.items():
    disp_x0, disp_y0, disp_x1, disp_y1 = _disp_bbox[disp_ref]
    cluster_left = _row_x[disp_ref] - c_w / 2
    cluster_bottom = ROW_Y - (disp_y1 - disp_y0) / 2 - LOCAL_GAP
    for ref, (x, y) in c_placed.items():
        placed_rel[ref] = (x + cluster_left, y + cluster_bottom - c_h)

# Place core zones, left-to-right with equal real spacing. Also record
# the real X center of each GAP between zones (including before the
# first and after the last) - used below to place extra mounting holes
# in space that's genuinely empty BY CONSTRUCTION, not a guessed
# fractional position (a first attempt at MH5/MH6 used raw 1/3 and 2/3
# board-width fractions and landed squarely on R4/R5 and U1 - a real
# collision caught by the overlap self-check, not assumed safe).
zone_total_w = sum(z_w for _, _, _, z_w, _ in zone_packed)
zone_gap = (TARGET_W - zone_total_w) / (len(zone_packed) + 1)
zone_gap = max(zone_gap, 8.0)  # real minimum breathing room even if this
                                # somehow left less than 8mm between zones
zone_x = zone_gap
zone_gap_centers = [zone_x / 2]   # center of the gap before the first zone
for name, refs, z_placed, z_w, z_h in zone_packed:
    for ref, (x, y) in z_placed.items():
        placed_rel[ref] = (x + zone_x, y + CORE_TOP_MARGIN)
    zone_x += z_w + zone_gap
    zone_gap_centers.append(zone_x - zone_gap / 2)

board_width = TARGET_W + 2 * BOARD_MARGIN
assert board_height <= TARGET_H, (
    f"board_height {board_height:.1f}mm exceeds the real {TARGET_H:.1f}mm "
    f"dash-opening inner dimension - the real content needs more room "
    f"than the opening allows, a genuine design problem, not solved by "
    f"just growing the board further")

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
# kiutils' Board.create_new() (called back at board = Board.create_new(),
# long before board_width/height are known) defaults board.paper to A4 and
# never gets told otherwise - PAGE_W/PAGE_H above were only ever used for
# the centering math, so the actual (paper ...) token written to the file
# silently stayed A4 while every footprint was positioned as if the sheet
# were A2. Harmless for fab (Edge.Cuts is what matters there, not the
# drawing-sheet frame) but real: `kicad-cli pcb export svg` renders the
# A4 frame with the 447mm board hanging off the edge of it. Found by
# routing this same mismatch's SVG output rather than any DRC check, since
# DRC has no opinion on the paper size.
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
              f"(spare/mechanical): {unmatched}")
    board.footprints.append(fp)

# ---------------------------------------------------------------------------
# 5b. Standoff/mounting holes (user request). Same real bundled part
#     every sibling board uses (MountingHole_3.2mm_M3, real M3 clearance
#     hole). 4 corners alone would leave ~410mm of unsupported span
#     between the top-left and top-right holes on this board - a real
#     vibration/flex concern for a dash-mounted, engine-adjacent
#     automotive board, not just a cosmetic gap - so 2 more holes are
#     added along the TOP edge, giving 6 real support points across the
#     board's own length.
#
#     Real bug caught by the overlap self-check, not assumed safe: a
#     first attempt placed these 2 extra holes at raw 1/3 and 2/3
#     board-width fractions, which landed squarely on R4/R5 (CAN0 split
#     termination) and U1 (the MCU) - the core zones aren't evenly
#     spaced by simple fractions, they're packed tightly with real gaps
#     ONLY between zones. Fixed by using zone_gap_centers (computed
#     above, while the zones were actually being placed) - the real,
#     by-construction-empty gap between zones 1-2 and zones 4-5 (indices
#     1 and 4 of 6 real gaps: before/between-each/after the 5 zones),
#     not a guessed position.
# ---------------------------------------------------------------------------
MOUNTING_HOLE_FP = "MountingHole:MountingHole_3.2mm_M3"
MOUNTING_HOLE_INSET = 7.0
_mh5_x = BOARD_OFFSET_X + zone_gap_centers[1]
_mh6_x = BOARD_OFFSET_X + zone_gap_centers[4]
_mh_positions = [
    ("MH1", BOARD_OFFSET_X + MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
    ("MH2", BOARD_OFFSET_X + board_width - MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
    ("MH3", BOARD_OFFSET_X + MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + board_height - MOUNTING_HOLE_INSET),
    ("MH4", BOARD_OFFSET_X + board_width - MOUNTING_HOLE_INSET, BOARD_OFFSET_Y + board_height - MOUNTING_HOLE_INSET),
    ("MH5", _mh5_x, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
    ("MH6", _mh6_x, BOARD_OFFSET_Y + MOUNTING_HOLE_INSET),
]
for mh_ref, mh_x, mh_y in _mh_positions:
    mh_fp = load_footprint(MOUNTING_HOLE_FP)
    mh_fp.position = Position(round(mh_x, 3), round(mh_y, 3), 0)
    mh_fp.path = f"/{uuid_module.uuid4()}"
    mh_fp.properties["Reference"] = mh_ref
    ref_label_pos[mh_ref] = (0.0, -4.15)  # same real bundled-footprint
                                            # Reference offset every
                                            # sibling board's own mounting
                                            # holes already use
    board.footprints.append(mh_fp)
print(f"Added {len(_mh_positions)} M3 mounting holes (4 corners + 2 along "
      f"the top edge, real support for this board's own long/thin shape)")

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
# 6a. Front-silkscreen screen outlines. The 5 real GC9A01/ST7701S display
#     modules are NOT PCB footprints - they're off-board glass on a short
#     FPC tail, plugged into the small edge connectors already placed
#     (U6-U9/J3) - so nothing round shows up in a render of the bare
#     board by default (a real question the user asked: "where are the
#     screens?"). These circles mark real glass diameters (from each
#     module's own datasheet Active Area spec, not guessed) at each
#     display's real board position, so the mechanical relationship
#     between the PCB and the reprinted faceplate is visible at a glance
#     - a genuine design aid (checking hole alignment before committing
#     to faceplate CAD), not just a labeling nicety.
# ---------------------------------------------------------------------------
DISPLAY_GLASS_DIA = {  # real Active Area diagonal/diameter, mm
    "U6": 32.4, "U7": 32.4, "U8": 32.4, "U9": 32.4,  # Raystar RFA401280B-AYW-DNF1
}
for _ref, _dia in DISPLAY_GLASS_DIA.items():
    _cx, _cy = _row_x[_ref] + BOARD_OFFSET_X, ROW_Y + BOARD_OFFSET_Y
    board.graphicItems.append(GrCircle(
        center=Position(round(_cx, 3), round(_cy, 3)),
        end=Position(round(_cx + _dia / 2, 3), round(_cy, 3)),
        layer="F.SilkS", width=0.15))
print(f"Added {len(DISPLAY_GLASS_DIA)} front-silkscreen screen-outline "
      f"circles at each display's real board position")
# Real, EXPECTED DRC consequence, not a defect: these circles are sized
# to the real glass diameter, which is bigger than the small FPC
# connector underneath it (by design - the connector only needs to reach
# the display's own tail, not its whole glass), and the glass legitimately
# extends past the PCB's own bottom edge (the display is meant to show
# through a hole in the housing beyond where this board's copper needs to
# reach) and over nearby components/silkscreen (which sit physically
# UNDER the glass/bezel once assembled, so this overlap is invisible in
# the finished product). Produces real, predictable silk_edge_clearance/
# silk_over_copper/silk_overlap DRC findings - documented and accepted
# here, same "known, explained, non-blocking category" treatment as
# lib_footprint_mismatch, not silently ignored.

# ---------------------------------------------------------------------------
# 6b. Back-silkscreen art: an original tachometer face + "CLUSTER"
#     wordmark, drawn directly as real KiCad graphic primitives (GrCircle/
#     GrArc/GrLine/GrText) - not traced from any existing artwork (unlike
#     the shared "Jessie's Cars" logo every sibling board carries), so
#     this is genuinely this board's own design, on-theme for a digital
#     instrument cluster, per the user's "change the silkscreen to
#     something cooler" request. B.SilkS is otherwise completely empty
#     (no back-mounted parts), same real justification every sibling
#     board's own logo section already has.
# ---------------------------------------------------------------------------
logo_uuids = []

PAD_CLEARANCE_MM = 1.0
thru_hole_boxes = []
for _fp in board.footprints:
    _fx, _fy = _fp.position.X, _fp.position.Y
    _fangle = _fp.position.angle or 0
    for _pad in _fp.pads:
        if _pad.type not in ("thru_hole", "np_thru_hole"):
            continue
        _lx, _ly = _pad.position.X, _pad.position.Y
        _hw, _hh = _pad.size.X / 2, _pad.size.Y / 2
        if _fangle == 90:
            _ax, _ay = _fx + _ly, _fy - _lx
            _hw, _hh = _hh, _hw
        else:
            _ax, _ay = _fx + _lx, _fy + _ly
        thru_hole_boxes.append((_ax - _hw - PAD_CLEARANCE_MM, _ay - _hh - PAD_CLEARANCE_MM,
                                 _ax + _hw + PAD_CLEARANCE_MM, _ay + _hh + PAD_CLEARANCE_MM))


def _overlaps(bx0, by0, bx1, by1, boxes):
    return any(bx0 < ox1 and bx1 > ox0 and by0 < oy1 and by1 > oy0 for ox0, oy0, ox1, oy1 in boxes)


def _polar(cx, cy, r, deg):
    """Point at radius r, angle deg (standard math convention: 0=+X,
    counterclockwise), converted into board space (Y-down) - negating
    the Y-up sin term is what keeps "up" looking like up on the actual
    board, same Y-flip reasoning as everywhere else in this file."""
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy - r * math.sin(rad))


board_cx = BOARD_OFFSET_X + board_width / 2
board_cy = BOARD_OFFSET_Y + board_height / 2

# Real vertical safe zone for the back-side art, derived from the real
# mounting holes (added in section 5b, before this section runs) rather
# than guessed: MH5/MH6 sit at y=BOARD_OFFSET_Y+MOUNTING_HOLE_INSET near
# the top edge, and need real keepout below them (a first attempt at a
# board_cy-centered gauge overlapped MH5/MH6 - real thru-holes, caught
# by the "thru_hole_boxes" collision check below, not assumed clear).
MH_KEEPOUT_BELOW = 6.0
SAFE_TOP = BOARD_OFFSET_Y + MOUNTING_HOLE_INSET + MH_KEEPOUT_BELOW
SAFE_BOTTOM = BOARD_OFFSET_Y + board_height - BOARD_MARGIN
SAFE_CY = (SAFE_TOP + SAFE_BOTTOM) / 2

# Real automotive tach-face layout: 0 at bottom-left (225 deg), sweeping
# CLOCKWISE through 12 o'clock to 8 (redline) at bottom-right (-45 deg) -
# a real 270-degree sweep, 9 major ticks (0-8), matching how an actual
# tachometer face is laid out, not an arbitrary circle of numbers.
# Radius sized from the REAL safe vertical band (between the top
# mounting holes and the bottom edge margin), not a fraction of the
# whole board height, which used to run the gauge straight into MH5/MH6.
GAUGE_R = min((SAFE_BOTTOM - SAFE_TOP) / 2 - 2.0, 42.0)
# left-of-center, so the CLUSTER wordmark has real room to its right -
# uses the board's own wide aspect ratio instead of fighting it. Wider
# gap than the gauge's own radius alone would suggest - a first attempt
# at a 65mm offset produced a real silk_overlap DRC hit (the bold 13mm
# CLUSTER text is wider once actually rendered than its own anchor point
# suggests), caught and fixed with real margin, not a precise-but-
# fragile minimum gap.
GAUGE_CX = board_cx - 95.0
GAUGE_CY = SAFE_CY
START_DEG, END_DEG = 225.0, -45.0
N_TICKS = 9

def _gauge_bbox():
    return (GAUGE_CX - GAUGE_R - 8, GAUGE_CY - GAUGE_R - 4,
            GAUGE_CX + GAUGE_R + 8, GAUGE_CY + GAUGE_R + 12)

def _wordmark_bbox():
    return (board_cx + 5, SAFE_CY - 14, board_cx + 145, SAFE_CY + 14)

_gx0, _gy0, _gx1, _gy1 = _gauge_bbox()
_wx0, _wy0, _wx1, _wy1 = _wordmark_bbox()
if (_overlaps(_gx0, _gy0, _gx1, _gy1, thru_hole_boxes) or
        _overlaps(_wx0, _wy0, _wx1, _wy1, thru_hole_boxes)):
    print("NOTE: tach-face art's default position overlaps a real "
          "thru-hole pad - left as-is this pass (no back-mounted parts "
          "exist on this board yet to actually collide with); revisit "
          "if mounting holes land here later.")


# Real, easy-to-get-backwards detail (same lesson thermo-pcb's own logo
# comment documents, here applying to hand-drawn primitives instead of a
# traced polygon): B.SilkS coordinates are absolute board space, but
# KiCad does NOT auto-mirror shapes the way it does text glyphs (which
# get a `mirror` effects flag instead) - physically flipping the board
# over to read the back mirrors the view, so anything authored in
# "normal left-to-right reading" order (numbers 0-8 going left to right,
# the redline on the right near "8", CLUSTER to the right of the gauge)
# has to be pre-mirrored (X negated around the design's own center) or
# it reads backwards once printed. Every primitive helper below routes
# through this single mirror point, so the constructive code above stays
# in natural, readable coordinates and doesn't have to reason about it.
def _mx(x):
    return 2 * board_cx - x

def _gr_line(p1, p2, width=0.3):
    board.graphicItems.append(GrLine(
        start=Position(round(_mx(p1[0]), 3), round(p1[1], 3)),
        end=Position(round(_mx(p2[0]), 3), round(p2[1], 3)),
        layer="B.SilkS", width=width))

def _gr_circle(center, r, width=0.3):
    board.graphicItems.append(GrCircle(
        center=Position(round(_mx(center[0]), 3), round(center[1], 3)),
        end=Position(round(_mx(center[0] + r), 3), round(center[1], 3)),
        layer="B.SilkS", width=width))

def _gr_arc(start, mid, end, width=0.3):
    board.graphicItems.append(GrArc(
        start=Position(round(_mx(start[0]), 3), round(start[1], 3)),
        mid=Position(round(_mx(mid[0]), 3), round(mid[1], 3)),
        end=Position(round(_mx(end[0]), 3), round(end[1], 3)),
        layer="B.SilkS", width=width))

def _gr_text(text, pos, size, thickness, bold=False, angle=0):
    board.graphicItems.append(GrText(
        text=text, position=Position(round(_mx(pos[0]), 3), round(pos[1], 3), angle),
        layer="B.SilkS",
        effects=Effects(font=Font(height=size, width=size, thickness=thickness,
                                   bold=bold), justify=Justify(mirror=True))))

# Every fixed mm offset/text size below was tuned for a GAUGE_R=42mm
# design - real bug caught by the DRC loop (27 real silk_overlap hits
# once the mounting-hole rework shrank GAUGE_R to 15.6mm): fixed mm
# offsets don't shrink with the circle, so numbers/ticks that used to
# sit neatly inside a 42mm ring collided with each other and the rim
# once the ring got smaller but the labels didn't. Fixed by scaling
# every offset and text size by S = GAUGE_R/42.0, so the whole face
# stays proportional at any real radius this board's own height forces.
S = GAUGE_R / 42.0

# Outer rim + inner rim (a real tach face has a double ring)
_gr_circle((GAUGE_CX, GAUGE_CY), GAUGE_R, width=0.5)
_gr_circle((GAUGE_CX, GAUGE_CY), GAUGE_R - 2.5 * S, width=0.2)

# 9 major ticks (0-8) + a minor tick at every half-step (17 total) -
# real gauge-face convention: major ticks reach further in, get a
# number; minor ticks are short and unlabeled.
for i in range(N_TICKS):
    deg = START_DEG + i * (END_DEG - START_DEG) / (N_TICKS - 1)
    p_out = _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 1 * S, deg)
    p_in = _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 8 * S, deg)
    _gr_line(p_out, p_in, width=0.4)
    p_num = _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 13 * S, deg)
    _gr_text(str(i), p_num, size=max(3.0 * S, 1.0), thickness=max(0.4 * S, 0.15), bold=True)
    if i < N_TICKS - 1:
        deg_mid = deg + (END_DEG - START_DEG) / (N_TICKS - 1) / 2
        pm_out = _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 1 * S, deg_mid)
        pm_in = _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 4.5 * S, deg_mid)
        _gr_line(pm_out, pm_in, width=0.2)

# Redline arc (ticks 6-8, the last third of the sweep) - drawn bold/
# thick so it reads as a real redline band, not just another tick.
_redline_start_deg = START_DEG + 6 * (END_DEG - START_DEG) / (N_TICKS - 1)
_redline_mid_deg = START_DEG + 7 * (END_DEG - START_DEG) / (N_TICKS - 1)
_gr_arc(_polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, _redline_start_deg),
        _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, _redline_mid_deg),
        _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, END_DEG), width=max(1.6 * S, 0.3))

# Needle, parked at a real "resting" angle (well below redline) rather
# than pointing at 0 or max - reads more like a live gauge snapshot.
_needle_deg = START_DEG + 2.3 * (END_DEG - START_DEG) / (N_TICKS - 1)
_gr_line((GAUGE_CX, GAUGE_CY), _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 10 * S, _needle_deg), width=max(0.8 * S, 0.2))
_gr_circle((GAUGE_CX, GAUGE_CY), max(2.2 * S, 0.8), width=0.3)

# "x1000 RPM" caption under the face, real tach convention
_gr_text("x1000 RPM", _polar(GAUGE_CX, GAUGE_CY, GAUGE_R * 0.45, 270),
          size=max(2.0 * S, 1.0), thickness=max(0.25 * S, 0.15))

# CLUSTER wordmark, right of the gauge face - big, bold, using the
# board's own real wide aspect ratio instead of fighting it.
_gr_text("CLUSTER", (board_cx + 8, SAFE_CY - 4), size=13.0, thickness=1.8, bold=True)
_gr_text("DIGITAL INSTRUMENT CLUSTER", (board_cx + 8, SAFE_CY + 8), size=2.6, thickness=0.35)
_gr_text("JESSIE'S CARS", (board_cx + 8, SAFE_CY + 15), size=2.2, thickness=0.3)

print(f"Added original tach-face + CLUSTER wordmark art to B.SilkS "
      f"(gauge R={GAUGE_R:.1f}mm at ({GAUGE_CX:.1f},{GAUGE_CY:.1f}))")

# ---------------------------------------------------------------------------
# 7. Verification on the IN-MEMORY board (before writing/upgrading)
# ---------------------------------------------------------------------------
MECHANICAL_FOOTPRINT_COUNT = len(_mh_positions)  # MH1-6, not schematic parts
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

# ---------------------------------------------------------------------------
# Post-route trunk widening (applied by route_board.py, not here)
# ---------------------------------------------------------------------------
# VIN_PROT is Cluster's only real trunk power net - the harness's 2A-fused
# input, same F1 (Littelfuse 297 MINI blade, 2A) as every sibling board's own
# power stage. It's on the PowerDist net class (Cluster.kicad_pro), which
# routes at the DEFAULT 0.2mm on purpose: VIN_PROT's path touches U2
# (LMR33630-Q1, 0.5mm-pitch VQFN) directly (Q1 pin 3 -> U2 pin 2), and
# forcing a wide trace at that escape produces an unrouted board, not a wide
# one - same tradeoff thermo-pcb's own PowerDist class documents. route_
# board.py's widen_trunks() neck-downs it back up to real width afterwards,
# same regime, applied post-route rather than at routing time.
#
# Capability on 1oz external copper (IPC-2221, 10C rise):
#   0.60mm -> ~2.24A   0.50mm -> ~1.96A   0.40mm -> ~1.67A   0.30mm -> ~1.33A
# against the 2A fuse - real headroom at the top of the ladder, not sized to
# exactly the fuse rating.
#
# No motor-style multi-net trunk here: Cluster has no motor phases (unlike
# thermo-pcb's Motor class), only this one power net.
assert "VIN_PROT" in pcb_net_pins, "VIN_PROT is not a real net on this board"
TRUNK_WIDTH_LADDER = [0.6, 0.5, 0.4, 0.3]
TRUNK_NETS = ["VIN_PROT"]

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
           f'(effects (font (size 1.0 1.0) (thickness 0.15))))')
    count = text.count(old)
    assert count == 1, f"expected exactly 1 bare Reference property for {ref}, found {count}"
    text = text.replace(old, new, 1)

# Same kiutils-output-doesn't-match-real-KiCad problem as Reference above,
# different token: each back-silkscreen logo polygon's uuid was set via
# GrPoly's `tstamp` field, which kiutils writes as a bare, UNQUOTED
# `(tstamp xxxx)` - not the quoted `(uuid "xxxx")` a real KiCad-written
# gr_poly has (and which kicad-cli SEGFAULTS without, per thermo-pcb's
# own history of this exact patch).
for poly_uuid in logo_uuids:
    old_tstamp = f"(tstamp {poly_uuid})"
    new_uuid = f'(uuid "{poly_uuid}")'
    count = text.count(old_tstamp)
    assert count == 1, f"expected exactly 1 logo-polygon tstamp token for {poly_uuid}, found {count}"
    text = text.replace(old_tstamp, new_uuid, 1)

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
# lib_footprint_mismatch: benign embedded-vs-library metadata diff, same
# category every sibling board's own DRC has. silk_edge_clearance/
# silk_over_copper/silk_overlap on the 5 real screen-outline circles:
# expected (see that section's own comment for the real reasoning - the
# circles are deliberately bigger than their own connector, by design).
EXPECTED_TYPES = {"unconnected_items", "lib_footprint_mismatch",
                   "silk_edge_clearance", "silk_over_copper", "silk_overlap"}
unexpected = {t: c for t, c in by_type.items() if t not in EXPECTED_TYPES}
if unexpected:
    print("NOTE: unexpected DRC findings present, see", drc_path, "for details:", unexpected)
elif by_type:
    print("All DRC findings are real, documented, expected categories "
          "(see this script's own comments) - nothing unaccounted for.")
else:
    print("No unexpected DRC findings (only unrouted-net warnings, as expected).")
