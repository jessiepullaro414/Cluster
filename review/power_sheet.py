#!/usr/bin/env python3
"""
power_sheet.py - rate a power net that's carried by a pour, by solving it.

    python review/power_sheet.py brain
    python review/power_sheet.py panel-tsd --pcb X.kicad_pcb --plot out.png

Why: layout_checks.py used to print "pour-carried?" for such a net and leave it at that. On brain/
that hid all of the buck's output on one 0.2 mm track (found 2026-11-06). A pour doesn't help a
pad that only reaches it through a thin track, and a track in parallel with a pour carries what
the circuit gives it, not what the net's total is, so a rating by net total says nothing either way.

So this builds the net's real copper as a resistor network and solves it:
  * tracks are 1-D resistors, joined where one track's end lies on another's copper;
  * every filled pour polygon is rasterised to a grid and solved as a resistive sheet (Rs = rho / t);
  * vias tie the layers through their barrels (18 um plating, JLCPCB's stated minimum);
  * pads are equipotential, and tie the tracks and the fill that lie on them.
Each load draws its current from its own pins, the source supplies it, and the result is rated:
  * each piece of track at the current it really carries, by IPC-2221 at 20 K. Track lying on a pad
    or inside a wider track isn't rated: that copper is there in parallel;
  * each via barrel the same way, as layout_checks.py does;
  * the sheet in amps per mm of width, over a 1 mm square, away from the vias and pads whose current
    has to spread out somewhere, against IPC-2221 for the width of copper at that spot (the widest
    circle of copper that fits over it). On 0.5 oz inner copper that's 0.98 A for 1 mm, 2.2 A for
    3 mm and 5.7 A for 11.3 mm. A patch over the limit that's smaller than that 1 mm square is
    current crowding round a corner, another net's via or a track's end, not a neck, and is only
    reported;
  * the drop from the source to each load, as a catch for what the three above don't see.

All of this is a calculation from generated copper. Nothing has been measured. Exit status 1 on FAIL.
"""
import argparse
import collections
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kmodel import Layout  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
RHO = 1.72e-5              # ohm mm, copper at 20 C
T = {"F.Cu": 0.035, "B.Cu": 0.035, "In1.Cu": 0.0175, "In2.Cu": 0.0175, "In3.Cu": 0.0175, "In4.Cu": 0.0175}
# JLC06161H-3313: distance of each copper layer from F.Cu, mm (a via barrel's length between two layers)
Z = {"F.Cu": 0.0, "In1.Cu": 0.13, "In2.Cu": 0.70, "In3.Cu": 0.83, "In4.Cu": 1.40, "B.Cu": 1.53}
VIA_PLATING = 0.018
DT_LIMIT = 20.0
SPREAD_R = 2.0             # mm round a via or pad where the sheet's density isn't rated: the current is still spreading
MAX_DROP_MV = 100.0        # source to any load


def rise_for(i, w_mm, oz, internal):
    area = (w_mm / 0.0254) * (oz * 1.378)
    k = 0.024 if internal else 0.048
    return (abs(i) / (k * area ** 0.725)) ** (1 / 0.44) if i else 0.0


def via_rise(i, drill_mm):
    """Barrel as an outer conductor as wide as its circumference (layout_checks.py does the same)."""
    return rise_for(i, math.pi * drill_mm, VIA_PLATING / 0.0347, False)


# What each board draws (A). brain/: review/thermal_derating.py table A2, module 10 W ASSUMED (Toradex
# hasn't published it), panels 4.03 W each, J17 advertises 1.5 A, J19 0.5 A. U3.8 stands for the misc
# 0.5 W. The "at its limit" cases put one switch at the TPS2557-Q1's maximum current limit, with the
# others scaled back so the total stays inside the LM61460-Q1's 6 A.
_J1 = ("J1", ("251", "253", "255", "257", "259"))
_U6, _U7, _U11, _U16, _MISC = ("U6", ("2", "3")), ("U7", ("2", "3")), ("U11", ("2", "3")), ("U16", ("2", "3")), ("U3", ("8",))
_ALFA = {_J1: 2.0, _U6: 0.8, _U7: 0.8, _U11: 1.5, _U16: 0.5, _MISC: 0.1}
_MUSTANG = {_J1: 2.0, _U6: 0.8, _U11: 1.5, _U16: 0.5, _MISC: 0.1}
_BUCK_A = 6.0


