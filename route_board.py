"""
Routes Cluster.kicad_pcb with FreeRouting, then adds GND/+3V3 zone
pours on top of the finished routing.

Four steps, each independently verifiable:
  1. Export a Specctra .dsn from the board using KiCad's OWN Python API
     (pcbnew.ExportSpecctraDSN) - the real exporter built into pcbnew, not a
     reimplementation. This runs under KiCad's *bundled* Python interpreter
     (which has the `pcbnew` module), not the Python running this script.
  2. Run FreeRouting headless (java -jar, no GUI) on the .dsn to produce a
     routed .ses session file.
  3. Import that .ses back into the board with KiCad's own
     pcbnew.ImportSpecctraSES and save.
  4. Add GND (In1.Cu) and +3V3 (In2.Cu) zone pours and fill them - done
     AFTER routing, not before, so they're purely additive copper on an
     already-100%-connected-by-traces board rather than something any net's
     connectivity actually depends on (see add_and_fill_zones' own comment
     for why doing this before routing backfired on thermo-pcb, the sibling
     board this script is adapted from).

Requires:
  - tools/freerouting-2.2.4.jar (see README - Java + FreeRouting setup;
    same jar every sibling board uses, copied in rather than re-fetched)
  - KiCad's bundled Python at KICAD_PYTHON below (ships with any KiCad
    install; distinct from the system Python used to run this file)

This does NOT run kicad-cli DRC itself - run run_drc.py afterward to verify
the routed result (clearance, unrouted-net count, etc).
"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "Cluster.kicad_pcb")
DSN = os.path.join(HERE, "Cluster.dsn")
SES = os.path.join(HERE, "Cluster.ses")
FREEROUTING_JAR = os.path.join(HERE, "tools", "freerouting-2.2.4.jar")

KICAD_PYTHON = r"C:\Program Files\KiCad\10.0\bin\python.exe"
JAVA_CANDIDATES = [
    r"C:\Program Files\Eclipse Adoptium\jre-25.0.3.9-hotspot\bin\java.exe",
]

# Autorouter effort: cap passes so a bad/congested board fails fast instead of
# spinning forever, rather than trying to tune "good enough" up front.
# `-oit 0` disables FreeRouting's "stop early if the score hasn't improved
# much in the last 10 passes" behavior, so it keeps trying up to MAX_PASSES
# instead of settling for a plateau - cheap insurance on a small board like
# this one. Same value thermo-pcb settled on after its own U6 (0.5mm-pitch
# VQFN) congestion needed several stochastic restarts to clear; Cluster has
# comparable fine-pitch parts (U1 S32K144 LQFP-64, U2 LMR33630-Q1 VQFN, U11
# BT817AQ QFN-64, all 0.5mm pitch) so the same headroom applies here.
# IMPORTANT: only run this on a FRESH unrouted board (via build_pcb.py) -
# thermo-pcb confirmed re-running route_board.py on a board that already has
# zones filled reliably HANGS FreeRouting indefinitely. If a re-route is
# ever needed, regenerate from build_pcb.py first.
MAX_PASSES = 150
OPTIMIZATION_IMPROVEMENT_THRESHOLD = 0


def find_java():
    import shutil
    exe = shutil.which("java")
    if exe:
        return exe
    for candidate in JAVA_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    raise SystemExit("java not found - see README for the Java + FreeRouting setup")


def run_kicad_python(label, script):
    result = subprocess.run([KICAD_PYTHON, "-c", script], capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"{label} failed (exit {result.returncode})")


def export_dsn():
    if not os.path.isfile(KICAD_PYTHON):
        raise SystemExit(f"KiCad's bundled Python not found at {KICAD_PYTHON}")
    # repr() on every embedded path, not an f-string splice - Windows paths
    # contain sequences like "\Users" that a plain (non-raw) generated string
    # literal misreads as a unicode escape (\U...); repr() escapes correctly
    # no matter where the path lands in the generated script text.
    run_kicad_python("DSN export", f'''
import pcbnew
board = pcbnew.LoadBoard({PCB!r})
ok = pcbnew.ExportSpecctraDSN(board, {DSN!r})
print("DSN export:", "OK" if ok else "FAILED", "->", {DSN!r})
if not ok:
    raise SystemExit(1)
''')


def run_freerouting(quiet=False):
    """Returns the number of connections FreeRouting reported as still
    unrouted (parsed from its own summary line), or None if that line
    couldn't be found."""
    java = find_java()
    if not os.path.isfile(FREEROUTING_JAR):
        raise SystemExit(f"FreeRouting jar not found at {FREEROUTING_JAR} - see README")
    cmd = [java, "-jar", FREEROUTING_JAR, "-de", DSN, "-do", SES,
           "-mp", str(MAX_PASSES), "-oit", str(OPTIMIZATION_IMPROVEMENT_THRESHOLD),
           "--gui.enabled=false"]
    if not quiet:
        print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    # FreeRouting logs to stdout even on success - keep the tail, it's where
    # the final pass/route-completion summary shows up.
    tail = result.stdout.strip().splitlines()[-40:]
    if not quiet:
        print("\n".join(tail))
    if result.returncode != 0:
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        raise SystemExit(f"FreeRouting failed (exit {result.returncode})")
    if not os.path.isfile(SES):
        raise SystemExit("FreeRouting exited OK but did not produce a .ses file")
    # FreeRouting's summary line carries a "(N unrouted)" only when N > 0 - on
    # a fully-routed board it just prints the score and stops. Treating a
    # missing count as "unknown" made every clean run look like a failure and
    # burned all the retries; a completed session with no count IS zero.
    m = None
    for line in result.stdout.splitlines():
        if "session completed" not in line:
            continue
        hit = re.search(r"\((\d+) unrouted\)", line)
        m = int(hit.group(1)) if hit else 0
    return m


