"""Dash assembly v2: the three routed boards in a factory-style 1966 housing, with every screen.

Builds the stock five-dial cluster's shape (from the owner's photos): a deep chrome pan lofted
round the trim outline, black side panels, domed chrome bezels and cups, a turned speedometer cup, the housing tub, a stand-in
for the steel dash around the opening, all five screens, the Verdin module and heatsink and the
flat cables, places the three boards from their kicad-cli STEP exports, and checks every pair
of solids for overlap. Writes:

  mech/out/dash_assembly.step   the whole assembly (open in FreeCAD, Fusion, Onshape)
  mech/out/dash_assembly.glb    the same, tessellated, for the web viewer
  mech/out/clearance.json       every clash, the gap under each small screen, the cable reach
  docs/dash-assembly.md         is written by hand from clearance.json

Frame: X to the right as the driver sees it, Y up, Z toward the driver; the origin is the
speedometer centre on the faceplate's front face. Every dimension below names its source;
the ones marked ASSUMED are our own design choices or guesses, not datasheet values.

Run: python mech/build_assembly.py   (after `kicad-cli pcb export step` of each board; the
script does that itself when a STEP is missing or older than its board).
"""
import json
import math
import os
import re
import subprocess
import sys

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Ax3, gp_Pnt, gp_Dir
from OCP.TopLoc import TopLoc_Location

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "review"))
from step_parts import read_parts, bbox  # noqa: E402
from kmodel import Layout  # noqa: E402

KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
BOARDS = {
    "gauges": os.path.join(ROOT, "gauges", "ClusterGauges.kicad_pcb"),
    "panel": os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_pcb"),
    "brain": os.path.join(ROOT, "brain", "ClusterBrain.kicad_pcb"),
}
PCB_T = 1.6

# ---------------------------------------------------------------------------
# Inputs: dash and parts
# ---------------------------------------------------------------------------
DASH_OPENING = (457.2, 116.69)      # owner drawing 2026-09-23 (outer); inner is 441.09 x 105.54
DASH_INNER = (441.09, 105.54)
TRIM = (518.0, 120.0)               # stock chrome trim outline, owner photos 2026-10-08 (+/-5 mm)
# The stock trim (front photo IMG_1697) leans in at both ends toward the bottom; the bottom width is
# ASSUMED from the photo (perspective makes it +/-5 mm), the corner radius too.
TRIM_BOTTOM_W, TRIM_R = 490.0, 30.0
# ASSUMED rim section (side photos IMG_1689/1691: a deep chrome pan with a rolled outer wall): (inset from
# the trim outline, Z) from the dash surface, over a crown 12 mm in front of the panels, down an inner
# wall to the panels 18.5 mm in from the outline.
RIM_PROFILE = [(0.0, -3.0), (0.0, 2.0), (0.8, 6.0), (2.4, 9.2), (4.8, 11.3), (7.5, 12.0), (10.0, 11.6),
               (12.2, 10.0), (14.2, 7.2), (16.2, 3.8), (17.8, 1.0), (18.5, 0.0)]
RIM_FOOT = RIM_PROFILE[-1][0]
GAUGE_RING = (58.0, 48.0, 4.0)       # small chrome bezels: OD, opening, dome height (stock about 61 / 47-50, photos and calipers)
CUP_OD = 54.0                        # ASSUMED: black cup round the 50.2 mm lens
INDICATOR = (13.0, 5.5, 29.0)        # turn windows: w, h, height above the small-gauge centres (photo IMG_1697)
POD_FRONT = 22.0                     # ASSUMED: speedometer pod lip, like the stock proud cup (stock 36 mm deep)
POD_THROAT_TOP = 58.0                # ASSUMED: the black throat flares from the 104 mm glass edge to 116 mm at the lip

FACE_T = 3.0                        # ASSUMED: printed or machined side-panel thickness
CENTRE_WINDOW = 103.5               # mechanical-fit.md: 102.5-104.5, nominal 103.5
POD_OD = 127.0                      # owner limit: 5 in across including the bezel (2026-10-08)

# TSD TST040HDBC-42 outline (datasheet V1.0 p4, mechanical-fit.md)
TSD_BODY_D, TSD_GLASS_D, TSD_T = 110.0, 105.0, 7.8
TSD_TAB_REACH = 113.49 - 55.0       # FPC side reaches 58.49 mm from the centre
TSD_TAB_W = 40.0                    # ASSUMED: tab width (not dimensioned in the notes)
TSD_FPC_LEN, TSD_FPC_W = 69.8, 30.0  # length from the datasheet; width ASSUMED

# Raystar RFA401280B-AYW-DNF1 contour drawing (software/refs/raystar/rfa.pdf p5)
RFA_LENS_D, RFA_LENS_T = 50.20, 2.0   # cover lens, "Lens T:2.0mm"
RFA_BODY_D = 37.74                    # backlight OD
RFA_T = 3.99                          # whole module
RFA_TOP_TO_TAIL = 65.04               # lens top edge to the FPC end
RFA_BOND_R = 37.74 / 2 + 2.76         # FPC bonding edge, (2.76) below the backlight edge
RFA_FPC_W = 9.5
RFA_FPC_FREE = RFA_TOP_TO_TAIL - RFA_LENS_D / 2 - RFA_BOND_R   # about 18.3 mm of free tail
F32Q_BODY = 4.5                       # Amphenol F32Q body depth, cable entry to back (KiCad footprint F.Fab)
F32Q_MIN_INSERT = 3.0                 # ASSUMED: seated when the tail is 3 mm past the entry edge

