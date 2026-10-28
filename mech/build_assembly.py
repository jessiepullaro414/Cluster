"""Dash assembly v1: the three routed boards in a housing of our own, with every screen.

Builds the faceplate, chrome bezels, gauge cups, the centre pod, the housing tub, a stand-in
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
GAUGE_X = {"U6": -196.89, "U7": -118.0, "U8": 118.0, "U9": 196.89}   # gauges/ slot centres (board)

FACE_T = 3.0                        # ASSUMED: printed or machined faceplate thickness
SMALL_WINDOW = 34.0                 # mechanical-fit.md: at least 33-35 mm over the 32.4 mm active area
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
SCREEN_HOLDER_H = 4.0                # small screen holders: lens back sits this far off the board
Z_GAUGES_FRONT = -17.8               # gauges/ component side; J1 (13.8 mm) stops 1 mm short of the faceplate
Z_SMALL_BACK = Z_GAUGES_FRONT + SCREEN_HOLDER_H
Z_SMALL_FRONT = Z_SMALL_BACK + RFA_T
Z_TSD_BACK = 1.0                     # the centre panel sits in the pod, 1 mm off the faceplate so its FPC folds under the tab
POD_H = Z_TSD_BACK + TSD_T + 2.2                 # pod stands this proud of the faceplate (lip 2 mm in front of the glass)
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

g_row_x = (lay["gauges"].fp["U7"][0] + lay["gauges"].fp["U8"][0]) / 2     # speedometer centre on gauges/
g_row_y = 232.34                                                          # screen row (silk circles)
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

face = rrect(TRIM[0], TRIM[1], 28, FACE_T, Z_FACE_BACK)
for x in GAUGE_X.values():
    face = face.cut(cyl(SMALL_WINDOW, Z_FACE_BACK - 1, 1, x))
face = face.cut(cq.Workplane("XY").workplane(offset=Z_FACE_BACK - 1)
                .center(0, -55.3).rect(TSD_FPC_W + 4, 3.5).extrude(FACE_T + 2))   # panel FPC slot, inside the tub wall
add("faceplate (ASSUMED 3 mm, trim outline)", "housing", face, (0.11, 0.11, 0.12))

for ref, x in GAUGE_X.items():
    add(f"bezel ring {ref}", "housing", ring(50.0, SMALL_WINDOW, 0, 2.5, x), CHROME)
    add(f"gauge cup {ref}", "housing", ring(40.0, 35.0, Z_SMALL_FRONT, Z_FACE_BACK, x), BLACK)

pod = (cq.Workplane("XY").circle(POD_OD / 2).extrude(POD_H)
       .cut(cq.Workplane("XY").circle(TSD_BODY_D / 2 + 0.5).extrude(POD_H - 2.0))
       .cut(cq.Workplane("XY").circle(CENTRE_WINDOW / 2).extrude(POD_H + 1))
       .cut(cq.Workplane("XY").center(0, -55.0).rect(TSD_TAB_W + 1, 12).extrude(Z_TSD_BACK + TSD_T + 0.3)))
add("centre pod bezel", "housing", pod, CHROME)

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
    holder = (ring(RFA_LENS_D, RFA_BODY_D + 1.0, Z_GAUGES_FRONT, Z_SMALL_BACK, x)
              .cut(cq.Workplane("XY").workplane(offset=Z_GAUGES_FRONT - 1).center(x, -RFA_LENS_D / 2).rect(RFA_FPC_W + 4, 16).extrude(8)))
    add(f"screen holder {ref} (ASSUMED printed ring)", "housing", holder, (0.3, 0.32, 0.36))

# Small-screen FPC, folded under the module toward its connector, at its real length.
fpc_report = {}
for ref, x in GAUGE_X.items():
    conn_y = -(lay["gauges"].fp[ref][1] - g_row_y)                     # connector centre, assembly Y
    pads = [p[0] for (r, _), p in lay["gauges"].pads.items() if r == ref]
    entry_y = -(max(p["y"] for p in pads) + 0.5 + 2.0 - g_row_y)       # body front edge (cable side), ASSUMED 2 mm past the pads
    y_bond = -RFA_BOND_R
    z_top = Z_SMALL_BACK - 0.1
    z_low = Z_GAUGES_FRONT + 2.2                                        # rides over the board parts into the connector
    # The fold: out of the bonding edge, down past the lens edge, back under the module.
    pts = [(y_bond, z_top), (y_bond - 2.0, z_top - 0.8), (y_bond - 2.6, z_low + 0.8), (y_bond - 2.0, z_low)]
    used = path_len(pts)
    need = used + abs((y_bond - 2.0) - (entry_y + 2.0))                  # plus the run to 2 mm inside the connector
    left = RFA_FPC_FREE - used
    end_y = (y_bond - 2.0) + left
    pts.append((end_y, z_low))
    add(f"Raystar {ref} FPC (real 18.3 mm tail)", "cables",
        strip(pts, RFA_FPC_W).translate((x, 0, 0)), (0.85, 0.55, 0.1))
    fpc_report[ref] = dict(tail_mm=round(RFA_FPC_FREE, 1), needed_mm=round(need, 1),
                           short_by_mm=round(need - RFA_FPC_FREE, 1),
                           connector_y_from_screen_centre=round(conn_y, 1), tail_end_y=round(end_y, 1))

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

depth = dict(faceplate_front=0.0, pod_front=round(POD_H, 1),
             deepest_part=round(min(d["bb"][2] for d in solids if d["group"] not in ("housing", "dash", "clash")), 1),
             tub_back=TUB_BACK_Z)
report = dict(clashes=clashes, under_small_screens_mm=under, small_fpc=fpc_report,
              tsd_fpc=dict(length_mm=TSD_FPC_LEN, path_mm=round(tsd_need, 1), spare_mm=round(TSD_FPC_LEN - tsd_need, 1)),
              ffc_mm=round(path_len(ffc_pts) + 6, 1), opening_fit=fit, depth_mm=depth,
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
assy.export(glb, tolerance=0.5, angularTolerance=0.8)

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

print(json.dumps({k: report[k] for k in ("clashes", "under_small_screens_mm", "small_fpc", "tsd_fpc", "ffc_mm", "opening_fit", "depth_mm")}, indent=1))