def _at_limit(sw, limit):
    out = dict(_ALFA)
    out[sw] = limit
    fixed = out[_J1] + out[_MISC] + limit
    rest = [k for k in out if k not in (_J1, _MISC, sw)]
    scale = min(1.0, (_BUCK_A - fixed) / sum(out[k] for k in rest))
    for k in rest:
        out[k] *= scale
    return out


BOARDS = {
    "brain": dict(
        pcb=os.path.join(ROOT, "brain", "ClusterBrain.kicad_pcb"),
        net="+5V",
        source=[("L1", "2")],
        source_ohm=1e-6,
        sense=("R10", "1"),
        scenarios={
            "Alfa, 2 panels, peak": _ALFA,
            "Mustang, 1 panel, peak": _MUSTANG,
            "U6 at its 1.98 A limit": _at_limit(_U6, 1.98),
            "U7 at its 1.98 A limit": _at_limit(_U7, 1.98),
            "U11 at its 1.98 A limit": _at_limit(_U11, 1.98),
            "U16 at its 1.27 A limit": _at_limit(_U16, 1.27),
        }),
    # The panel's 5 V comes in on four FH12 contacts: 0.75 A to the backlight boost, 0.1 A to the bias
    # boost, 0.15 A to the bias inverter (layout_checks.py's NEEDS total of 1.0 A). The FH12's 50 mohm
    # contact resistance shares the current between the contacts.
    "panel-tsd": dict(
        pcb=os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_pcb"),
        net="+5V",
        source=[("J1", "2"), ("J1", "3"), ("J1", "4"), ("J1", "5")],
        source_ohm=0.05,
        sense=None,
        scenarios={"panel at 1.0 A": {("L4", ("1",)): 0.75, ("L2", ("1",)): 0.1, ("U6", ("5", "6")): 0.15}}),
}


def pad_box(q):
    """Half extents of a pad on the board's axes. kmodel gives a pad's absolute angle; these boards only use right angles."""
    a = q.get("angle", 0.0) % 180
    return (q["h"] / 2, q["w"] / 2) if abs(a - 90) < 1 else (q["w"] / 2, q["h"] / 2)


