// Host tests for clusterd's logic: dial angle, shell, CAN transmit schedule, power and parked-car policy, telemetry
// JSON, LIVI status parsing, settings files. Frames are checked by unpacking them with the generated
// codec, the same code gauges/ runs.
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#include "bridge.h"
#include "dial_angle.h"
#include "link_tx.h"
#include "shell.h"
#include "state_io.h"
#include "telemetry.h"
extern "C" {
#include "cluster_codec.h"
}

using namespace clusterd;

static int failures, checks;
#define CHECK(c) do { checks++; if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)
#define HAS(s, sub) CHECK((s).find(sub) != std::string::npos)

// raw counts for an angle on a 12-bit sensor spanning 0..4095
static uint32_t raw_at(float deg) {
    while (deg < 0) deg += 360;
    while (deg >= 360) deg -= 360;
    return uint32_t(deg / 360.0f * 4096.0f);
}

static int turn_by(DialAngle& d, float from, float to, float step_deg = 1.0f) {
    int steps = 0;
    float dir = to > from ? 1.0f : -1.0f;
    for (float a = from; dir > 0 ? a <= to : a >= to; a += dir * step_deg) steps += d.sample(raw_at(a));
    for (int i = 0; i < 10; i++) steps += d.sample(raw_at(to));   // let the filter settle
    return steps;
}

static void test_dial() {
    {   // a full turn clockwise is 24 detents, and back again -24; across the 0/360 seam too. The end points
        // sit 5 degrees past a detent: the filter approaches its target and never quite lands on a boundary.
        DialAngle d;
        CHECK(d.sample(raw_at(350)) == 0);   // first reading only sets the anchor
        CHECK(turn_by(d, 350, 350 + 365) == 24);
        CHECK(turn_by(d, 350 + 365, 345) == -24);
    }
    {   // half a detent does nothing; a whole one does one step; dithering around a boundary does not chatter
        DialAngle d;
        d.sample(raw_at(100));
        CHECK(turn_by(d, 100, 107) == 0);
        CHECK(turn_by(d, 107, 116) == 1);
        int n = 0;
        for (int i = 0; i < 50; i++) n += d.sample(raw_at(i % 2 ? 114 : 117));
        CHECK(n == 0);
    }
    {   // a single wild reading is ignored; a far reading that persists becomes the new zero, with no steps
        DialAngle d;
        d.sample(raw_at(10));
        CHECK(d.sample(raw_at(200)) == 0);
        CHECK(turn_by(d, 10, 10) == 0);
        int n = 0;
        for (int i = 0; i < 5; i++) n += d.sample(raw_at(200));
        CHECK(n == 0);
        CHECK(turn_by(d, 200, 235) == 2);
    }
    {   // readings outside the valid band are ignored
        DialConfig c;
        c.raw_min = 200;
        c.raw_max = 3900;
        DialAngle d(c);
        CHECK(d.sample(100) == 0 && d.sample(4000) == 0);
        d.sample(1000);
        CHECK(d.sample(4050) == 0);
    }
    {   // exact one-detent jumps (a mouse wheel on the bench panel, 12 detents = 30 degrees) give one step each
        DialConfig c;
        c.detents_per_turn = 12;
        DialAngle d(c);
        d.sample(raw_at(0));
        int n = 0;
        for (int k = 1; k <= 6; k++)
            for (int i = 0; i < 20; i++) n += d.sample(raw_at(30.0f * k));
        CHECK(n == 6);
        for (int k = 5; k >= 0; k--)
            for (int i = 0; i < 20; i++) n += d.sample(raw_at(30.0f * k));
        CHECK(n == 0);
    }
    {   // rezero after a resume: a reading far away is the new zero, not a turn
        DialAngle d;
        d.sample(raw_at(0));
        d.rezero();
        CHECK(d.sample(raw_at(170)) == 0);
        CHECK(turn_by(d, 170, 170) == 0);
    }
}

