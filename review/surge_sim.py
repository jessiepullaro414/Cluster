#!/usr/bin/env python3
"""
surge_sim.py - ISO 7637-2 / ISO 16750-2 style pulses through the 12 V front end.

Both boards use the same stage: fuse -> TVS (SMCJ33A) -> LM74930-Q1 with two
PMV55ENEA (load switch Q3 + ideal diode Q1) and a 5 mohm / 2 mohm sense resistor ->
bulk capacitor -> buck. The model is a lumped, time-domain one (scipy Radau):

    source Us(t), Ri  --  harness + fuse R  --  [VIN_FUSED: TVS to GND]  --  R49 + Q3 + Q1
        --  [VIN_PROT: Cin, buck as a constant-power load]

  * TVS: knee at VBR(min), slope (Vc(max) - VBR(typ)) / Ipp, forward diode for negative pulses.
  * LM74930 overvoltage clamp: when VIN_PROT reaches the clamp threshold Q3 turns linear and holds
    VIN_PROT there (smooth controller, 0.3 V proportional band); Q3 then dissipates
    (Vin - Vclamp) x I and the 'overvoltage clamp circuit-breaker' timer starts
    (T = 1.2 V x CTMR / 2.8 uA, SNOSDF6 eq. 8).
  * Q1 (ideal diode) blocks reverse current: modelled as a diode with the FET's RDS(on).

What this is NOT: a SPICE run with package parasitics. It gives first-order stress numbers
(peak voltages, TVS current and energy, fuse I2t, Q3 power and time) that are compared with
each part's absolute maximum. Waveform parameters are those of ISO 7637-2:2011 / ISO 16750-2:2012
for 12 V systems as I know them (the standards themselves are not in the repository, so verify the
Ri/td values before quoting a compliance claim); the pulse amplitudes are the Level IV values
the TCAN1044-Q1 datasheet (SLLSF17D, 6.3) lists: pulse 1 -100 V, 2a +75 V, 3a -150 V, 3b +100 V.

    python review/surge_sim.py            # prints the tables
    python review/surge_sim.py --json out.json
"""
import argparse
import json
import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# device data (datasheet numbers; see docs/electrical-review.md for sources)
# ---------------------------------------------------------------------------
TVS = {   # SMCJ33A (1500 W class): VBR 36.7..40.6 V, VC <= 53.3 V at IPP 28.2 A (10/1000 us), distributor-listed
    "SMCJ33A": dict(vbr_min=36.7, vbr_typ=38.6, vc=53.3, ipp=28.2, ppk=1500.0, vf0=0.8, rf=0.04),
    "SMBJ33A": dict(vbr_min=36.7, vbr_typ=38.6, vc=53.3, ipp=11.3, ppk=600.0, vf0=0.8, rf=0.1),
}


def tvs_current(v, t):
    """Current into the TVS (positive = from the protected node to GND)."""
    if v > t["vbr_min"]:
        rd = (t["vc"] - t["vbr_typ"]) / t["ipp"]
        return (v - t["vbr_min"]) / rd
    if v < -t["vf0"]:
        return (v + t["vf0"]) / t["rf"]        # forward conduction, negative current
    return 0.0


def tvs_ppk(t, tp):
    """Rectangular-equivalent peak power rating at pulse width tp (s): the 10/1000 us rating scaled
    with the usual 1500 W class slope (~ t^-0.55 between 10 us and 10 ms). An approximation of the
    family's published curve (the curve itself is not retrievable offline)."""
    return t["ppk"] * (1e-3 / max(tp, 1e-6)) ** 0.55