# Verdin module, socket and heatsink (Toradex Carrier Board Design Guide V1.2, mechanical-stackup.md)
VERDIN_L, VERDIN_W, VERDIN_T = 69.6, 31.0, 1.2
VERDIN_GAP = 2.62                     # carrier top to module bottom, nominal
VERDIN_TOP_PARTS = 2.4                # ASSUMED: tallest part on the module top side
HEATSINK_BASE_Z, HEATSINK_BASE_T, HEATSINK_FIN_H = 7.0, 3.0, 9.0   # base on the 7.0 mm standoffs; fins ASSUMED
SOCKET_H, SOCKET_D, SOCKET_L = 5.2, 6.0, 79.0                       # ASSUMED stand-in for the missing socket model

# ---------------------------------------------------------------------------
# Our stack-up (ASSUMED: the design this file proposes; change here and re-run)
# ---------------------------------------------------------------------------
Z_FACE_BACK = -FACE_T                # the faceplate sits on the dash surface
SCREEN_HOLDER_H = 4.0                # small screens: module back this far off the board (they hang from their cups)
Z_GAUGES_FRONT = -17.8               # gauges/ component side; J1 (13.8 mm) stops 1 mm short of the faceplate
Z_SMALL_BACK = Z_GAUGES_FRONT + SCREEN_HOLDER_H
Z_SMALL_FRONT = Z_SMALL_BACK + RFA_T
Z_TSD_BACK = 1.0                     # the centre panel sits in the pod, 1 mm off the faceplate so its FPC folds under the tab
Z_PANEL_BARE = Z_GAUGES_FRONT - PCB_T - 3.0     # panel-tsd/ hangs below and behind gauges/, parts to the rear
PANEL_Y = -25.0                      # panel-tsd/ centre height, set so the 69.8 mm FPC reaches J4
Z_BRAIN_BARE = Z_PANEL_BARE - PCB_T - 7.0      # brain/ behind it, parts (module, heatsink) to the rear
TUB_OUT = (456.6, 115.5)             # passes the 457.2 x 116.69 opening, 0.3 mm a side across the car
TUB_WALL, TUB_BACK_Z = 1.2, -56.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ensure_step(name, pcb):
    step = os.path.join(OUT, os.path.splitext(os.path.basename(pcb))[0] + ".step")
    if not os.path.exists(step) or os.path.getmtime(step) < os.path.getmtime(pcb):
        os.makedirs(OUT, exist_ok=True)
        subprocess.run([KICAD_CLI, "pcb", "export", "step", "--subst-models", "--no-dnp", "-f",
                        "-o", step, pcb], check=True, capture_output=True)
    return step


def trsf_board(centre_kicad, origin, z_ref, flip):
    """KiCad STEP coords -> assembly. flip=False: component side faces the driver, its surface at z_ref.
    flip=True: turned 180 deg about X (parts to the rear, board upside down), bare side at z_ref."""
    kx, ky = centre_kicad
    t = gp_Trsf()
    if not flip:
        t.SetTranslation(gp_Vec(origin[0] - kx, origin[1] + ky, z_ref - PCB_T))
        return t
    r = gp_Trsf()
    r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.pi)      # (x, y, z) -> (x, -y, -z)
    m = gp_Trsf()
    m.SetTranslation(gp_Vec(origin[0] - kx, origin[1] - ky, z_ref))       # STEP y = -ky, so -y = ky
    m.Multiply(r)
    return m


def moved(shape, t):
    return shape.Moved(TopLoc_Location(t))


def kpt(t, kx, ky, kz):
    """A point given in KiCad board coordinates (z above the board top) -> assembly coordinates."""
    p = gp_Pnt(kx, -ky, PCB_T + kz).Transformed(t)
    return p.X(), p.Y(), p.Z()


def volume(shape):
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    return g.Mass()


def boxes_overlap(a, b, pad=0.0):
    return not (a[3] + pad < b[0] or b[3] + pad < a[0] or a[4] + pad < b[1] or b[4] + pad < a[1]
                or a[5] + pad < b[2] or b[5] + pad < a[2])


def rrect(w, h, r, t, z0):
    return cq.Workplane("XY").workplane(offset=z0).rect(w, h).extrude(t).edges("|Z").fillet(r)


def cyl(d, z0, z1, x=0.0, y=0.0):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(z1 - z0)


def ring(od, idd, z0, z1, x=0.0, y=0.0):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(od / 2).circle(idd / 2).extrude(z1 - z0)


def strip(points, width, th=0.15):
    """A flat cable: a thin ribbon along a polyline of (x, y, z) points (or (y, z) at x = 0), its
    width kept as close to the X axis as the run allows (folds are drawn as straight joints)."""
    pts = [p if len(p) == 3 else (0.0, p[0], p[1]) for p in points]
    out = None
    for p, q in zip(pts, pts[1:]):
        d = [q[i] - p[i] for i in range(3)]
        L = math.sqrt(sum(c * c for c in d))
        if L < 1e-6:
            continue
        u = [c / L for c in d]
        w = [1 - u[0] * u[0], -u[0] * u[1], -u[0] * u[2]]
        wn = math.sqrt(sum(c * c for c in w))
        w = [c / wn for c in w]
        n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]   # u x w
        box = cq.Solid.makeBox(width, L, th, pnt=cq.Vector(-width / 2, 0, -th / 2))
        t = gp_Trsf()
        t.SetTransformation(gp_Ax3(gp_Pnt(*p), gp_Dir(*[-c for c in n]), gp_Dir(*w)))
        seg = cq.Workplane("XY").add(cq.Shape.cast(box.wrapped.Moved(TopLoc_Location(t.Inverted()))))
        out = seg if out is None else out.union(seg)
    return out