static void test_shell() {
    Shell sh;
    // no phone, "No phone shows: Gauge" (the default): the dashboard
    Action a = sh.start();
    CHECK(a.path && std::string(a.path) == kPathGauge);
    CHECK(sh.centre_shows_speed());
    a = sh.turn(+1);   // hmi.h: turn on Home flips
    CHECK(a.path && std::string(a.path) == kPathMaps && a.key == Key::None);
    a = sh.turn(+1);
    CHECK(a.path && std::string(a.path) == kPathGauge);

    // CarPlay arrives while the gauge shows: maps come to the front
    a = sh.set_phone(Phone::CarPlay);
    CHECK(a.path && std::string(a.path) == kPathMaps);
    CHECK(sh.phone_owns_dial());
    CHECK(sh.gauge_theme() == 2);   // "With CarPlay: Apple look"
    CHECK(sh.set_phone(Phone::CarPlay).path == nullptr);
    // the dial now belongs to the phone
    a = sh.turn(-1);
    CHECK(a.key == Key::KnobLeft && a.path == nullptr);
    a = sh.turn(+1);
    CHECK(a.key == Key::KnobRight);
    uint32_t t = 1000;
    sh.press(t);
    a = sh.release(t + 120);
    CHECK(a.key == Key::Select);
    // hold 0.6 s: Back for the phone, then nothing until 1.5 s, then our speedometer, even with the phone
    t = 2000;
    sh.press(t);
    CHECK(sh.tick(t + 300).key == Key::None);
    a = sh.tick(t + 600);
    CHECK(a.key == Key::Back && a.path == nullptr);
    CHECK(sh.tick(t + 1000).path == nullptr);
    a = sh.tick(t + 1500);
    CHECK(a.path && std::string(a.path) == kPathGauge && a.key == Key::None);
    CHECK(sh.view() == View::Gauge && sh.centre_shows_speed());
    CHECK(sh.tick(t + 1600).path == nullptr);
    a = sh.release(t + 1700);
    CHECK(a.key == Key::None && a.path == nullptr);   // letting go after a long press does nothing
    CHECK(!sh.phone_owns_dial());

    // on our speedometer the dial is ours: a turn goes back to the map (and the phone gets the dial again) ...
    a = sh.turn(+1);
    CHECK(a.path && std::string(a.path) == kPathMaps && a.key == Key::None && sh.phone_owns_dial());
    // ... the 1.5 s hold again for the speedometer, and from it a 0.6 s hold opens Settings
    sh.press(2800);
    sh.tick(3400);                        // Back to the phone
    a = sh.tick(4300);
    CHECK(a.path && std::string(a.path) == kPathGauge);
    sh.release(4400);
    sh.press(4500);
    a = sh.tick(5100);
    CHECK(sh.ui().screen() == hmi::Screen::Settings && a.path == nullptr && a.key == Key::None);   // gauge and settings share /custom
    sh.release(5200);

    // in Settings the dial is ours: turn moves rows, no keys to the phone
    a = sh.turn(+1);
    CHECK(a.key == Key::None && sh.ui().row() == hmi::Row::MatchCarPlay);
    // edit "With CarPlay": off, keep -> the small screens go back to the owner's theme
    sh.press(5300);
    sh.release(5350);
    sh.turn(+1);
    sh.press(5400);
    sh.release(5450);
    CHECK(sh.mutable_ui().take_committed());
    CHECK(!sh.ui().model().match_carplay && sh.gauge_theme() == 1);
    // hold in the list: back to Home on our speedometer; a click there goes back to the map and the phone
    sh.press(6000);
    sh.tick(6600);
    sh.release(6700);
    CHECK(sh.ui().screen() == hmi::Screen::Home && sh.view() == View::Gauge);
    sh.press(6800);
    a = sh.release(6850);
    CHECK(a.path && std::string(a.path) == kPathMaps && sh.phone_owns_dial());

    // a short hold that ends before 1.5 s is only Back
    sh.press(8000);
    CHECK(sh.tick(8600).key == Key::Back);
    sh.release(8800);
    CHECK(sh.tick(10000).path == nullptr);

    // a busy loop: a 0.7 s hold whose release arrives before any tick saw 0.6 s is still a hold, never a click
    {
        Shell b;
        b.start();
        b.turn(+1);                       // Home on the maps (no phone): a hold opens Settings
        b.press(10000);
        Action late = b.release(10700);
        CHECK(late.path && std::string(late.path) == kPathSettings && b.ui().screen() == hmi::Screen::Settings);
        b.press(11000);
        b.release(11100);                 // a short press is still a click: edit the row
        CHECK(b.ui().screen() == hmi::Screen::Edit);
    }

    // Android Auto: the owner's theme on the small screens
    sh.set_phone(Phone::AndroidAuto);
    CHECK(sh.gauge_theme() == 1);
    // phone leaves: back to the no-phone default, the gauge
    a = sh.set_phone(Phone::None);
    CHECK(a.path && std::string(a.path) == kPathGauge);

    // "No phone shows: Home" starts on LIVI's own home
    Shell h;
    h.mutable_ui().mutable_model().no_phone_home = true;
    a = h.start();
    CHECK(a.path && std::string(a.path) == kPathMaps && !h.phone_owns_dial());
    CHECK(h.turn(+1).key == Key::None);   // with no phone a turn flips, it is not a knob key
}

