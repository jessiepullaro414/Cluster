#!/usr/bin/env python3
"""
make_kelvin_footprint.py - a 1206 current-sense land pattern with Kelvin taps, written into a board's footprints/.

TI SNOSDF6 8.5.1 asks for a Kelvin connection from the LM74930's CS+ and CS- pins to the sense resistor. On an autorouted
board the two-pad land pattern leaves that to chance: a sense pin on the power net can tap it anywhere, and on gauges/ the
first route put about 10 mohm of inner-layer copper in series with the 5 mohm resistor (review/layout_checks.py, Kelvin
check), which would have tripped the 1.49 A breaker near 0.45 A. So the taps are nets of their own: this footprint is KiCad's
R_1206_3216Metric with two small extra pads, 3 and 4, each bridged to its terminal pad (1 and 2) by copper inside the
footprint and declared as a net tie. The resistor itself is the same two-terminal part; pads 3 and 4 take no solder (copper
only, covered by solder mask). The sense lines can then only reach the power path at the resistor's own terminals.

    python tools/make_kelvin_footprint.py        # writes gauges/footprints and brain/footprints
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = r"C:\Program Files\KiCad\10.0\share\kicad\footprints\Resistor_SMD.pretty\R_1206_3216Metric.kicad_mod"
NAME = "R_1206_3216Metric_Kelvin"
LIB = "Kelvin_R"

# Terminal pads: x +-1.4625, 1.125 x 1.75 mm, top edge at y = -0.875. The taps sit above their inner half, so the 0.45 mm gap
# keeps the board's 0.2 mm clearance while the router reaches them, and no track of another net fits through the gap.
TAP_X, TAP_Y, TAP = 1.15, -1.575, 0.5
BRIDGE_W, BRIDGE_TOP, BRIDGE_BOT = 0.25, TAP_Y + TAP / 2 + 0.05, -0.85
COURT_TOP = TAP_Y - TAP / 2 - 0.25


def bridge(x):
    x0, x1 = x - BRIDGE_W / 2, x + BRIDGE_W / 2
    return (f'\t(fp_poly\n\t\t(pts\n\t\t\t(xy {x0:.3f} {BRIDGE_TOP:.3f}) (xy {x1:.3f} {BRIDGE_TOP:.3f})'
            f' (xy {x1:.3f} {BRIDGE_BOT:.3f}) (xy {x0:.3f} {BRIDGE_BOT:.3f})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.Cu")\n\t)\n')


def tap(number, x):
    return (f'\t(pad "{number}" smd rect\n\t\t(at {x:.3f} {TAP_Y:.3f})\n\t\t(size {TAP} {TAP})\n'
            f'\t\t(layers "F.Cu")\n\t)\n')


def main():
    s = open(SRC, encoding="utf-8").read()
    s = s.replace('(footprint "R_1206_3216Metric"', f'(footprint "{NAME}"', 1)
    old = "(start -2.28 -1.13)"
    assert old in s, "KiCad's courtyard changed: check this script"
    s = s.replace(old, f"(start -2.28 {COURT_TOP:.3f})", 1)
    assert "(attr smd)" in s
    s = s.replace("(attr smd)", '(attr smd)\n\t(net_tie_pad_groups "1, 3" "2, 4")', 1)
    marker = '\t(pad "1" smd roundrect'
    assert marker in s
    s = s.replace(marker, bridge(-TAP_X) + bridge(TAP_X) + marker, 1)
    marker = "\t(embedded_fonts no)"
    assert marker in s
    s = s.replace(marker, tap(3, -TAP_X) + tap(4, TAP_X) + marker, 1)
    for board in ("gauges", "brain"):
        d = os.path.join(ROOT, board, "footprints", f"{LIB}.pretty")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{NAME}.kicad_mod"), "w", encoding="utf-8", newline="\n") as f:
            f.write(s)
        table = os.path.join(ROOT, board, "fp-lib-table")
        t = open(table, encoding="utf-8").read()
        if f'(name "{LIB}")' not in t:
            entry = (f'\t(lib (name "{LIB}") (type "KiCad") (uri "${{KIPRJMOD}}/footprints/{LIB}.pretty") (options "") '
                     f'(descr "1206 sense resistor with Kelvin taps as net-tied pads 3 and 4, made by tools/make_kelvin_footprint.py"))\n')
            i = t.rindex(")")
            t = t[:i] + entry + t[i:]
            open(table, "w", encoding="utf-8").write(t)
        print("wrote", os.path.join(d, f"{NAME}.kicad_mod"))


if __name__ == "__main__":
    main()