def path_len(points):
    pts = [p if len(p) == 3 else (0.0, p[0], p[1]) for p in points]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def band_height(board, x0, x1, y0, y1):
    """How far the parts of `board` stand off its component side inside an assembly X/Y window."""
    surf = {"gauges": Z_GAUGES_FRONT, "panel": Z_PANEL_BARE - PCB_T, "brain": Z_BRAIN_BARE - PCB_T}[board]
    h = 0.0
    for d in solids:
        if d["board"] != board or d["name"].endswith(":board"):
            continue
        b = bbox(d["shape"])
        if b[3] < min(x0, x1) or b[0] > max(x0, x1) or b[4] < min(y0, y1) or b[1] > max(y0, y1):
            continue
        h = max(h, (b[5] - surf) if board == "gauges" else (surf - b[2]))
    return h


# ---------------------------------------------------------------------------
# 1. Boards
# ---------------------------------------------------------------------------
lay = {k: Layout(v) for k, v in BOARDS.items()}
centre = {}
for k, L in lay.items():
    x0, y0, x1, y1 = L.board_bbox()
    centre[k] = ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)

# Small-screen centres: gauges/ marks each one with a 32.4 mm F.SilkS circle (build_pcb.py, SCREEN_Y).
_circles = sorted((float(a), float(b)) for a, b in re.findall(
    r"\(gr_circle\s+\(center ([\d.]+) ([\d.]+)\)\s+\(end [\d.]+ [\d.]+\)\s+\(stroke\s+\(width [\d.]+\)\s+\(type \w+\)\s+\)"
    r"\s+\(fill no\)\s+\(layer \"F.SilkS\"\)", open(BOARDS["gauges"], encoding="utf-8").read()))
assert len(_circles) == 4, _circles
SCREEN_REFS = ["U6", "U7", "U8", "U9"]                                    # left to right
g_row_x = (_circles[1][0] + _circles[2][0]) / 2                           # speedometer centre on gauges/
g_row_y = _circles[0][1]
GAUGE_X = {r: round(c[0] - g_row_x, 2) for r, c in zip(SCREEN_REFS, _circles)}
T = {
    "gauges": trsf_board((g_row_x, g_row_y), (0, 0), Z_GAUGES_FRONT, False),
    "panel": trsf_board(centre["panel"][:2], (0, PANEL_Y), Z_PANEL_BARE, True),
    "brain": trsf_board(centre["brain"][:2], (0, 0), Z_BRAIN_BARE, True),
}

COLOR_PREFIX = [("J", (0.92, 0.92, 0.88)), ("U", (0.08, 0.08, 0.09)), ("Q", (0.08, 0.08, 0.09)),
                ("D", (0.12, 0.12, 0.12)), ("L", (0.25, 0.25, 0.27)), ("F", (0.95, 0.75, 0.15)),
                ("C", (0.62, 0.48, 0.32)), ("R", (0.15, 0.15, 0.15)), ("X", (0.7, 0.7, 0.7)),
                ("Y", (0.75, 0.75, 0.78)), ("BT", (0.8, 0.8, 0.82)), ("SW", (0.2, 0.2, 0.2))]
PCB_COLOR = (0.10, 0.36, 0.20)

solids = []          # dict(name, group, shape, color, board)


def add(name, group, shape, color, board=None, alpha=1.0):
    s = shape.val().wrapped if isinstance(shape, cq.Workplane) else shape
    solids.append(dict(name=name, group=group, shape=s, color=color, board=board, alpha=alpha))


for k, pcb in BOARDS.items():
    step = ensure_step(k, pcb)
    for n, s in read_parts(step):
        s = moved(s, T[k])
        if n.startswith("=>") or not n:
            add(f"{k}:board", k, s, PCB_COLOR, board=k)
            continue
        col = next((c for p, c in COLOR_PREFIX if n.startswith(p)), (0.4, 0.4, 0.4))
        add(f"{k}:{n}", k, s, col, board=k)

# Stand-ins for footprints whose 3D model is missing from the KiCad library (heights from the
# part datasheets where known; footprint = pad extent + 0.5 mm).
MISSING_H = {("gauges", "U6"): 2.0, ("gauges", "U7"): 2.0, ("gauges", "U8"): 2.0, ("gauges", "U9"): 2.0}
have = {d["name"] for d in solids}
for k, L in lay.items():
    for ref in L.fp:
        if f"{k}:{ref}" in have or ref.startswith(("MH", "S", "H", "TP", "JP", "G")):
            continue
        pads = [p[0] for (r, _), p in L.pads.items() if r == ref]
        if not pads:
            continue
        h = MISSING_H.get((k, ref), 1.2 if not ref.startswith("J") else 2.0)
        if k == "brain" and ref == "J1":
            continue                      # SODIMM socket: modelled with the module below
        xs = [p["x"] for p in pads]
        ys = [p["y"] for p in pads]
        a = kpt(T[k], min(xs) - 0.5, min(ys) - 0.5, 0)
        b = kpt(T[k], max(xs) + 0.5, max(ys) + 0.5, h)
        lo = [min(a[i], b[i]) for i in range(3)]
        hi = [max(a[i], b[i]) for i in range(3)]
        box = cq.Workplane("XY").box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], centered=False).translate(tuple(lo))
        add(f"{k}:{ref}", k, box, (0.85, 0.3, 0.85), board=k)       # magenta = stand-in