static void test_link_tx() {
    LinkTx tx;
    VehicleSetup v;
    v.pulses_per_mile = 16000;
    v.tank_capacity_l = 62.5f;
    v.lamp_invert_mask = 0x05;
    v.tach_enabled = true;
    v.tach_pulses_per_rev = 4;
    tx.set_vehicle(v);
    DisplayState d;
    d.brightness_pct = 70;
    d.units_mph = false;
    d.gauge_theme = 3;
    d.centre_shows_speed = true;
    tx.set_display(d);
    tx.set_heartbeat(Heartbeat::Running);

    Frame f[LinkTx::kCount];
    int n = tx.poll(10, f);
    CHECK(n == 5);
    bool seen[5] = {};
    for (int i = 0; i < n; i++) {
        switch (f[i].id) {
            case CAN_ID_DISPLAYSETTINGS: {
                cluster_display_settings_t s;
                CHECK(cluster_display_settings_unpack(f[i].data, &s) == 0);
                CHECK(s.brightness_pct == 70 && !s.units_mph && s.gauge_theme == 3 && s.center_shows_speed && s.car_profile == 1 && s.car_bitrate == 1);
                CHECK(std::fabs(s.tank_capacity_l - 62.5f) < 0.06f);
                seen[0] = true;
                break;
            }
            case CAN_ID_SPEEDCALIBRATION: {
                cluster_speed_calibration_t s;
                CHECK(cluster_speed_calibration_unpack(f[i].data, &s) == 0 && s.pulses_per_mile == 16000);
                seen[1] = true;
                break;
            }
            case CAN_ID_INPUTCONFIG: {
                cluster_input_config_t s;
                CHECK(cluster_input_config_unpack(f[i].data, &s) == 0 && s.lamp_invert_mask == 5 && s.tach_enabled && s.tach_pulses_per_rev == 4);
                seen[2] = true;
                break;
            }
            case CAN_ID_TRIPCOMMAND: seen[3] = true; break;
            case CAN_ID_DISPLAYHEARTBEAT: {
                cluster_display_heartbeat_t s;
                CHECK(cluster_display_heartbeat_unpack(f[i].data, &s) == 0 && s.state == 1 && s.counter == 0);
                seen[4] = true;
                break;
            }
        }
    }
    CHECK(seen[0] && seen[1] && seen[2] && seen[3] && seen[4]);
    CHECK(tx.poll(500, f) == 0);           // nothing changed, not due
    d.gauge_theme = 2;
    tx.set_display(d);
    n = tx.poll(510, f);                   // a change goes out at once, with the next counter
    CHECK(n == 1 && f[0].id == CAN_ID_DISPLAYSETTINGS);
    cluster_display_settings_t s;
    CHECK(cluster_display_settings_unpack(f[0].data, &s) == 0 && s.gauge_theme == 2 && s.counter == 1);
    tx.set_display(d);                     // the same values again: no extra frame
    CHECK(tx.poll(520, f) == 0);
    n = tx.poll(1010, f);                  // the period: the four others (settings was sent at 510)
    CHECK(n == 4);
    n = tx.poll(1510, f);
    CHECK(n == 1 && f[0].id == CAN_ID_DISPLAYSETTINGS);
    // counters wrap at 16 and never repeat back to back
    uint8_t last = 0xFF;
    bool repeat = false;
    for (uint32_t k = 0; k < 40; k++) {
        n = tx.poll(2000 + k * 1000, f);
        for (int i = 0; i < n; i++)
            if (f[i].id == CAN_ID_DISPLAYHEARTBEAT) {
                cluster_display_heartbeat_t h = {};
                CHECK(cluster_display_heartbeat_unpack(f[i].data, &h) == 0);
                if (h.counter == last) repeat = true;
                last = h.counter;
            }
    }
    CHECK(!repeat && last < 16);
    // trip reset: a bump sends TripCommand at once
    v.trip_reset_count = 1;
    tx.set_vehicle(v);
    n = tx.poll(50000, f);
    bool trip = false;
    for (int i = 0; i < n; i++)
        if (f[i].id == CAN_ID_TRIPCOMMAND) {
            cluster_trip_command_t c;
            trip = cluster_trip_command_unpack(f[i].data, &c) == 0 && c.trip_reset_count == 1;
        }
    CHECK(trip);
}

static void test_power() {
    PowerPolicy p;
    CHECK(!p.update(0, true, false, 0) && p.heartbeat() == Heartbeat::Running);
    CHECK(!p.update(100, true, true, 3) && p.pending() && p.heartbeat() == Heartbeat::Suspending);
    CHECK(!p.update(3000, true, true, 2));   // the countdown ticking down does not move the deadline
    CHECK(p.update(3100, true, true, 0));    // fires once
    CHECK(!p.update(3200, true, true, 0));
    p.resumed();
    CHECK(!p.pending());
    // ignition back on before the deadline cancels
    CHECK(!p.update(10000, true, true, 5));
    CHECK(!p.update(12000, true, false, 0) && !p.pending());
    CHECK(!p.update(20000, true, false, 0));
    // stale PowerState changes nothing
    CHECK(!p.update(30000, true, true, 1));
    CHECK(!p.update(40000, false, false, 0) && p.pending());
    CHECK(p.update(40001, true, true, 0));
    // zero seconds: at once
    PowerPolicy q;
    CHECK(q.update(5, true, true, 0));
}

static void feed_power(vhal::Bridge& b, uint32_t t, uint8_t ctr, bool ign, bool req, uint32_t secs) {
    uint8_t raw[8];
    cluster_power_state_t m = {};
    m.ignition_on = ign; m.suspend_request = req; m.suspend_in_seconds = secs;
    cluster_power_state_pack(&m, ctr, raw);
    b.on_frame(CAN_ID_POWERSTATE, raw, 8, t);
}

// A car for the parked tests: the policy and both clocks. Awake time moves both; a sleep moves only CLOCK_BOOTTIME.
struct Car {
    ParkPolicy p;
    uint32_t now = 1000;
    uint64_t boot = 500;
    uint32_t boot_ms = 0;
    explicit Car(uint32_t limit_s) : p(limit_s) {}

