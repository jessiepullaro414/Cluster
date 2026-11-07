"""
usb1_topology.py - brain/'s USB_1 pair: its shape on the routed board, and what the
branch that isn't in use does at 480 Mbit/s.

Since 2026-11-06 the pair goes from the module's pins (J1 163, 165) to two places: the
USB-C port J19 through the common-mode choke L3 and the ESD array U17, and the bench header
J13. Whichever one isn't plugged in is an open stub on the other's path. This reads the real tracks for the
lengths, then estimates the loss with a plain chain-matrix model of the differential
half circuit.

CALCULATED, NOT MEASURED. The route is planned by brain/usb_route.py at about 45 ohm per
line, 90 ohm differential, by field solve (review/dsi_impedance.py); the board house's
tolerance isn't in this. Capacitances are datasheet or estimates, as noted below. What
decides is an eye test on a real board (docs/audio-and-usb.md section 2a).
"""
import cmath
import heapq
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kmodel import Layout  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
PCB = os.path.join(ROOT, "brain", "ClusterBrain.kicad_pcb")

Z0 = 45.0               # ohm per line: USB 2.0's 90 ohm differential
V_MM_NS = 170.0         # mm/ns: effective Dk about 3.08 on the outer layers, from the field solve
C_VIA = 0.4e-12         # F per line: the branch's via. Estimate
C_ESD = 0.5e-12         # F per line: TPD4E05U06-Q1, 0.5 pF (BOM, TI SLVSCO7C)
C_USBC = 0.5e-12        # F per line: receptacle contact and pads. Estimate
C_HEADER = 1.0e-12      # F per line: through-hole header pad and an empty pin. Estimate
L_CHOKE = 2.0e-9        # H per line: L3's leakage, from Wurth's differential impedance curve (744230900 page 2, about 25 ohm at 1 GHz, read off a plot)
L3_THROUGH = 1.45       # mm, pad centre to pad centre across L3, counted as length
FREQS = (240e6, 480e6, 720e6, 1200e6)   # fundamental at 480 Mbit/s, its 2nd, 3rd and 5th multiples


def graph(lay, nets):
    """Nodes are track ends and vias, keyed by position (the layer doesn't matter for length)."""
    adj = {}
    key = lambda x, y: (round(x, 2), round(y, 2))

    def link(a, b, w):
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))

    segs = [t for t in lay.tracks if t["net"] in nets]
    for t in segs:
        link(key(t["x1"], t["y1"]), key(t["x2"], t["y2"]), math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]))
    # A pad joins whatever ends on it (J19's B7 has one track on each end)
    for (_ref, _num), lst in lay.pads.items():
        for p in lst:
            if p["net"] not in nets:
                continue
            on = [n for n in adj if abs(n[0] - p["x"]) <= p["w"] / 2 and abs(n[1] - p["y"]) <= p["h"] / 2]
            for a, b in zip(on, on[1:]):
                link(a, b, 0.0)
    return adj, segs


def at_pad(lay, adj, ref, pin):
    """The graph node on a pad."""
    p = lay.pads[(ref, str(pin))][0]
    best, bd = None, 1e9
    for n in adj:
        d = math.hypot(n[0] - p["x"], n[1] - p["y"])
        if d < bd:
            best, bd = n, d
    if bd > max(p["w"], p["h"]):
        raise SystemExit(f"no track reaches {ref} pad {pin} (nearest {bd:.2f} mm)")
    return best


def dijkstra(adj, start):
    dist, prev = {start: 0.0}, {}
    q = [(0.0, start)]
    while q:
        d, n = heapq.heappop(q)
        if d > dist[n]:
            continue
        for m, w in adj[n]:
            if d + w < dist.get(m, 1e18):
                dist[m], prev[m] = d + w, n
                heapq.heappush(q, (d + w, m))
    return dist, prev


def path(prev, n):
    out = [n]
    while n in prev:
        n = prev[n]
        out.append(n)
    return out[::-1]


def measure(lay, nets, j1_pin, j13_pin, u17_pin, j19_pins, l3_pins):
    adj, segs = graph(lay, nets)
    l3_m, l3_c = at_pad(lay, adj, "L3", l3_pins[0]), at_pad(lay, adj, "L3", l3_pins[1])
    adj[l3_m].append((l3_c, L3_THROUGH))
    adj[l3_c].append((l3_m, L3_THROUGH))
    start = at_pad(lay, adj, "J1", j1_pin)
    dist, prev = dijkstra(adj, start)
    to_13 = at_pad(lay, adj, "J13", j13_pin)
    to_17 = at_pad(lay, adj, "U17", u17_pin)
    to_19 = max((at_pad(lay, adj, "J19", p) for p in j19_pins), key=lambda n: dist[n])
    common = None
    for a, b in zip(path(prev, to_13), path(prev, to_19)):
        if a != b:
            break
        common = a
    return dict(
        total=sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in segs),
        layers=sorted({t["layer"] for t in segs}),
        to_j13=dist[to_13], to_u17=dist[to_17], to_j19=dist[to_19], to_l3=dist[l3_m],
        tee=dist[common], tee_at=common,
        j13_branch=dist[to_13] - dist[common], j19_branch=dist[to_19] - dist[common],
    )