class Sheet:
    def __init__(self, pcb, net, h):
        import numpy as np
        self.np = np
        self.lay = Layout(pcb)
        self.net, self.h = net, h
        lay = self.lay
        xs = [p["x"] for lst in lay.pads.values() for p in lst]
        ys = [p["y"] for lst in lay.pads.values() for p in lst]
        self.x0, self.y0 = min(xs) - 3.0, min(ys) - 3.0
        self.nx = int((max(xs) + 3.0 - self.x0) / h) + 3
        self.ny = int((max(ys) + 3.0 - self.y0) / h) + 3
        self._rasterise()
        self._network()

    def ij(self, x, y):
        return int(round((x - self.x0) / self.h)) + 1, int(round((y - self.y0) / self.h)) + 1

    def _rasterise(self):
        """Even-odd scanline, which also copes with the zero-width slits KiCad cuts to fracture a fill's holes."""
        np, h = self.np, self.h
        self.masks = {}
        for z in self.lay.zones:
            if z["net"] != self.net:
                continue
            for layer, pts in z.get("filled", []):
                m = self.masks.setdefault(layer, np.zeros((self.ny, self.nx), dtype=bool))
                P = np.array(pts)
                xa, ya = P[:, 0], P[:, 1]
                xb, yb = np.roll(xa, -1), np.roll(ya, -1)
                for j in range(self.ny):
                    yc = self.y0 + (j - 1) * h
                    hit = (ya > yc) != (yb > yc)
                    if not hit.any():
                        continue
                    cross = np.sort(xa[hit] + (yc - ya[hit]) * (xb[hit] - xa[hit]) / (yb[hit] - ya[hit]))
                    for s, e in zip(cross[0::2], cross[1::2]):
                        i0 = int(math.ceil((s - self.x0) / h)) + 1
                        i1 = int(math.floor((e - self.x0) / h)) + 1
                        if i1 >= i0:
                            m[j, max(i0, 0):min(i1 + 1, self.nx)] = True

    def _network(self):
        np, h, lay, net = self.np, self.h, self.lay, self.net
        self.cell_id = {}
        n = 0
        rows, cols, vals = [], [], []
        for L, m in self.masks.items():
            ids = -np.ones(m.shape, dtype=np.int64)
            js, cs = np.nonzero(m)
            ids[js, cs] = np.arange(n, n + len(js))
            n += len(js)
            self.cell_id[L] = ids
            gs = T[L] / RHO         # one square per link
            for dj, di in ((0, 1), (1, 0)):
                a = ids[:ids.shape[0] - dj, :ids.shape[1] - di]
                b = ids[dj:, di:]
                ok = (a >= 0) & (b >= 0)
                p, q = a[ok], b[ok]
                rows += [p, q, p, q]
                cols += [p, q, q, p]
                vals += [np.full(len(p), gs), np.full(len(p), gs), np.full(len(p), -gs), np.full(len(p), -gs)]
        self.n_cells = n
        self.idx = {}

        def node(k):
            if k not in self.idx:
                self.idx[k] = n + len(self.idx)
            return self.idx[k]

        extra = []            # (p, q, ohms)

        def res(p, q, r):
            extra.append((p, q, r))

        segs = [t for t in lay.tracks if t["net"] == net]
        by_layer = collections.defaultdict(list)
        for t in segs:
            by_layer[t["layer"]].append(t)
        vias = [v for v in lay.vias if v["net"] == net]

        # Cut each track where something joins it: another track's end on its copper, or a via.
        self.pieces = []       # (p, q, ohms, width, layer, x0, y0, x1, y1)
        ties = []              # points tied to a point on a track
        for L, ts in by_layer.items():
            ends = [(t["x1"], t["y1"]) for t in ts] + [(t["x2"], t["y2"]) for t in ts]
            for t in ts:
                ax, ay, bx, by = t["x1"], t["y1"], t["x2"], t["y2"]
                ln = math.hypot(bx - ax, by - ay)
                if ln < 1e-6:
                    continue
                cuts = {0.0, 1.0}
                m = max(1, int(ln))          # a node each mm, so a track lying in a fill ties to it along its length
                cuts.update(k / m for k in range(1, m))
                pts = ends + [(v["x"], v["y"]) for v in vias]
                for px, py in pts:
                    u = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ln ** 2))   # a track's ends are round
                    cx, cy = ax + u * (bx - ax), ay + u * (by - ay)
                    if math.hypot(cx - px, cy - py) <= t["width"] / 2 + 0.005:
                        cuts.add(round(u, 6))
                        if math.hypot(cx - px, cy - py) > 1e-3:
                            ties.append((L, (px, py), (cx, cy)))
                cuts = sorted(cuts)
                for u, w in zip(cuts, cuts[1:]):
                    sx, sy = ax + u * (bx - ax), ay + u * (by - ay)
                    ex, ey = ax + w * (bx - ax), ay + w * (by - ay)
                    r = RHO * math.hypot(ex - sx, ey - sy) / (t["width"] * T[L])
                    p, q = node((L, round(sx, 3), round(sy, 3))), node((L, round(ex, 3), round(ey, 3)))
                    if p != q:
                        res(p, q, max(r, 1e-7))
                        self.pieces.append((p, q, max(r, 1e-7), t["width"], L, sx, sy, ex, ey))
        for L, a, b in ties:
            ka, kb = (L, round(a[0], 3), round(a[1], 3)), (L, round(b[0], 3), round(b[1], 3))
            if ka in self.idx and kb in self.idx:
                res(self.idx[ka], self.idx[kb], 1e-6)
        pts_on = collections.defaultdict(list)
        for k in list(self.idx):
            pts_on[k[0]].append(k)

        def cells_in(L, x0, y0, x1, y1):
            ids = self.cell_id.get(L)
            if ids is None:
                return []
            i0, j0 = self.ij(x0, y0)
            i1, j1 = self.ij(x1, y1)
            sub = ids[max(j0, 0):j1 + 1, max(i0, 0):i1 + 1]
            return sub[sub >= 0].tolist()

        # A track over a fill is tied to it at each node
        for L, keys in pts_on.items():
            if L not in self.cell_id:
                continue
            for k in keys:
                c = cells_in(L, k[1] - h / 2, k[2] - h / 2, k[1] + h / 2, k[2] + h / 2)
                if c:
                    res(self.idx[k], c[0], 1e-5)

        # Vias: one barrel node at In3's height (the pour is where the current goes), a land on each layer
        self.via_ties = []     # per via: (drill, [(barrel node, land node, ohms)], x, y)
        for vi, v in enumerate(vias):
            barrel = node(("via", vi))
            r_mm = RHO / (math.pi * v["drill"] * VIA_PLATING)
            lands = []
            for L in ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"):
                r = max(r_mm * abs(Z[L] - Z["In3.Cu"]), 1e-6)
                land = node(("land", vi, L))
                hit = False
                for k in pts_on.get(L, ()):
                    if math.hypot(k[1] - v["x"], k[2] - v["y"]) <= v["size"] / 2 + 1e-3:
                        res(land, self.idx[k], 1e-6)
                        hit = True
                rad = v["size"] / 2
                for c in cells_in(L, v["x"] - rad, v["y"] - rad, v["x"] + rad, v["y"] + rad):
                    res(land, c, 1e-5)
                    hit = True
                if hit:
                    res(barrel, land, r)
                    lands.append((barrel, land, r))
            self.via_ties.append((v["drill"], lands, v["x"], v["y"]))

        # Pads
        self.pad_nodes = {}
        self.pad_list = []
        for (ref, pin), plist in lay.pads.items():
            for q in plist:
                if q["net"] != net:
                    continue
                pn = node(("pad", ref, pin))
                self.pad_nodes[(ref, pin)] = pn
                hx, hy = pad_box(q)
                layers = [x for x in q["layers"] if x.endswith(".Cu")]
                if "*.Cu" in q["layers"]:
                    layers = list(T)
                self.pad_list.append((q["x"], q["y"], hx, hy, layers))
                for L in layers:
                    for k in pts_on.get(L, ()):
                        if abs(k[1] - q["x"]) <= hx + 1e-3 and abs(k[2] - q["y"]) <= hy + 1e-3:
                            res(pn, self.idx[k], 1e-6)
                    cs = cells_in(L, q["x"] - hx, q["y"] - hy, q["x"] + hx, q["y"] + hy)
                    for c in cs[:: max(1, len(cs) // 8)]:
                        res(pn, c, 1e-4)
        self.src = None
        self.n = n + len(self.idx)
        self._rows, self._cols, self._vals, self._extra = rows, cols, vals, extra
        self._node = node

    def factor(self, source, source_ohm):
        import scipy.sparse as sp
        import scipy.sparse.csgraph as csg
        import scipy.sparse.linalg as spl
        np = self.np
        src = self._node(("source",))
        for key in source:
            self._extra.append((src, self.pad_nodes[key], source_ohm))
        self.n = self.n_cells + len(self.idx)
        self.src = src
        rows = list(self._rows)
        cols = list(self._cols)
        vals = list(self._vals)
        e = np.array([(p, q, 1.0 / r) for p, q, r in self._extra])
        p, q, g = e[:, 0].astype(np.int64), e[:, 1].astype(np.int64), e[:, 2]
        rows += [p, q, p, q]
        cols += [p, q, q, p]
        vals += [g, g, -g, -g]
        A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(self.n, self.n))
        _, lab = csg.connected_components(A, directed=False)
        self.lab = lab
        keep = np.nonzero((lab == lab[src]) & (np.arange(self.n) != src))[0]
        self.pos = -np.ones(self.n, dtype=np.int64)
        self.pos[keep] = np.arange(len(keep))
        self.keep = keep
        self.lu = spl.splu(A[keep][:, keep].tocsc(), permc_spec="COLAMD")

    def unit(self, ref, pins):
        """Node voltages for 1 A drawn from these pins, shared equally, into the source."""
        np = self.np
        b = np.zeros(len(self.keep))
        for pin in pins:
            b[self.pos[self.pad_nodes[(ref, pin)]]] -= 1.0 / len(pins)
        v = np.zeros(self.n)
        v[self.keep] = self.lu.solve(b)
        return v

    def rate_tracks(self, v):
        """Worst rises, the length over the limit and the loss. A piece on a pad, or inside a wider same-net track, isn't rated."""
        worst, over, loss = (0.0, None), collections.defaultdict(float), 0.0
        for k, (p, q, r, w, L, sx, sy, ex, ey) in enumerate(self.pieces):
            i = (v[p] - v[q]) / r
            loss += i * i * r
            if self._covered[k]:
                continue
            dt = rise_for(i, w, 0.5 if L.startswith("In") else 1.0, L.startswith("In"))
            ln = math.hypot(ex - sx, ey - sy)
            if dt > DT_LIMIT:
                over[(round(abs(i), 1), w, L)] += ln
            if dt > worst[0]:
                worst = (dt, f"{abs(i):.2f} A in {w} mm on {L} near ({sx:.1f}, {sy:.1f})")
        return worst, over, loss

    def find_covered(self):
        """Which track pieces have other same-net copper round them."""
        lay, net = self.lay, self.net
        tracks = [t for t in lay.tracks if t["net"] == net]
        self._covered = []
        for p, q, r, w, L, sx, sy, ex, ey in self.pieces:
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            hit = False
            for x, y, hx, hy, layers in self.pad_list:
                if L in layers and abs(mx - x) <= hx and abs(my - y) <= hy:
                    hit = True
                    break
            if not hit:
                for t in tracks:
                    if t["layer"] != L or t["width"] <= w + 1e-6:
                        continue
                    ax, ay, bx, by = t["x1"], t["y1"], t["x2"], t["y2"]
                    ln2 = (bx - ax) ** 2 + (by - ay) ** 2
                    u = 0.0 if ln2 < 1e-12 else max(0.0, min(1.0, ((mx - ax) * (bx - ax) + (my - ay) * (by - ay)) / ln2))
                    if math.hypot(ax + u * (bx - ax) - mx, ay + u * (by - ay) - my) <= t["width"] / 2:
                        hit = True
                        break
            self._covered.append(hit)

    def rate_vias(self, v):
        worst = (0.0, None)
        for drill, lands, x, y in self.via_ties:
            i = max((abs(v[b] - v[l]) / r for b, l, r in lands), default=0.0)
            dt = via_rise(i, drill)
            if dt > worst[0]:
                worst = (dt, f"{i:.2f} A, {drill} mm drill at ({x:.1f}, {y:.1f})")
        return worst

    def spread_mask(self):
        """True where the sheet is rated: outside SPREAD_R of this net's vias and pads."""
        np, h = self.np, self.h
        yy, xx = np.mgrid[0:self.ny, 0:self.nx]
        X, Y = self.x0 + (xx - 1) * h, self.y0 + (yy - 1) * h
        out = np.ones((self.ny, self.nx), dtype=bool)
        r = int(SPREAD_R / h) + 1
        centres = [(v["x"], v["y"]) for v in self.lay.vias if v["net"] == self.net]
        for x, y, hx, hy, layers in self.pad_list:
            centres.append((x, y))
        for x, y in centres:
            i, j = self.ij(x, y)
            j0, j1, i0, i1 = max(j - r, 0), min(j + r + 1, self.ny), max(i - r, 0), min(i + r + 1, self.nx)
            near = (X[j0:j1, i0:i1] - x) ** 2 + (Y[j0:j1, i0:i1] - y) ** 2 <= SPREAD_R ** 2
            out[j0:j1, i0:i1] &= ~near
        return out

    def width_limit(self, L, live):
        """Amps per mm allowed at each cell: IPC-2221 at DT_LIMIT for the width of copper there. The width at a cell is the
        largest circle of copper that covers it (a morphological opening, by distance transforms)."""
        from scipy.ndimage import distance_transform_edt as edt
        np, h = self.np, self.h
        width = np.full(live.shape, 0.5)
        for w in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 11.0, 16.0, 22.0):
            r = w / 2 / h
            core = edt(live) > r
            if not core.any():
                break
            width[edt(~core) <= r] = w
        oz = 0.5
        return 0.024 * DT_LIMIT ** 0.44 * ((width / 0.0254) * (oz * 1.378)) ** 0.725 / width

    def density(self, v, L):
        """A per mm of width in layer L's sheet, averaged over a 1 mm square; and the sheet's loss."""
        np, h = self.np, self.h
        ids = self.cell_id[L]
        live = (ids >= 0) & (self.lab[np.maximum(ids, 0)] == self.lab[self.src])
        V = np.where(live, v[np.maximum(ids, 0)], np.nan)
        gs = T[L] / RHO
        dx = (V[:, 1:] - V[:, :-1]) * gs / h
        dy = (V[1:, :] - V[:-1, :]) * gs / h
        loss = float(np.nansum(((V[:, 1:] - V[:, :-1]) ** 2) * gs) + np.nansum(((V[1:, :] - V[:-1, :]) ** 2) * gs))
        dx, dy = np.nan_to_num(dx), np.nan_to_num(dy)
        jx, jy = np.zeros(V.shape), np.zeros(V.shape)
        jx[:, 1:] += dx
        jx[:, :-1] += dx
        jy[1:, :] += dy
        jy[:-1, :] += dy
        J = np.hypot(jx, jy) / 2
        # 1 mm box average over the copper
        k = max(1, int(round(1.0 / h)))
        from scipy.ndimage import uniform_filter
        cu = uniform_filter(live.astype(float), size=k, mode="constant")
        sm = uniform_filter(J, size=k, mode="constant")
        return np.where(live, sm / np.maximum(cu, 1e-6), 0.0), loss, live


