#!/usr/bin/env python3
"""
can_protocol.py - single source of truth for Cluster's CAN messages (rev 2).

Generates (never hand-edit the outputs):
  cluster_private.dbc    gauges/ <-> display/ private link (our own format)
  car_haltech_v2.dbc     the subset of Haltech's CAN Broadcast Protocol V2.35.0
                         that gauges/ reads from the car bus
  can_protocol.md        human-readable tables
  cluster_can.h          C header: IDs, scaling, CRC-8, Haltech decode helpers

TOPOLOGY (decided 2026-09-30, see the plan): gauges/ is the gateway. Only
gauges/ is on the car bus, and it only listens. display/ (Android) talks to
gauges/ over a private two-node CAN link. gauges/ aggregates the values
(ECU if fresh, else its own sender readings; speed from the Hall input if
present, else ECU) and sends display/ one consolidated state.

PRIVATE LINK: classic CAN, 11-bit IDs, little-endian (Intel), 500 kbit/s
(proposed; it is a short two-node link and could go faster). Every
state/command message ends with a 4-bit rolling counter (bits 52-55) and a
CRC-8 in byte 7 (SAE J1850: poly 0x1D, init 0xFF, final XOR 0xFF, over
bytes 0-6), so a stale or corrupted frame is detectable.

CAR BUS: bit rate is a setting (Haltech runs 1 Mbit/s; other ECUs commonly
500 kbit/s). Haltech V2 is big-endian. Its layout was verified against
Haltech's own PDF (V2.35.0) on 2026-09-30; only the messages below were read
and used. ecu-pcb will adopt the same layout (user decision 2026-09-30), which
also needs a speed input on ecu-pcb that does not exist yet.

STATUS: a PROPOSAL. Nothing here is implemented on any node. Only ecu-pcb's
placeholder 0x100 exists in firmware today (to be replaced by this layout).
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

CRC8_POLY, CRC8_INIT, CRC8_XOROUT = 0x1D, 0xFF, 0xFF
DISPLAY_TIMEOUT_MS = 1500
CAR_BUS_TIMEOUT_MS = 500

S = lambda n, f, o, lo, hi, u, s, l, signed=False, rx=None, doc="": dict(
    name=n, factor=f, offset=o, min=lo, max=hi, unit=u, start=s, length=l,
    signed=signed, rx=rx or [], doc=doc)


def e2e(rx):
    """Counter + CRC signals every protected private message ends with."""
    return [S("Counter", 1, 0, 0, 15, "", 52, 4, rx=rx,
              doc="rolling 0-15, increments per transmission"),
            S("Crc8", 1, 0, 0, 255, "", 56, 8, rx=rx,
              doc="CRC-8 SAE J1850 over bytes 0-6")]


G, D = ["GAUGES"], ["DISPLAY"]

# --- private link (little-endian) -------------------------------------------
PRIVATE = [
    dict(id=0x300, name="VehicleMotion", sender="GAUGES", period=50, dlc=8,
         doc="Consolidated motion data, chosen by gauges/ from the Hall input "
             "and the car bus.",
         signals=[
             S("SpeedKph", 0.1, 0, 0, 400, "km/h", 0, 16, rx=D),
             S("Rpm", 1, 0, 0, 12000, "rpm", 16, 16, rx=D),
             S("BatteryV", 0.01, 0, 0, 20, "V", 32, 16, rx=D),
             S("SpeedValid", 1, 0, 0, 1, "", 48, 1, rx=D),
             S("RpmValid", 1, 0, 0, 1, "", 49, 1, rx=D),
             S("BatteryValid", 1, 0, 0, 1, "", 50, 1, rx=D),
             S("SpeedFromHall", 1, 0, 0, 1, "", 51, 1, rx=D,
               doc="1 = Hall sender, 0 = car bus"),
         ] + e2e(D)),
    dict(id=0x302, name="VehicleFluids", sender="GAUGES", period=100, dlc=8,
         doc="Consolidated fluid data: ECU value if fresh, else local sender.",
         signals=[
             S("FuelPct", 0.01, 0, 0, 100, "%", 0, 16, rx=D),
             S("CoolantC", 0.1, 0, -40, 150, "degC", 16, 16, True, rx=D),
             S("OilKpa", 0.1, 0, 0, 1000, "kPa", 32, 16, rx=D,
               doc="gauge pressure"),
             S("FuelValid", 1, 0, 0, 1, "", 48, 1, rx=D),
             S("CoolantValid", 1, 0, 0, 1, "", 49, 1, rx=D),
             S("OilValid", 1, 0, 0, 1, "", 50, 1, rx=D),
         ] + e2e(D)),
    dict(id=0x301, name="GaugesStatus", sender="GAUGES", period=1000, dlc=8,
         doc="Health, identity and where each value currently comes from.",
         signals=[
             S("FwMajor", 1, 0, 0, 255, "", 0, 8, rx=D),
             S("FwMinor", 1, 0, 0, 255, "", 8, 8, rx=D),
             S("FuelSenderOpen", 1, 0, 0, 1, "", 16, 1, rx=D),
             S("OilSenderOpen", 1, 0, 0, 1, "", 17, 1, rx=D),
             S("TempSenderOpen", 1, 0, 0, 1, "", 18, 1, rx=D),
             S("CarBusActive", 1, 0, 0, 1, "", 19, 1, rx=D,
               doc="1 = car-bus frames seen within the timeout"),
             S("FuelFromCar", 1, 0, 0, 1, "", 20, 1, rx=D),
             S("CoolantFromCar", 1, 0, 0, 1, "", 21, 1, rx=D),
             S("OilFromCar", 1, 0, 0, 1, "", 22, 1, rx=D),
             S("BatteryFromCar", 1, 0, 0, 1, "", 23, 1, rx=D),
             S("ActiveProfile", 1, 0, 0, 255, "", 24, 8, rx=D,
               doc="car-bus profile in use: 0 none, 1 Haltech V2"),
             S("DisplayOffline", 1, 0, 0, 1, "", 32, 1, rx=D,
               doc="1 = gauges/ lost the display heartbeat"),
         ]),
    dict(id=0x310, name="PowerState", sender="GAUGES", period=500, dlc=8,
         doc="Ignition and sleep coordination; also sent on every change.",
         signals=[
             S("IgnitionOn", 1, 0, 0, 1, "", 0, 1, rx=D),
             S("SuspendRequest", 1, 0, 0, 1, "", 1, 1, rx=D,
               doc="display/ should save state and suspend"),
             S("SuspendInSeconds", 1, 0, 0, 255, "s", 8, 8, rx=D),
         ] + e2e(D)),
    dict(id=0x400, name="DisplaySettings", sender="DISPLAY", period=1000,
         dlc=8, doc="Persistent settings owned by Android; sent on change and "
                    "every second. gauges/ keeps the last copy in flash.",
         signals=[
             S("BrightnessPct", 1, 0, 0, 100, "%", 0, 8, rx=G),
             S("NightMode", 1, 0, 0, 1, "", 8, 1, rx=G),
             S("UnitsMph", 1, 0, 0, 1, "", 9, 1, rx=G),
             S("CarProfile", 1, 0, 0, 255, "", 16, 8, rx=G,
               doc="0 none, 1 Haltech V2"),
             S("CarBitrate", 1, 0, 0, 3, "", 24, 2, rx=G,
               doc="0 = 500 kbit/s, 1 = 1 Mbit/s, 2 = 250 kbit/s"),
             S("TankCapacityL", 0.1, 0, 0, 200, "L", 32, 16, rx=G,
               doc="converts a litres fuel level to a percentage"),
         ] + e2e(G)),
    dict(id=0x410, name="SpeedCalibration", sender="DISPLAY", period=1000,
         dlc=8, doc="Pulses per mile for the Hall sender (AutoMeter 16-pulse "
                    "sender at 1000 rev/mile = 16000).",
         signals=[
             S("PulsesPerMile", 1, 0, 100, 200000, "", 0, 32, rx=G),
         ] + e2e(G)),
    dict(id=0x4F0, name="DisplayHeartbeat", sender="DISPLAY", period=1000,
         dlc=8, doc="Liveness plus coarse state; gauges/ marks the display "
                    "offline if this stops.",
         signals=[
             S("State", 1, 0, 0, 3, "", 0, 2, rx=G,
               doc="0 booting, 1 running, 2 suspending"),
         ] + e2e(G)),
]

# --- Haltech V2.35.0 subset (big-endian), verified against the PDF -----------
# Motorola (@0) DBC convention: start bit is the MSB of the signal.
H = lambda n, byte, f, o, lo, hi, u, signed=False, doc="": dict(
    name=n, factor=f, offset=o, min=lo, max=hi, unit=u,
    start=byte * 8 + 7, length=16, signed=signed, rx=["GAUGES"], doc=doc)

HALTECH = [
    dict(id=0x360, name="HaltechEngine", sender="ECU", period=20, dlc=8,
         doc="RPM, manifold pressure (absolute), throttle, coolant pressure.",
         signals=[
             H("Rpm", 0, 1, 0, 0, 20000, "rpm"),
             H("MapKpaAbs", 2, 0.1, 0, 0, 1000, "kPa"),
             H("ThrottlePct", 4, 0.1, 0, 0, 100, "%"),
             H("CoolantPressureKpa", 6, 0.1, -101.3, -101.3, 1000, "kPa"),
         ]),
    dict(id=0x361, name="HaltechPressures", sender="ECU", period=20, dlc=8,
         doc="Fuel pressure, oil pressure (absolute minus 101.3), demand.",
         signals=[
             H("FuelPressureKpa", 0, 0.1, -101.3, -101.3, 1000, "kPa"),
             H("OilPressureKpa", 2, 0.1, -101.3, -101.3, 1000, "kPa"),
             H("EngineDemandPct", 4, 0.1, 0, 0, 400, "%"),
         ]),
    dict(id=0x370, name="HaltechSpeed", sender="ECU", period=50, dlc=8,
         doc="Vehicle speed (only sent if the ECU's speed input is set up).",
         signals=[H("VehicleSpeedKph", 0, 0.1, 0, 0, 400, "km/h")]),
    dict(id=0x372, name="HaltechBattery", sender="ECU", period=100, dlc=8,
         doc="Battery voltage.",
         signals=[H("BatteryV", 0, 0.1, 0, 0, 30, "V")]),
    dict(id=0x3E0, name="HaltechTemps", sender="ECU", period=200, dlc=8,
         doc="Temperatures in kelvin (x/10).",
         signals=[
             H("CoolantTempK", 0, 0.1, 0, 0, 500, "K"),
             H("AirTempK", 2, 0.1, 0, 0, 500, "K"),
             H("FuelTempK", 4, 0.1, 0, 0, 500, "K"),
             H("OilTempK", 6, 0.1, 0, 0, 500, "K"),
         ]),
    dict(id=0x3E2, name="HaltechFuelLevel", sender="ECU", period=200, dlc=8,
         doc="Fuel level in litres (x/10).",
         signals=[H("FuelLevelL", 0, 0.1, 0, 0, 500, "L")]),
]

NODES_PRIVATE = ["GAUGES", "DISPLAY"]
NODES_CAR = ["ECU", "GAUGES"]


def crc8(data):
    crc = CRC8_INIT
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ CRC8_POLY) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ CRC8_XOROUT


def check():
    for msgs, nodes in ((PRIVATE, NODES_PRIVATE), (HALTECH, NODES_CAR)):
        ids = [m["id"] for m in msgs]
        assert len(ids) == len(set(ids)), "duplicate CAN IDs"
        for m in msgs:
            assert 0 <= m["id"] <= 0x7FF and m["dlc"] <= 8
            used = set()
            for s in m["signals"]:
                if s["start"] % 8 == 7 and s["length"] == 16 and msgs is HALTECH:
                    byte0 = s["start"] // 8
                    bits = set(range(byte0 * 8, byte0 * 8 + 16))
                else:
                    bits = set(range(s["start"], s["start"] + s["length"]))
                assert not (bits & used), f"{m['name']}.{s['name']} overlaps"
                assert max(bits) < m["dlc"] * 8, f"{m['name']}.{s['name']} > DLC"
                used |= bits
            assert m["sender"] in nodes
    # every message that carries Counter/Crc8 must end exactly at bit 63
    for m in PRIVATE:
        names = [s["name"] for s in m["signals"]]
        if "Crc8" in names:
            assert m["dlc"] == 8 and "Counter" in names


def fnum(x):
    return f"{x:g}"


def write_dbc(path, msgs, nodes, big_endian, version):
    out = [f'VERSION "{version}"', "", "NS_ :", "", "BS_:", "",
           "BU_: " + " ".join(nodes), ""]
    order = "0+" if big_endian else "1"
    for m in msgs:
        out.append(f"BO_ {m['id']} {m['name']}: {m['dlc']} {m['sender']}")
        for s in m["signals"]:
            sign = "-" if s["signed"] else "+"
            rx = ",".join(s["rx"]) if s["rx"] else "Vector__XXX"
            endian = "0" if big_endian else "1"
            out.append(
                f" SG_ {s['name']} : {s['start']}|{s['length']}@{endian}{sign} "
                f"({fnum(s['factor'])},{fnum(s['offset'])}) "
                f"[{fnum(s['min'])}|{fnum(s['max'])}] \"{s['unit']}\" {rx}")
        out.append("")
    for m in msgs:
        out.append(f'CM_ BO_ {m["id"]} "{m["doc"]}";')
    out += ['', 'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;',
            'BA_DEF_DEF_ "GenMsgCycleTime" 0;']
    for m in msgs:
        out.append(f'BA_ "GenMsgCycleTime" BO_ {m["id"]} {m["period"]};')
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")


def md_table(msgs, title, intro):
    o = [f"## {title}", "", intro, "",
         "| ID | Name | Sender | Period | DLC |", "|---|---|---|---|---|"]
    for m in msgs:
        o.append(f"| 0x{m['id']:03X} | {m['name']} | {m['sender']} | "
                 f"{m['period']} ms | {m['dlc']} |")
    for m in msgs:
        o += ["", f"### 0x{m['id']:03X} {m['name']} ({m['sender']}, "
              f"{m['period']} ms)", "", m["doc"], "",
              "| Signal | Start bit | Length | Scale | Offset | Range | Unit |",
              "|---|---|---|---|---|---|---|"]
        for s in m["signals"]:
            sg = " signed" if s["signed"] else ""
            o.append(f"| {s['name']} | {s['start']} | {s['length']}{sg} | "
                     f"{fnum(s['factor'])} | {fnum(s['offset'])} | "
                     f"{fnum(s['min'])}..{fnum(s['max'])} | {s['unit']} |")
    return o


def write_md(path):
    o = ["# Cluster CAN protocol, rev 2 (proposal)", "",
         "Generated by `can_protocol.py`; do not edit by hand.", "",
         "gauges/ is the gateway: only it is on the car bus (listen-only). "
         "display/ talks to gauges/ over a private link. See the plan for "
         "the topology and the reasons.", ""]
    o += md_table(PRIVATE, "Private link (gauges/ <-> display/)",
                  "Little-endian, 500 kbit/s (proposed). Messages with "
                  "`Counter` and `Crc8` end with a 4-bit rolling counter "
                  "(bits 52-55) and CRC-8 SAE J1850 (poly 0x1D, init 0xFF, "
                  "final XOR 0xFF) over bytes 0-6. Missing display heartbeat "
                  f"for {DISPLAY_TIMEOUT_MS} ms means DisplayOffline.")
    o += [""]
    o += md_table(HALTECH, "Car bus: Haltech V2.35.0 subset (read only)",
                  "Big-endian, 11-bit IDs, 1 Mbit/s on Haltech (the bit "
                  "rate is a setting). Layout verified against Haltech's PDF "
                  "on 2026-09-30. Oil pressure and coolant/fuel pressure are "
                  "absolute kPa minus 101.3. Temperatures are kelvin. Car-bus "
                  f"frames older than {CAR_BUS_TIMEOUT_MS} ms are stale.")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(o) + "\n")


def write_h(path):
    o = ["/* cluster_can.h - GENERATED by protocol/can_protocol.py. Do not edit. */",
         "#ifndef CLUSTER_CAN_H", "#define CLUSTER_CAN_H", "",
         "#include <stdint.h>", "",
         f"#define CLUSTER_DISPLAY_TIMEOUT_MS  {DISPLAY_TIMEOUT_MS}u",
         f"#define CLUSTER_CAR_BUS_TIMEOUT_MS  {CAR_BUS_TIMEOUT_MS}u", "",
         "/* CRC-8 SAE J1850 over bytes 0-6 of an 8-byte private message. */",
         "static inline uint8_t cluster_crc8(const uint8_t *d, uint8_t n) {",
         f"    uint8_t crc = 0x{CRC8_INIT:02X}u;",
         "    for (uint8_t i = 0; i < n; i++) {",
         "        crc ^= d[i];",
         "        for (uint8_t b = 0; b < 8; b++)",
         f"            crc = (crc & 0x80u) ? (uint8_t)((crc << 1) ^ 0x{CRC8_POLY:02X}u) : (uint8_t)(crc << 1);",
         "    }",
         f"    return (uint8_t)(crc ^ 0x{CRC8_XOROUT:02X}u);",
         "}", "", "/* ---- private link (little-endian) ---- */"]
    for m in PRIVATE:
        n = m["name"].upper()
        o.append(f"#define CAN_ID_{n:<22} 0x{m['id']:03X}u")
        o.append(f"#define CAN_PERIOD_MS_{n:<14} {m['period']}u")
        for s in m["signals"]:
            sn = f"{n}_{s['name'].upper()}"
            o.append(f"#define CAN_{sn}_START {s['start']}u")
            o.append(f"#define CAN_{sn}_LEN {s['length']}u")
            o.append(f"#define CAN_{sn}_FACTOR {fnum(s['factor'])}f")
        o.append("")
    o.append("/* ---- car bus: Haltech V2.35.0 subset (big-endian, byte index "
             "of the 16-bit field's high byte) ---- */")
    for m in HALTECH:
        n = m["name"].upper()
        o.append(f"#define CAN_ID_{n:<22} 0x{m['id']:03X}u")
        for s in m["signals"]:
            sn = f"{n}_{s['name'].upper()}"
            o.append(f"#define CAN_{sn}_BYTE {s['start'] // 8}u")
            o.append(f"#define CAN_{sn}_FACTOR {fnum(s['factor'])}f")
            o.append(f"#define CAN_{sn}_OFFSET {fnum(s['offset'])}f")
        o.append("")
    o += ["#endif"]
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(o) + "\n")


if __name__ == "__main__":
    check()
    write_dbc(os.path.join(HERE, "cluster_private.dbc"), PRIVATE,
              NODES_PRIVATE, False, "cluster-private-0.2")
    write_dbc(os.path.join(HERE, "car_haltech_v2.dbc"), HALTECH,
              NODES_CAR, True, "haltech-v2.35.0-subset")
    write_md(os.path.join(HERE, "can_protocol.md"))
    write_h(os.path.join(HERE, "cluster_can.h"))
    print(f"OK: {len(PRIVATE)} private + {len(HALTECH)} Haltech messages -> "
          "cluster_private.dbc, car_haltech_v2.dbc, can_protocol.md, "
          "cluster_can.h")