def line(l_mm, f):
    th = 2j * math.pi * f * (l_mm / V_MM_NS) * 1e-9
    return ((cmath.cosh(th), Z0 * cmath.sinh(th)), (cmath.sinh(th) / Z0, cmath.cosh(th)))


def shunt(y):
    return ((1, 0), (y, 1))


def series(z):
    return ((1, z), (0, 1))


def mul(a, b):
    return ((a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]),
            (a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]))


def open_stub_y(l_mm, c_end, f):
    """Admittance looking into an open line with a capacitor at its far end."""
    th = 2j * math.pi * f * (l_mm / V_MM_NS) * 1e-9
    yl = 2j * math.pi * f * c_end
    t = cmath.tanh(th)
    return (1 / Z0) * (yl + t / Z0) / (1 / Z0 + yl * t)


def s21_db(chain):
    (a, b), (c, d) = chain
    s21 = 2 / (a + b / Z0 + c * Z0 + d)
    return 20 * math.log10(abs(s21))


def j19_in_use(m, f):
    """Module to J19, with J13 empty: the J13 branch is the stub."""
    w = 2j * math.pi * f
    ch = line(m["tee"], f)
    ch = mul(ch, shunt(open_stub_y(m["j13_branch"], C_HEADER, f) + w * C_VIA))
    ch = mul(ch, line(max(m["to_l3"] - m["tee"], 0.0), f))
    ch = mul(ch, series(w * L_CHOKE))
    ch = mul(ch, line(max(m["to_u17"] - m["to_l3"], 0.0), f))
    ch = mul(ch, shunt(w * C_ESD))
    ch = mul(ch, line(max(m["to_j19"] - m["to_u17"], 0.0), f))
    return mul(ch, shunt(w * C_USBC))


def j13_in_use(m, f):
    """J13 to the module, with J19 empty: the J19 branch and its ESD array are the stub."""
    w = 2j * math.pi * f
    # the stub seen from the tee: line to U17, the array, line to J19's contacts
    y_end = open_stub_y(max(m["to_j19"] - m["to_u17"], 0.0), C_USBC, f) + w * C_ESD

    def through_line(y, l_mm):
        t = cmath.tanh(2j * math.pi * f * (l_mm / V_MM_NS) * 1e-9)
        return (1 / Z0) * (y + t / Z0) / (1 / Z0 + y * t)
    y_l3 = through_line(y_end, max(m["to_u17"] - m["to_l3"], 0.0))
    y_l3 = 1 / (1 / y_l3 + w * L_CHOKE)
    y_stub = through_line(y_l3, max(m["to_l3"] - m["tee"], 0.0))
    ch = line(m["j13_branch"], f)
    ch = mul(ch, shunt(w * C_VIA))
    ch = mul(ch, shunt(y_stub))
    return mul(ch, line(m["tee"], f))


def main():
    lay = Layout(PCB)
    p = measure(lay, ("USB_DP", "USB1_C_DP"), 165, 3, 1, ["A6", "B6"], ("2", "1"))
    n = measure(lay, ("USB_DN", "USB1_C_DN"), 163, 2, 2, ["A7", "B7"], ("3", "4"))
    print("USB_1 pair on the routed board (mm):")
    print("  net      total  module->J19  module->U17  module->J13  shared  J13 branch  J19 branch  layers")
    for name, m in (("USB_DP", p), ("USB_DN", n)):
        print(f"  {name:7s}{m['total']:7.1f}{m['to_j19']:13.1f}{m['to_u17']:13.1f}{m['to_j13']:13.1f}"
              f"{m['tee']:8.1f}{m['j13_branch']:12.1f}{m['j19_branch']:12.1f}  {','.join(str(x) for x in m['layers'])}")
    print(f"  skew module->J19: {abs(p['to_j19'] - n['to_j19']):.1f} mm, {abs(p['to_j19'] - n['to_j19']) / V_MM_NS * 1e3:.0f} ps")
    m = dict((k, max(p[k], n[k])) for k in ("tee", "j13_branch", "j19_branch", "to_l3", "to_u17", "to_j19", "to_j13"))
    print("\nInsertion loss, calculated (dB), longer leg of the pair, " + f"{Z0:.0f} ohm per line:")
    print("  use                                " + "".join(f"{f / 1e6:9.0f} MHz" for f in FREQS))
    print("  J19 in use, J13 empty (or a PC on J19)" + "".join(f"{s21_db(j19_in_use(m, f)):13.2f}" for f in FREQS))
    print("  J13 in use, J19 empty                 " + "".join(f"{s21_db(j13_in_use(m, f)):13.2f}" for f in FREQS))
    vq = V_MM_NS / (4 * m["j19_branch"]) * 1e3
    print(f"\nJ19 branch as a stub: quarter-wave notch near {vq:.0f} MHz, without its capacitors.")
    print(f"J13 branch as a stub: {m['j13_branch']:.1f} mm, {m['j13_branch'] / V_MM_NS * 1e3:.0f} ps one way, about {(m['j13_branch'] * 0.12e-12 + C_VIA + C_HEADER) * 1e12:.1f} pF per line with the via and the empty header.")


if __name__ == "__main__":
    main()