def check(board, pcb=None, h=0.25, plot=None, log=print):
    """Solve and rate the board's pour-carried net. Returns the list of failures (empty: ok)."""
    try:
        import numpy as np
        import scipy  # noqa: F401
    except ImportError as e:
        log(f"      power_sheet.py needs numpy and scipy: {e}  [FAIL]")
        return ["numpy/scipy missing"]
    cfg = BOARDS[board]
    S = Sheet(pcb or cfg["pcb"], cfg["net"], h)
    S.factor(cfg["source"], cfg["source_ohm"])
    S.find_covered()
    src_name = "/".join(f"{r}.{p}" for r, p in cfg["source"])
    fails = []
    log(f"      {cfg['net']} solved with its pours as copper sheets (review/power_sheet.py, {h} mm grid), from {src_name}; calculated, not measured:")
    for L, m in S.masks.items():
        ids = S.cell_id[L]
        live = (ids >= 0) & (S.lab[np.maximum(ids, 0)] == S.lab[S.src])
        log(f"        {L}: {m.sum() * h * h:.0f} mm2 of fill, {live.sum() * h * h:.0f} mm2 of it tied to the source")
    loads = {k for sc in cfg["scenarios"].values() for k in sc}
    for ref, pins in sorted(loads):
        for pin in pins:
            if S.lab[S.pad_nodes[(ref, pin)]] != S.lab[S.src]:
                fails.append(f"{ref}.{pin} isn't connected to the source")
    # Every other pad on the net, however small its load, has to be on the same copper
    for key, pn in S.pad_nodes.items():
        if S.lab[pn] != S.lab[S.src] and f"{key[0]}.{key[1]} isn't connected to the source" not in fails:
            fails.append(f"{key[0]}.{key[1]} isn't connected to the source")
    if fails:
        for f in fails:
            log(f"        {f}  [FAIL]")
        return fails
    unit = {(ref, pins): S.unit(ref, pins) for ref, pins in loads}
    rated = S.spread_mask()
    sense = None if not cfg.get("sense") else S.pad_nodes.get(cfg["sense"])
    limits = {}
    for name, sc in cfg["scenarios"].items():
        v = np.zeros(S.n)
        for k, amps in sc.items():
            v += unit[k] * amps
        total = sum(sc.values())
        worst, over, loss = S.rate_tracks(v)
        vw = S.rate_vias(v)
        drops = {k: -min(v[S.pad_nodes[(k[0], p)]] for p in k[1]) * 1e3 for k in sc}
        worst_drop = max(drops.values())
        sheet_txt, sheet_bad = [], 0.0
        for L in S.masks:
            J, sloss, live = S.density(v, L)
            loss += sloss
            if L not in limits:
                limits[L] = S.width_limit(L, live)
            ratio = J * rated / limits[L]
            peak = float(ratio.max())
            bad = float((ratio > 1.0).sum() * h * h)
            if bad > 1.0:
                sheet_bad += bad
            sheet_txt.append(f"{L} up to {100 * peak:.0f} % of what IPC-2221 allows for its width" + (f", {bad:.1f} mm2 over" if bad else ""))
            if bad:
                j, i = np.unravel_index(int(ratio.argmax()), ratio.shape)
                sheet_txt[-1] += f", worst near ({S.x0 + (i - 1) * h:.1f}, {S.y0 + (j - 1) * h:.1f})"
        status = []
        if over:
            status.append(f"{sum(over.values()):.1f} mm of track over {DT_LIMIT:.0f} K")
        if vw[0] > DT_LIMIT:
            status.append(f"via at {vw[0]:.0f} K")
        if sheet_bad:
            status.append(f"{sheet_bad:.1f} mm2 of sheet over IPC-2221 for its width")
        if worst_drop > MAX_DROP_MV:
            status.append(f"{worst_drop:.0f} mV drop")
        tag = "FAIL" if status else "ok"
        log(f"        {name}, {total:.2f} A: loss {loss * 1e3:.0f} mW; worst drop {worst_drop:.0f} mV; worst track {worst[0]:.1f} K {worst[1] or ''}; "
            f"worst via {vw[0]:.1f} K {vw[1] or ''}; {'; '.join(sheet_txt)}  [{tag}]")
        log("          drop at each load: " + ", ".join(f"{k[0]} {drops[k]:.0f} mV" for k in sorted(drops))
            + (f"; the buck's FB top senses {-v[sense] * 1e3:.0f} mV" if sense is not None else ""))
        for (i, w, L), ln in sorted(over.items(), reverse=True)[:8]:
            log(f"          {ln:.1f} mm of {w:.2f} mm on {L} carrying {i:.1f} A: {rise_for(i, w, 0.5 if L.startswith('In') else 1.0, L.startswith('In')):.0f} K")
        fails += [f"{name}: {s}" for s in status]
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        v = np.zeros(S.n)
        first = next(iter(cfg["scenarios"].values()))
        for k, amps in first.items():
            v += unit[k] * amps
        Ls = list(S.masks)
        fig, axs = plt.subplots(len(Ls), 1, figsize=(16, 9.5 * len(Ls)), squeeze=False)
        for ax, L in zip(axs[:, 0], Ls):
            J, _, live = S.density(v, L)
            im = ax.imshow(np.ma.masked_where(~live, J), extent=(S.x0 - h, S.x0 + (S.nx - 1) * h, S.y0 + (S.ny - 1) * h, S.y0 - h),
                           cmap="inferno", vmin=0, vmax=1.0)
            fig.colorbar(im, ax=ax, label="A per mm of copper width", shrink=0.7)
            for ref, pins in first:
                q = S.lay.pads[(ref, pins[0])][0]
                ax.plot(q["x"], q["y"], "c+", ms=10)
                ax.text(q["x"] + 1, q["y"], ref, color="c", fontsize=9)
            ax.set_title(f"{cfg['net']} on {L}, {next(iter(cfg['scenarios']))}")
        fig.tight_layout()
        fig.savefig(plot, dpi=90)
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=tuple(BOARDS))
    ap.add_argument("--pcb")
    ap.add_argument("--h", type=float, default=0.25, help="grid, mm")
    ap.add_argument("--plot")
    a = ap.parse_args()
    fails = check(a.board, a.pcb, a.h, a.plot)
    print("FAIL: " + "; ".join(fails) if fails else "ok")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