# The autorouter is stochastic - it does randomized restarts, and this
# board's 0.5mm-pitch parts (U1, U2, U11, plus the 0.5mm FPC connectors for
# the 5 displays) sit at the edge of what it can solve in one shot, same
# regime thermo-pcb hit with its own 0.5mm-pitch VQFN. Retrying is what
# actually converges: keep the first clean result, and if none of the
# attempts is clean, keep the best one and say so loudly rather than leaving
# a silently-incomplete board behind.
MAX_ROUTE_ATTEMPTS = 6


def route_until_clean():
    best_unrouted, best_ses = None, None
    for attempt in range(1, MAX_ROUTE_ATTEMPTS + 1):
        unrouted = run_freerouting(quiet=(attempt > 1))
        print(f"route attempt {attempt}/{MAX_ROUTE_ATTEMPTS}: "
              f"{unrouted if unrouted is not None else '?'} unrouted")
        if unrouted == 0:
            return 0
        if unrouted is not None and (best_unrouted is None or unrouted < best_unrouted):
            best_unrouted = unrouted
            best_ses = open(SES, encoding="utf-8").read()
    if best_ses is not None:
        open(SES, "w", encoding="utf-8").write(best_ses)
    print(f"WARNING: no fully-routed result in {MAX_ROUTE_ATTEMPTS} attempts - "
          f"keeping the best ({best_unrouted} unrouted). The remaining "
          f"connections need hand-routing in pcbnew before this board is real.")
    return best_unrouted


def import_ses():
    run_kicad_python("SES import", f'''
import pcbnew
board = pcbnew.LoadBoard({PCB!r})
ok = pcbnew.ImportSpecctraSES(board, {SES!r})
print("SES import:", "OK" if ok else "FAILED")
if not ok:
    raise SystemExit(1)
board.Save({PCB!r})
print("Saved routed board to", {PCB!r})
''')


ZONE_INSET_MM = 0.5   # clearance from Edge.Cuts


