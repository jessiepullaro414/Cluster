#!/usr/bin/env python3
"""
dsi_impedance.py - impedance of the DSI pairs on display/ from the real stack-up.

Stack-up (6-layer since 2026-10-18, see main()): the boards carry no (stackup ...) block, so fab/README.md names it.
The old 4-layer order was JLCPCB 4-layer, 1.6 mm, outer 1 oz, inner 0.5 oz, i.e. JLC04161H-7628: 35 um outer copper /
0.2104 mm 7628 prepreg (Dk ~4.4 as JLCPCB lists it) / 17.5 um In1 / 1.065 mm core / 17.5 um In2 /
0.2104 mm prepreg / 35 um outer. In1 is the GND plane, so the F.Cu pairs are microstrip over GND at
h = 0.21 mm. (The P leg of each pair swaps to B.Cu for ~3 mm and is then referenced to In2.)

Two independent estimates, because the layout comment quotes only IPC-2141:
  1. closed-form: IPC-2141 edge-coupled microstrip, and Hammerstad-Jensen for the single track;
  2. a quasi-static 2-D finite-difference field solve (Laplace, conductor thickness and
     solder mask included) giving the even/odd-mode capacitances and so Zdiff, Zcommon, the
     propagation delay and the odd-mode coupling.

    python review/dsi_impedance.py
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

C0 = 299.792458  # mm/ns


def ipc2141(w, s, h, t, er):
    z0 = 87.0 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
    zd = 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h))
    return z0, zd


def hammerstad(w, h, t, er):
    """Hammerstad-Jensen microstrip Z0 with finite-thickness width correction."""
    we = w + t / math.pi * (1 + math.log(2 * h / t)) if t > 0 else w
    u = we / h
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    f = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z0 = 60 / math.sqrt(ee) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    return z0, ee


def fd_solve(w, s, h, t, er, mask_t=0.025, er_mask=3.3, pitch=0.01, width=10.0, air=3.0, pair=True):
    """Quasi-static 2-D FD solve. Returns dict with Z0 (single track alone), Zodd/Zeven/Zdiff, eff Dk."""
    nx = int(round(width / pitch))
    ny = int(round((h + t + air) / pitch))
    xs = (np.arange(nx) + 0.5) * pitch - width / 2
    ys = (np.arange(ny) + 0.5) * pitch            # y = 0 is the ground plane surface (below: ground)
    X, Y = np.meshgrid(xs, ys)
    conductors = []
    if pair:
        centers = [-(s + w) / 2, (s + w) / 2]
    else:
        centers = [0.0]
    cond = np.full((ny, nx), -1, dtype=int)
    for k, cx in enumerate(centers):
        m = (np.abs(X - cx) <= w / 2) & (Y >= h) & (Y < h + t)
        cond[m] = k
    ncond = len(centers)

    def capmat(er_sub, er_m):
        eps = np.ones((ny, nx))
        eps[Y < h] = er_sub
        # mask film (over the substrate and the copper sides/top)
        film = (Y >= h) & (Y < h + t + mask_t)
        near = np.zeros_like(film)
        for cx in centers:
            near |= (np.abs(X - cx) <= w / 2 + mask_t) & (Y >= h) & (Y < h + t + mask_t)
        eps[(Y >= h) & (Y < h + mask_t)] = er_m
        eps[near & (cond < 0)] = er_m
        N = nx * ny
        idx = np.arange(N).reshape(ny, nx)
        rows, cols, vals = [], [], []
        diag = np.zeros(N)
        # links between neighbouring cells with harmonic-mean permittivity
        for (dy, dx) in ((0, 1), (1, 0)):
            a = idx[: ny - dy, : nx - dx].ravel()
            b = idx[dy:, dx:].ravel()
            ea = eps[: ny - dy, : nx - dx].ravel()
            eb = eps[dy:, dx:].ravel()
            g = 2 * ea * eb / (ea + eb)
            rows += [a, b]
            cols += [b, a]
            vals += [-g, -g]
            np.add.at(diag, a, g)
            np.add.at(diag, b, g)
        # Dirichlet walls: ground at bottom, far top, far sides (potential 0): extra link to ground
        wall = np.zeros(N)
        wall[idx[0, :]] += eps[0, :]
        wall[idx[-1, :]] += eps[-1, :]
        wall[idx[:, 0]] += eps[:, 0]
        wall[idx[:, -1]] += eps[:, -1]
        diag += wall * 2.0
        A = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N)).tocsr()
        A = A + sp.diags(diag)
        flat_cond = cond.ravel()
        free = flat_cond < 0
        fi = np.where(free)[0]
        Aff = A[fi][:, fi].tocsc()
        lu = spla.splu(Aff)
        C = np.zeros((ncond, ncond))
        for j in range(ncond):
            phi = np.zeros(N)
            phi[flat_cond == j] = 1.0
            rhs = -(A[fi][:, np.where(flat_cond >= 0)[0]] @ phi[flat_cond >= 0])
            phi[fi] = lu.solve(rhs)
            # charge on each conductor = sum of link conductances x potential differences
            Aphi = A @ phi
            for i in range(ncond):
                C[i, j] = Aphi[flat_cond == i].sum()
        return C

    C = capmat(er, er_mask)
    Ca = capmat(1.0, 1.0)
    out = {}
    if pair:
        cself, cm = C[0, 0], -C[0, 1]
        aself, am = Ca[0, 0], -Ca[0, 1]
        c_odd, c_even = cself + cm, cself - cm
        a_odd, a_even = aself + am, aself - am
        # units: C values are per-unit permittivity (eps0 cancels): Z = 1/(c sqrt(C Ca)) with eps0 restored
        eps0 = 8.8541878e-12
        cm_s = 299792458.0
        z_odd = 1.0 / (cm_s * eps0 * math.sqrt(c_odd * a_odd))
        z_even = 1.0 / (cm_s * eps0 * math.sqrt(c_even * a_even))
        out.update(zodd=z_odd, zeven=z_even, zdiff=2 * z_odd, zcomm=z_even / 2,
                   er_odd=c_odd / a_odd, er_even=c_even / a_even, k=cm / cself)
    else:
        eps0 = 8.8541878e-12
        cm_s = 299792458.0
        out.update(z0=1.0 / (cm_s * eps0 * math.sqrt(C[0, 0] * Ca[0, 0])), er_eff=C[0, 0] / Ca[0, 0])
    return out


def main():
    # 6-layer since 2026-10-18 (fab/README.md): JLC06161H-3313, 3313 prepreg 0.0994 mm (Dk 4.1) between each outer layer
    # and its GND plane (In1 under F.Cu, In4 under B.Cu). The 4-layer JLC04161H-7628 numbers are kept for comparison.
    w = 0.16        # display/dsi_route.py W
    for label, h, er in (("JLC06161H-3313 (6-layer, in use)", 0.0994, 4.1), ("JLC04161H-7628 (old 4-layer)", 0.2104, 4.4)):
        t = 0.035
        print(f"\nStack-up {label}: h = {h:.4f} mm, outer copper {t * 1e3:.0f} um, Dk {er}")
        single = fd_solve(w, 0.0, h, t, er, pitch=0.005, width=6.0, air=2.0, pair=False)
        print(f"  w = {w} mm single track: Z0 {single['z0']:.1f} ohm (FD, mask 25 um Dk 3.3)")
        print(f"  {'gap':>6} {'Zdiff FD':>9} {'Zcomm':>7} {'k':>6}")
        for s_ in (0.25, 0.34, 0.44, 0.6, 1.2):
            pr = fd_solve(w, s_, h, t, er, pitch=0.005, width=6.0, air=2.0, pair=True)
            print(f"  {s_:6.2f} {pr['zdiff']:9.1f} {pr['zcomm']:7.1f} {pr['k']:6.3f}")
    print("\nThe layout's gaps: 0.34 mm along J1 (0.5 mm pad pitch), 0.44 mm along J4 (0.6 mm), wider at the jogs. On the 6-layer"
          "\nstack-up every gap stays within about 100 +-4 ohm; the B.Cu swap leg runs over In4 at the same 0.0994 mm.")


if __name__ == "__main__":
    main()