    ParkInput in(Ignition pin, Ignition link) const {
        ParkInput i;
        i.now_ms = now;
        i.boot_s = boot;
        i.pin = pin;
        i.link = link;
        return i;
    }
    void tick() {
        now += 100;
        boot_ms += 100;
        if (boot_ms == 1000) { boot_ms = 0; boot++; }
    }
    // Runs ms of awake time in 100 ms loops. Returns the first action asked for, or None.
    ParkAction run(uint32_t ms, Ignition pin = Ignition::Unknown, Ignition link = Ignition::Unknown) {
        for (uint32_t t = 0; t < ms; t += 100) {
            tick();
            ParkAction a = p.update(in(pin, link));
            if (a != ParkAction::None) return a;
        }
        return ParkAction::None;
    }
    // One loop with gauges/ awake, saying the key is off and it wants a suspend in secs.
    ParkAction gauges_off(uint32_t secs, Ignition pin = Ignition::Off) {
        tick();
        ParkInput i = in(pin, Ignition::Off);
        i.request_valid = i.suspend_request = true;
        i.suspend_in_s = secs;
        return p.update(i);
    }
    // One loop with gauges/ awake and the key on.
    ParkAction gauges_on() {
        tick();
        ParkInput i = in(Ignition::On, Ignition::On);
        i.request_valid = true;
        return p.update(i);
    }
    void sleep(uint64_t s) {
        boot += s;
        p.resumed(now);
    }
};