def add_and_fill_zones():
    # Deliberately done AFTER routing is complete, not before - same lesson
    # thermo-pcb's own history already paid for: adding the GND/+3V3 zone
    # OUTLINES before routing makes FreeRouting's DSN "plane" mechanism treat
    # In1.Cu/In2.Cu as pre-claimed, which (1) makes an already-tight board
    # noticeably harder to fully autoroute, since a solid zone removes a
    # WHOLE layer's normal "just drop a via here" flexibility everywhere, not
    # only where the plane's own net needs it, and (2) can report "100%
    # routed" while a pad is only connected via a plane fill that, once
    # actually computed with real clearance to nearby copper, doesn't quite
    # reach it.
    #
    # Fix: route everything as ordinary traces first, THEN add the zones as
    # purely ADDITIVE copper on top of an already-100%-connected board. Any
    # GND/+3V3 trace or via the zone happens to overlap just becomes
    # redundant (harmless) rather than being the ONLY connection.
    #
    # Solid (not thermal-relief) pad connections: no spoke geometry to fail,
    # and this board isn't hand-soldered at a scale where thermal relief's
    # easier-rework benefit matters more than connection reliability.
    #
    # ONE ZONE PER SUBPROCESS CALL, not both in one script: thermo-pcb
    # confirmed filling two zones on two different layers in the SAME
    # pcbnew process reliably SEGFAULTS on the subsequent board.Save() (one
    # zone at a time, identical settings, never does) - looks like a real
    # threading/state bug in this KiCad build's zone filler under scripting.
    # Two independent load-add-fill-save cycles, each in its own process,
    # sidesteps it entirely: the second cycle loads the file the first cycle
    # already saved (with its zone intact) and adds/fills only the new one.
    for net_name, layer_name in [("GND", "In1_Cu"), ("+3V3", "In2_Cu")]:
        run_kicad_python(f"Add + fill {net_name} zone ({layer_name})", f'''
import pcbnew
board = pcbnew.LoadBoard({PCB!r})
bbox = board.GetBoardEdgesBoundingBox()
inset = pcbnew.FromMM({ZONE_INSET_MM})
x0, y0 = bbox.GetLeft() + inset, bbox.GetTop() + inset
x1, y1 = bbox.GetRight() - inset, bbox.GetBottom() - inset

net = board.FindNet({net_name!r})
if net is None:
    raise SystemExit(f"net {net_name!r} not found on board")
zone = pcbnew.ZONE(board)
zone.SetLayer(pcbnew.{layer_name})
zone.SetNet(net)
zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
zone.SetLocalClearance(pcbnew.FromMM(0.2))
zone.SetMinThickness(pcbnew.FromMM(0.2))
outline = pcbnew.SHAPE_POLY_SET()
outline.NewOutline()
for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
    outline.Append(pcbnew.VECTOR2I(int(x), int(y)))
zone.SetOutline(outline)
board.Add(zone)

filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
board.Save({PCB!r})
print("Added + filled", {net_name!r}, "zone on", {layer_name!r}, "- saved to", {PCB!r})
''')


# ---------------------------------------------------------------------------
# Neck-down: widen VIN_PROT after routing
# ---------------------------------------------------------------------------
# The autorouter has to route VIN_PROT at 0.2mm because that's the PowerDist
# net class's routing width (see build_pcb.py's own comment on that choice) -
# VIN_PROT's path runs straight into U2 (LMR33630-Q1, 0.5mm-pitch VQFN), and
# 0.2mm is what fits between neighbouring pads there at this board's 0.15mm
# clearance. That escape width is fine for the last fraction of a millimetre
# into the pad, and NOT fine for the rest of the run: VIN_PROT sits behind a
# real 2A fuse (F1, Littelfuse 297 MINI blade).
#
# So do what a human hand-routing this would do - keep the escape narrow,
# widen everything past it. A segment is widened only if BOTH endpoints clear
# every other pad/via/track by enough room for the wider trace plus
# clearance; anything touching the escape region keeps its routed width.
# FreeRouting can't express this itself (one width per net class), which is
# the only reason it happens here instead of at routing time.
#
# This is verified, not assumed: run_drc.py afterwards re-checks clearance
# with KiCad's own engine, and any widening that created a real conflict
# shows up there as a clearance violation rather than passing silently.
# Real, not 0.15 (the netclass "clearance" field's own value) - this
# board's own .kicad_pro leaves design_settings.rules.min_clearance
# UNSET like every sibling project's does, so kicad-cli's real DRC
# engine falls back to its own stock 0.2mm board-wide minimum
# regardless of what the netclass field says. Confirmed the hard way on
# gauges/route_board.py's own first real route+widen+zone pass (235
# real clearance violations, every one on a widened VIN_PROT segment,
# all citing "clearance 0.2000mm" as the required value) - this file's
# own 0.15 was the same latent bug, just never exercised since this
# board was superseded before a widened trunk ever got DRC'd against
# real neighboring copper at this density.
TRACK_CLEARANCE = 0.2