# Verdin socket, module, heatsink in brain/ board coordinates
bx = lay["brain"].fp
s1, s2, s3, s4 = (bx[r][:2] for r in ("S1", "S2", "S3", "S4"))
mod_x0, mod_x1 = (s3[0] + s4[0]) / 2 - VERDIN_L / 2, (s3[0] + s4[0]) / 2 + VERDIN_L / 2
mod_y_edge = lay["brain"].fp["J1"][1]                 # socket line (the module's gold fingers)
mod_y_far = mod_y_edge - VERDIN_W


def brain_box(kx0, ky0, kx1, ky1, kz0, kz1):
    a = kpt(T["brain"], kx0, ky0, kz0)
    b = kpt(T["brain"], kx1, ky1, kz1)
    lo = [min(a[i], b[i]) for i in range(3)]
    hi = [max(a[i], b[i]) for i in range(3)]
    return cq.Workplane("XY").box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], centered=False).translate(tuple(lo))


add("brain:J1 SODIMM socket (stand-in)", "verdin", brain_box(bx["J1"][0] - SOCKET_L / 2, mod_y_edge - 1.0,
                                                             bx["J1"][0] + SOCKET_L / 2, mod_y_edge + SOCKET_D - 1.0, 0, SOCKET_H),
    (0.15, 0.15, 0.15))
add("Verdin iMX95 module", "verdin", brain_box(mod_x0, mod_y_far, mod_x1, mod_y_edge, VERDIN_GAP, VERDIN_GAP + VERDIN_T),
    (0.05, 0.3, 0.15))
add("Verdin module parts (ASSUMED 2.4 mm)", "verdin",
    brain_box(mod_x0 + 4, mod_y_far + 2, mod_x1 - 8, mod_y_edge - 3, VERDIN_GAP + VERDIN_T, VERDIN_GAP + VERDIN_T + VERDIN_TOP_PARTS),
    (0.1, 0.1, 0.1))
add("Verdin heatsink base", "verdin", brain_box(mod_x0, mod_y_far, mod_x1, mod_y_edge, HEATSINK_BASE_Z, HEATSINK_BASE_Z + HEATSINK_BASE_T),
    (0.75, 0.76, 0.8))
for i in range(12):
    fx = mod_x0 + 2 + i * (VERDIN_L - 4) / 11
    add(f"Verdin heatsink fin {i + 1} (ASSUMED height)", "verdin",
        brain_box(fx - 0.6, mod_y_far, fx + 0.6, mod_y_edge, HEATSINK_BASE_Z + HEATSINK_BASE_T,
                  HEATSINK_BASE_Z + HEATSINK_BASE_T + HEATSINK_FIN_H), (0.75, 0.76, 0.8))

# ---------------------------------------------------------------------------
# 2. Housing: faceplate, bezels, cups, pod, tub, dash
# ---------------------------------------------------------------------------
CHROME = (0.86, 0.87, 0.9)
BLACK = (0.07, 0.07, 0.08)
GRAIN = (0.10, 0.10, 0.11)           # the stock panels are black grained vinyl-look


def trim_wire(inset, z):
    """The stock trim outline (wider at the top, ends leaning in), shrunk by `inset`, as a wire at height z."""
    hwt, hwb, hh = TRIM[0] / 2 - inset, TRIM_BOTTOM_W / 2 - inset, TRIM[1] / 2 - inset
    w = cq.Wire.makePolygon([cq.Vector(-hwt, hh, z), cq.Vector(hwt, hh, z), cq.Vector(hwb, -hh, z),
                             cq.Vector(-hwb, -hh, z)], close=True)
    return w.fillet2D(max(TRIM_R - inset, 3.0), w.Vertices())


def trim_shape(inset, z0, t):
    return cq.Workplane("XY").add(cq.Solid.extrudeLinear(cq.Face.makeFromWires(trim_wire(inset, z0)), cq.Vector(0, 0, t)))


def turned(pts, x=0.0):
    """A part turned about the Z axis from an (r, z) section, centred at (x, 0)."""
    return cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0)).translate((x, 0, 0))


def dome(r_in, r_out, z0, h, n=16):
    """(r, z) points over a rolled half-round lip from r_out to r_in, its base at z0."""
    rc, a = (r_in + r_out) / 2, (r_out - r_in) / 2
    return [(rc + a * math.cos(math.pi * i / n), z0 + h * math.sin(math.pi * i / n)) for i in range(n + 1)]


# Chrome rim: a deep pan round the whole cluster, lofted through the rim section at every inset, then
# opened in the middle (the panels) and where the speedometer pod passes through it top and bottom.
rim = cq.Workplane("XY").add(cq.Solid.makeLoft([trim_wire(d, z) for d, z in RIM_PROFILE], False))
rim = rim.cut(trim_shape(RIM_FOOT, Z_FACE_BACK - 1, FACE_T + 2)).cut(cyl(POD_OD + 1.0, Z_FACE_BACK - 1, RIM_PROFILE[5][1] + 2))
add("chrome trim rim", "housing", rim, CHROME)

# Black grained side panels (one plate behind the pod), with the gauge, indicator and FPC openings.
face = trim_shape(RIM_FOOT - 0.3, Z_FACE_BACK, FACE_T)
for x in GAUGE_X.values():
    face = face.cut(cyl(GAUGE_RING[1], Z_FACE_BACK - 1, 1, x))