BOARDS = {
    "gauges": dict(
        # c_in: C1 10 uF + C59 + C60 (10 uF 50 V X7S 1210 each) derated to ~3.5 uF each near the 30 V clamp, plus 0.22 uF
        label="gauges/ (with C59, C60)", tvs="SMCJ33A", r_fuse=0.08, r_path=0.005 + 0.06 + 0.06, c_in=10.5e-6,
        # R49 5 mohm + Q3 + Q1 (PMV55ENEA RDSon 60 mohm max at VGS 10 V)
        p_load=1.8, clamp=(27.8, 29.9, 31.0), ctmr=100e-9, fuse="2 A MINI (Littelfuse 297)", fuse_a=2.0,
        vlim=dict(U3_VS_CS=70.0, Q_VDS=60.0, buck_abs=38.0, buck_op=36.0, C1_rating=50.0, TJA1043_VBAT=40.0),
    ),
    "gauges_before": dict(
        label="gauges/ before the review (C1 only)", tvs="SMCJ33A", r_fuse=0.08, r_path=0.005 + 0.06 + 0.06, c_in=3.5e-6,
        p_load=1.8, clamp=(27.8, 29.9, 31.0), ctmr=100e-9, fuse="2 A MINI (Littelfuse 297)", fuse_a=2.0,
        vlim=dict(U3_VS_CS=70.0, Q_VDS=60.0, buck_abs=38.0, buck_op=36.0, C1_rating=50.0, TJA1043_VBAT=40.0),
    ),
    "display": dict(
        label="display/", tvs="SMCJ33A", r_fuse=0.03, r_path=0.002 + 0.06 + 0.06, c_in=100e-6 + 2 * 3.0e-6,
        p_load=12.0, clamp=(27.8, 29.9, 31.0), ctmr=100e-9, fuse="5 A MINI (Littelfuse 0297005)", fuse_a=5.0,
        vlim=dict(U1_VS_CS=70.0, Q_VDS=60.0, buck_abs=42.0, buck_op=36.0, C1_rating=35.0),
    ),
}

PULSES = [
    # name, shape, Us (V), Ri (ohm), td (s), t_end (s)
    ("ISO 7637-2 pulse 1 (Level IV)", "exp", -100.0, 10.0, 2e-3, 8e-3),
    ("ISO 7637-2 pulse 2a (Level IV)", "exp", 75.0, 2.0, 50e-6, 400e-6),
    ("ISO 7637-2 pulse 3a (Level IV), one 100 ns pulse", "exp", -150.0, 50.0, 150e-9, 2e-6),
    ("ISO 7637-2 pulse 3b (Level IV), one 100 ns pulse", "exp", 100.0, 50.0, 150e-9, 2e-6),
    ("27 V load dump, 400 ms (owner's figure), Ri 2 ohm", "flat", 27.0, 2.0, 0.4, 3e-3),
    ("35 V suppressed load dump (ISO 16750-2 test B), 400 ms, Ri 2 ohm", "flat", 35.0, 2.0, 0.4, 3e-3),
    ("24 V jump start, 60 s (steady)", "flat", 24.0, 0.2, 60.0, 61.0),
    ("Unsuppressed load dump 101 V, 400 ms, Ri 2 ohm (ISO 16750-2 test A)", "flat", 101.0, 2.0, 0.4, 3e-3),
    ("Reverse battery -14 V, 60 s", "flat", -14.0, 0.01, 60.0, 61.0),
]


def source(shape, us, td):
    if shape == "exp":
        tau = td / math.log(10) * 1.0
        return lambda t: us * math.exp(-t / tau) if t >= 0 else 0.0
    # flat pulse with 10 us ramp (ISO 16750-2 rise times are ms; faster is the conservative case)
    return lambda t: us * min(1.0, max(0.0, t / 10e-6)) if t < td else 0.0


T_OV_OFF = 5.5e-6     # HGATE turn-off de-glitch on OV (SNOSDF6 6.6: 4 us typ .. 7 us max; 5.5 us used)
T_OV_ON = 9e-6        # HGATE turn-on de-glitch after OV clears (SNOSDF6 6.6: 9 us)


