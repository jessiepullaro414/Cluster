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
bbox computation, net assignment, overlap/net-count self-checks,
board-outline drawing, the Reference-label bare-property patch, the
real DRC-verify loop) is reused near-verbatim. The skyline bin-packer
itself was generalized here (pack_sized_blocks(), operating on
pre-sized blocks rather than loading footprints per-zone) after this
board's own real layout history (see below) moved away from the
per-zone packing gauges/ still uses.

WHAT IS GENUINELY NEW, not a copy of any sibling board's own layout:
this board has no real fixed target width the way gauges/ does (that
board's width is pinned by 4 real, unmoving dash holes; this board's
real job is just to sit somewhere behind the center opening, and
nothing here dictates its footprint size the way the dash-opening did
for the original 5-connector board). Instead, this board's real shape
is driven by ONE big, unavoidable mechanical fact: the Toradex Verdin
module plugging into the SODIMM-260 socket (U1) and lying flat over a
real keepout zone that nothing else on the board can occupy - Toradex's
own Verdin Carrier Board Design Guide (docs.toradex.com/
108140-verdin-carrier-board-design-guide.pdf), pulled and read directly
(not assumed), Figure 110/111 and Figure 114, confirms: the module's
real PCB outline is 69.60 x 35.00mm (NOT 69.6x47mm - an earlier,
less authoritative web source gave the wrong width, caught by going to
Toradex's own primary document instead of trusting it), and Table 43
confirms the recommended 5.2mm-stack SODIMM connector allows ZERO
component height underneath the module anywhere except right next to
the connector's own edge - "reserving the complete component height to
the module" is Toradex's own stated best practice, not extra caution
added here. So the real keepout is just the module's own real outline
(see MODULE_KEEPOUT_W/H below for the axis-by-axis derivation), not a
padded guess - an earlier pass here used a 60x82mm reservation (down
from an original 90x90mm) justified only by an unconfirmed direction
for the module's own overhang past the connector; that guess is now
replaced with Toradex's own real numbers.

Layout strategy has gone through several real revisions in response to
direct user feedback, each replacing the previous one rather than
patching around it:
  1. Zone blocks aligned into a rigid 2-column grid - rejected: "look
     at all the dead space. parts do not need to be in line."
  2. Zone blocks tight-packed as whole rectangles around the module
     keepout - better, but hit a real floor: board width couldn't
     shrink below the single widest zone's own packed width no matter
     how the zones were arranged, since each was shaped into one rigid
     block before ever being placed.
  3. CURRENT: every individual real component (all 72 real parts,
     CORE_ZONES' own grouping kept only for documentation/bookkeeping,
     not placement) is packed directly into whatever space is actually
     available around the module keepout - a real, deliberate tradeoff
     ("break zone grouping for max density") against keeping a part
     physically close to the rest of its own circuit, chosen because
     the user prioritized density over that locality.
The pack itself is bounded at the module's own real 82mm height (a
genuine fixed constraint - Toradex's own numbers, see above) and grows
in WIDTH only as much as actually needed, then any real leftover height
is used by stretching component spacing to fill it (real board height
that's being paid for either way, better spent as breathing room than
left as one blank band). Board size is DERIVED from what's actually
packed (same "don't inflate past real content" discipline the original
cluster-pcb board's own height-shrink established), with the real
dash-opening hard limit (116.69mm height) checked as a final sanity
ceiling, not a target.
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

def pack_sized_blocks(blocks, max_width, margin, initial_skyline=None, optimize="height"):
    """Real skyline bin-packing algorithm (same technique every sibling
    project's build_pcb.py uses for its own zone/footprint placement,
    generalized here to operate on pre-sized (key, w, h) blocks
    directly rather than loading footprints) - used to pack every real
    individual component on this board into whatever space is actually
    available, rather than pre-grouping them into rigid per-zone
    rectangles first. Real, direct user tradeoff ("break zone grouping
    for max density") after a zone-block approach hit a real floor -
    board width couldn't shrink below the single widest zone's own
    packed width no matter how the zones were arranged, since each zone
    was shaped into one rigid rectangle before ever being placed.

    optimize="width" picks whichever ordering minimizes the packer's
    own "w" (bounded) axis first instead of "h" (grown) axis - useful
    when the caller will stretch the result along "h" afterward
    regardless of what the pack produces (so minimizing that axis here
    would target a dimension that gets thrown away)."""
    def _pack(order_key):
        sized = sorted(blocks, key=order_key, reverse=True)
        skyline = list(initial_skyline) if initial_skyline is not None else [(0.0, max_width, 0.0)]

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
            return segs

        placed = {}
        for key, w, h in sized:
            pos = best_position(w + margin)
            if pos is None:
                raise RuntimeError(f"pack_sized_blocks: {key} ({w:.1f}mm wide) "
                                    f"doesn't fit in max_width={max_width:.1f}mm")
            y, x = pos
            skyline = update_skyline(x, w + margin, y + h + margin)
            placed[key] = (x, y)
        used_w = max((x + w for (x, y), (_, w, h) in zip(placed.values(), sized)), default=0.0)
        used_h = max((y + h for (x, y), (_, w, h) in zip(placed.values(), sized)), default=0.0)
        return placed, used_w, used_h

    strategies = {
        "area-desc": lambda t: t[1] * t[2],
        "height-desc": lambda t: t[2],
        "width-desc": lambda t: t[1],
    }
    best_name, best_result = None, None
    for name, key in strategies.items():
        result = _pack(key)
        _, used_w, used_h = result
        rank = (used_w, used_h) if optimize == "width" else (used_h, used_w)
        if best_result is None:
            best_name, best_result, best_rank = name, result, rank
        elif rank < best_rank:
            best_name, best_result, best_rank = name, result, rank
    print(f"zone grid pack: tried {len(strategies)} orderings, best was "
          f"'{best_name}' ({best_result[1]:.1f}x{best_result[2]:.1f}mm used)")
    return best_result


# Real, not the family's usual 3.0mm: this board's content is packed
# tight to its own real size (no big external constraint leaving slack
# in the corners the way gauges/'s dash-width-driven layout does), so
# BOARD_MARGIN also has to clear the real M3 mounting holes placed at
# MOUNTING_HOLE_INSET (7mm) plus their own real keepout (~3.2mm hole +
# annular ring) - a real M3-vs-U4 corner collision at BOARD_MARGIN=3.0
# is what caught this before it became a first-run fluke.
BOARD_MARGIN = 12.0

# --- Real dash-opening hard limit (same real user-supplied dimension
# every sibling board checks against) - a sanity ceiling here, not a
# target, since this board's own real shape is driven by the module
# keepout + zone content, not the dash width. ---
DASH_OPENING_W = 457.2   # 18.00in
DASH_OPENING_H = 116.69  # 4.594in

# --- U1 (Verdin X1 SODIMM-260 socket) + the real module that plugs
# into it - pulled out of the general packer, real mechanical reason.
# Reserved as a real keepout sized from Toradex's own published
# numbers, not a padded guess (see this file's own header). ---
CONNECTOR_REFS = ["J1"]
_conn_fp = {ref: load_footprint(parts[ref]["footprint"]) for ref in CONNECTOR_REFS}
_conn_bbox = {ref: footprint_bbox(fp) for ref, fp in _conn_fp.items()}
# Real axis-by-axis derivation, both axes now confirmed by Toradex's own
# Verdin Carrier Board Design Guide (Figure 110: module outline
# 69.60 x 35.00mm; Figure 114: carrier board land pattern/connector
# footprint 68.80 x 31.00mm - the module sits centered over the
# connector on both drawings, per the matching "4.00"/"2.00" notch
# offsets shown on both figures):
#   - LENGTH axis: the connector's own real housing (79.0mm, pulled
#     from its bundled KiCad footprint's courtyard - the ejector-latch
#     housing is real and extends past the module's own 69.60mm PCB
#     edge on this axis) is what needs clearing, not the shorter
#     module - already covered by J1's own real footprint placement,
#     so this axis needs only a small assembly margin on top of it.
#   - WIDTH axis: here the MODULE (35.00mm) is the wider of the two
#     (vs. the connector's own ~27.1mm body), overhanging it by
#     (35.00-27.1)/2 ~= 4mm per side if centered - confirmed centered,
#     not assumed, by the matching notch offsets in Toradex's own
#     drawings. This is the one axis that genuinely needs real margin
#     beyond J1's own footprint.
# An earlier pass here used 60x82mm, justified only by an unconfirmed
# guess at a 47mm module width (wrong - see header) and an assumed
# worst-case one-sided overhang; both numbers are replaced with real
# ones now that the real Toradex drawing has actually been read.
MODULE_KEEPOUT_W = 38.0   # 35.00mm real module width + ~3mm real margin
MODULE_KEEPOUT_H = 82.0   # 79.0mm real connector housing length (longer
                          # than the module) + a small real margin

# --- J4 (panel connector) - also pulled out, real mechanical reason:
# it needs to sit toward the board's "front" edge (facing the round
# panel), same as U1/the module, not buried in the middle of a packed
# zone. ---
placed_rel = {}

# --- Everything else: 5 real functional zones, same "keep a real
# relationship short" reasoning as gauges/'s own CORE_ZONES. J4 (the
# panel connector) is folded into CONTROL rather than pulled out into
# its own reserved block - it's an external connector just like
# J8/J9/J10 already in that zone, so packing it there gives it a real,
# sensible neighbor instead of leaving it to float alone with nothing
# around it (a real problem the previous rigid 2-column grid attempt
# then "fixed" by forcing every zone into aligned columns - which
# traded that problem for a worse one: large dead rectangles, per the
# user's own direct correction: "parts do not need to be in line"). ---
CORE_ZONES = [
    ("POWER", ["J2", "F1", "D1", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
               "L1", "Q1", "Q2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
               "R9", "R10", "R11", "R12", "R13", "R14", "R15", "R16", "U1", "U2",
               "C54", "C55", "C56", "C57", "C58", "C59"]),
    ("CAN0_1V8", ["C9", "C10", "C11", "C12", "C13", "J3", "R17", "R18", "R19",
                  "R20", "R21", "U3", "U4"]),
    ("PANEL_BIAS", ["C40", "C41", "C42", "C43", "C44", "C45", "C46", "C47",
                    "C48", "C49", "D2", "D3", "L2", "L3", "R37", "R38", "R39",
                    "R40", "R41", "U6"]),
    ("PANEL_BACKLIGHT", ["C50", "C51", "C52", "D4", "L4", "R42", "U7"]),
    ("CONTROL", ["C39", "J4", "J8", "J9", "J10", "JP1", "JP2", "R43", "R44",
                 "R45", "R46", "R47", "R48", "R49", "R50", "R51", "R52", "R53",
                 "C53", "D5", "Q3", "J11", "R54", "R55", "R56", "R57", "C60",
                 "C61", "C62", "D6", "D7"]),
]

_accounted = set(CONNECTOR_REFS)
for _, refs in CORE_ZONES:
    _accounted.update(refs)
_missing = set(parts.keys()) - _accounted
_extra = _accounted - set(parts.keys())
assert not _missing, f"parts in the schematic but not assigned to any zone: {sorted(_missing)}"
assert not _extra, f"zone refs that don't exist in the schematic: {sorted(_extra)}"

rotated_refs = set()

# --- ONE flat, transposed pack of every individual part, not zone-by-
# zone: real, direct user tradeoff ("break zone grouping for max
# density") after the previous zone-block approach hit a real floor -
# board width couldn't shrink below the single widest zone's own
# packed width (POWER, 85.4mm) no matter how the zones were arranged
# relative to each other, because each zone was pre-shaped into one
# rigid rectangle before ever being placed. Individual components have
# far more real opportunities to nest into each other's gaps than whole
# zones do; CORE_ZONES above still documents the real functional
# grouping (kept for the "every part is accounted for" check and as
# real design documentation), but placement itself no longer respects
# zone boundaries - components from different zones will end up
# interleaved on the board. That's a genuine tradeoff against real
# trace-length/routing locality between a part and the rest of its own
# circuit, made deliberately, not accidentally.
#
# Same transpose reasoning as the zone-block version this replaces:
# bound the pack at the module's own real 82mm height (a genuine fixed
# constraint) and let width grow only as much as actually needed,
# rather than the reverse.
_conn_x0, _conn_y0, _conn_x1, _conn_y1 = _conn_bbox["J1"]

ZONE_GAP = 8.0
_all_refs = [ref for _, refs in CORE_ZONES for ref in refs]
_fp_bbox = {}
_flat_blocks = []
for ref in _all_refs:
    fp = load_footprint(parts[ref]["footprint"])
    x0, y0, x1, y1 = footprint_bbox(fp)
    _fp_bbox[ref] = (x0, y0, x1, y1)
    _flat_blocks.append((ref, x1 - x0, y1 - y0))

_flat_blocks_t = [(ref, h, w) for ref, w, h in _flat_blocks]
_flat_placed_t, _used_h_axis, _used_w_axis = pack_sized_blocks(
    _flat_blocks_t, max_width=MODULE_KEEPOUT_H, margin=MARGIN)

RIGHT_X0 = MODULE_KEEPOUT_W + ZONE_GAP
_targets = {ref: (ty + RIGHT_X0, tx) for ref, (tx, ty) in _flat_placed_t.items()}
packed_w = RIGHT_X0 + _used_w_axis
packed_h = _used_h_axis

# Same real "the module's height is a fixed cost, use it instead of
# leaving it blank" fix as before, now operating on individual real
# component target positions rather than whole zone blocks.
if 0 < packed_h < MODULE_KEEPOUT_H:
    _y_scale = MODULE_KEEPOUT_H / packed_h
    _tight_h = packed_h
    _targets = {ref: (x, y * _y_scale) for ref, (x, y) in _targets.items()}
    packed_h = MODULE_KEEPOUT_H
    print(f"Stretched component spacing to fill the module's real "
          f"{MODULE_KEEPOUT_H:.0f}mm height (was {_tight_h:.1f}mm tight-packed).")

# Convert each part's real target (bbox top-left corner) into its real
# footprint origin (subtract the footprint's own local bbox-min corner
# so that corner, not the footprint's local (0,0), lands on the real
# target position) - this pass doesn't rotate parts, so no rotation
# correction is needed here.
for ref in _all_refs:
    x0, y0, x1, y1 = _fp_bbox[ref]
    tx, ty = _targets[ref]
    placed_rel[ref] = (tx + BOARD_MARGIN - x0, ty + BOARD_MARGIN - y0)

# packed_w already has the module column (RIGHT_X0) baked in, and
# packed_h is already exactly the module's own real height (either from
# the transposed pack's own real cap, or stretched up to it above) -
# both already reflect the real minimum, no separate max() needed.
board_width = packed_w + 2 * BOARD_MARGIN
board_height = packed_h + 2 * BOARD_MARGIN

print(f"Real minimal board size: {board_width:.1f} x {board_height:.1f}mm "
      f"(module keepout {MODULE_KEEPOUT_W:.0f}x{MODULE_KEEPOUT_H:.0f}mm is a "
      f"real fixed obstacle, the 5 zones packed tightly around it - not "
      f"forced into aligned rows/columns, per the user's own correction)")

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

# Place U1 (module keepout) at top-left - the fixed obstacle everything
# else was packed around.
_mod_cx = BOARD_MARGIN + MODULE_KEEPOUT_W / 2
_mod_cy = BOARD_MARGIN + MODULE_KEEPOUT_H / 2
placed_rel["J1"] = (_mod_cx - (_conn_x0 + _conn_x1) / 2, _mod_cy - (_conn_y0 + _conn_y1) / 2)

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
# 6b. Back-silkscreen art: the same original tachometer face + "CLUSTER"
#     wordmark gauges/ carries (itself inherited from the original single-
#     board design, drawn as real KiCad graphic primitives, not traced
#     art) - ported here too so BOTH real boards in this family get the
#     same "cool" treatment rather than leaving this one plain. B.SilkS
#     is otherwise completely empty here (no back-mounted parts), same
#     real justification as gauges/'s own art.
#
#     The board's own real content (module keepout + J4 + all 5 zones)
#     is unified-packed on the FRONT side, so it says nothing about what's
#     safe on the BACK - the only real back-side constraint is thru-hole
#     pads, since THT copper passes through both layers (that's what
#     actually caused the earlier silk_over_copper hit on J9, not
#     proximity to front-side SMD content). So the safe area here is
#     derived from just the real board edges/mounting holes, and gauge +
#     wordmark placement is verified directly against real thru-hole pad
#     boxes below - not inferred from front-side layout geometry.
#
#     A first attempt copied gauges/'s own side-by-side layout (gauge
#     left-of-center, wordmark to its right) verbatim, assuming this
#     board's new wide proportions (204.5x114mm) made it fit the way it
#     fits gauges/'s own long strip. It didn't: real thru-hole boxes
#     printed from a first build showed J1's SODIMM socket carries two
#     real alignment-peg holes around x=137, right where that layout's
#     gauge radius reached back to - not caught by DRC (they're NPTH,
#     unplated, so silk_over_copper doesn't fire on them) but a real
#     mechanical hole poking through a hand-drawn tach face is still
#     wrong. So instead of hand-picking a position, the code below finds
#     the real widest clear vertical corridor spanning the full safe
#     height, by collecting every thru-hole box's real X-span, merging
#     overlaps, and taking the largest gap - then stacks the gauge above
#     the wordmark inside THAT real corridor (this board's dense CAN/
#     power connector cluster on the right leaves less width than
#     gauges/'s own open strip, so stacked reads better here than
#     side-by-side once sized honestly).
# ---------------------------------------------------------------------------
def _polar(cx, cy, r, deg):
    """Point at radius r, angle deg (standard math convention: 0=+X,
    counterclockwise), converted into board space (Y-down)."""
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy - r * math.sin(rad))


board_cx = BOARD_OFFSET_X + board_width / 2
board_cy = BOARD_OFFSET_Y + board_height / 2

# Real thru-hole pad boxes (same technique as gauges/'s own art section):
# every THT/NPTH pad's real absolute position+size on the board, inflated
# by a real clearance margin - used below to verify the art doesn't clip
# real copper, rather than assuming a hand-picked rectangle is clear.
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


# Real safe area avoiding all 4 corner mounting holes (this board's own
# holes sit in every corner, not just the top edge the way gauges/'s
# long/thin board does - so keepout applies on all 4 sides here).
MH_KEEPOUT = 10.0
SAFE_LEFT = BOARD_OFFSET_X + MOUNTING_HOLE_INSET + MH_KEEPOUT
SAFE_RIGHT = BOARD_OFFSET_X + board_width - MOUNTING_HOLE_INSET - MH_KEEPOUT
SAFE_TOP = BOARD_OFFSET_Y + MOUNTING_HOLE_INSET + MH_KEEPOUT
SAFE_BOTTOM = BOARD_OFFSET_Y + board_height - MOUNTING_HOLE_INSET - MH_KEEPOUT
safe_h = SAFE_BOTTOM - SAFE_TOP

# Real widest clear vertical corridor: merge every thru-hole box's X-span
# (for boxes that actually intersect the safe vertical band) and take the
# largest gap between them within [SAFE_LEFT, SAFE_RIGHT] - the real free
# real estate to design into, not a guess.
def _widest_corridor(boxes, left, right, top, bottom):
    spans = sorted((max(x0, left), min(x1, right))
                   for x0, y0, x1, y1 in boxes if y1 > top and y0 < bottom)
    spans = [s for s in spans if s[1] > s[0]]
    merged = []
    for x0, x1 in spans:
        if merged and x0 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], x1))
        else:
            merged.append((x0, x1))
    gaps, prev = [], left
    for x0, x1 in merged:
        if x0 > prev:
            gaps.append((prev, x0))
        prev = max(prev, x1)
    if prev < right:
        gaps.append((prev, right))
    return max(gaps, key=lambda g: g[1] - g[0])