IND_X = [(GAUGE_X["U6"] + GAUGE_X["U7"]) / 2, (GAUGE_X["U8"] + GAUGE_X["U9"]) / 2]
for x in IND_X:
    face = face.cut(cq.Workplane("XY").workplane(offset=Z_FACE_BACK - 1).center(x, INDICATOR[2])
                    .rect(INDICATOR[0], INDICATOR[1]).extrude(FACE_T + 2))
face = face.cut(cq.Workplane("XY").workplane(offset=Z_FACE_BACK - 1)
                .center(0, -55.3).rect(TSD_FPC_W + 4, 3.5).extrude(FACE_T + 2))   # panel FPC slot, under the pod
add("side panels, black grain (ASSUMED 3 mm)", "housing", face, GRAIN)

# The thin chrome bead that follows each side panel's edge on the stock cluster, closed beside the pod.
for side in (-1, 1):
    x_in = POD_OD / 2 + 6.0
    keep = cq.Workplane("XY").workplane(offset=-1).center(side * 200, 0).rect(400 - 2 * x_in, 200).extrude(3)
    hole = cq.Workplane("XY").workplane(offset=-1).center(side * 201.2, 0).rect(400 - 2 * x_in - 2.4, 200).extrude(3)
    bead = trim_shape(RIM_FOOT + 2.2, 0, 0.8).intersect(keep).cut(trim_shape(RIM_FOOT + 3.4, -0.5, 2).intersect(hole))
    add(f"chrome panel bead {'left' if side < 0 else 'right'}", "housing", bead, CHROME)

for ref, x in GAUGE_X.items():
    r_in, r_out = GAUGE_RING[1] / 2, GAUGE_RING[0] / 2
    add(f"chrome gauge ring {ref}", "housing",
        turned([(r_in, 0.0), (r_out, 0.0)] + dome(r_in, r_out, 0.6, GAUGE_RING[2] - 0.6), x), CHROME)
    # The cup carries its screen, like the stock gauges hang from the cluster face: the lens sits against
    # the cup's end, a sleeve round it and a clip lip behind its rim (outside the 37.74 mm backlight).
    z_clip = Z_SMALL_FRONT - RFA_LENS_T - 0.8
    cup = (ring(CUP_OD, GAUGE_RING[1], Z_SMALL_FRONT, Z_FACE_BACK, x)
           .union(ring(CUP_OD, RFA_LENS_D + 0.4, Z_SMALL_FRONT - RFA_LENS_T, Z_SMALL_FRONT, x))
           .union(ring(CUP_OD, RFA_BODY_D + 3.0, z_clip, Z_SMALL_FRONT - RFA_LENS_T, x)))
    add(f"gauge cup {ref} (carries the screen)", "housing", cup, BLACK)
for i, x in enumerate(IND_X):
    side = "left" if i == 0 else "right"
    frame = (cq.Workplane("XY").center(x, INDICATOR[2]).rect(INDICATOR[0] + 2.4, INDICATOR[1] + 2.4).extrude(1.0)
             .cut(cq.Workplane("XY").workplane(offset=-0.5).center(x, INDICATOR[2]).rect(*INDICATOR[:2]).extrude(2.0)))
    add(f"chrome indicator frame {side}", "housing", frame, CHROME)
    add(f"turn lens {side}", "housing",
        cq.Workplane("XY").workplane(offset=-1.5).center(x, INDICATOR[2]).rect(*INDICATOR[:2]).extrude(1.4), (0.15, 0.75, 0.3))
    # Light pipe from the turn LED (gauges/ D26, D27) up to the back of the lens.
    led = lay["gauges"].fp["D26" if i == 0 else "D27"]
    lx, ly, _ = kpt(T["gauges"], led[0], led[1], 0)
    col = [d["bb"][5] if "bb" in d else bbox(d["shape"])[5] for d in solids
           if d["name"] in {f"gauges:{r}" for r in (("D26", "D24", "R82") if i == 0 else ("D27", "D25", "R83"))}]
    z0 = max(col) + 0.3
    add(f"turn light pipe {side} (ASSUMED 2.5 mm square)", "housing",
        cq.Workplane("XY").workplane(offset=z0).center(lx, ly).rect(2.5, 2.5).extrude(-1.5 - z0), (0.8, 0.95, 0.85), alpha=0.6)

# Speedometer pod: a turned chrome cup standing proud of the panels and through the rim top and bottom,
# a rolled lip, and a black throat that flares from the TSD glass to the lip (stock: a deep cup).
Z_GLASS = Z_TSD_BACK + TSD_T
z_lip = POD_FRONT - 2.5
POD_SECTION = ([(POD_OD / 2 - 3.0, 0.0), (POD_OD / 2, 0.0), (POD_OD / 2, z_lip - 6.0), (POD_OD / 2 - 0.2, z_lip)]
               + dome(POD_THROAT_TOP - 0.1, POD_OD / 2 - 0.2, z_lip, 2.5)[1:] + [(POD_OD / 2 - 3.0, z_lip)])
add("centre pod barrel", "housing", turned(POD_SECTION)
    .cut(cq.Workplane("XY").workplane(offset=-1).center(0, -60).rect(TSD_TAB_W + 2, 12).extrude(Z_TSD_BACK + 1.5 + 1.5)), CHROME)
THROAT = [(TSD_GLASS_D / 2 - 0.5, Z_GLASS), (POD_OD / 2 - 3.0, Z_GLASS), (POD_OD / 2 - 3.0, z_lip), (POD_THROAT_TOP, z_lip)]
add("centre pod throat", "housing", turned(THROAT), BLACK)


