#!/usr/bin/env python3
"""
connector_audit.py - for every off-board connector pin, what sits between the pin and the silicon.

    python review/connector_audit.py gauges
    python review/connector_audit.py display --sch X.kicad_sch

For each connector pin it walks the netlist: parts hanging on the pin's net (TVS arrays, clamps, series and
pull resistors, capacitors) and, through one series resistor, the parts on the far node (clamp diodes, dividers,
the IC pin). The output is a markdown table for docs/electrical-review.md; the judgement about whether the
protection is enough is in the report, not in this script.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kmodel import Netlist, value_of  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCH = {"gauges": os.path.join(ROOT, "gauges", "ClusterGauges.kicad_sch"),
       "display": os.path.join(ROOT, "display", "ClusterDisplay.kicad_sch")}
# connectors that leave the board on a harness (bench headers are listed but marked)
OFFBOARD = {
    "gauges": {"J1": "12 V / GND / ignition (DTM06-3S)", "J7": "car CAN + 3 senders (DTM06-5S)", "J8": "private CAN link to display/",
               "J9": "Hall speed sender", "J10": "6 lamp inputs + dimmer", "J11": "tach", "J2": "SWD Tag-Connect (bench)"},
    "display": {"J2": "12 V / GND / ignition", "J3": "private CAN link to gauges/", "J11": "rotary dial + click",
                "J8": "JTAG (bench)", "J9": "buttons (bench)", "J12": "A55 console UART (bench)", "J13": "USB OTG (bench)", "J10": "RTC cell"},
}


def label(nl, ref):
    v = nl.comps[ref]["value"].split()
    return f"{ref} {v[0]}" if ref[0] in "RC" and v else f"{ref} {nl.comps[ref]['value'].split(' (')[0][:34]}"


def chain(nl, net, depth=0, seen=None):
    seen = seen or {net}
    parts = []
    for nd in nl.nets.get(net, []):
        if nd.ref[0] == "J":
            continue
        c = nl.comps[nd.ref]
        if nd.ref[0] == "U":
            parts.append(f"{nd.ref}.{nd.pin}")
        elif nd.ref[0] in "DQ":
            parts.append(label(nl, nd.ref))
        elif nd.ref[0] in "RLFC":
            other = nl.other_net(nd.ref, net) if nd.ref[0] != "F" else (nl.net_of(nd.ref, "2") if nl.net_of(nd.ref, "1") == net else nl.net_of(nd.ref, "1"))
            parts.append(f"{label(nl, nd.ref)}->{other}")
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("gauges", "display"))
    ap.add_argument("--sch")
    a = ap.parse_args()
    nl = Netlist(a.sch or SCH[a.board])
    print(f"| connector | pin | net | parts on the pin's net (part->far net) |")
    print("|---|---|---|---|")
    for j, what in OFFBOARD[a.board].items():
        if j not in nl.comps:
            continue
        pins = sorted([p for (r, p) in nl.pinnet if r == j], key=lambda x: int(x) if x.isdigit() else 0)
        for p in pins:
            net = nl.net_of(j, p)
            if net == "GND":
                print(f"| {j} {what} | {p} | GND | return |")
                continue
            if nl.is_nc_net(net):
                print(f"| {j} {what} | {p} | (open) | |")
                continue
            print(f"| {j} {what} | {p} | {net} | " + "; ".join(chain(nl, net)) + " |")


if __name__ == "__main__":
    main()