_corr_left, _corr_right = _widest_corridor(thru_hole_boxes, SAFE_LEFT, SAFE_RIGHT,
                                            SAFE_TOP, SAFE_BOTTOM)
_corr_cx = (_corr_left + _corr_right) / 2
_corr_w = _corr_right - _corr_left
print(f"Widest real clear corridor: x={_corr_left:.1f}-{_corr_right:.1f} "
      f"({_corr_w:.1f}mm wide)")

# Gauge on top, wordmark stacked below it, both centered in the real
# corridor - sized from whichever of corridor width / safe height is
# tighter, same proportional-scaling discipline as gauges/'s own art.
#
# The _gr_* drawing helpers below mirror every point across board_cx
# (2*board_cx - x) before writing it, since B.SilkS needs a pre-mirror
# for shapes. GAUGE_CX/word_cx are LOGICAL (pre-mirror) coordinates fed
# to those helpers, so choosing them equal to the real corridor center
# is wrong - it draws the art back at the mirror image of the corridor
# instead (a real first attempt did exactly this and got a genuine
# silk_over_copper hit on a J1 alignment peg at the mirrored location,
# caught by DRC, not by the bbox check below - which was ALSO checking
# the wrong, pre-mirror position). Both the logical coordinates and the
# verification bboxes are computed from the real target (_corr_cx) here
# so they agree with where the art actually lands.
DRAW_CX = _corr_cx
GAUGE_R = min(_corr_w / 2 - 6.0, safe_h * 0.30, 40.0)
GAUGE_CX = 2 * board_cx - DRAW_CX
GAUGE_CY = SAFE_TOP + GAUGE_R + 6.0
START_DEG, END_DEG = 225.0, -45.0
N_TICKS = 9
S = GAUGE_R / 42.0  # same proportional-scaling fix the original board's
                     # own mounting-hole rework established - every
                     # internal offset/text size below scales with the
                     # real radius instead of using fixed mm values that
                     # would collide at a different real size.

