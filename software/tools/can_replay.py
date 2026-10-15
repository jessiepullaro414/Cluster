#!/usr/bin/env python3
"""Replay a scripted drive onto a CAN bus, from the generated DBCs.

Two roles, one drive scenario:
  --role car      the ECU side of the car bus: Haltech V2.35.0 frames
                  (protocol/car_haltech_v2.dbc, big-endian, 1 Mbit/s). Feeds
                  gauges/ CAN0. Use it on a bench with the board and an adapter.
  --role gauges   the gauges/ side of the private link: VehicleMotion,
                  VehicleFluids and Indicators (protocol/cluster_private.dbc,
                  500 kbit/s) with the rolling counter and CRC-8 computed
                  exactly as protocol/can_protocol.py defines them. Feeds the
                  display/ VHAL bridge, so the Android side can be developed
                  with no gauges/ board.

Every frame is encoded by cantools from the DBC, so this script cannot drift
from the protocol tables. The scenario is a plain Python function (see
drive()); edit it for other tests.

  python can_replay.py --role car --dry-run --seconds 3
  python can_replay.py --role gauges --interface socketcan --channel can0
  python can_replay.py --selftest        # encode -> bus -> decode, no hardware

python-can picks the adapter: --interface socketcan|pcan|slcan|virtual|...
(see python-can's documentation for channel names). Nothing here ever sends
on the car bus in a real car: gauges/ is receive-only there, and this tool is
a bench simulator of the ECU.
"""
import argparse
import math
import os
import sys
import time

import can
import cantools

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(os.path.dirname(os.path.dirname(HERE)), "protocol")
sys.path.insert(0, PROTO)
import can_protocol as p  # noqa: E402  (crc8, message periods)


def drive(t):
    """The scenario: state of the car t seconds after the start.

    0-3 s key on, idle; 3-13 s accelerate to 90 km/h; 13-23 s cruise;
    23-30 s brake to a stop; then repeat. All values are plausible for a
    restomod V8, not measured.
    """
    t = t % 30.0
    if t < 3:
        v = 0.0
    elif t < 13:
        v = 90.0 * (t - 3) / 10.0
    elif t < 23:
        v = 90.0
    else:
        v = 90.0 * (30.0 - t) / 7.0
    rpm = 800 + v * 28.0 + 40 * math.sin(t * 6.0)
    return dict(
        speed_kph=v,
        rpm=rpm,
        battery_v=13.8 if t > 1 else 12.4,        # alternator charging once running
        coolant_c=min(92.0, 40.0 + 2.0 * t),
        oil_kpa=min(380.0, 150.0 + rpm * 0.08),
        fuel_pct=68.0 - 0.02 * t,
        fuel_l=0.01 * 68.0 * 60.0 - 0.01 * t,     # 60 L tank
        turn_left=(int(t) % 2 == 0) and 18 < t < 22,
        high_beam=False,
    )


def car_frames(db, s):
    """Haltech frames for scenario state s (tuple: arbitration id, bytes)."""
    k = lambda c: c + 273.15                                   # noqa: E731
    out = []
    for name, vals in [
        ("HaltechEngine", dict(Rpm=s["rpm"], MapKpaAbs=40 + s["speed_kph"], ThrottlePct=min(100.0, s["speed_kph"] / 1.2),
                               CoolantPressureKpa=0.0)),
        ("HaltechPressures", dict(FuelPressureKpa=300.0, OilPressureKpa=s["oil_kpa"], EngineDemandPct=20.0)),
        ("HaltechSpeed", dict(VehicleSpeedKph=s["speed_kph"])),
        ("HaltechBattery", dict(BatteryV=s["battery_v"])),
        ("HaltechTemps", dict(CoolantTempK=k(s["coolant_c"]), AirTempK=k(30.0), FuelTempK=k(30.0), OilTempK=k(s["coolant_c"]))),
        ("HaltechFuelLevel", dict(FuelLevelL=s["fuel_l"])),
    ]:
        m = db.get_message_by_name(name)
        out.append((name, m.frame_id, m.encode(vals)))
    return out


class PrivateEncoder:
    """Private-link frames with a per-message rolling counter and CRC-8."""

    def __init__(self, db):
        self.db = db
        self.counter = {}

    def frame(self, name, vals):
        m = self.db.get_message_by_name(name)
        c = self.counter.get(name, 0)
        self.counter[name] = (c + 1) & 0xF
        raw = bytearray(m.encode(dict(vals, Counter=c, Crc8=0)))
        raw[7] = p.crc8(raw[:7])
        return (name, m.frame_id, bytes(raw))


