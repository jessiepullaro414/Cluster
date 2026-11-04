// What the centre sends to gauges/ on the private link, and when; and how it reacts to PowerState.
// Pure C++17. Every frame is packed by the generated protocol/cluster_codec.h, never by hand.
//
// Messages (protocol/can_protocol.md, all DISPLAY -> GAUGES, 1000 ms):
//   0x400 DisplaySettings, 0x410 SpeedCalibration, 0x420 InputConfig, 0x430 TripCommand, 0x4F0 DisplayHeartbeat.
// Each goes out every period, and at once when its contents change, with its own rolling counter
// (gauges/ ignores a frame whose counter repeats, so a resend after a change must not reuse one).
#pragma once

#include <cstdint>
#include <string>

#include "bridge.h"

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

// What the key is known to be, from one source. Unknown: that source has nothing to say right now.
enum class Ignition : uint8_t { Unknown, Off, On };

// What main_linux.cpp has to do this loop.
enum class ParkAction : uint8_t {
    None,
    KeyOn,      // awake with the key on: clear the RTC alarm, carry on as normal
    Suspend,    // arm the RTC for alarm_s() seconds (0: leave the RTC alone), then suspend_cmd
    PowerOff,   // clear the RTC alarm, then poweroff_cmd
};

struct ParkInput {
    uint32_t now_ms = 0;                 // CLOCK_MONOTONIC: stops while suspended
    uint64_t boot_s = 0;                 // CLOCK_BOOTTIME: keeps counting while suspended
    Ignition pin = Ignition::Unknown;    // CTRL_WAKE1_MICO#; Unknown when not configured or unreadable
    Ignition link = Ignition::Unknown;   // PowerState.IgnitionOn; Unknown while PowerState is not fresh
    bool request_valid = false;          // PowerState is fresh, so the next two mean something
    bool suspend_request = false;
    uint32_t suspend_in_s = 0;
};

// The PowerState half of ParkInput, from the decoder.
ParkInput park_input(const vhal::Bridge& b, uint32_t now_ms, uint64_t boot_s, Ignition pin);

// The parked car, around PowerPolicy (docs/electrical-review.md section 9, B-01: brain/'s ignition latch). A suspended
// module still draws current, so every suspend arms the RTC; if the car is still parked when the time is up the module
// powers off, the latch lets go and the board falls to microamps. The next key on is then a cold boot.
//
// After a wake only the ignition matters, not what caused the wake:
//   * On is believed at once, from either source. A dark screen while driving is the failure to avoid, so neither a
//     broken link (the pin says On) nor a broken pin (a PowerState says On) can cause one.
//   * Off has to wait kGraceMs. gauges/ sleeps with its transceivers in standby, so the link is silent after an alarm
//     wake and also for the first moments of a key-on wake: gauges/ boots in about 0.5 s and sends PowerState every
//     500 ms, and Linux has to bring CAN back. Nothing saying On for that long reads as key off.
//   * Key off with time left is a stray wake: back to sleep with the alarm set to what is left, measured on
//     CLOCK_BOOTTIME from the first suspend of this parked period. Only a key on restarts that period.
//
// Three more ways to end up awake with the key off and nobody to say so, each of which would flatten the battery:
//   * The module booted after the key went off: it takes far longer to boot than gauges/ takes to count down and
//     sleep, so no SuspendRequest ever arrives. The same goes for a link that has broken. If the pin says Off and no
//     PowerState is heard for kGraceMs, that is a key off. Only the pin can start this, so a PC bench never does.
//   * suspend_cmd failed (command_failed()), or returned and nothing happened for kCommandTimeoutMs of awake time:
//     decide again and retry. After kMaxFailedSleeps in a row the module cannot sleep here, so it powers off.
//   * A power-off that did not happen: the same retry.
//
// A limit of 0 turns the timer off: no alarm and never a power-off. Key-off wakes still go back to sleep, because
// nothing else would. Pure logic: main_linux.cpp only reads the clocks and pin and runs the commands.
class ParkPolicy {
public:
    static constexpr uint32_t kGraceMs = 5000;
    static constexpr uint32_t kCommandTimeoutMs = 30000;
    static constexpr uint32_t kMaxFailedSleeps = 3;
    static constexpr uint32_t kEarlyAlarmS = 60;   // an alarm this close to the limit counts as the limit

    explicit ParkPolicy(uint32_t limit_s) : limit_s_(limit_s) {}

    // Call on every loop. Returns each action once.
    ParkAction update(const ParkInput& in);
    // CLOCK_BOOTTIME jumped against CLOCK_MONOTONIC: we were asleep. The caller also forgets what the decoder heard
    // before the sleep (a new vhal::Bridge): CLOCK_MONOTONIC stopped too, so it would still read as fresh.
    void resumed(uint32_t now_ms);
    // The command for Suspend or PowerOff exited non-zero.
    void command_failed(uint32_t now_ms);

    uint32_t alarm_s() const { return alarm_s_; }
    // A suspend or power-off is due or under way: the heartbeat says Suspending.
    bool going_down() const { return state_ == State::Waiting || power_.pending(); }
    // Waiting on a command or deciding after a wake: the pin is worth reading on every loop.
    bool parked() const { return state_ != State::Idle; }

private:
    enum class State : uint8_t { Idle, Waiting, Deciding };

    uint32_t limit_s_;
    PowerPolicy power_;
    State state_ = State::Idle;
    uint32_t since_ms_ = 0;         // Waiting: when the command ran. Deciding: when the grace started
    uint64_t parked_since_s_ = 0;   // CLOCK_BOOTTIME at the first suspend of this parked period
    uint32_t alarm_s_ = 0;
    uint32_t failed_ = 0;           // suspends in a row that did not put us to sleep
    bool quiet_ = false;            // Idle: the pin says Off and nothing has been heard since quiet_since_ms_
    uint32_t quiet_since_ms_ = 0;
};

// What to write to /sys/class/rtc/rtcN/wakealarm: "+N" arms N seconds from now, "0" clears. Writing a new alarm over
// an enabled one is EBUSY (drivers/rtc/sysfs.c), so clear first.
std::string wakealarm_text(uint32_t seconds_from_now);

}  // namespace clusterd