_word_cx = GAUGE_CX
_DRAW_WORD_CX = DRAW_CX
_word_w = _corr_w
_word_top = GAUGE_CY + GAUGE_R + 8.0


def _gauge_bbox():
    return (DRAW_CX - GAUGE_R - 4, GAUGE_CY - GAUGE_R - 4,
            DRAW_CX + GAUGE_R + 4, GAUGE_CY + GAUGE_R + 4)


def _wordmark_bbox():
    return (_DRAW_WORD_CX - _word_w / 2, _word_top, _DRAW_WORD_CX + _word_w / 2, SAFE_BOTTOM)


_gx0, _gy0, _gx1, _gy1 = _gauge_bbox()
_wx0, _wy0, _wx1, _wy1 = _wordmark_bbox()
if (_overlaps(_gx0, _gy0, _gx1, _gy1, thru_hole_boxes) or
        _overlaps(_wx0, _wy0, _wx1, _wy1, thru_hole_boxes)):
    print("NOTE: tach-face art's default position overlaps a real "
          "thru-hole pad - revisit placement if this fires.")
else:
    print(f"Verified: gauge+wordmark back-art clears all {len(thru_hole_boxes)} "
          f"real thru-hole pads on the board.")

# Same real "B.SilkS needs a pre-mirror, KiCad doesn't auto-mirror
# shapes" lesson as gauges/'s own art.
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

