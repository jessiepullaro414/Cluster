// Host tests for clusterd's logic: dial angle, shell, CAN transmit schedule, power policy, telemetry
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
    // hold 0.6 s: Back for the phone, then nothing until 1.5 s, then our Settings
    t = 2000;
    sh.press(t);
    CHECK(sh.tick(t + 300).key == Key::None);
    a = sh.tick(t + 600);
    CHECK(a.key == Key::Back && a.path == nullptr);
    CHECK(sh.tick(t + 1000).path == nullptr);
    a = sh.tick(t + 1500);
    CHECK(a.path && std::string(a.path) == kPathSettings && a.key == Key::None);
    CHECK(sh.tick(t + 1600).path == nullptr);
    a = sh.release(t + 1700);
    CHECK(a.key == Key::None && a.path == nullptr);   // letting go after a long press does nothing
    CHECK(!sh.phone_owns_dial());

    // in Settings the dial is ours: turn moves rows, no keys to the phone
    a = sh.turn(+1);
    CHECK(a.key == Key::None && sh.ui().row() == hmi::Row::MatchCarPlay);
    // edit "With CarPlay": off, keep -> the small screens go back to the owner's theme
    sh.press(3000);
    sh.release(3050);
    sh.turn(+1);
    sh.press(3100);
    sh.release(3150);
    CHECK(sh.mutable_ui().take_committed());
    CHECK(!sh.ui().model().match_carplay && sh.gauge_theme() == 1);
    // hold in the list: back to Home, the maps, the phone has the dial again
    sh.press(4000);
    a = sh.tick(4600);
    CHECK(a.path && std::string(a.path) == kPathMaps);
    sh.release(4700);
    CHECK(sh.phone_owns_dial());

    // a short hold that ends before 1.5 s is only Back
    sh.press(5000);
    CHECK(sh.tick(5600).key == Key::Back);
    sh.release(5800);
    CHECK(sh.tick(7000).path == nullptr);

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
        CHECK(edc.detents_per_turn == 24 && edc.raw_max == 4095);
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

    Shell sh;
    std::string s = page_state_json(sh);
    HAS(s, "\"screen\":\"home\"");
    HAS(s, "[\"Gauge theme\",\"Modern\"]");
    HAS(s, "\"phone\":null");
    sh.set_phone(Phone::CarPlay);
    sh.press(0);
    sh.tick(600);
    sh.tick(1500);
    s = page_state_json(sh);
    HAS(s, "\"screen\":\"settings\"");
    HAS(s, "\"phone\":\"cp\"");
    HAS(s, "\"theme\":2");
}

int main() {
    test_dial();
    test_shell();
    test_link_tx();
    test_power();
    test_telemetry();
    test_state_io();
    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
