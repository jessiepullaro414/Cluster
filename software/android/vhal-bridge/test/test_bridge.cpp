// Host tests for the VHAL bridge policy. Frames come from two places:
//  * GOLDEN: bytes produced by cantools from the DBC (via tools/can_replay.py
//    --dry-run), independent of every C++/C encoder in this repo;
//  * the generated cluster_*_pack functions, for cases that need chosen values.
#include <cmath>
#include <cstdio>
#include <cstring>

#include "bridge.h"
extern "C" {
#include "cluster_codec.h"
}

static int failures;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)
#define NEAR(a, b, tol) (std::fabs(static_cast<double>(a) - static_cast<double>(b)) <= (tol))

using vhal::Prop;
using vhal::Result;

static Result send_motion(vhal::Bridge& b, float kph, uint32_t rpm, uint8_t counter, uint32_t t,
                          bool speed_valid = true, bool rpm_valid = true) {
    cluster_vehicle_motion_t m = {};
    m.speed_kph = kph; m.rpm = rpm; m.battery_v = 13.8f;
    m.speed_valid = speed_valid; m.rpm_valid = rpm_valid; m.battery_valid = 1;
    uint8_t raw[8];
    cluster_vehicle_motion_pack(&m, counter, raw);
    return b.on_frame(CAN_ID_VEHICLEMOTION, raw, 8, t);
}

