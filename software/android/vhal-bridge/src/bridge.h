// Decodes private-link CAN frames into vehicle property values with freshness.
//
// Pure C++17, no Android or SocketCAN dependency: the AAOS vehicle HAL glue
// (PLAN.md B3) feeds it raw frames and publishes what snapshot() returns. All
// wire decoding is the generated protocol/cluster_codec.h, so this file adds
// only policy:
//   * a frame with a bad CRC, wrong length or unknown id never changes state;
//   * a frame whose rolling counter equals the previous one does not refresh
//     freshness (a frozen or replaying sender must age out, not look alive);
//   * a property is available only while its message is fresh (younger than
//     kStaleFactor x the protocol period) AND the sender's valid flag is set.
#pragma once

#include <cstdint>

namespace vhal {

enum class Prop : uint8_t {
    SpeedMps,            // PERF_VEHICLE_SPEED is metres per second
    EngineRpm,
    BatteryV,
    FuelPct,
    CoolantC,
    OilKpa,
    TurnLeft,
    TurnRight,
    HighBeam,
    BrakeWarning,
    AlternatorWarning,
    OilWarning,
    DashLightsOn,
    DashDimmerPct,
    IgnitionOn,
    SuspendRequest,
    SuspendInSeconds,
    FuelOhms,            // SenderOhms (0x305): live sender resistance, for measuring the curves in the car
    OilOhms,
    CoolantOhms,
    kCount
};

struct PropValue {
    float value = 0.0f;
    bool available = false;
};

enum class Result : uint8_t { Ok, UnknownId, BadLength, BadCrc, RepeatedCounter };

struct Stats {
    uint32_t accepted = 0;
    uint32_t bad_crc = 0;
    uint32_t bad_length = 0;
    uint32_t repeated_counter = 0;
    uint32_t missed_frames = 0;   // counter gaps: frames lost between two accepted ones
};

class Bridge {
public:
    static constexpr uint32_t kStaleFactor = 3;

    // One CAN frame. now_ms is any monotonic millisecond clock.
    Result on_frame(uint32_t id, const uint8_t* data, uint8_t len, uint32_t now_ms);

    // Current value of every property as of now_ms.
    PropValue get(Prop p, uint32_t now_ms) const;

    // True once a GaugesStatus or any other private frame was seen within the
    // freshness window of PowerState (the link is alive).
    bool link_alive(uint32_t now_ms) const;

    const Stats& stats() const { return stats_; }

private:
    struct Slot {
        bool seen = false;
        uint8_t counter = 0;
        uint32_t last_ms = 0;
        uint32_t period_ms = 0;
    };
    enum Msg { kMotion, kFluids, kIndicators, kPower, kSenders, kMsgCount };

    bool fresh(Msg m, uint32_t now_ms) const;
    Result accept(Msg m, uint8_t counter, uint32_t now_ms);

    Slot slot_[kMsgCount];
    // latest decoded raw message contents
    float speed_kph_ = 0, battery_v_ = 0, fuel_pct_ = 0, coolant_c_ = 0, oil_kpa_ = 0;
    uint32_t rpm_ = 0, dimmer_ = 0, suspend_s_ = 0;
    bool speed_ok_ = false, rpm_ok_ = false, battery_ok_ = false;
    bool fuel_ok_ = false, coolant_ok_ = false, oil_ok_ = false;
    bool turn_l_ = false, turn_r_ = false, high_ = false, brake_ = false, alt_ = false, oilw_ = false, dash_ = false;
    bool ign_ = false, susp_ = false;
    float ohm_[3] = {0, 0, 0};           // fuel, oil, coolant
    bool ohm_ok_[3] = {false, false, false};
    Stats stats_;
};

}  // namespace vhal
