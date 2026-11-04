#!/usr/bin/env python3
"""Time-step model of the two-wire VR speed input on gauges/ (J12, U13). Stdlib only.

    python review/vr_input_sim.py

The circuit (gauges/build_schematic.py, section "VR SPEED INPUT"):

    wire A -- R99 47k --+-- VR_FP --- R101 10k --+-- VR_P -- U13 IN+
                        |                        |
                     C68 4.7n, D35 clamp         +-- R102 680k -- U13 OUT (VR_SPEED_IN, to the MCU)

    wire B -- R100 47k -+-- VR_N ------------------------------ U13 IN-
                        |
                     C69 4.7n, D36 clamp, R103 2M to +3V3, R104 2M to GND

What it answers, with the parts at their tolerance corners:
  * the smallest sensor voltage that gives pulses, and how that moves with frequency
  * exactly one rising edge per tooth from there up to 120 V peak, the figure onsemi's AND8149 gives for what VR sensors
    can reach (the capture interrupt counts rising edges, so a second one reads as double speed)
  * no edges at all with the sensor unplugged
  * ignition-style spikes on the wires
  * one sensor wire grounded, as when the sensor also feeds a PCM that references it to ground
  * the stress on the series resistors and how much current reaches the clamps

It models the sensor as an EMF behind its coil resistance. The inductance (onsemi's example unit is 680 mH) is left out: at
1 kHz it is 4.3 k against the 94 k in the loop. It is a calculation, not a measurement: nothing here has been built.
"""
import math
import os
import sys

VCC = 3.3
R_S = 47e3                    # R99, R100
R_I = 10e3                    # R101
R_F = 680e3                   # R102
R_UP = R_DN = 2e6             # R103, R104
C_LEG = 4.7e-9                # C68, C69
CLAMP_V = 0.6                 # BAV99-Q forward drop into the rails: enough for these currents, and a hard limit keeps the model stable
VHYS = 6.5e-3                 # TLV7031-Q1 internal hysteresis at 25 C; datasheet range 2..17 mV
VOS = 0.0                     # input offset, datasheet +-8 mV maximum
R_COIL = 220.0                # Ford lists 190..250 ohm for this sensor


class Parts:
    def __init__(self, r_s=R_S, r_i=R_I, r_f=R_F, r_up=R_UP, r_dn=R_DN, c_p=C_LEG, c_n=C_LEG, vhys=VHYS, vos=VOS, r_coil=R_COIL):
        self.__dict__.update(locals())


def corners():
    """The corners that widen or narrow the threshold most, and shift it to one side."""
    yield "nominal", Parts()
    yield "offset +8 mV, hysteresis 17 mV, caps +-10 %", Parts(vos=8e-3, vhys=17e-3, c_p=C_LEG * 1.1, c_n=C_LEG * 0.9)
    yield "offset -8 mV, hysteresis 2 mV, caps -+10 %", Parts(vos=-8e-3, vhys=2e-3, c_p=C_LEG * 0.9, c_n=C_LEG * 1.1)
    yield "resistors high (+1 %), 2.5 k coil", Parts(r_s=R_S * 1.01, r_f=R_F * 0.99, r_i=R_I * 1.01, r_coil=2500.0)


