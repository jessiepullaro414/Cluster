#!/usr/bin/env python3
"""Checks the generated DBCs against the generator's own tables with cantools.

Run: python can_protocol.py && python test_protocol.py
"""
import os
import sys

import cantools

import can_protocol as p

HERE = os.path.dirname(os.path.abspath(__file__))


def test_crc():
    # Published check value for CRC-8/SAE-J1850 over ASCII "123456789".
    assert p.crc8(b"123456789") == 0x4B, hex(p.crc8(b"123456789"))


def test_private_roundtrip():
    db = cantools.database.load_file(os.path.join(HERE, "cluster_private.dbc"))
    assert len(db.messages) == len(p.PRIVATE)
    m = db.get_message_by_name("VehicleMotion")
    vals = {"SpeedKph": 88.8, "Rpm": 3000, "BatteryV": 13.82,
            "SpeedValid": 1, "RpmValid": 1, "BatteryValid": 1,
            "SpeedFromHall": 1, "Counter": 5, "Crc8": 0}
    raw = bytearray(m.encode(vals))
    raw[7] = p.crc8(raw[:7])
    back = m.decode(bytes(raw))
    assert abs(back["SpeedKph"] - 88.8) < 1e-6 and back["Rpm"] == 3000
    assert abs(back["BatteryV"] - 13.82) < 1e-6 and back["Counter"] == 5
    assert back["Crc8"] == p.crc8(raw[:7])
    f = db.get_message_by_name("VehicleFluids")
    raw = f.encode({"FuelPct": 68.0, "CoolantC": -12.3, "OilKpa": 310.5,
                    "FuelValid": 1, "CoolantValid": 1, "OilValid": 0,
                    "Counter": 0, "Crc8": 0})
    d = f.decode(raw)
    assert d["CoolantC"] == -12.3 and d["OilKpa"] == 310.5 and d["OilValid"] == 0


def test_haltech_decode():
    db = cantools.database.load_file(os.path.join(HERE, "car_haltech_v2.dbc"))
    spd = db.get_message_by_name("HaltechSpeed")
    # 300 -> 30.0 km/h, big-endian bytes 0-1 = 0x012C
    assert spd.decode(bytes([0x01, 0x2C, 0, 0, 0, 0, 0, 0]))["VehicleSpeedKph"] == 30.0
    eng = db.get_message_by_name("HaltechEngine")
    d = eng.decode(bytes([0x0B, 0xB8, 0x03, 0xE8, 0x01, 0x90, 0, 0]))
    assert d["Rpm"] == 3000 and d["MapKpaAbs"] == 100.0 and d["ThrottlePct"] == 40.0
    pr = db.get_message_by_name("HaltechPressures")
    # oil raw 4113 -> 411.3 - 101.3 = 310.0 kPa gauge
    assert abs(pr.decode(bytes([0, 0, 0x10, 0x11, 0, 0, 0, 0]))["OilPressureKpa"] - 310.0) < 1e-6
    t = db.get_message_by_name("HaltechTemps")
    # 3631 -> 363.1 K = 89.95 C
    assert abs(t.decode(bytes([0x0E, 0x2F, 0, 0, 0, 0, 0, 0]))["CoolantTempK"] - 363.1) < 1e-6


if __name__ == "__main__":
    for fn in (test_crc, test_private_roundtrip, test_haltech_decode):
        fn()
        print("ok", fn.__name__)
    sys.exit(0)
