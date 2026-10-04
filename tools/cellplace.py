"""
Constructive "cell" placer for the display carrier's power converters.

Why this exists (2026-10-04, external design review): the previous layout
packed every part into one flat skyline, so a converter's own parts ended up
scattered (the LM61460 input capacitor 57 mm from its VIN pin, the boost
switch nodes 75 mm long). A switching converter has to be laid out as a tight
cell: input capacitor right at the VIN/PGND pins, inductor right at SW, boot
capacitor next to the BOOT/SW pins, feedback divider at the FB pin.

How it works: one anchor part (the converter IC) is fixed at the origin. The
other members are placed one at a time, in the order the caller gives, each at
the free position (and 0/90/180/270 rotation) that minimises the weighted
distance from each of its pads to the pads it connects to. Nets can carry
weights (switch nodes weigh most), and a part can be pulled toward specific
pads of another part (for example an input capacitor toward VIN and PGND
pins 8/9 rather than toward "any +12V pad"). No part overlaps another part's
bounding box (pads plus courtyard) and a small gap is kept between them.

Coordinates here are footprint ORIGINS in the cell frame with the anchor at
(0, 0); rotation uses KiCad's file convention (positive = counter-clockwise on
screen, y down): (x, y) -> (y, -x) for 90 degrees.
"""
import math

import numpy as np

GAP = 0.35          # minimum clearance between two parts' bounding boxes, mm
ANCHOR_GAP = 1.6    # around the converter IC: room for fan-out vias on 0.5 mm-pitch QFNs
GRID = 0.5          # coarse search step, mm
FINE = 0.1          # refinement step, mm
SEARCH = 26.0       # search half-window around the anchor, mm
COMPACT = 0.02      # tiny pull toward the anchor so cells stay compact
ROTATIONS = (0, 90, 180, 270)


def rot_xy(x, y, a):
    if a == 0:
        return x, y
    if a == 90:
        return y, -x
    if a == 180:
        return -x, -y
    return -y, x