def widen_trunks():
    # The ladder and net list live in build_pcb.py so the routing width and
    # the final width are defined next to each other; read them out rather
    # than keeping a second copy here that could drift.
    src = open(os.path.join(HERE, "build_pcb.py"), encoding="utf-8").read()
    ladder_m = re.search(r"^TRUNK_WIDTH_LADDER = (\[.*?\])", src, re.S | re.M)
    nets_m = re.search(r"^TRUNK_NETS = (\[.*?\])", src, re.S | re.M)
    if not (ladder_m and nets_m):
        raise SystemExit("build_pcb.py no longer defines TRUNK_WIDTH_LADDER/TRUNK_NETS")
    ladder = ast.literal_eval(ladder_m.group(1))
    trunk_nets = ast.literal_eval(nets_m.group(1))

    run_kicad_python("Trunk widening", f'''
import math
import pcbnew

LADDER = {ladder!r}
TRUNK_NETS = set({trunk_nets!r})
TRACK_CLEARANCE = {TRACK_CLEARANCE!r}

board = pcbnew.LoadBoard({PCB!r})
MM = pcbnew.ToMM

def seg_point_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def seg_seg_dist(a1, a2, b1, b2):
    # No proper intersection test: two copper segments that genuinely cross
    # are either the same net (fine) or already a DRC error the router
    # wouldn't have produced. Endpoint-to-segment minimum is what matters for
    # the near-miss case this is actually guarding.
    return min(
        seg_point_dist(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1]),
        seg_point_dist(a1[0], a1[1], a2[0], a2[1], b2[0], b2[1]),
        seg_point_dist(b1[0], b1[1], b2[0], b2[1], a1[0], a1[1]),
        seg_point_dist(b1[0], b1[1], b2[0], b2[1], a2[0], a2[1]))

# Build the full obstacle list ONCE: every pad, via and track on the board,
# with the layers it occupies, its net, and a half-extent. This checks
# against everything on the board, not just the fine-pitch parts, because
# what matters is "does this segment, once wider, still clear everything
# around it" - not "is this segment inside a known pad escape region".
pads, vias, tracks = [], [], []
for fp in board.GetFootprints():
    for pad in fp.Pads():
        pos = pad.GetPosition()
        sz = pad.GetSize()
        pads.append((MM(pos.x), MM(pos.y),
                     math.hypot(MM(sz.x), MM(sz.y)) / 2,
                     pad.GetNetCode(), set(pad.GetLayerSet().Seq())))
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        pos = t.GetPosition()
        # GetWidth() with NO layer argument trips a wxWidgets assert inside
        # PCB_VIA in KiCad 10 ("called without a layer argument"). Under
        # kicad-cli's headless python that assert does not raise and does not
        # print - it BLOCKS, forever, with the process sitting at 0% CPU.
        # Always pass the layer (thermo-pcb paid for this finding once).
        vias.append((MM(pos.x), MM(pos.y), MM(t.GetWidth(pcbnew.F_Cu)) / 2,
                     t.GetNetCode(), None))          # None = all layers
    else:
        s, e = t.GetStart(), t.GetEnd()
        tracks.append((t, (MM(s.x), MM(s.y)), (MM(e.x), MM(e.y)),
                       MM(t.GetWidth()) / 2, t.GetNetCode(), t.GetLayer()))
print("obstacles:", len(pads), "pads,", len(vias), "vias,", len(tracks), "tracks")

def can_widen(track, s, e, layer, netcode, target):
    half = target / 2
    for px, py, pr, pnet, players in pads:
        if pnet == netcode or (players is not None and layer not in players):
            continue
        if seg_point_dist(s[0], s[1], e[0], e[1], px, py) < half + pr + TRACK_CLEARANCE:
            return False
    for vx, vy, vr, vnet, _ in vias:
        if vnet == netcode:
            continue
        if seg_point_dist(s[0], s[1], e[0], e[1], vx, vy) < half + vr + TRACK_CLEARANCE:
            return False
    for ot, os_, oe, ohalf, onet, olayer in tracks:
        if onet == netcode or olayer != layer or ot is track:
            continue
        if seg_seg_dist(s, e, os_, oe) < half + ohalf + TRACK_CLEARANCE:
            return False
    return True

# Split trunk traces into short chunks BEFORE deciding widths - the
# difference between neck-down working and not working at all. The router
# emits each trace as a few long segments; testing a whole long segment as
# one unit means a pinch at one end vetoes widening the rest of it. Chunking
# makes the decision local, so the escape stays thin and the run past it
# fattens up.
CHUNK_MM = 0.4
made = 0
for track, s, e, half, netcode, layer in tracks:
    if track.GetNetname() not in TRUNK_NETS:
        continue
    length = math.hypot(e[0] - s[0], e[1] - s[1])
    n = max(1, int(math.ceil(length / CHUNK_MM)))
    if n == 1:
        made += 1
        continue
    for i in range(n):
        t0, t1 = i / n, (i + 1) / n
        a = (s[0] + (e[0] - s[0]) * t0, s[1] + (e[1] - s[1]) * t0)
        b = (s[0] + (e[0] - s[0]) * t1, s[1] + (e[1] - s[1]) * t1)
        nt = pcbnew.PCB_TRACK(board)
        nt.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
        nt.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
        nt.SetWidth(track.GetWidth())
        nt.SetLayer(layer)
        nt.SetNetCode(netcode)
        board.Add(nt)
        made += 1
    board.Remove(track)
print("split trunk traces into", made, "chunks at", CHUNK_MM, "mm")

# The obstacle list still holds the ORIGINAL long segments, which would now
# veto their own replacements. Rebuild it from what is actually on the
# board. Entries are LISTS, not tuples, because a chunk that gets widened
# has to be seen at its NEW width by every chunk tested after it -
# otherwise two neighbouring nets could each widen against the other's
# stale narrow width and end up genuinely too close, with nothing catching
# it until fab. (SWIG's PCB_TRACK is not hashable, so no dict keyed by
# track - the widening loop below just iterates the obstacle entries
# themselves and mutates them in place, which needs no lookup at all.)
tracks = []
trunk_entries = []
for t in board.GetTracks():
    if t.GetClass() == "PCB_VIA":
        continue
    s2, e2 = t.GetStart(), t.GetEnd()
    entry = [t, (MM(s2.x), MM(s2.y)), (MM(e2.x), MM(e2.y)),
             MM(t.GetWidth()) / 2, t.GetNetCode(), t.GetLayer()]
    tracks.append(entry)
    if t.GetNetname() in TRUNK_NETS:
        trunk_entries.append(entry)

hist = {{}}
total_len = {{}}
for entry in trunk_entries:
    track, s, e, half, netcode, layer = entry
    seg_len = math.hypot(e[0] - s[0], e[1] - s[1])
    chosen = half * 2
    for target in LADDER:
        if target <= chosen + 1e-6:
            break
        if can_widen(track, s, e, layer, netcode, target):
            track.SetWidth(pcbnew.FromMM(target))
            entry[3] = target / 2      # keep the obstacle list honest
            chosen = target
            break
    key = round(chosen, 2)
    hist[key] = hist.get(key, 0) + 1
    total_len[key] = total_len.get(key, 0.0) + seg_len

board.Save({PCB!r})
grand = sum(total_len.values()) or 1.0
print("Trunk widening, final width distribution on", sorted(TRUNK_NETS), ":")
for w in sorted(hist, reverse=True):
    print(f"  {{w:.2f}}mm: {{hist[w]:3d}} segments, {{total_len[w]:6.1f}}mm "
          f"({{100 * total_len[w] / grand:4.1f}}% of trunk length)")
''')


if __name__ == "__main__":
    export_dsn()
    route_until_clean()
    import_ses()
    widen_trunks()
    add_and_fill_zones()
    print("\nDone. Run: python run_drc.py")
