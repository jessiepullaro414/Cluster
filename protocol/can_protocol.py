#!/usr/bin/env python3
"""
can_protocol.py - the single source of truth for Cluster's CAN0 message set.

Generates, from the tables below (never hand-edit the outputs):
  cluster.dbc          standard CAN database (open in any DBC tool / SavvyCAN)
  can_protocol.md      human-readable message and signal tables
  cluster_can.h        C header: IDs, periods, timeouts, scaling for firmware

Bus: CAN0, classic CAN (not FD), 11-bit standard IDs, 500 kbit/s (proposed:
the ECU firmware leaves the bit rate to register config, see
ecu-firmware/inc/flexcan.h). Three nodes: ECU (ecu-pcb), GAUGES (gauges/,
S32K144), DISPLAY (display/, Verdin iMX95 running Android). All signals are
little-endian (Intel) and unsigned unless marked signed.

STATUS: a PROPOSAL. Only 0x100 exists in firmware today, as a placeholder
that ecu-firmware/src/main.c's broadcast_can() sends (engine_state, 1 byte);
its own comment says a real ID map is undecided. Nothing else here is
implemented on any node yet. Lower ID = higher arbitration priority, so
commands and safety-relevant data sit below telemetry.

Source-of-truth policy (the firmware question raised at the start of the
project): DISPLAY aggregates. For each small gauge it prefers the ECU value
if a fresh ECU message (< ECU_TIMEOUT_MS) is present, otherwise GAUGES' own
local resistive-sender reading, and commands GAUGES what to draw on
0x400. If DISPLAY's heartbeat (0x4F0) is silent for DISPLAY_TIMEOUT_MS,
GAUGES stops waiting and renders standalone using the same ECU-then-local
rule itself, so the small gauges still work with Android off or crashed.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

NODES = ["ECU", "GAUGES", "DISPLAY"]
ECU_TIMEOUT_MS = 500
DISPLAY_TIMEOUT_MS = 1500

# name, factor, offset, min, max, unit, bit_start, bit_len, signed, receivers
# Each message: id, name, sender, period_ms, dlc, description, [signals]
S = lambda n, f, o, lo, hi, u, s, l, signed=False, rx=None, doc="": dict(
    name=n, factor=f, offset=o, min=lo, max=hi, unit=u, start=s, length=l,
    signed=signed, rx=rx or [], doc=doc)

MESSAGES = [
    dict(id=0x100, name="EcuState", sender="ECU", period=100, dlc=1,
         doc="Existing placeholder broadcast from ecu-firmware (keep the ID).",
         signals=[
             S("EngineState", 1, 0, 0, 255, "", 0, 8,
               rx=["GAUGES", "DISPLAY"], doc="ecu-firmware engine_state enum"),
         ]),
    dict(id=0x200, name="EcuEngine", sender="ECU", period=50, dlc=7,
         doc="Engine telemetry the cluster shows or derives from.",
         signals=[
             S("Rpm", 1, 0, 0, 12000, "rpm", 0, 16, rx=["GAUGES", "DISPLAY"]),
             S("MapKpa", 0.1, 0, 0, 400, "kPa", 16, 16, rx=["DISPLAY"]),
             S("CoolantC", 0.1, 0, -40, 150, "degC", 32, 16, True,
               rx=["GAUGES", "DISPLAY"]),
             S("ThrottlePct", 0.4, 0, 0, 100, "%", 48, 8, rx=["DISPLAY"]),
         ]),
    dict(id=0x201, name="EcuVehicle", sender="ECU", period=100, dlc=7,
         doc="Vehicle-level values the ECU knows.",
         signals=[
             S("SpeedKph", 0.1, 0, 0, 300, "km/h", 0, 16, rx=["DISPLAY"]),
             S("BatteryV", 0.01, 0, 0, 20, "V", 16, 16,
               rx=["GAUGES", "DISPLAY"]),
             S("OilPressKpa", 1, 0, 0, 1000, "kPa", 32, 16,
               rx=["GAUGES", "DISPLAY"]),
             S("CheckEngine", 1, 0, 0, 1, "", 48, 1, rx=["DISPLAY"]),
         ]),
    dict(id=0x300, name="GaugesSense", sender="GAUGES", period=100, dlc=8,
         doc="Local resistive-sender readings, after the ADC lookup tables. "
             "Used when the ECU is absent or silent.",
         signals=[
             S("FuelPct", 0.01, 0, 0, 100, "%", 0, 16, rx=["DISPLAY"]),
             S("OilKpa", 1, 0, 0, 1000, "kPa", 16, 16, rx=["DISPLAY"]),
             S("CoolantC", 0.1, 0, -40, 150, "degC", 32, 16, True,
               rx=["DISPLAY"]),
             S("BatteryV", 0.01, 0, 0, 20, "V", 48, 16, rx=["DISPLAY"]),
         ]),
    dict(id=0x301, name="GaugesStatus", sender="GAUGES", period=1000, dlc=4,
         doc="Health and firmware identity.",
         signals=[
             S("FwMajor", 1, 0, 0, 255, "", 0, 8, rx=["DISPLAY"]),
             S("FwMinor", 1, 0, 0, 255, "", 8, 8, rx=["DISPLAY"]),
             S("FuelSenderOpen", 1, 0, 0, 1, "", 16, 1, rx=["DISPLAY"]),
             S("OilSenderOpen", 1, 0, 0, 1, "", 17, 1, rx=["DISPLAY"]),
             S("TempSenderOpen", 1, 0, 0, 1, "", 18, 1, rx=["DISPLAY"]),
             S("StandaloneMode", 1, 0, 0, 1, "", 19, 1, rx=["DISPLAY"],
               doc="1 = GAUGES lost the DISPLAY heartbeat and is rendering itself"),
         ]),
    dict(id=0x400, name="DisplayGauges", sender="DISPLAY", period=50, dlc=8,
         doc="What each small gauge should draw, as a fraction of full scale "
             "(0-100%). Order: fuel, coolant temp, oil pressure, battery.",
         signals=[
             S("FuelFrac", 0.01, 0, 0, 100, "%", 0, 16, rx=["GAUGES"]),
             S("CoolantFrac", 0.01, 0, 0, 100, "%", 16, 16, rx=["GAUGES"]),
             S("OilFrac", 0.01, 0, 0, 100, "%", 32, 16, rx=["GAUGES"]),
             S("BatteryFrac", 0.01, 0, 0, 100, "%", 48, 16, rx=["GAUGES"]),
         ]),
    dict(id=0x401, name="DisplayState", sender="DISPLAY", period=100, dlc=3,
         doc="Global rendering state for the small gauges.",
         signals=[
             S("BrightnessPct", 1, 0, 0, 100, "%", 0, 8, rx=["GAUGES"]),
             S("NightMode", 1, 0, 0, 1, "", 8, 1, rx=["GAUGES"]),
             S("FuelFromEcu", 1, 0, 0, 1, "", 9, 1, rx=["GAUGES"],
               doc="source flag: 1 = ECU value, 0 = local sender"),
             S("CoolantFromEcu", 1, 0, 0, 1, "", 10, 1, rx=["GAUGES"]),
             S("OilFromEcu", 1, 0, 0, 1, "", 11, 1, rx=["GAUGES"]),
             S("BatteryFromEcu", 1, 0, 0, 1, "", 12, 1, rx=["GAUGES"]),
             S("WarnFuel", 1, 0, 0, 1, "", 16, 1, rx=["GAUGES"]),
             S("WarnCoolant", 1, 0, 0, 1, "", 17, 1, rx=["GAUGES"]),
             S("WarnOil", 1, 0, 0, 1, "", 18, 1, rx=["GAUGES"]),
             S("WarnBattery", 1, 0, 0, 1, "", 19, 1, rx=["GAUGES"]),
         ]),
    dict(id=0x4F0, name="DisplayHeartbeat", sender="DISPLAY", period=1000,
         dlc=2, doc="Liveness; GAUGES goes standalone if this stops.",
         signals=[
             S("Counter", 1, 0, 0, 65535, "", 0, 16, rx=["GAUGES"]),
         ]),
]


def check():
    ids = [m["id"] for m in MESSAGES]
    assert len(ids) == len(set(ids)), "duplicate CAN IDs"
    for m in MESSAGES:
        assert 0 <= m["id"] <= 0x7FF and m["dlc"] <= 8
        used = set()
        for s in m["signals"]:
            bits = set(range(s["start"], s["start"] + s["length"]))
            assert not (bits & used), f"{m['name']}.{s['name']} overlaps"
            assert max(bits) < m["dlc"] * 8, f"{m['name']}.{s['name']} > DLC"
            used |= bits
        assert m["sender"] in NODES
        for s in m["signals"]:
            assert set(s["rx"]) <= set(NODES) - {m["sender"]}
    # names unique per message and messages sorted by ID = priority order
    assert ids == sorted(ids)


def fnum(x):
    return f"{x:g}"


def write_dbc(path):
    out = ['VERSION "cluster-can-0.1"', "", "NS_ :", "", "BS_:", "",
           "BU_: " + " ".join(NODES), ""]
    for m in MESSAGES:
        out.append(f"BO_ {m['id']} {m['name']}: {m['dlc']} {m['sender']}")
        for s in m["signals"]:
            sign = "-" if s["signed"] else "+"
            rx = ",".join(s["rx"]) if s["rx"] else "Vector__XXX"
            out.append(
                f" SG_ {s['name']} : {s['start']}|{s['length']}@1{sign} "
                f"({fnum(s['factor'])},{fnum(s['offset'])}) "
                f"[{fnum(s['min'])}|{fnum(s['max'])}] \"{s['unit']}\" {rx}")
        out.append("")
    for m in MESSAGES:
        out.append(f'CM_ BO_ {m["id"]} "{m["doc"]}";')
    out.append("")
    out.append('BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;')
    out.append('BA_DEF_DEF_ "GenMsgCycleTime" 0;')
    for m in MESSAGES:
        out.append(f'BA_ "GenMsgCycleTime" BO_ {m["id"]} {m["period"]};')
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")


def write_md(path):
    o = ["# Cluster CAN0 protocol (proposal)", "",
         "Generated by `can_protocol.py`; do not edit by hand.", "",
         "Classic CAN, 11-bit IDs, 500 kbit/s (proposed), little-endian. "
         "Nodes: **ECU** (ecu-pcb), **GAUGES** (gauges/, S32K144), "
         "**DISPLAY** (display/, Android). Only `0x100` exists in firmware "
         "today (placeholder in `ecu-firmware`).", "",
         "**Value policy.** DISPLAY aggregates: per small gauge it prefers a "
         f"fresh ECU value (< {ECU_TIMEOUT_MS} ms old), else GAUGES' local "
         "sender reading, and commands GAUGES on `0x400`. If DISPLAY's "
         f"heartbeat `0x4F0` is silent for {DISPLAY_TIMEOUT_MS} ms, GAUGES "
         "renders standalone with the same ECU-then-local rule.", "",
         "| ID | Name | Sender | Period | DLC |", "|---|---|---|---|---|"]
    for m in MESSAGES:
        o.append(f"| 0x{m['id']:03X} | {m['name']} | {m['sender']} | "
                 f"{m['period']} ms | {m['dlc']} |")
    for m in MESSAGES:
        o += ["", f"## 0x{m['id']:03X} {m['name']} ({m['sender']}, "
              f"{m['period']} ms)", "", m["doc"], "",
              "| Signal | Bits | Scale | Offset | Range | Unit | Receivers |",
              "|---|---|---|---|---|---|---|"]
        for s in m["signals"]:
            sg = " signed" if s["signed"] else ""
            o.append(
                f"| {s['name']} | {s['start']}..{s['start']+s['length']-1}{sg} "
                f"| {fnum(s['factor'])} | {fnum(s['offset'])} | "
                f"{fnum(s['min'])}..{fnum(s['max'])} | {s['unit']} | "
                f"{', '.join(s['rx'])} |")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(o) + "\n")


def write_h(path):
    o = ["/* cluster_can.h - GENERATED by protocol/can_protocol.py. Do not edit. */",
         "#ifndef CLUSTER_CAN_H", "#define CLUSTER_CAN_H", "",
         f"#define CLUSTER_ECU_TIMEOUT_MS      {ECU_TIMEOUT_MS}u",
         f"#define CLUSTER_DISPLAY_TIMEOUT_MS  {DISPLAY_TIMEOUT_MS}u", ""]
    for m in MESSAGES:
        n = m["name"].upper()
        o.append(f"#define CAN_ID_{n:<22} 0x{m['id']:03X}u")
        o.append(f"#define CAN_PERIOD_MS_{n:<14} {m['period']}u")
        o.append(f"#define CAN_DLC_{n:<20} {m['dlc']}u")
        for s in m["signals"]:
            sn = f"{n}_{s['name'].upper()}"
            o.append(f"#define CAN_{sn}_START {s['start']}u")
            o.append(f"#define CAN_{sn}_LEN {s['length']}u")
            o.append(f"#define CAN_{sn}_FACTOR {fnum(s['factor'])}f")
        o.append("")
    o += ["#endif"]
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(o) + "\n")


if __name__ == "__main__":
    check()
    write_dbc(os.path.join(HERE, "cluster.dbc"))
    write_md(os.path.join(HERE, "can_protocol.md"))
    write_h(os.path.join(HERE, "cluster_can.h"))
    print(f"OK: {len(MESSAGES)} messages, "
          f"{sum(len(m['signals']) for m in MESSAGES)} signals -> "
          f"cluster.dbc, can_protocol.md, cluster_can.h")