def hood_angle(r_active, z_glass, section):
    """How far off-axis the far edge of the active area stays in view past a turned hood's (r, z) section."""
    return round(min(math.degrees(math.atan2(r - r_active, z - z_glass)) for r, z in section if z > z_glass + 0.1), 1)


view_angle = dict(speedometer=hood_angle(101.52 / 2, Z_GLASS, THROAT + POD_SECTION),
                  small=hood_angle(32.4 / 2, Z_SMALL_FRONT, [(GAUGE_RING[1] / 2, GAUGE_RING[2]), (GAUGE_RING[1] / 2, 0.0)]))

tub_outer = rrect(TUB_OUT[0], TUB_OUT[1], 4, Z_FACE_BACK - TUB_BACK_Z, TUB_BACK_Z)
tub_inner = rrect(TUB_OUT[0] - 2 * TUB_WALL, TUB_OUT[1] - 2 * TUB_WALL, 3, Z_FACE_BACK - TUB_BACK_Z - 2.0, TUB_BACK_Z + 2.0)
tub = tub_outer.cut(tub_inner)
for vx in range(-60, 61, 8):                                   # vents behind the heatsink
    tub = tub.cut(cq.Workplane("XY").workplane(offset=TUB_BACK_Z - 1).center(vx, -5).rect(3, 40).extrude(4))
add("housing tub (ASSUMED 1.5 mm walls)", "housing", tub, (0.18, 0.18, 0.2), alpha=0.35)

dash = (cq.Workplane("XY").workplane(offset=Z_FACE_BACK - 1.2).rect(680, 240).extrude(1.2)
        .cut(cq.Workplane("XY").workplane(offset=Z_FACE_BACK - 2).rect(*DASH_OPENING).extrude(3)))
add("dash panel around the opening (reference)", "dash", dash, (0.42, 0.06, 0.07), alpha=0.25)

# ---------------------------------------------------------------------------
# 3. Screens
# ---------------------------------------------------------------------------
add("TSD TST040HDBC-42 body", "screens", cyl(TSD_BODY_D, Z_TSD_BACK, Z_TSD_BACK + TSD_T - 1.0), (0.2, 0.2, 0.22))
add("TSD tab", "screens", cq.Workplane("XY").workplane(offset=Z_TSD_BACK).center(0, -(TSD_TAB_REACH + 50) / 2)
    .rect(TSD_TAB_W, TSD_TAB_REACH - 50).extrude(1.5), (0.2, 0.2, 0.22))
add("TSD glass (101.52 active)", "screens", cyl(TSD_GLASS_D, Z_TSD_BACK + TSD_T - 1.0, Z_TSD_BACK + TSD_T), (0.02, 0.03, 0.06))

for ref, x in GAUGE_X.items():
    add(f"Raystar {ref} lens", "screens", cyl(RFA_LENS_D, Z_SMALL_FRONT - RFA_LENS_T, Z_SMALL_FRONT, x), (0.02, 0.03, 0.06))
    add(f"Raystar {ref} LCD + backlight", "screens", cyl(RFA_BODY_D, Z_SMALL_BACK, Z_SMALL_FRONT - RFA_LENS_T, x), (0.3, 0.3, 0.32))

# Small-screen FPC, folded under the module toward its connector, at its real length.
fpc_report = {}
for ref, x in GAUGE_X.items():
    conn_y = -(lay["gauges"].fp[ref][1] - g_row_y)                     # connector origin (body centre), assembly Y
    entry_y = conn_y - F32Q_BODY / 2                                    # cable-entry edge (faces the board edge, down)
    y_bond = -RFA_BOND_R
    z_top = Z_SMALL_BACK - 0.1
    z_ins = Z_GAUGES_FRONT + 0.9                                        # the connector's slot height
    # The fold: out of the bonding edge, down past the lens edge, back under the module, then up into the slot.
    pts = [(y_bond, z_top), (y_bond - 2.0, z_top - 0.8), (y_bond - 2.6, z_ins + 0.8), (y_bond - 2.0, z_ins)]
    left = RFA_FPC_FREE - path_len(pts)
    end_y = (y_bond - 2.0) + left
    pts.append((end_y, z_ins))
    add(f"Raystar {ref} FPC (real 18.3 mm tail)", "cables",
        strip(pts, RFA_FPC_W).translate((x, 0, 0)), (0.85, 0.55, 0.1))
    fpc_report[ref] = dict(tail_mm=round(RFA_FPC_FREE, 1), connector_y_from_screen_centre=round(conn_y, 1),
                           inserted_mm=round(end_y - entry_y, 2), body_depth_mm=F32Q_BODY,
                           seated=F32Q_MIN_INSERT <= end_y - entry_y <= F32Q_BODY)

# Centre panel FPC: from the tab, back through the faceplate slot, under panel-tsd/, up into J4.
pj4 = lay["panel"].fp["J4"]
j4 = kpt(T["panel"], pj4[0], pj4[1], 0)
j4_body = [p[0] for (r, _), p in lay["panel"].pads.items() if r == "J4"]
j4_entry = kpt(T["panel"], pj4[0], min(p["y"] for p in j4_body) - 0.5, 0)[1]   # cable side faces down after the flip
y_floor = -(TUB_OUT[1] / 2 - TUB_WALL) + 0.8
z_panel_rear = (Z_PANEL_BARE - PCB_T
                - band_height("panel", j4[0] - TSD_FPC_W / 2, j4[0] + TSD_FPC_W / 2, y_floor, j4_entry - 3) - 0.4)