# Outer rim + inner rim (a real tach face has a double ring)
_gr_circle((GAUGE_CX, GAUGE_CY), GAUGE_R, width=0.5)
_gr_circle((GAUGE_CX, GAUGE_CY), GAUGE_R - 2.5 * S, width=0.2)

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

_redline_start_deg = START_DEG + 6 * (END_DEG - START_DEG) / (N_TICKS - 1)
_redline_mid_deg = START_DEG + 7 * (END_DEG - START_DEG) / (N_TICKS - 1)
_gr_arc(_polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, _redline_start_deg),
        _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, _redline_mid_deg),
        _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 5.5 * S, END_DEG), width=max(1.6 * S, 0.3))

_needle_deg = START_DEG + 2.3 * (END_DEG - START_DEG) / (N_TICKS - 1)
_gr_line((GAUGE_CX, GAUGE_CY), _polar(GAUGE_CX, GAUGE_CY, GAUGE_R - 10 * S, _needle_deg), width=max(0.8 * S, 0.2))
_gr_circle((GAUGE_CX, GAUGE_CY), max(2.2 * S, 0.8), width=0.3)

_gr_text("x1000 RPM", _polar(GAUGE_CX, GAUGE_CY, GAUGE_R * 0.45, 270),
          size=max(2.0 * S, 1.0), thickness=max(0.25 * S, 0.15))