def run(board, pulse, clamp_v):
    """Backward-Euler integration of VIN_PROT with the LM74930 OV clamp modelled as a hysteretic
    controller with the datasheet's de-glitch delays (the thing that lets a fast pulse overshoot)."""
    b = BOARDS[board]
    name, shape, us, ri, td, t_end = pulse
    tvs = TVS[b["tvs"]]
    vs = source(shape, us, td)
    r_up = ri + b["r_fuse"] + 0.05
    r_path, c_in = b["r_path"], b["c_in"]
    pl = b["p_load"]
    ov_hi = clamp_v                       # OV rising threshold (V)
    ov_lo = clamp_v * 0.55 / 0.6          # OV falling threshold, same divider
    r_off = 1e5

    def i_load(vp):
        return pl / max(vp, 6.0) if vp > 5.0 else 0.0

    def vf_of(vp, t, r_q):
        def f(vf):
            ip = max(0.0, (vf - vp) / r_q)
            return (vs(t) - vf) / r_up - tvs_current(vf, tvs) - ip
        return brentq(f, -10.0, 200.0, xtol=1e-7)

    t = 0.0
    vp = 13.0
    q3_on = True
    timer = 0.0
    log = []
    t_clamp_on = 0.0
    while t < t_end:
        # step size: fine near the clamp, pulse edges and the short pulses
        near = (vp > ov_lo - 2.0) and (vs(t) > ov_lo or q3_on is False)
        dt = 0.25e-6 if near else (t_end / 3000.0 if t_end > 1e-3 else t_end / 2000.0)
        dt = min(dt, 0.25e-6) if (td < 1e-5 and t < 5 * td) else dt
        dt = max(dt, 1e-10)
        r_q = r_path if q3_on else r_off
        # backward Euler for vp
        def g(vn):
            vf = vf_of(vn, t + dt, r_q)
            ip = max(0.0, (vf - vn) / r_q)
            return vn - vp - dt / c_in * (ip - i_load(vn))
        try:
            vn = brentq(g, 0.0, 200.0, xtol=1e-7)
        except ValueError:
            vn = vp
        vf = vf_of(vn, t + dt, r_q)
        ip = max(0.0, (vf - vn) / r_q)
        t += dt
        vp = vn
        # controller with de-glitch
        if q3_on:
            timer = timer + dt if vp > ov_hi else 0.0
            if timer >= T_OV_OFF:
                q3_on, timer = False, 0.0
        else:
            timer = timer + dt if vp < ov_lo else 0.0
            if timer >= T_OV_ON:
                q3_on, timer = True, 0.0
        q3p = max(0.0, vf - ip * (r_path - 0.06) - vp) * ip if q3_on else 0.0
        log.append((t, vf, vp, tvs_current(vf, tvs), (vs(t) - vf) / r_up, q3p, 0 if q3_on else 1, ip))
    arr = np.array(log)
    ts, vfs, vps, itvs, ifuse, q3, off, ips = arr.T
    dts = np.diff(ts, prepend=ts[0])
    e_tvs = float(np.sum(np.where(itvs > 0, itvs * vfs, 0.0) * dts))
    i2t = float(np.sum(ifuse ** 2 * dts))
    # average Q3 dissipation while the clamp cycles (after the first 5 % of the pulse)
    mask = ts > min(td * 0.05, 0.2e-3)
    q3_avg = float(np.mean(q3[mask])) if mask.any() else 0.0
    clamp_cycles = int(np.sum(np.diff(off) == 1))
    return dict(
        pulse=name, vf_peak=float(vfs.max()), vf_min=float(vfs.min()), vp_peak=float(vps.max()),
        itvs_peak=float(itvs.max()), itvs_fwd=float(-itvs.min()) if itvs.min() < 0 else 0.0,
        e_tvs=e_tvs, p_tvs_peak=float(np.max(itvs * np.maximum(vfs, 0))),
        ifuse_peak=float(np.max(np.abs(ifuse))), fuse_i2t=i2t,
        q3_p_peak=float(q3.max()), q3_p_avg=q3_avg, clamp_cycles=clamp_cycles,
        t_clamp=(td if clamp_cycles > 0 or off.max() > 0 else 0.0) if shape == "flat" else 0.0,
        q1_vds_rev=float(np.max(vps - np.minimum(vfs, 0.0))), tp=td,
    )


def report(board, clamp_idx=1):
    b = BOARDS[board]
    cl = b["clamp"][clamp_idx]
    rows = []
    for p in PULSES:
        if p[0].startswith("24 V jump") or p[0].startswith("Reverse"):
            # steady-state, algebraic: no need to integrate 60 s
            rows.append(steady(board, p))
            continue
        rows.append(run(board, p, cl))
    return rows