# The FPC leaves the back of the tab (ASSUMED: the drawing's exit side was not recorded) and goes
# straight back through the faceplate slot.
tsd_pts = [(-TSD_TAB_REACH + 1.0, Z_TSD_BACK - 0.3), (-55.6, Z_TSD_BACK - 0.6),
           (-55.4, Z_FACE_BACK - 2), (y_floor, Z_FACE_BACK - 6), (y_floor, z_panel_rear),
           (j4_entry - 3, z_panel_rear), (j4_entry - 1.0, Z_PANEL_BARE - PCB_T - 0.6)]
tsd_pts = [(j4[0] * min(1.0, i / 6), y, z) for i, (y, z) in enumerate(tsd_pts)]
tsd_need = path_len(tsd_pts) + 2.0
add("TSD panel FPC (69.8 mm)", "cables", strip(tsd_pts, TSD_FPC_W), (0.85, 0.55, 0.1))

# Screen-port ribbon: panel-tsd/ J1 -> over brain/'s top edge -> brain/ J4 (port A).
pj1 = lay["panel"].fp["J1"]
bj4 = lay["brain"].fp["J4"]
p1 = kpt(T["panel"], pj1[0], pj1[1], 0)
b4 = kpt(T["brain"], bj4[0], bj4[1], 0)
y_top = centre["brain"][3] / 2 + 1.5
z_pr = Z_PANEL_BARE - PCB_T - band_height("panel", p1[0] - 11, p1[0] + 11, p1[1] + 3, PANEL_Y + centre["panel"][3] / 2) - 0.4
z_mid = Z_BRAIN_BARE + 2.4 + 0.6                     # just clear of brain/'s front-side screw heads
z_brain_rear = Z_BRAIN_BARE - PCB_T - band_height("brain", b4[0] - 11, b4[0] + 11, b4[1] + 3, y_top) - 0.4
ffc_pts = [(p1[0], p1[1] + 3.0, Z_PANEL_BARE - PCB_T - 0.6), (p1[0], p1[1] + 6.0, z_pr), (p1[0], p1[1] + 9.0, z_mid),
           (b4[0], y_top - 12.0, z_mid), (b4[0], y_top, z_mid), (b4[0], y_top + 1.0, Z_BRAIN_BARE - 0.8),
           (b4[0], y_top, z_brain_rear), (b4[0], b4[1] + 5.0, z_brain_rear), (b4[0], b4[1] + 3.0, Z_BRAIN_BARE - PCB_T - 0.6)]
add("screen-port FFC, 40-way 0.5 mm", "cables", strip(ffc_pts, 21.0), (0.9, 0.9, 0.86))

# Gauges/ standoffs to the faceplate (top-row holes) and M3 screw heads on the others
for ref in ("MH1", "MH2", "MH5", "MH6", "MH3", "MH4"):
    x, y, _, _ = lay["gauges"].fp[ref]
    X, Y, _ = kpt(T["gauges"], x, y, 0)
    if ref in ("MH3", "MH4"):
        add(f"gauges {ref} M3 pan head", "housing", cyl(5.5, Z_GAUGES_FRONT, Z_GAUGES_FRONT + 2.4, X, Y), CHROME)
    else:
        add(f"gauges {ref} standoff to faceplate", "housing", cyl(5.5, Z_GAUGES_FRONT, Z_FACE_BACK, X, Y), CHROME)
for ref in ("MH1", "MH2", "MH3", "MH4"):
    x, y, _, _ = lay["brain"].fp[ref]
    X, Y, _ = kpt(T["brain"], x, y, 0)
    add(f"brain {ref} standoff to tub", "housing", cyl(5.5, TUB_BACK_Z + 2.0, Z_BRAIN_BARE - PCB_T, X, Y), CHROME)
    add(f"brain {ref} M3 head", "housing", cyl(5.5, Z_BRAIN_BARE, Z_BRAIN_BARE + 2.4, X, Y), CHROME)
for ref in ("MH1", "MH2", "MH3", "MH4"):
    x, y, _, _ = lay["panel"].fp[ref]
    X, Y, _ = kpt(T["panel"], x, y, 0)
    add(f"panel-tsd {ref} standoff to brain", "housing", cyl(5.0, Z_BRAIN_BARE + 2.4, Z_PANEL_BARE - PCB_T, X, Y), CHROME)

# ---------------------------------------------------------------------------
# 4. Clash check: every pair of solids from different groups (or different boards)
# ---------------------------------------------------------------------------
INTENDED = [("housing", "dash")]           # the tub passes through the dash opening by design (checked separately)
MATES = {(f"Raystar {r} FPC (real 18.3 mm tail)", f"gauges:{r}") for r in GAUGE_X}   # each tail sits in its connector
for d in solids:
    d["bb"] = bbox(d["shape"])
clashes = []
clash_solids = []
for i, a in enumerate(solids):
    for b in solids[i + 1:]:
        if a["board"] and a["board"] == b["board"]:
            continue                                    # parts on one board were checked by DRC
        if a["group"] == b["group"] and not a["board"]:
            continue                                    # parts of one generated group touch by design
        if (a["group"], b["group"]) in INTENDED or (b["group"], a["group"]) in INTENDED:
            continue
        if (a["name"], b["name"]) in MATES or (b["name"], a["name"]) in MATES:
            continue
        if not boxes_overlap(a["bb"], b["bb"]):
            continue
        common = BRepAlgoAPI_Common(a["shape"], b["shape"]).Shape()
        v = volume(common)
        if v > 0.05:
            cb = bbox(common)
            clashes.append(dict(a=a["name"], b=b["name"], volume_mm3=round(v, 1),
                                depth_z_mm=round(cb[5] - cb[2], 2),
                                at=[round((cb[0] + cb[3]) / 2, 1), round((cb[1] + cb[4]) / 2, 1), round((cb[2] + cb[5]) / 2, 1)]))
            a["clash"] = b["clash"] = True
            clash_solids.append(dict(name=f"CLASH {a['name']} x {b['name']}", group="clash", shape=common,
                               color=(1.0, 0.0, 0.0), board=None, alpha=1.0, bb=cb))

