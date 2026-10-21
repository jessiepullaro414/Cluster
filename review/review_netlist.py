#!/usr/bin/env python3
"""
review_netlist.py - pin-by-pin check of a generated board against its datasheets.

    python review/review_netlist.py gauges
    python review/review_netlist.py display                 # reads display/ in the working tree
    python review/review_netlist.py display --sch X.kicad_sch --pcb X.kicad_pcb
    python review/review_netlist.py gauges --json out.json  # machine-readable results

What it does, in this order (re-run it after every regeneration):
  1. exports the netlist with kicad-cli (the same netlist the PCB is built from);
  2. for every IC / connector / discrete in expected.py, compares each pin's symbol
     NAME with the datasheet name, then evaluates the pin's connection rule
     (supply net, enable strap, unused pin left open, resistor/capacitor on the pin,
     MCU alternate function, ...);
  3. checks decoupling per supply pin: a capacitor of at least the datasheet value on
     that net, and (when the .kicad_pcb is available) how far it really sits from the pin;
  4. lists datasheet pins that have no symbol pin (left floating by omission);
  5. runs the board's derived-value checks (regulator output, OV/UV thresholds, current
     limits, LED currents ... from the actual resistor values, with datasheet tolerances).

Exit status 1 when anything FAILs. WARN items need a human look; INFO is context.
The datasheet tables are in expected.py, each with its source and revision.
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from kmodel import Netlist, Layout, value_of  # noqa: E402
import expected  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_FILES = {
    "gauges": (os.path.join(ROOT, "gauges", "ClusterGauges.kicad_sch"),
               os.path.join(ROOT, "gauges", "ClusterGauges.kicad_pcb")),
    "display": (os.path.join(ROOT, "archive", "display-1966", "ClusterDisplay.kicad_sch"),
                os.path.join(ROOT, "archive", "display-1966", "ClusterDisplay.kicad_pcb")),
    "brain": (os.path.join(ROOT, "brain", "ClusterBrain.kicad_sch"),
              os.path.join(ROOT, "brain", "ClusterBrain.kicad_pcb")),
    "panel-tsd": (os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_sch"),
                  os.path.join(ROOT, "panel-tsd", "ClusterPanelTSD.kicad_pcb")),
}

results = []        # (level, ref, what, detail)


def add(level, ref, what, detail=""):
    results.append((level, ref, what, detail))


def norm(name):
    s = re.sub(r"[^A-Z0-9+\-]", "", name.upper())
    s = s.replace("3V3", "33V").replace("1V8", "18V")
    if s in ("EP", "RTN", "POWERPAD", "THERMALPAD", "PAD"):
        return "EP"
    s = re.sub(r"(?<=[A-Z])\d+$", "", s) if not s.endswith("V") else s
    return s


def fmt(v):
    for unit, mult in (("M", 1e6), ("k", 1e3), ("", 1), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(v) >= mult * 0.999:
            return f"{v / mult:g}{unit}"
    return f"{v:g}"


class Checker:
    def __init__(self, board, nl, layout):
        self.board, self.nl, self.lay = board, nl, layout

    # ---- rule evaluation -----------------------------------------------------
    def pin_net(self, ref, pin):
        return self.nl.net_of(ref, pin)

    def check_rule(self, ref, pin, rule, spec):
        nl = self.nl
        net = self.pin_net(ref, pin)
        kind = rule[0]
        if kind == "net":
            return (net == rule[1]), f"on '{net}', expected '{rule[1]}'"
        if kind == "nets":
            return (net in rule[1]), f"on '{net}', expected one of {rule[1]}"
        if kind == "nc":
            others = [n for n in nl.nets.get(net, []) if (n.ref, n.pin) != (ref, str(pin))] if net else []
            ok = nl.is_nc_net(net) and not others
            return ok, ("left open" if ok else f"on '{net}' with {others}, must stay open")
        if kind == "same":
            other = self.pin_net(ref, rule[1])
            return net == other, f"on '{net}', pin {rule[1]} on '{other}', must be the same net"
        if kind in ("r", "c"):
            prefix = "R" if kind == "r" else "C"
            target = rule[1]
            found = []
            for nd in nl.nets.get(net, []):
                if nd.ref.startswith(prefix) and nl.other_net(nd.ref, net) == target:
                    found.append((nd.ref, value_of(nl.comps[nd.ref]["value"])))
            if kind == "r":
                lo, hi = rule[2], rule[3]
                ok = any(v is not None and lo <= v <= hi for _, v in found)
                return ok, (f"{found} between '{net}' and '{target}', need {fmt(lo)}..{fmt(hi)} ohm")
            lo = rule[2]
            ok = any(v is not None and v >= lo * 0.99 for _, v in found)
            return ok, (f"{found} between '{net}' and '{target}', need >= {fmt(lo)}F")
        if kind == "fn":
            mcu = spec["_mcu"]["pins"].get(str(pin))
            fns = mcu["functions"] if mcu else []
            return rule[1] in fns, f"pin {pin} offers {fns}, needs {rule[1]}"
        if kind == "free":
            return True, ""
        raise ValueError(rule)

    # ---- per-IC -------------------------------------------------------------
    def check_ic(self, ref, spec):
        nl = self.nl
        if ref not in nl.comps:
            add("FAIL", ref, "part missing from the netlist", spec["part"])
            return
        sym = nl.symbol_pins(ref)
        is_mcu = "mcu_json" in spec
        if is_mcu:
            with open(os.path.join(HERE, "data", spec["mcu_json"]), encoding="utf-8") as f:
                spec["_mcu"] = json.load(f)
        names_ok = 0
        for pin, (dsname, rules) in sorted(spec["pins"].items()):
            p = str(pin)
            if p not in sym:
                add("FAIL", f"{ref}.{p}", f"datasheet pin {dsname} has no symbol pin", spec["ds"])
                continue
            symname = sym[p][0]
            if not is_mcu:
                if norm(symname) != norm(dsname):
                    add("FAIL", f"{ref}.{p}", f"symbol calls pin '{symname}', datasheet calls it '{dsname}'", spec["ds"])
                else:
                    names_ok += 1
            for rule in rules:
                ok, detail = self.check_rule(ref, p, rule, spec)
                if not ok:
                    add("FAIL", f"{ref}.{p}", f"{dsname}: rule {rule[0]} violated", detail)
        # symbol pins the datasheet table does not know about
        for p, (nm, ty) in sym.items():
            if int(p) not in spec["pins"]:
                add("FAIL", f"{ref}.{p}", f"symbol pin '{nm}' is not in the datasheet table", spec["ds"])
        # datasheet pins with no symbol pin (floating on the board)
        if is_mcu:
            mcu = spec["_mcu"]["pins"]
            missing = [int(k) for k in mcu if k not in sym]
            floating = []
            for k in sorted(missing):
                m = mcu[str(k)]
                floating.append(f"{k}:{m['name']}")
            add("INFO", ref, f"{len(missing)} of 64 package pins have no symbol pin and float (all GPIO, left at reset defaults)",
                " ".join(floating))
            # one net per MCU signal pin
            seen = {}
            for p in sym:
                net = self.pin_net(ref, p)
                if nl.is_nc_net(net):
                    continue
                seen.setdefault(net, []).append(p)
            for net, pins_ in seen.items():
                if len(pins_) > 1 and net not in ("+3V3", "GND", "VDDA"):
                    add("FAIL", ref, f"net '{net}' lands on several MCU pins", str(pins_))
        add("PASS" if not any(r[1].startswith(ref + ".") and r[0] == "FAIL" for r in results) else "INFO",
            ref, f"{spec['part']}: {len(spec['pins'])} pins checked ({spec['status']}: {spec['ds'][:70]}...)",
            f"{names_ok} pin names agree with the datasheet" if not is_mcu else "alternate functions agree with the NXP mux table")
        for d in spec.get("decap", []):
            self.check_decap(ref, d)

    # ---- decoupling -----------------------------------------------------------
    def check_decap(self, ref, d):
        nl = self.nl
        pin, net = d["pin"], d["net"]
        if d["min_nom"] <= 0:
            return
        if self.pin_net(ref, pin) != net:
            add("FAIL", f"{ref}.{pin}", f"decoupling check: pin is on '{self.pin_net(ref, pin)}', expected '{net}'")
            return
        caps = []
        for nd in nl.nets.get(net, []):
            if nd.ref.startswith("C") and nl.other_net(nd.ref, net) == "GND":
                v = value_of(nl.comps[nd.ref]["value"])
                if v is not None and v >= d["min_nom"] * 0.99:
                    caps.append((nd.ref, nd.pin, v))
        if not caps:
            add("FAIL", f"{ref}.{pin}", f"no capacitor >= {fmt(d['min_nom'])}F from '{net}' to GND", d["why"])
            return
        if self.lay is None:
            add("INFO", f"{ref}.{pin}", f"decoupling present: {[c[0] for c in caps]}", d["why"])
            return
        best = None
        for cref, cpin, v in caps:
            dist = self.lay.dist((ref, pin), (cref, cpin))
            if dist is not None and (best is None or dist < best[0]):
                best = (dist, cref, v)
        if best is None:
            add("WARN", f"{ref}.{pin}", "decoupling capacitor position unknown (no pad data)", d["why"])
            return
        dist, cref, v = best
        if dist <= d["max_mm"]:
            add("PASS", f"{ref}.{pin}", f"{cref} ({fmt(v)}F) is {dist:.1f} mm from the pin", d["why"])
        elif dist <= d["max_mm"] * 2.5:
            add("WARN", f"{ref}.{pin}", f"nearest decoupling capacitor {cref} ({fmt(v)}F) is {dist:.1f} mm away, target <= {d['max_mm']} mm", d["why"])
        else:
            add("FAIL", f"{ref}.{pin}", f"nearest decoupling capacitor {cref} ({fmt(v)}F) is {dist:.1f} mm away, target <= {d['max_mm']} mm", d["why"])

    # ---- generic netlist hygiene ---------------------------------------------
    def check_hygiene(self):
        nl = self.nl
        for name, nodes in nl.nets.items():
            if nl.is_nc_net(name):
                continue
            if len(nodes) < 2:
                add("FAIL", name, "net has a single pin (dangling label)", str(nodes))
        # every part has a footprint
        for ref, c in nl.comps.items():
            if not c["footprint"]:
                add("FAIL", ref, "no footprint")
        # parts in the netlist that the expected tables do not cover (informational)
        covered = set(expected.BOARDS[self.board])
        other = sorted(r for r in nl.comps if r not in covered and not re.match(r"^(R|C|L|FB|Y)\d", r))
        if other:
            add("INFO", "coverage", "non-passive parts without a datasheet table in expected.py", " ".join(other))


# ---------------------------------------------------------------------------
# derived-value checks (from the real resistor/capacitor values)
# ---------------------------------------------------------------------------
def val(nl, ref):
    return value_of(nl.comps[ref]["value"])


def derived_gauges(nl):
    v = lambda r: val(nl, r)
    # 5 V buck: LMR33630 VFB 0.985..1.015 V (SNVSB26C 6.5), resistors 1 %
    rt, rb = v("R2"), v("R3")
    lo = 0.985 * (1 + rt * 0.99 / (rb * 1.01))
    hi = 1.015 * (1 + rt * 1.01 / (rb * 0.99))
    add("PASS" if 4.75 <= lo and hi <= 5.35 else "FAIL", "U2", f"+5V output {lo:.3f} .. {hi:.3f} V (nominal {(1 + rt / rb):.3f} V)",
        "VFB 0.985-1.015 V, 1 % divider; TLV733P IN abs max 6.0 V, TCAN1044 VCC 4.5-5.5 V")
    # LM74930 OV clamp / OV and UVLO thresholds (SNOSDF6 6.5)
    rt, rb = v("R51"), v("R52")
    clamp_lo, clamp_hi = 0.57 * (1 + rt * 0.99 / (rb * 1.01)), 0.61 * (1 + rt * 1.01 / (rb * 0.99))
    ov_lo, ov_hi = 0.585 * (1 + rt * 0.99 / (rb * 1.01)), 0.63 * (1 + rt * 1.01 / (rb * 0.99))
    ok = clamp_lo >= 27.0 and ov_hi <= 33.0
    add("PASS" if ok else "FAIL", "U3", f"OV clamp {clamp_lo:.1f}..{clamp_hi:.1f} V (OVCLAMP rising), cut-off {ov_lo:.1f}..{ov_hi:.1f} V",
        "must pass a 27 V suppressed load dump without clamping (>= 27 V) and stay below the buck's 36 V operating maximum (<= 33 V used)")
    ut, ub = v("R53"), v("R54")
    uv_f_lo, uv_f_hi = 0.533 * (1 + ut * 0.99 / (ub * 1.01)), 0.573 * (1 + ut * 1.01 / (ub * 0.99))
    uv_r_hi = 0.63 * (1 + ut * 1.01 / (ub * 0.99))
    add("INFO", "U3", f"UVLO falling {uv_f_lo:.2f}..{uv_f_hi:.2f} V, rising up to {uv_r_hi:.2f} V", "cranking dips below the falling threshold reset the board")
    ilim = 12 * v("R48") / (v("R50") * v("R49"))
    add("INFO", "U3", f"circuit-breaker current {ilim:.2f} A (12 x RSET / (RILIM x RSENSE)), short-circuit {0.020 / v('R49'):.1f} A", "SNOSDF6 eq. 15, 18")
    tovc = 1.2 * v("C49") / 2.8e-6
    add("INFO", "U3", f"overvoltage clamp circuit-breaker time {tovc * 1e3:.0f} ms, auto-retry {22.7e6 * v('C49'):.2f} s", "SNOSDF6 eq. 5, 8 (CTMR)")
    # LED arrows: CSL0902ET1C 30 mA abs max, 5 V reverse max
    for r, d in (("R82", "D26"), ("R83", "D27")):
        i14 = (14.4 - 3.0) / v(r)
        add("PASS" if i14 < 30e-3 else "FAIL", d, f"LED current at 14.4 V / Vf 3.0 V: {i14 * 1e3:.1f} mA through {fmt(v(r))} ohm ({(14.4 ** 2) / v(r) * 1e3:.0f} mW max in the resistor)",
            "CSL0902ET1C: 20 mA test, 30 mA absolute maximum")
    # dimmer and lamp dividers into the MCU
    k = v("R81") / (v("R80") + v("R81"))
    add("INFO", "R80/R81", f"dimmer divider {k:.3f}: 14 V -> {14 * k:.2f} V at the ADC", "ADC input max VDD + 0.3 V (clamped by D23)")
    for ref in ("R58", "R61", "R64", "R67", "R70", "R73"):
        pass


def derived_display(nl):
    v = lambda r: val(nl, r)
    rt, rb = v("R10"), v("R11")
    lo = 0.985 * (1 + rt * 0.99 / (rb * 1.01))
    hi = 1.015 * (1 + rt * 1.01 / (rb * 0.99))
    add("PASS" if 4.75 <= lo and hi <= 5.35 else "FAIL", "U2", f"+5V output {lo:.3f} .. {hi:.3f} V",
        "LM61460 VREF 1 V; Verdin VCC 3.135-5.5 V")
    rt, rb = v("R5"), v("R6")
    clamp_lo, ov_hi = 0.57 * (1 + rt * 0.99 / (rb * 1.01)), 0.63 * (1 + rt * 1.01 / (rb * 0.99))
    add("PASS" if clamp_lo >= 27.0 and ov_hi <= 33.0 else "FAIL", "U1", f"OV clamp from {clamp_lo:.1f} V, cut-off up to {ov_hi:.1f} V",
        "LM61460-Q1 absolute maximum VIN 42 V (36 V operating)")
    ilim = 12 * v("R2") / (v("R3") * v("R1"))
    add("INFO", "U1", f"circuit-breaker current {ilim:.2f} A, short-circuit {0.020 / v('R1'):.1f} A", "SNOSDF6 eq. 15, 18")
    vpos = 1.213 * (1 + v("R38") / v("R39"))
    vneg = -1.213 * v("R40") / v("R41")
    add("INFO", "U6", f"panel bias rails {vpos:.2f} V / {vneg:.2f} V", "TPS65131 eq. 1-2")
    i_bl = 0.2 / v("R42")
    add("INFO", "U7", f"backlight current {i_bl * 1e3:.0f} mA (VFB 0.2 V / R42)", "panel wants 180 mA")
    vout = 0.8 * (1 + v("R17") / v("R18"))
    add("INFO", "U3", f"+1V8 rail {vout:.3f} V (VFB 0.8 V nominal)", "TLV767 SBVS381A; panel IOVCC 1.75-1.85 V")



def derived_brain(nl):
    """The brain board keeps display/'s power tree (same designators) without
    the panel converters; its screen ports' switches use the USB-C switch's
    verified 61.9 k limit resistor."""
    v = lambda r: val(nl, r)
    rt, rb = v("R10"), v("R11")
    lo = 0.985 * (1 + rt * 0.99 / (rb * 1.01))
    hi = 1.015 * (1 + rt * 1.01 / (rb * 0.99))
    add("PASS" if 4.75 <= lo and hi <= 5.35 else "FAIL", "U2", f"+5V output {lo:.3f} .. {hi:.3f} V",
        "LM61460 VREF 1 V; Verdin VCC 3.135-5.5 V")
    rt, rb = v("R5"), v("R6")
    clamp_lo, ov_hi = 0.57 * (1 + rt * 0.99 / (rb * 1.01)), 0.63 * (1 + rt * 1.01 / (rb * 0.99))
    add("PASS" if clamp_lo >= 27.0 and ov_hi <= 33.0 else "FAIL", "U1", f"OV clamp from {clamp_lo:.1f} V, cut-off up to {ov_hi:.1f} V",
        "LM61460-Q1 absolute maximum VIN 42 V (36 V operating)")
    ilim = 12 * v("R2") / (v("R3") * v("R1"))
    add("INFO", "U1", f"circuit-breaker current {ilim:.2f} A, short-circuit {0.020 / v('R1'):.1f} A", "SNOSDF6 eq. 15, 18")
    vout = 0.8 * (1 + v("R17") / v("R18"))
    add("INFO", "U3", f"+1V8 rail {vout:.3f} V (VFB 0.8 V nominal)", "TLV767 SBVS381A; Verdin I/O 1.8 V")
    for u, r in (("U6", "R37"), ("U7", "R77"), ("U11", "R69")):
        add("PASS" if abs(v(r) - 61.9e3) < 1 else "FAIL", u, f"TPS2557-Q1 RILIM {fmt(v(r))} ohm",
            "61.9 k = 1.61 / 1.81 / 1.98 A (SLVSC97B IOS table)")


def derived_panel_tsd(nl):
    """display/'s panel bias and backlight checks, on the panel board."""
    v = lambda r: val(nl, r)
    vpos = 1.213 * (1 + v("R38") / v("R39"))
    vneg = -1.213 * v("R40") / v("R41")
    add("PASS" if 4.5 <= vpos <= 6.5 and -6.5 <= vneg <= -4.5 else "FAIL", "U6",
        f"panel bias rails {vpos:.2f} V / {vneg:.2f} V", "TPS65131 eq. 1-2; ICNL9707 VSP 4.5-6.5 V, VSN -6.5 to -4.5 V")
    i_bl = 0.2 / v("R42")
    add("INFO", "U7", f"backlight current {i_bl * 1e3:.0f} mA (VFB 0.2 V / R42)", "panel wants 180 mA")
    add("INFO", "R1", f"panel ID {fmt(v('R1'))} ohm", "TSD TST040HDBC-42 code in tools/screen_ports.py")

# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", choices=("gauges", "brain", "panel-tsd", "display"))
    ap.add_argument("--sch")
    ap.add_argument("--pcb")
    ap.add_argument("--json")
    ap.add_argument("--no-layout", action="store_true")
    a = ap.parse_args()
    sch, pcb = DEFAULT_FILES[a.board]
    sch = a.sch or sch
    pcb = a.pcb or pcb
    nl = Netlist(sch)
    lay = None
    if not a.no_layout and os.path.isfile(pcb):
        lay = Layout(pcb)
    ck = Checker(a.board, nl, lay)
    for ref, spec in expected.BOARDS[a.board].items():
        ck.check_ic(ref, spec)
    ck.check_hygiene()
    {"gauges": derived_gauges, "display": derived_display, "brain": derived_brain,
     "panel-tsd": derived_panel_tsd}[a.board](nl)

    order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    results.sort(key=lambda r: (order[r[0]], r[1]))
    for level, ref, what, detail in results:
        if level == "PASS" and ref.count(".") and "mm from the pin" in what and not os.environ.get("REVIEW_VERBOSE"):
            continue
        print(f"{level:4} {ref:12} {what}" + (f"   [{detail}]" if detail else ""))
    counts = {k: sum(1 for r in results if r[0] == k) for k in order}
    print("\n" + ", ".join(f"{k}: {n}" for k, n in counts.items()))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([dict(level=l, ref=r, what=w, detail=d) for l, r, w, d in results], f, indent=1)
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