int main() {
    // GOLDEN: VehicleMotion 0x300 at t = 0 of the can_replay scenario:
    // speed 0, rpm 800, battery 12.40 V, all valid, from Hall, counter 0.
    {
        const uint8_t g[8] = {0x00, 0x00, 0x20, 0x03, 0xd8, 0x04, 0x0f, 0x53};
        vhal::Bridge b;
        CHECK(b.on_frame(0x300, g, 8, 1000) == Result::Ok);
        CHECK(NEAR(b.get(Prop::EngineRpm, 1000).value, 800.0, 0.5) && b.get(Prop::EngineRpm, 1000).available);
        CHECK(NEAR(b.get(Prop::BatteryV, 1000).value, 12.40, 0.001));
        CHECK(NEAR(b.get(Prop::SpeedMps, 1000).value, 0.0, 1e-6) && b.get(Prop::SpeedMps, 1000).available);
    }
    // GOLDEN: VehicleFluids 0x302: fuel 68 %, coolant 40.0 C, oil 150+ kPa (values from can_replay at t=0)
    {
        const uint8_t g[8] = {0x90, 0x1a, 0x90, 0x01, 0x5c, 0x08, 0x07, 0xab};
        vhal::Bridge b;
        CHECK(b.on_frame(0x302, g, 8, 0) == Result::Ok);
        CHECK(NEAR(b.get(Prop::FuelPct, 0).value, 68.0, 0.01));
        CHECK(NEAR(b.get(Prop::CoolantC, 0).value, 40.0, 0.05));
        CHECK(NEAR(b.get(Prop::OilKpa, 0).value, 214.0, 0.05));
    }

    // km/h to m/s
    {
        vhal::Bridge b;
        CHECK(send_motion(b, 90.0f, 3000, 0, 0) == Result::Ok);
        CHECK(NEAR(b.get(Prop::SpeedMps, 0).value, 25.0, 0.01));
    }

    // a valid flag of 0 makes the property unavailable even though the frame is fresh
    {
        vhal::Bridge b;
        CHECK(send_motion(b, 50.0f, 2000, 0, 0, /*speed_valid=*/false, /*rpm_valid=*/true) == Result::Ok);
        CHECK(!b.get(Prop::SpeedMps, 0).available && b.get(Prop::SpeedMps, 0).value == 0.0f);
        CHECK(b.get(Prop::EngineRpm, 0).available);
    }

    // staleness: available through 3 x 50 ms, gone after
    {
        vhal::Bridge b;
        send_motion(b, 10.0f, 1000, 0, 1000);
        CHECK(b.get(Prop::EngineRpm, 1150).available);
        CHECK(!b.get(Prop::EngineRpm, 1151).available);
        CHECK(!b.link_alive(1151));
        CHECK(b.link_alive(1100));
    }

    // 32-bit clock wrap does not make fresh data look stale
    {
        vhal::Bridge b;
        send_motion(b, 10.0f, 1000, 0, 0xFFFFFFF0u);
        CHECK(b.get(Prop::EngineRpm, 0x00000010u).available);          // 32 ms later across the wrap
        CHECK(!b.get(Prop::EngineRpm, 0x00000100u).available);         // 272 ms later
    }

    // bad CRC: rejected and the earlier value stays
    {
        vhal::Bridge b;
        send_motion(b, 20.0f, 1500, 0, 0);
        cluster_vehicle_motion_t m = {};
        m.speed_kph = 99.0f; m.rpm = 5000; m.speed_valid = m.rpm_valid = m.battery_valid = 1;
        uint8_t raw[8];
        cluster_vehicle_motion_pack(&m, 1, raw);
        raw[7] ^= 0x01;
        CHECK(b.on_frame(CAN_ID_VEHICLEMOTION, raw, 8, 10) == Result::BadCrc);
        CHECK(NEAR(b.get(Prop::EngineRpm, 10).value, 1500.0, 0.5));
        CHECK(b.stats().bad_crc == 1);
    }

    // wrong length and unknown id never touch state
    {
        vhal::Bridge b;
        uint8_t raw[8] = {};
        CHECK(b.on_frame(CAN_ID_VEHICLEMOTION, raw, 7, 0) == Result::BadLength);
        CHECK(b.on_frame(0x123, raw, 8, 0) == Result::UnknownId);
        CHECK(!b.link_alive(0));
    }

    // frozen sender: same counter does not refresh freshness
    {
        vhal::Bridge b;
        CHECK(send_motion(b, 30.0f, 1800, 5, 0) == Result::Ok);
        CHECK(send_motion(b, 30.0f, 1800, 5, 100) == Result::RepeatedCounter);
        CHECK(!b.get(Prop::EngineRpm, 200).available);                  // aged out from t = 0
        CHECK(send_motion(b, 30.0f, 1800, 6, 200) == Result::Ok);
        CHECK(b.get(Prop::EngineRpm, 200).available);
    }

    // missed frames are counted from counter gaps, including the 4-bit wrap
    {
        vhal::Bridge b;
        send_motion(b, 1.0f, 1000, 14, 0);
        send_motion(b, 1.0f, 1000, 1, 50);                              // 14 -> 1 skips 15 and 0
        CHECK(b.stats().missed_frames == 2);
        CHECK(b.stats().accepted == 2);
    }

    // indicators and power
    {
        vhal::Bridge b;
        cluster_indicators_t i = {};
        i.turn_left = 1; i.brake_warning = 1; i.dash_lights_on = 1; i.dash_dimmer_pct = 62;
        uint8_t raw[8];
        cluster_indicators_pack(&i, 0, raw);
        CHECK(b.on_frame(CAN_ID_INDICATORS, raw, 8, 0) == Result::Ok);
        CHECK(b.get(Prop::TurnLeft, 0).value == 1.0f && b.get(Prop::TurnRight, 0).value == 0.0f);
        CHECK(b.get(Prop::BrakeWarning, 0).value == 1.0f && b.get(Prop::DashLightsOn, 0).value == 1.0f);
        CHECK(NEAR(b.get(Prop::DashDimmerPct, 0).value, 62.0, 0.01));
        CHECK(!b.get(Prop::TurnLeft, 301).available);                   // 3 x 100 ms

        cluster_power_state_t p = {};
        p.ignition_on = 0; p.suspend_request = 1; p.suspend_in_seconds = 20;
        cluster_power_state_pack(&p, 3, raw);
        CHECK(b.on_frame(CAN_ID_POWERSTATE, raw, 8, 0) == Result::Ok);
        CHECK(b.get(Prop::SuspendRequest, 0).value == 1.0f && b.get(Prop::IgnitionOn, 0).value == 0.0f);
        CHECK(NEAR(b.get(Prop::SuspendInSeconds, 0).value, 20.0, 0.01));
    }

    if (failures) { std::printf("%d failure(s)\n", failures); return 1; }
    std::printf("vhal-bridge: all tests passed\n");
    return 0;
}