solids += clash_solids

# The tub and the boards against the dash opening sizes
fit = []
for k in BOARDS:
    w, h = centre[k][2], centre[k][3]
    fit.append(dict(item=f"{k}/ board", w=round(w, 1), h=round(h, 1),
                    fits_outer=w <= DASH_OPENING[0] and h <= DASH_OPENING[1],
                    fits_inner=w <= DASH_INNER[0] and h <= DASH_INNER[1]))
fit.append(dict(item="housing tub", w=TUB_OUT[0], h=TUB_OUT[1], fits_outer=True,
                fits_inner=TUB_OUT[0] <= DASH_INNER[0] and TUB_OUT[1] <= DASH_INNER[1]))

# Gap under each small screen: the tallest gauges/ part inside the lens footprint
under = {}
for ref, x in GAUGE_X.items():
    worst = []
    for d in solids:
        if d["board"] != "gauges" or d["name"] == "gauges:board":
            continue
        b = d["bb"]
        dx = max(b[0] - x, 0, x - b[3])
        dy = max(b[1], 0, -b[4])
        if math.hypot(dx, dy) < RFA_LENS_D / 2:
            worst.append((round(b[5] - Z_GAUGES_FRONT, 2), d["name"].split(":")[1]))
    worst.sort(reverse=True)
    under[ref] = worst[:4]

depth = dict(faceplate_front=0.0, rim_front=max(z for _, z in RIM_PROFILE), pod_front=POD_FRONT,
             deepest_part=round(min(d["bb"][2] for d in solids if d["group"] not in ("housing", "dash", "clash")), 1),
             tub_back=TUB_BACK_Z)
report = dict(clashes=clashes, under_small_screens_mm=under, small_fpc=fpc_report,
              tsd_fpc=dict(length_mm=TSD_FPC_LEN, path_mm=round(tsd_need, 1), spare_mm=round(TSD_FPC_LEN - tsd_need, 1)),
              ffc_mm=round(path_len(ffc_pts) + 6, 1), opening_fit=fit, depth_mm=depth, view_angle_deg=view_angle,
              stack=dict(Z_FACE_BACK=Z_FACE_BACK, Z_SMALL_FRONT=Z_SMALL_FRONT, Z_SMALL_BACK=Z_SMALL_BACK,
                         Z_GAUGES_FRONT=Z_GAUGES_FRONT, Z_TSD_BACK=Z_TSD_BACK, Z_PANEL_BARE=Z_PANEL_BARE,
                         Z_BRAIN_BARE=Z_BRAIN_BARE, PANEL_Y=PANEL_Y))
with open(os.path.join(OUT, "clearance.json"), "w") as f:
    json.dump(report, f, indent=1)

# ---------------------------------------------------------------------------
# 5. Export
# ---------------------------------------------------------------------------
assy = cq.Assembly(name="dash_assembly_v1")
groups = {}
for i, d in enumerate(solids):
    g = groups.setdefault(d["group"], cq.Assembly(name=d["group"]))
    col = (1.0, 0.15, 0.15) if d.get("clash") and d["group"] != "clash" and d["board"] else d["color"]
    g.add(cq.Shape.cast(d["shape"]), name=f"{i:03d} {d['name']}"[:80], color=cq.Color(*col, d["alpha"]))
for g in groups.values():
    assy.add(g)
assy.export(os.path.join(OUT, "dash_assembly.step"))
# The writer turns OCC's Z-up into glTF's Y-up; the viewer turns it back (mech/viewer/index.html).
glb = os.path.join(OUT, "dash_assembly.glb")
assy.export(glb, tolerance=0.25, angularTolerance=0.2)   # fine enough that the chrome rings read round

# The web viewer: artifact hosting serves no .glb, so the model ships as base64 in script chunks.
import base64  # noqa: E402
VIEWER = os.path.join(HERE, "viewer")
for old in [f for f in os.listdir(VIEWER) if f.startswith("model-") and f.endswith(".js")]:
    os.remove(os.path.join(VIEWER, old))
b64 = base64.b64encode(open(glb, "rb").read()).decode("ascii")
CHUNK = 6_000_000
n_chunks = (len(b64) + CHUNK - 1) // CHUNK
for i in range(n_chunks):
    with open(os.path.join(VIEWER, f"model-{i + 1}.js"), "w") as f:
        f.write(f"(window.DASH_GLB = window.DASH_GLB || [])[{i}] = \"{b64[i * CHUNK:(i + 1) * CHUNK]}\";\n")
with open(os.path.join(VIEWER, "model-count.js"), "w") as f:
    f.write(f"window.DASH_GLB_CHUNKS = {n_chunks};\n")

print(json.dumps({k: report[k] for k in ("clashes", "under_small_screens_mm", "small_fpc", "tsd_fpc", "ffc_mm", "opening_fit", "depth_mm", "view_angle_deg")}, indent=1))