static void test_park() {
    using A = ParkAction;
    using I = Ignition;
    const uint32_t kGrace = ParkPolicy::kGraceMs;
    const uint32_t kLimit = 48u * 3600u;

    {   // the alarm wakes it with the key still off and gauges/ asleep: it powers off, once, after the grace
        Car c(kLimit);
        CHECK(c.gauges_off(0) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit);
        CHECK(c.p.going_down() && c.p.parked());
        c.sleep(kLimit);
        CHECK(c.run(kGrace - 100, I::Off) == A::None);    // the link gets its chance first
        CHECK(c.run(100, I::Off) == A::PowerOff);
        CHECK(c.run(10000, I::Off) == A::None);           // asked once
        CHECK(c.p.going_down());
    }
    {   // key-on wake, from the pin: carries on at once, and nothing happens however long the drive
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(1000);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(!c.p.parked() && !c.p.going_down());
        CHECK(c.run(3600000, I::On, I::On) == A::None);
    }
    {   // key-on wake after the whole limit: the key decides, not the time
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit * 2);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(c.run(100000, I::On, I::On) == A::None);
    }
    {   // key turned on during the alarm wake, at the last loop before it would have fired
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(kGrace - 100, I::Off) == A::None);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(c.run(100000, I::On) == A::None);
    }
    {   // the same, seen only on the link: the pin is unreadable and gauges/ has just come up
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(kGrace - 200) == A::None);
        CHECK(c.run(100, I::Unknown, I::On) == A::KeyOn);
    }
    {   // the policy disabled: no alarm, never a power-off, however long or however often it fails to sleep
        Car c(0);
        CHECK(c.gauges_off(0) == A::Suspend);
        CHECK(c.p.alarm_s() == 0);
        c.sleep(10u * 365u * 24u * 3600u);
        CHECK(c.run(kGrace, I::Off) == A::Suspend);       // a stray wake still goes back to sleep
        CHECK(c.p.alarm_s() == 0);
        for (int i = 0; i < 10; i++) {
            c.p.command_failed(c.now);
            CHECK(c.run(kGrace, I::Off) == A::Suspend);
            CHECK(c.p.alarm_s() == 0);
        }
        c.sleep(1000);
        CHECK(c.run(100, I::On) == A::KeyOn);
    }

    // ---- a quiet gauges link at resume
    {   // the pin says On, the link never speaks: the screen stays up, whatever is wrong with gauges/
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(c.run(3600000, I::On) == A::None);
    }
    {   // no pin, and the link is silent for less than the grace, then says On: never a decision before that
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(kGrace - 2000) == A::None);
        CHECK(c.run(100, I::Unknown, I::On) == A::KeyOn);
    }
    {   // no pin and silence for the whole grace reads as key off: gauges/ sleeps at key off
        Car c(kLimit);
        c.gauges_off(0, I::Unknown);
        c.sleep(kLimit);
        CHECK(c.run(kGrace) == A::PowerOff);
    }
    {   // the two sources disagree: On wins, either way round
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(100, I::Off, I::On) == A::KeyOn);
        Car d(kLimit);
        d.gauges_off(0);
        d.sleep(kLimit);
        CHECK(d.run(100, I::On, I::Off) == A::KeyOn);
    }

    // ---- stray wakes and the clock
    {   // a stray wake goes back to sleep with what is left, and the alarm then ends it on time
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(3600);
        CHECK(c.run(kGrace, I::Off) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit - 3600 - 5);        // 5 s of grace counted too
        c.sleep(c.p.alarm_s());
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
    }
    {   // an alarm that comes a little early still counts; earlier than that is a stray wake
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit - 30);
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
        Car d(kLimit);
        d.gauges_off(0);
        d.sleep(kLimit - ParkPolicy::kEarlyAlarmS - 10);
        CHECK(d.run(kGrace, I::Off) == A::Suspend);
        CHECK(d.p.alarm_s() == ParkPolicy::kEarlyAlarmS + 5);
    }
    {   // a drive starts the parked period again
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit - 100);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(c.run(600000, I::On, I::On) == A::None);
        CHECK(c.gauges_off(0) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit);
        c.sleep(kLimit - 100);
        CHECK(c.run(kGrace, I::Off) == A::Suspend);       // not up yet, counted from this key off
    }
    {   // gauges/ never slept: its key-off frames neither restart the period nor start a second suspend
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        for (uint32_t t = 0; t < kGrace - 100; t += 100) CHECK(c.gauges_off(0) == A::None);
        CHECK(c.gauges_off(0) == A::PowerOff);
        Car d(kLimit);
        d.gauges_off(0);
        d.sleep(1000);
        int suspends = 0;
        for (uint32_t t = 0; t < kGrace + 1000; t += 100) suspends += d.gauges_off(0) == A::Suspend;
        CHECK(suspends == 1);
    }
    {   // a blip of the key: gauges/ wakes, says On, then counts down again. A full new parked period.
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit - 10);
        CHECK(c.run(100, I::Off, I::On) == A::KeyOn);
        CHECK(c.gauges_off(1) == A::None);
        CHECK(c.p.going_down());
        CHECK(c.gauges_off(1) == A::None);
        for (uint32_t t = 0; t < 700; t += 100) CHECK(c.gauges_off(1) == A::None);
        CHECK(c.gauges_off(0) == A::None);                // 1 s from the first request, not from each frame
        CHECK(c.gauges_off(0) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit);
    }
    {   // the millisecond clock wraps during a wake
        Car c(kLimit);
        c.now = 0xFFFFFFFFu - 2000u;
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(kGrace - 100, I::Off) == A::None);
        CHECK(c.run(100, I::Off) == A::PowerOff);
    }

    // ---- what the decoder hears around a sleep
    {
        vhal::Bridge b;
        const uint32_t t = 5000;
        feed_power(b, t, 3, true, false, 0);
        ParkInput i = park_input(b, t, 77, I::Off);
        CHECK(i.link == I::On && i.pin == I::Off && i.request_valid && !i.suspend_request && i.now_ms == t && i.boot_s == 77);
        feed_power(b, t + 500, 4, false, true, 4);
        i = park_input(b, t + 500, 77, I::Unknown);
        CHECK(i.link == I::Off && i.request_valid && i.suspend_request && i.suspend_in_s == 4);
        // no PowerState for 3 periods: the link has nothing to say
        i = park_input(b, t + 500 + 1501, 77, I::Unknown);
        CHECK(i.link == I::Unknown && !i.request_valid && !i.suspend_request);

        // CLOCK_MONOTONIC stops in suspend, so a request from just before the sleep still reads as fresh on waking...
        vhal::Bridge s;
        feed_power(s, t, 5, false, true, 0);
        CHECK(park_input(s, t + 100, 77, I::On).suspend_request);
        // ... which is why main_linux.cpp starts a new decoder at resume: the key is on, and nothing puts it back down
        s = vhal::Bridge();
        i = park_input(s, t + 100, 77, I::On);
        CHECK(i.link == I::Unknown && !i.request_valid);
        Car c(kLimit);
        c.now = t;
        CHECK(c.gauges_off(0) == A::Suspend);
        c.sleep(1000);
        CHECK(c.p.update(i) == A::KeyOn);
        i.now_ms = t + 200;
        CHECK(c.p.update(i) == A::None);
        // and gauges/ after its reset is heard even if its counter happens to match its last frame
        feed_power(s, t + 300, 5, true, false, 0);
        CHECK(park_input(s, t + 300, 77, I::On).link == I::On);
    }

    // ---- nobody to say the key went off
    {   // booted with the key already off: gauges/ is asleep, no request will come, the pin is the only witness
        Car c(kLimit);
        CHECK(c.run(kGrace, I::Off) == A::None);          // counted from the first loop that saw it
        CHECK(c.run(100, I::Off) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit);
        c.sleep(kLimit);
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
    }
    {   // the key coming on before the grace ends starts it over, and PowerState heard means gauges/ is in charge
        Car c(kLimit);
        CHECK(c.run(kGrace, I::Off) == A::None);
        CHECK(c.run(100, I::On) == A::None);
        CHECK(c.run(kGrace, I::Off) == A::None);
        CHECK(c.run(100, I::Off, I::Off) == A::None);
        CHECK(c.run(kGrace, I::Off) == A::None);
        CHECK(c.run(100000, I::Off, I::On) == A::None);
        CHECK(c.run(100000, I::On) == A::None);
    }
    {   // a wake in the middle of that wait starts it over: gauges/ gets its whole chance to come up
        Car c(kLimit);
        CHECK(c.run(kGrace, I::Off) == A::None);
        c.sleep(1000);
        CHECK(c.run(kGrace, I::Off) == A::None);
        CHECK(c.run(100, I::Off) == A::Suspend);
    }
    {   // no pin and no gauges, as on a PC bench: nothing, ever, even across a resume nobody here asked for
        Car c(kLimit);
        CHECK(c.run(100000) == A::None);
        c.sleep(kLimit * 2);
        CHECK(c.run(100000) == A::None);
        CHECK(!c.p.parked());
    }
    {   // a resume nobody here asked for, on the car, with the key off: the pin path puts it back
        Car c(kLimit);
        CHECK(c.run(100, I::On) == A::None);
        c.sleep(1000);
        CHECK(c.run(kGrace + 100, I::Off) == A::Suspend);
        CHECK(c.p.alarm_s() == kLimit);
    }

    // ---- commands that do not work
    {   // suspend_cmd fails: try again after the grace, and after kMaxFailedSleeps power off rather than run flat
        Car c(kLimit);
        CHECK(c.gauges_off(0) == A::Suspend);
        for (uint32_t i = 1; i < ParkPolicy::kMaxFailedSleeps; i++) {
            c.p.command_failed(c.now);
            CHECK(c.run(kGrace - 100, I::Off) == A::None);
            CHECK(c.run(100, I::Off) == A::Suspend);
        }
        c.p.command_failed(c.now);
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
    }
    {   // suspend_cmd returns 0 and nothing happens: the same, on a timeout of awake time
        Car c(kLimit);
        CHECK(c.gauges_off(0) == A::Suspend);
        for (uint32_t i = 1; i < ParkPolicy::kMaxFailedSleeps; i++) {
            CHECK(c.run(ParkPolicy::kCommandTimeoutMs + kGrace - 100, I::Off) == A::None);
            CHECK(c.run(100, I::Off) == A::Suspend);
        }
        CHECK(c.run(ParkPolicy::kCommandTimeoutMs + kGrace, I::Off) == A::PowerOff);
    }
    {   // a suspend that did not take and then the key: carries on, and the failures are forgotten
        Car c(kLimit);
        c.gauges_off(0);
        CHECK(c.run(ParkPolicy::kCommandTimeoutMs - 100, I::On) == A::None);
        CHECK(c.run(100, I::On) == A::KeyOn);
        CHECK(!c.p.parked());
        CHECK(c.gauges_on() == A::None);
        CHECK(c.gauges_off(0) == A::Suspend);
        for (uint32_t i = 1; i < ParkPolicy::kMaxFailedSleeps; i++) {
            c.p.command_failed(c.now);
            CHECK(c.run(kGrace, I::Off) == A::Suspend);
        }
        c.p.command_failed(c.now);                        // the one that would have ended in a power-off, but the key
        CHECK(c.gauges_on() == A::KeyOn);
        CHECK(c.gauges_off(0) == A::Suspend);
        for (uint32_t i = 1; i < ParkPolicy::kMaxFailedSleeps; i++) {
            c.p.command_failed(c.now);
            CHECK(c.run(kGrace, I::Off) == A::Suspend);
        }
    }
    {   // a sleep that really happened clears the failures too
        Car c(kLimit);
        c.gauges_off(0);
        for (uint32_t i = 1; i < ParkPolicy::kMaxFailedSleeps; i++) {
            c.p.command_failed(c.now);
            CHECK(c.run(kGrace, I::Off) == A::Suspend);
        }
        c.sleep(1000);
        CHECK(c.run(kGrace, I::Off) == A::Suspend);
        CHECK(c.p.alarm_s() != 0);
        c.p.command_failed(c.now);                        // one more would have been the last, without that sleep
        CHECK(c.run(kGrace, I::Off) == A::Suspend);
    }
    {   // a power-off that fails or never happens is asked for again, and the key can still save it
        Car c(kLimit);
        c.gauges_off(0);
        c.sleep(kLimit);
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
        c.p.command_failed(c.now);
        CHECK(c.run(kGrace, I::Off) == A::PowerOff);
        CHECK(c.run(ParkPolicy::kCommandTimeoutMs + kGrace, I::Off) == A::PowerOff);
        CHECK(c.run(ParkPolicy::kCommandTimeoutMs, I::On) == A::KeyOn);
    }

    // the heartbeat follows gauges/'s countdown, as before
    {
        Car c(kLimit);
        CHECK(!c.p.going_down());
        CHECK(c.gauges_off(5) == A::None);
        CHECK(c.p.going_down() && !c.p.parked());
        c.tick();
        ParkInput on = c.in(I::On, I::On);
        on.request_valid = true;
        CHECK(c.p.update(on) == A::None);                 // key back on before the countdown ends: cancelled
        CHECK(!c.p.going_down());
    }

    CHECK(wakealarm_text(0) == "0");
    CHECK(wakealarm_text(172800) == "+172800");
}