# CLUSTER wordmark, stacked below the gauge in the same real corridor -
# this board's dense right-side connector cluster leaves a tall narrow
# strip rather than gauges/'s own wide open one, so stacking (not
# side-by-side) is what the real obstacle layout actually supports.
_gr_text("CLUSTER", (_word_cx, _word_top + 7.0), size=min(9.0, _word_w * 0.19),
          thickness=1.3, bold=True)
_gr_text("ANDROID DISPLAY CARRIER", (_word_cx, _word_top + 15.5),
          size=2.2, thickness=0.3)
_gr_text("JESSIE'S CARS", (_word_cx, _word_top + 21.0), size=1.9, thickness=0.26)

print(f"Added tach-face + CLUSTER wordmark art to B.SilkS "
      f"(gauge R={GAUGE_R:.1f}mm at ({GAUGE_CX:.1f},{GAUGE_CY:.1f}))")

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

# +12V_PROT is this board's own real trunk power net - the fused/reverse-
# protected input (through F1, a real 5A fuse, + U1's LM74930-Q1 ideal
# diode). Real, not just a backlight rail: it's also VIN1/VIN2 on U2
# (LM61460-Q1, the main +5V buck feeding the whole Verdin module), so it
# genuinely can carry most of this board's real current, not just the
# backlight boost converter's small draw - the ladder below is sized
# toward F1's real 5A rating, not gauges/'s own smaller 2A-fuse ladder.
# It's on the Default net class (this board's ClusterDisplay.kicad_pro
# has no PowerDist pattern of its own yet), which already routes at
# 0.2mm - +12V_PROT's path runs close to fine-pitch parts (U7's 0.5mm-
# pitch SO-8, U2's own VQFN), and forcing a wide trace at that escape
# produces an unrouted board, not a wide one. route_board.py's
# widen_trunks() neck-downs it back up to real width afterwards, as far
# as this board's own tight (105x106mm) real space allows - can_widen()
# simply falls back a rung wherever there isn't room, so listing an
# ambitious top rung costs nothing where it doesn't fit.
#
# Capability on 1oz external copper (IPC-2221, 10C rise; k calibrated so
# 0.6mm matches gauges/'s own already-used 2.24A figure, same formula
# extended to wider rungs rather than a new one invented here):
#   1.50mm -> ~4.35A   1.20mm -> ~3.71A   1.00mm -> ~3.25A  0.80mm -> ~2.76A
#   0.60mm -> ~2.24A   0.50mm -> ~1.96A   0.40mm -> ~1.67A  0.30mm -> ~1.33A
assert "+12V_PROT" in pcb_net_pins, "+12V_PROT is not a real net on this board"
TRUNK_WIDTH_LADDER = [1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3]
TRUNK_NETS = ["+12V_PROT"]

board.to_file(PCB)
print("Wrote", PCB)

text = open(PCB, encoding="utf-8").read()
for ref, (dx, dy) in ref_label_pos.items():
    old = f'(property "Reference" "{ref}")'
    new = (f'(property "Reference" "{ref}" (at {dx} {dy} 0) (layer "F.SilkS") '
           f'(effects (font (size 1.0 1.0) (thickness 0.15))))')
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


def _only_on_solder_jumpers(v):
    """An OPEN solder jumper's F.Mask aperture deliberately spans pads on
    different nets (JP1/JP2, the panel polarity jumpers) so a solder blob
    can bridge them - KiCad's solder_mask_bridge check flags exactly that
    by design. Any such finding NOT on a JP part is still a real problem."""
    if v.get("type") != "solder_mask_bridge":
        return False
    return all(any(f" of {jp} " in it.get("description", "") or
                   f"of {jp} on" in it.get("description", "")
                   for jp in ("JP1", "JP2")) for it in v.get("items", []))


violations = [v for v in violations if not _only_on_solder_jumpers(v)]
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