def simulate(p, emf, t_end, dt, grounded_b=False, sensor=True, out0=False, settle=0.0):
    """Returns (rising edge times, worst clamp current in A). emf(t) is the sensor voltage, wire A positive."""
    v_fp, v_n = VCC / 2, VCC / 2
    out = out0
    edges = []
    i_clamp = 0.0
    t = 0.0
    g_fb = 1.0 / (p.r_f + p.r_i)
    k_i = 1.0 / p.r_i
    k_f = 1.0 / p.r_f
    while t < t_end:
        v_out = VCC if out else 0.0
        e = emf(t) if sensor else 0.0
        if not sensor:
            i_link = 0.0
            i_b = 0.0
        elif grounded_b:
            i_link = (e - v_fp) / (p.r_s + p.r_coil)        # wire B is at board ground: only wire A's leg carries the sensor current
            i_b = -v_n / p.r_s
        else:
            i_link = (v_n + e - v_fp) / (2 * p.r_s + p.r_coil)   # N -> R100 -> coil and EMF -> R99 -> FP
            i_b = -i_link
        d_fp = i_link + (v_out - v_fp) * g_fb
        d_n = i_b + (VCC - v_n) / p.r_up - v_n / p.r_dn
        v_fp += d_fp * dt / p.c_p
        v_n += d_n * dt / p.c_n
        for name in ("fp", "n"):
            v = v_fp if name == "fp" else v_n
            limit = None
            if v > VCC + CLAMP_V:
                limit = VCC + CLAMP_V
            elif v < -CLAMP_V:
                limit = -CLAMP_V
            if limit is not None:
                i_clamp = max(i_clamp, abs(d_fp if name == "fp" else d_n))
                if name == "fp":
                    v_fp = limit
                else:
                    v_n = limit
        v_p = (v_fp * k_i + v_out * k_f) / (k_i + k_f)
        diff = v_p - v_n - p.vos
        if not out and diff > p.vhys / 2:
            out = True
            if t >= settle:
                edges.append(t)
        elif out and diff < -p.vhys / 2:
            out = False
        t += dt
    return edges, i_clamp


def edges_per_cycle(p, amp, freq, cycles=6, settle_cycles=3, **kw):
    period = 1.0 / freq
    dt = min(5e-6, period / 400) if freq > 200 else min(20e-6, period / 400)
    emf = lambda t: amp * math.sin(2 * math.pi * freq * t)   # noqa: E731
    settle = settle_cycles * period
    edges, ic = simulate(p, emf, settle + cycles * period, dt, settle=settle, **kw)
    return len(edges) / cycles, ic


def threshold(p, freq, **kw):
    """Smallest EMF peak with a steady one rising edge per cycle (bisection on a log scale)."""
    lo, hi = 0.01, 20.0
    for _ in range(11):
        mid = math.sqrt(lo * hi)
        rate, _ = edges_per_cycle(p, mid, freq, cycles=4, settle_cycles=2, **kw)
        if abs(rate - 1.0) < 0.01:
            hi = mid
        else:
            lo = mid
    return hi