class Part:
    def __init__(self, ref, bbox, pads, fixed_rot=None):
        self.ref = ref
        self.bbox = bbox                      # local (x0, y0, x1, y1)
        self.pads = pads                      # [(number, x, y, net)] local, nets only for wired pads
        self.fixed_rot = fixed_rot

    def rbbox(self, a):
        x0, y0, x1, y1 = self.bbox
        pts = [rot_xy(x, y, a) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def rpads(self, a):
        return [(n, *rot_xy(x, y, a), net) for n, x, y, net in self.pads]


def place_cell(parts, anchor, order, net_weight, pulls=None, default_weight=1.0,
               allowed_rot=None, verbose=False):
    """parts: ref -> Part. anchor: ref placed at the origin. order: refs in
    placement order. net_weight: net -> weight (nets not listed use
    default_weight; GND-like nets should be listed low). pulls:
    ref -> {net: (target_ref, [pad numbers], weight)} overrides the default
    "nearest already-placed pad on that net" target for that part's net.
    allowed_rot: ref -> tuple of rotations (default all four).
    Returns {ref: (ox, oy, rot)} and the cell bbox."""
    pulls = pulls or {}
    allowed_rot = allowed_rot or {}
    placed = {anchor: (0.0, 0.0, 0)}
    abs_pads = {}        # net -> list of (x, y, ref) of already-placed pads

    def add_pads(ref):
        ox, oy, a = placed[ref]
        for n, x, y, net in parts[ref].rpads(a):
            abs_pads.setdefault(net, []).append((ox + x, oy + y, ref, n))

    add_pads(anchor)
    boxes = []

    def add_box(ref):
        ox, oy, a = placed[ref]
        x0, y0, x1, y1 = parts[ref].rbbox(a)
        g = ANCHOR_GAP if ref == anchor else GAP
        boxes.append((ox + x0 - g, oy + y0 - g, ox + x1 + g, oy + y1 + g))

    add_box(anchor)

    def cost_grid(ref, a, xs, ys):
        """Cost over a grid of origin positions xs (n,) x ys (m,) -> (m, n)."""
        X, Y = np.meshgrid(xs, ys)
        total = np.zeros_like(X)
        for n, px, py, net in parts[ref].rpads(a):
            if net is None or net.startswith("unconnected"):
                continue
            spec = pulls.get(ref, {}).get(net)
            if spec is not None:
                tref, tpads, w = spec
                targets = [(tx, ty) for tx, ty, r, num in abs_pads.get(net, [])
                           if r == tref and num in tpads]
            else:
                w = net_weight.get(net, default_weight)
                targets = [(tx, ty) for tx, ty, r, num in abs_pads.get(net, [])]
            if not targets or w == 0:
                continue
            d = np.full_like(X, 1e9)
            for tx, ty in targets:
                d = np.minimum(d, np.hypot(X + px - tx, Y + py - ty))
            total += w * d
        total += COMPACT * np.hypot(X, Y)
        return total

    def free_mask(ref, a, xs, ys):
        x0, y0, x1, y1 = parts[ref].rbbox(a)
        X, Y = np.meshgrid(xs, ys)
        ok = np.ones_like(X, dtype=bool)
        for bx0, by0, bx1, by1 in boxes:
            hit = ((X + x1 > bx0) & (X + x0 < bx1) & (Y + y1 > by0) & (Y + y0 < by1))
            ok &= ~hit
        return ok

    for ref in order:
        part = parts[ref]
        best = None
        for a in (allowed_rot.get(ref) or ROTATIONS):
            xs = np.arange(-SEARCH, SEARCH + 1e-9, GRID)
            ys = np.arange(-SEARCH, SEARCH + 1e-9, GRID)
            c = cost_grid(ref, a, xs, ys)
            c = np.where(free_mask(ref, a, xs, ys), c, np.inf)
            i = np.unravel_index(np.argmin(c), c.shape)
            if np.isfinite(c[i]) and (best is None or c[i] < best[0]):
                best = (float(c[i]), a, float(xs[i[1]]), float(ys[i[0]]))
        if best is None:
            raise RuntimeError(f"cell placer: nowhere to put {ref}")
        _, a, cx, cy = best
        # refine around the coarse optimum on a finer grid
        xs = np.arange(cx - GRID, cx + GRID + 1e-9, FINE)
        ys = np.arange(cy - GRID, cy + GRID + 1e-9, FINE)
        c = cost_grid(ref, a, xs, ys)
        c = np.where(free_mask(ref, a, xs, ys), c, np.inf)
        i = np.unravel_index(np.argmin(c), c.shape)
        if np.isfinite(c[i]):
            cx, cy = float(xs[i[1]]), float(ys[i[0]])
        placed[ref] = (round(cx, 3), round(cy, 3), a)
        add_pads(ref)
        add_box(ref)
        if verbose:
            print(f"    {ref:5s} rot {a:3d} at ({cx:6.2f},{cy:6.2f})  cost {best[0]:.2f}")

    xs0, ys0, xs1, ys1 = [], [], [], []
    for ref, (ox, oy, a) in placed.items():
        x0, y0, x1, y1 = parts[ref].rbbox(a)
        xs0.append(ox + x0)
        ys0.append(oy + y0)
        xs1.append(ox + x1)
        ys1.append(oy + y1)
    return placed, (min(xs0), min(ys0), max(xs1), max(ys1))


def pad_abs(parts, placed, ref, number):
    ox, oy, a = placed[ref]
    for n, x, y, net in parts[ref].rpads(a):
        if n == number:
            return ox + x, oy + y
    raise KeyError((ref, number))


def pull(tref, pads, w):
    """A pull spec for place_cell(): attract toward pad(s) `pads` of part `tref`."""
    return (tref, [str(p) for p in pads], w)


def make_parts(parts_info, pad_net, load_footprint, footprint_bbox):
    """ref -> Part for every schematic part in parts_info (ref -> {footprint,...})."""
    out = {}
    for ref, info in parts_info.items():
        fp = load_footprint(info["footprint"])
        pads = [(str(p.number), p.position.X, p.position.Y, pad_net.get((ref, str(p.number))))
                for p in fp.pads if str(p.number) != ""]
        out[ref] = Part(ref, footprint_bbox(fp), pads)
    return out


def plan_cells(parts, cells, net_weight):
    """cells: name -> dict(anchor, order, pulls[, rot]). Returns ({name: (placed,
    bbox)}, set of every ref used). Each ref may appear in only one cell."""
    seen, result = set(), {}
    for name, c in cells.items():
        for m in [c["anchor"]] + c["order"]:
            assert m not in seen, f"{m} is in two cells"
            assert m in parts, f"{m} in cell {name} is not a schematic part"
            seen.add(m)
        result[name] = place_cell(parts, c["anchor"], c["order"], net_weight,
                                  pulls=c["pulls"], allowed_rot=c.get("rot"))
    return result, seen


def rotate_cell(placed, bbox, r):
    """Rotate a whole cell by r degrees (0/90/180/270). Returns (placed', bbox')."""
    if r == 0:
        return placed, bbox
    out = {}
    for ref, (ox, oy, a) in placed.items():
        nx, ny = rot_xy(ox, oy, r)
        out[ref] = (round(nx, 3), round(ny, 3), (a + r) % 360)
    x0, y0, x1, y1 = bbox
    pts = [rot_xy(x, y, r) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    return out, (min(p[0] for p in pts), min(p[1] for p in pts),
                 max(p[0] for p in pts), max(p[1] for p in pts))