def steady(board, pulse):
    b = BOARDS[board]
    name, shape, us, ri, td, t_end = pulse
    tvs = TVS[b["tvs"]]
    r_up = ri + b["r_fuse"] + 0.05
    vp = min(us - 0.3, b["clamp"][1]) if us > 0 else 0.0

    def f(vf):
        ip = max(0.0, (vf - vp) / b["r_path"]) if us > 0 else 0.0
        return (us - vf) / r_up - tvs_current(vf, tvs) - ip
    vf = brentq(f, -30, 60)
    itvs = tvs_current(vf, tvs)
    ifuse = (us - vf) / r_up
    return dict(pulse=name, vf_peak=max(vf, 0), vf_min=min(vf, 0), vp_peak=vp, itvs_peak=max(itvs, 0), itvs_fwd=max(-itvs, 0),
                e_tvs=0.0, p_tvs_peak=max(itvs, 0) * max(vf, 0), ifuse_peak=abs(ifuse), fuse_i2t=ifuse ** 2 * td,
                q3_p_peak=0.0, q3_p_avg=0.0, clamp_cycles=0, t_clamp=0.0, q1_vds_rev=(b["clamp"][1] if us < 0 else 0) + (abs(vf) if us < 0 else 0), tp=td)


def judge(board, r):
    """List of (severity, message) comparing a result with absolute maxima."""
    b = BOARDS[board]
    out = []
    lim = b["vlim"]
    vs_lim = lim.get("U3_VS_CS", lim.get("U1_VS_CS"))
    if r["vf_peak"] > vs_lim:
        out.append(("FAIL", f"VIN_FUSED {r['vf_peak']:.1f} V > LM74930 VS/CS/A abs max {vs_lim:.0f} V"))
    if r["vf_peak"] > 0.9 * 60 and r["vf_peak"] <= vs_lim:
        pass
    if r["vp_peak"] > lim["buck_abs"]:
        out.append(("FAIL", f"VIN_PROT {r['vp_peak']:.1f} V > buck abs max {lim['buck_abs']:.0f} V"))
    elif r["vp_peak"] > lim["buck_op"]:
        out.append(("WARN", f"VIN_PROT {r['vp_peak']:.1f} V above the buck's {lim['buck_op']:.0f} V operating maximum"))
    if r["q1_vds_rev"] > lim["Q_VDS"]:
        out.append(("FAIL", f"Q1 reverse VDS {r['q1_vds_rev']:.0f} V > {lim['Q_VDS']:.0f} V"))
    t = TVS[b["tvs"]]
    if r["itvs_peak"] > 0 and r["tp"] > 0:
        pr = tvs_ppk(t, min(r["tp"], 10.0))
        if r["p_tvs_peak"] > pr:
            out.append(("FAIL", f"TVS peak power {r['p_tvs_peak']:.0f} W > ~{pr:.0f} W allowed at this pulse width"))
    if r["ifuse_peak"] > b["fuse_a"] * 4 and r["tp"] >= 1.0:
        out.append(("WARN", f"fuse carries {r['ifuse_peak']:.0f} A for {r['tp']:.0f} s: it will open (reverse battery / fault)"))
    if r["t_clamp"] > 1.2 * b["ctmr"] / 2.8e-6:
        out.append(("WARN", f"OV clamp active {r['t_clamp'] * 1e3:.0f} ms > breaker time {1.2 * b['ctmr'] / 2.8e-6 * 1e3:.0f} ms: board powers down and retries"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    allres = {}
    for board in BOARDS:
        b = BOARDS[board]
        print(f"\n=== {b['label']}  fuse {b['fuse']}, TVS {b['tvs']}, Cin {b['c_in'] * 1e6:.1f} uF, load {b['p_load']:.1f} W, "
              f"OV clamp {b['clamp'][0]}/{b['clamp'][1]}/{b['clamp'][2]} V, breaker {1.2 * b['ctmr'] / 2.8e-6 * 1e3:.0f} ms")
        print(f"{'pulse':<72} {'VIN_FUSED':>10} {'VIN_PROT':>9} {'TVS I':>7} {'TVS P':>7} {'fuse I':>7} {'Q3 Ppk':>7} {'Q3 Pavg':>8} {'clamp':>7}")
        res = report(board)
        allres[board] = res
        for r in res:
            print(f"{r['pulse'][:72]:<72} {r['vf_min']:6.1f}/{r['vf_peak']:<4.1f} {r['vp_peak']:9.1f} {max(r['itvs_peak'], r['itvs_fwd']):6.1f}A "
                  f"{r['p_tvs_peak']:6.0f}W {r['ifuse_peak']:6.1f}A {r["q3_p_peak"]:5.1f}W {r["q3_p_avg"]:5.2f}W {r["t_clamp"] * 1e3:5.0f}ms")
            for sev, msg in judge(board, r):
                print(f"      {sev}: {msg}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(allres, f, indent=1)


if __name__ == "__main__":
    main()