def main():
    fails = []

    def check(ok, what):
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            fails.append(what)

    # the model must be of the circuit on the board, not of what the circuit once was
    sch = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gauges", "build_schematic.py"), encoding="utf-8").read()
    for ref, value in (("R99", "47k"), ("R100", "47k"), ("R101", "10k"), ("R102", "680k"), ("R103", "2M"), ("R104", "2M"),
                       ("C68", "4.7nF"), ("C69", "4.7nF")):
        check(f'"{ref}", "{value} ' in sch, f"{ref} is {value} in gauges/build_schematic.py, as modelled here")

    print("Smallest EMF that gives pulses (volts peak), floating sensor:")
    print(f"  {'':46s} {'10 Hz':>7s} {'100 Hz':>7s} {'500 Hz':>7s} {'1 kHz':>7s} {'2 kHz':>7s}")
    worst = 0.0
    for name, p in corners():
        row = [threshold(p, f) for f in (10.0, 100.0, 500.0, 1000.0, 2000.0)]
        worst = max(worst, row[0])
        print(f"  {name:46s} " + " ".join(f"{v:7.3f}" for v in row))
    check(worst < 0.2, f"worst low-speed threshold {worst * 1000:.0f} mV peak: below the 100-250 mV AC a healthy VR sensor gives turned by hand")
    p = Parts()
    t10 = threshold(p, 10.0)
    check(t10 > 0.05, f"nominal threshold {t10 * 1000:.0f} mV peak: well above the comparator's own offset and hysteresis")

    print("\nExactly one rising edge per tooth, up to 120 V peak:")
    bad = []
    tried = 0
    for name, c in corners():
        for f in (3.0, 10.0, 60.0, 300.0, 700.0, 1400.0, 2000.0):
            floor = 1.3 * threshold(c, f)         # a sensor's EMF rises with frequency, so 0.3 V at 2 kHz is not a real case
            for amp in (0.3, 1.0, 3.0, 10.0, 40.0, 120.0):
                if amp < floor:
                    continue
                tried += 1
                rate, ic = edges_per_cycle(c, amp, f)
                if abs(rate - 1.0) > 0.01:
                    bad.append((name, f, amp, rate))
    check(not bad, f"{tried} frequency, amplitude and corner combinations above the threshold: {'every one' if not bad else bad[:6]}")

    print("\nOne wire grounded (a sensor shared with a PCM that references it to ground):")
    tg = threshold(p, 10.0, grounded_b=True)
    print(f"  threshold {tg * 1000:.0f} mV peak (offset toward one side, because wire B no longer floats)")
    badg = [(f, a) for f in (10.0, 100.0, 700.0) for a in (0.5, 3.0, 40.0, 120.0)
            if abs(edges_per_cycle(p, a, f, grounded_b=True)[0] - 1.0) > 0.01]
    check(tg < 0.35 and not badg, f"still one edge per tooth, threshold under 350 mV: {badg or 'yes'}")

    print("\nSensor unplugged:")
    for out0 in (False, True):
        edges, _ = simulate(p, lambda t: 0.0, 0.5, 20e-6, sensor=False, out0=out0, settle=0.02)
        check(not edges, f"no edges with the output starting {'high' if out0 else 'low'}, so the firmware sees an absent sensor")

    print("\nIgnition-style spikes (1 us, 400 Hz: a V8 at 6000 rpm) with a weak sensor signal, 0.4 V peak at 20 Hz:")
    period = 1.0 / 20.0

    def spiky(vs, width=1e-6, rate=400.0):
        return lambda t: 0.4 * math.sin(2 * math.pi * 20.0 * t) + (vs if (t * rate) % 1.0 < width * rate else 0.0)

    for vs in (5.0, 10.0, 20.0):
        edges, _ = simulate(p, spiky(vs), 8 * period, 1e-6, settle=2 * period)
        n = len(edges) / 6
        print(f"  {vs:4.0f} V differential spike: {n:.2f} rising edges per tooth")
        check(abs(n - 1.0) < 0.01, f"{vs:.0f} V differential spikes on the wires add no edges")
    # the firmware's own blanking is the second line: an edge sooner than half the last period is dropped (capture.c)

    print("\nStress at 120 V peak:")
    rate, ic = edges_per_cycle(p, 120.0, 300.0)
    vrms = 120.0 / math.sqrt(2)
    # the loop holds the two series resistors and little else once the clamps conduct
    p_r = (vrms / 2) ** 2 / R_S
    print(f"  clamp current {ic * 1000:.2f} mA (BAV99-Q 215 mA; comparator input limit 10 mA, and R101 keeps IN+ out of it)")
    print(f"  each 47 k: {60:.0f} V peak across it when both clamps conduct, {p_r * 1000:.0f} mW; if the far leg were tied down, 120 V peak, {vrms ** 2 / R_S * 1000:.0f} mW")
    check(ic < 10e-3, "clamp current under the TLV7031-Q1's 10 mA limit")
    check(vrms ** 2 / R_S < 0.2, "each 47 k stays under 0.2 W (AC1206: 0.25 W, 200 V)")

    print("\nKey-off cost: R103 + R104 draw {:.2f} uA from +3V3 and U13 0.32 uA (datasheet typical), about 1 uA from the battery".format(VCC / (R_UP + R_DN) * 1e6))

    print()
    if fails:
        print(f"{len(fails)} FAILED")
        return 1
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