def gauges_frames(enc, s):
    return [
        enc.frame("VehicleMotion", dict(SpeedKph=s["speed_kph"], Rpm=s["rpm"], BatteryV=s["battery_v"],
                                        SpeedValid=1, RpmValid=1, BatteryValid=1, SpeedFromHall=1)),
        enc.frame("VehicleFluids", dict(FuelPct=s["fuel_pct"], CoolantC=s["coolant_c"], OilKpa=s["oil_kpa"],
                                        FuelValid=1, CoolantValid=1, OilValid=1)),
        enc.frame("Indicators", dict(TurnLeft=int(s["turn_left"]), TurnRight=0, HighBeam=int(s["high_beam"]),
                                     BrakeWarning=0, AlternatorWarning=0, OilWarning=0,
                                     DashLightsOn=0, DashDimmerPct=0)),
    ]


def periods(db, role):
    """name -> period in seconds, from the protocol tables (single source)."""
    table = p.HALTECH if role == "car" else p.PRIVATE
    return {m["name"]: m["period"] / 1000.0 for m in table if m.get("period")}


def run(args):
    car_db = cantools.database.load_file(os.path.join(PROTO, "car_haltech_v2.dbc"))
    priv_db = cantools.database.load_file(os.path.join(PROTO, "cluster_private.dbc"))
    enc = PrivateEncoder(priv_db)
    per = periods(None, args.role)
    bus = None
    if not args.dry_run:
        bus = can.Bus(interface=args.interface, channel=args.channel,
                      bitrate=args.bitrate or (1000000 if args.role == "car" else 500000))
    last = {}
    t0 = time.monotonic()
    sent = 0
    try:
        while True:
            t = time.monotonic() - t0
            if args.seconds and t >= args.seconds:
                break
            s = drive(t)
            frames = car_frames(car_db, s) if args.role == "car" else gauges_frames(enc, s)
            for name, fid, data in frames:
                if t - last.get(name, -1e9) < per.get(name, 0.1):
                    continue
                last[name] = t
                if bus:
                    bus.send(can.Message(arbitration_id=fid, data=data, is_extended_id=False))
                else:
                    print(f"{t:7.3f}s  0x{fid:03X}  {name:<18} {data.hex(' ')}")
                sent += 1
            time.sleep(0.005)
    finally:
        if bus:
            bus.shutdown()
    print(f"sent {sent} frames", file=sys.stderr)


def selftest():
    """Encode a scenario, send it over python-can's in-process virtual bus,
    decode it with an independent cantools decode, and check the values and
    the private-link counter and CRC."""
    car_db = cantools.database.load_file(os.path.join(PROTO, "car_haltech_v2.dbc"))
    priv_db = cantools.database.load_file(os.path.join(PROTO, "cluster_private.dbc"))
    tx = can.Bus(interface="virtual", channel="replay-selftest")
    rx = can.Bus(interface="virtual", channel="replay-selftest")
    s = drive(15.0)   # cruise at 90 km/h
    enc = PrivateEncoder(priv_db)
    for _ in range(18):                      # more than one counter wrap
        for name, fid, data in car_frames(car_db, s) + gauges_frames(enc, s):
            tx.send(can.Message(arbitration_id=fid, data=data, is_extended_id=False))
    seen_counters = []
    n = 0
    while True:
        msg = rx.recv(timeout=0.2)
        if msg is None:
            break
        n += 1
        fid = msg.arbitration_id
        if fid in (m.frame_id for m in car_db.messages):
            d = car_db.decode_message(fid, msg.data)
            if fid == 0x370:
                assert abs(d["VehicleSpeedKph"] - 90.0) < 0.06, d
            if fid == 0x3E0:
                assert abs(d["CoolantTempK"] - (s["coolant_c"] + 273.15)) < 0.1, d
        else:
            assert p.crc8(msg.data[:7]) == msg.data[7], f"bad CRC on 0x{fid:03X}"
            d = priv_db.decode_message(fid, msg.data)
            if fid == 0x300:
                assert abs(d["SpeedKph"] - 90.0) < 0.06 and d["SpeedValid"] == 1, d
                seen_counters.append(d["Counter"])
    tx.shutdown()
    rx.shutdown()
    assert n == 18 * 9, n
    assert seen_counters == [i & 0xF for i in range(18)], seen_counters
    print(f"can_replay selftest: {n} frames round-tripped, counter wraps, CRCs valid")


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--role", choices=["car", "gauges"], default="car")
    a.add_argument("--interface", default="socketcan")
    a.add_argument("--channel", default="can0")
    a.add_argument("--bitrate", type=int, default=0, help="default 1000000 (car) or 500000 (gauges)")
    a.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = run until Ctrl-C)")
    a.add_argument("--dry-run", action="store_true", help="print frames instead of sending")
    a.add_argument("--selftest", action="store_true")
    args = a.parse_args()
    if args.selftest:
        selftest()
    else:
        run(args)


if __name__ == "__main__":
    main()