static void feed(vhal::Bridge& b, uint32_t t, uint8_t ctr, float kph, bool left, bool right, bool lights) {
    uint8_t raw[8];
    cluster_vehicle_motion_t m = {};
    m.speed_kph = kph; m.rpm = 2500; m.battery_v = 13.9f;
    m.speed_valid = 1; m.rpm_valid = 1; m.battery_valid = 1;
    cluster_vehicle_motion_pack(&m, ctr, raw);
    b.on_frame(CAN_ID_VEHICLEMOTION, raw, 8, t);
    cluster_indicators_t ind = {};
    ind.turn_left = left; ind.turn_right = right; ind.dash_lights_on = lights; ind.high_beam = 1;
    ind.dash_dimmer_pct = 40;
    cluster_indicators_pack(&ind, ctr, raw);
    b.on_frame(CAN_ID_INDICATORS, raw, 8, t);
}

static void test_telemetry() {
    vhal::Bridge b;
    feed(b, 1000, 0, 72.0f, true, false, true);
    std::string j = telemetry_json(b, 1000);
    HAS(j, "\"speedKph\":72.0");
    HAS(j, "\"rpm\":2500");
    HAS(j, "\"batteryV\":13.90");
    HAS(j, "\"coolantC\":null");          // no VehicleFluids yet
    HAS(j, "\"turnSignal\":\"left\"");
    HAS(j, "\"hazards\":false");
    HAS(j, "\"highBeam\":true");
    HAS(j, "\"nightMode\":true");
    HAS(j, "\"dimmerPct\":40");
    CHECK(j.front() == '{' && j.back() == '}');
    feed(b, 1050, 1, 72.0f, true, true, false);
    j = telemetry_json(b, 1050);
    HAS(j, "\"turnSignal\":\"none\"");
    HAS(j, "\"hazards\":true");
    HAS(j, "\"nightMode\":false");
    j = telemetry_json(b, 60000);         // everything stale
    HAS(j, "\"speedKph\":null");
    HAS(j, "\"turnSignal\":null");
    CHECK(j.find("72.0") == std::string::npos);
    // LIVI's core socket frames: little-endian length, then the JSON of livi-core-proto's ToCore
    {
        std::string k = livi_key_frame("F14", true);
        std::string body = "{\"type\":\"input\",\"input\":{\"kind\":\"key\",\"code\":\"F14\",\"down\":true}}";
        CHECK(k.size() == 4 + body.size() && k.substr(4) == body);
        CHECK(uint8_t(k[0]) == body.size() && k[1] == 0 && k[2] == 0 && k[3] == 0);
        std::string h = livi_hello_frame("clusterd");
        CHECK(h.substr(4) == "{\"type\":\"hello\",\"protocol\":8,\"client\":\"clusterd\"}");
    }
    // the harness line, the same text the Android app's Telemetry.encode writes
    {
        vhal::Bridge hb;
        feed(hb, 1000, 0, 72.0f, true, false, true);    // VehicleMotion carries 0.1 km/h steps: 72.0 exactly
        std::string l = harness_line(hb, 1000, true, 3, false);
        CHECK(l.rfind("CL1 imperial=1 theme=3 center=0 speed=72.00 rpm=2500 batt=13.90 fuel=- cool=- oil=-", 0) == 0);
        HAS(l, " tl=1 tr=0 hb=1 br=0 alt=0 oilw=0 dash=1 dim=40");
        l = harness_line(hb, 60000, false, 1, true);
        CHECK(l.rfind("CL1 imperial=0 theme=1 center=1 speed=- rpm=-", 0) == 0);
    }
    CHECK(path_json("/custom") == "{\"path\":\"/custom\"}");
    CHECK(path_json("/a\"b") == "{\"path\":\"/ab\"}");
    std::FILE* f = std::fopen("build/telemetry_sample.json", "w");
    if (f) { feed(b, 70000, 2, 88.5f, false, true, true); std::fputs(telemetry_json(b, 70000).c_str(), f); std::fclose(f); }
}

