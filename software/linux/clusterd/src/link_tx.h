// What the centre sends to gauges/ on the private link, and when; and how it reacts to PowerState.
// Pure C++17. Every frame is packed by the generated protocol/cluster_codec.h, never by hand.
//
// Messages (protocol/can_protocol.md, all DISPLAY -> GAUGES, 1000 ms):
//   0x400 DisplaySettings, 0x410 SpeedCalibration, 0x420 InputConfig, 0x430 TripCommand, 0x4F0 DisplayHeartbeat.
// Each goes out every period, and at once when its contents change, with its own rolling counter
// (gauges/ ignores a frame whose counter repeats, so a resend after a change must not reuse one).
#pragma once

#include <cstdint>

namespace clusterd {

struct Frame {
    uint32_t id = 0;
    uint8_t data[8] = {};
};

// What the user and the car's setup decide (settings page and clusterd.conf).
struct DisplayState {
    uint32_t brightness_pct = 100;
    bool night = false;
    bool units_mph = true;
    uint32_t gauge_theme = 1;
    bool centre_shows_speed = false;
};

struct VehicleSetup {
    uint32_t car_profile = 1;          // 0 none, 1 Haltech V2
    uint32_t car_bitrate = 1;          // 0 500k, 1 1M, 2 250k
    float tank_capacity_l = 60.0f;
    uint32_t pulses_per_mile = 16000;  // AutoMeter 16-pulse sender at 1000 rev/mile
    uint32_t lamp_invert_mask = 0;
    bool tach_enabled = false;
    uint32_t tach_pulses_per_rev = 4;  // V8 four-stroke
    uint32_t trip_reset_count = 0;     // bump (mod 16) to reset the trip meter once
};

enum class Heartbeat : uint32_t { Booting = 0, Running = 1, Suspending = 2 };

class LinkTx {
public:
    static constexpr uint32_t kPeriodMs = 1000;
    enum { kSettings, kCalib, kInput, kTrip, kHeartbeat, kCount };

    void set_display(const DisplayState& d);
    void set_vehicle(const VehicleSetup& v);
    void set_heartbeat(Heartbeat h);

    // Frames due at now_ms, into out (room for kCount). Returns how many.
    int poll(uint32_t now_ms, Frame* out);

private:
    void pack(int m, Frame* f);

    DisplayState disp_;
    VehicleSetup veh_;
    Heartbeat hb_ = Heartbeat::Booting;
    bool dirty_[kCount] = {true, true, true, true, true};
    bool sent_once_[kCount] = {};
    uint32_t last_ms_[kCount] = {};
    uint8_t counter_[kCount] = {};
};

// Ignition-off handling (PLAN.md: suspend-to-RAM, wake on ignition). gauges/ sets SuspendRequest and a
// countdown in PowerState; the centre saves its state, tells gauges/ it is suspending, and suspends when
// the countdown has run out. Ignition back on (the request cleared) before then cancels it.
class PowerPolicy {
public:
    // Call on every loop with the latest PowerState values (valid = the message is fresh).
    // Returns true exactly once, when it is time to suspend now.
    bool update(uint32_t now_ms, bool valid, bool suspend_request, uint32_t suspend_in_s);
    Heartbeat heartbeat() const { return pending_ ? Heartbeat::Suspending : Heartbeat::Running; }
    bool pending() const { return pending_; }
    // After waking up: start over.
    void resumed() { pending_ = fired_ = false; }

private:
    bool pending_ = false, fired_ = false;
    uint32_t due_ms_ = 0;
};

}  // namespace clusterd