static void test_state_io() {
    CHECK(parse_livi_phone("{\"ui\":{\"path\":\"/\"},\"projection\":{\"active\":\"cp\",\"streaming\":true,\"phoneType\":\"CarPlay\"}}") == Phone::CarPlay);
    CHECK(parse_livi_phone("{\n  \"ui\": {\"path\": \"/\"},\n  \"projection\": {\n    \"active\": \"aa\",\n    \"streaming\": true }}") == Phone::AndroidAuto);
    CHECK(parse_livi_phone("{\"projection\":{\"active\":null,\"streaming\":false,\"phoneType\":null}}") == Phone::None);
    CHECK(parse_livi_phone("") == Phone::None);
    CHECK(parse_livi_phone("{\"projection\":") == Phone::None);

    Config c;
    DialConfig dc;
    c.dial = &dc;
    parse_config("# car\ncar_profile = 0\ncar_bitrate=2\ntank_capacity_l = 64.5  # litres\npulses_per_mile = 8000\n"
                 "lamp_invert_mask = 0x21\ntheme = 3\nbrightness = 7\nbogus = 1\ncan_if = vcan0\ndial_detents = 32\n"
                 "map_shape_cmd = /usr/bin/livi_config --shape\n", &c);
    CHECK(c.vehicle.car_profile == 0 && c.vehicle.car_bitrate == 2 && c.vehicle.pulses_per_mile == 8000);
    CHECK(std::fabs(c.vehicle.tank_capacity_l - 64.5f) < 1e-4f && c.vehicle.lamp_invert_mask == 0x21);
    CHECK(c.model.theme == 3 && c.model.brightness == 100);   // 7 % is out of range: kept the default
    CHECK(c.can_if == "vcan0" && dc.detents_per_turn == 32 && c.map_shape_cmd == "/usr/bin/livi_config --shape");

    {   // the shipped example config parses to what it says
        std::FILE* ex = std::fopen("../deploy/clusterd.conf.example", "r");
        CHECK(ex != nullptr);
        std::string text;
        if (ex) { char b[512]; size_t n; while ((n = std::fread(b, 1, sizeof b, ex)) > 0) text.append(b, n); std::fclose(ex); }
        Config e;
        DialConfig edc;
        e.dial = &edc;
        parse_config(text, &e);
        CHECK(e.can_if == "can1" && e.vehicle.pulses_per_mile == 16000 && e.vehicle.tach_pulses_per_rev == 4);
        CHECK(e.suspend_cmd == "systemctl suspend" && e.map_shape_cmd.find("livi_config.py --apply") != std::string::npos);
        CHECK(e.poweroff_cmd == "systemctl poweroff" && e.parked_poweroff_s == 48u * 3600u);
        CHECK(e.rtc_wakealarm == "/sys/class/rtc/rtc1/wakealarm");
        CHECK(edc.detents_per_turn == 24 && edc.raw_max == 4095);
    }

    {   // the parked timer: hours with decimals, 0 turns it off, and anything else keeps the battery protected
        auto hours = [](const char* v) {
            Config p;
            parse_config(std::string("parked_poweroff_hours = ") + v + "\n", &p);
            return p.parked_poweroff_s;
        };
        const uint32_t kDefault = Config().parked_poweroff_s;
        CHECK(kDefault == 48u * 3600u);
        CHECK(hours("24") == 24u * 3600u);
        CHECK(hours("0") == 0);
        CHECK(hours("0.05") == 180);                   // bring-up: 3 minutes
        CHECK(hours("720") == 720u * 3600u);
        CHECK(hours("721") == kDefault && hours("-1") == kDefault && hours("0.001") == kDefault);
        CHECK(hours("never") == kDefault && hours("48h") == kDefault && hours("nan") == kDefault);
        Config p;
        parse_config("poweroff_cmd = /bin/echo off\nrtc_wakealarm = /tmp/alarm\nparked_poweroff_hours =\n", &p);
        CHECK(p.poweroff_cmd == "/bin/echo off" && p.rtc_wakealarm == "/tmp/alarm" && p.parked_poweroff_s == kDefault);
    }

    hmi::Model m;
    m.theme = 0; m.match_carplay = false; m.imperial = false; m.no_phone_home = true; m.map_shape = 2; m.brightness = 40;
    VehicleSetup v;
    v.trip_reset_count = 9;
    Config back;
    parse_config(format_settings(m, v), &back);
    CHECK(back.model == m && back.vehicle.trip_reset_count == 9);

    {   // can_replay.py --dry-run lines, the bench input
        uint32_t t, id;
        uint8_t d[8], n;
        CHECK(parse_replay_line("  1.234s  0x300  VehicleMotion      00 00 20 03 d8 04 0f 53", &t, &id, d, &n));
        CHECK(t == 1234 && id == 0x300 && n == 8 && d[2] == 0x20 && d[7] == 0x53);
        CHECK(!parse_replay_line("sent 2308 frames", &t, &id, d, &n));
        CHECK(!parse_replay_line("  0.000s  0x300  VehicleMotion", &t, &id, d, &n));
        CHECK(!parse_replay_line("  0.000s  0x300  X 00 11 22 33 44 55 66 77 88", &t, &id, d, &n));
        CHECK(!parse_replay_line("  0.000s  300  X 00", &t, &id, d, &n));
        CHECK(!parse_replay_line("  0.000s  0x300  X 0g", &t, &id, d, &n));
    }

    {   // the simulated CAN bus datagram
        const uint8_t ok[13] = {0x00, 0x03, 0, 0, 8, 1, 2, 3, 4, 5, 6, 7, 8};
        uint32_t id;
        uint8_t d[8], n;
        CHECK(parse_udp_can(ok, 13, &id, d, &n) && id == 0x300 && n == 8 && d[0] == 1 && d[7] == 8);
        const uint8_t big[13] = {0x00, 0x08, 0, 0, 8};     // 0x800: not an 11-bit id
        CHECK(!parse_udp_can(big, 13, &id, d, &n));
        const uint8_t zero[13] = {0x00, 0x03, 0, 0, 0};
        CHECK(!parse_udp_can(zero, 13, &id, d, &n));
        CHECK(!parse_udp_can(ok, 12, &id, d, &n));
    }

    Shell sh;
    std::string s = page_state_json(sh, vhal::Bridge(), 0);
    HAS(s, "\"view\":\"gauge\"");          // no phone, "No phone shows: Gauge"
    HAS(s, "\"screen\":\"home\"");
    HAS(s, "[\"Gauge theme\",\"Modern\"]");
    HAS(s, "\"phone\":null");
    HAS(s, "\"imperial\":true");
    HAS(s, "\"veh\":{\"link\":false,\"speed_mps\":null");   // nothing heard: no number, the page says NO DATA
    sh.set_phone(Phone::CarPlay);
    CHECK(sh.view() == View::Maps);
    sh.press(0);
    sh.tick(600);
    sh.tick(1500);                         // the 1.5 s hold: our speedometer while the phone stays connected
    sh.release(1600);
    s = page_state_json(sh, vhal::Bridge(), 0);
    HAS(s, "\"view\":\"gauge\"");
    HAS(s, "\"screen\":\"home\"");
    HAS(s, "\"phone\":\"cp\"");
    HAS(s, "\"theme\":2");

    // the speedometer's values come from the private link, through the same decoder as the telemetry
    vhal::Bridge b;
    feed(b, 5000, 0, 90.0f, false, false, true);
    Shell g;
    s = page_state_json(g, b, 5000);
    HAS(s, "\"link\":true");
    HAS(s, "\"speed_mps\":25.000");           // 90 km/h
    HAS(s, "\"lights\":true");
    HAS(s, "\"dimmer\":40");
    HAS(s, "\"hi\":true");
    HAS(s, "\"brake\":false");
    CHECK(g.centre_shows_speed());
}

int main() {
    test_dial();
    test_shell();
    test_link_tx();
    test_power();
    test_park();
    test_telemetry();
    test_state_io();
    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
