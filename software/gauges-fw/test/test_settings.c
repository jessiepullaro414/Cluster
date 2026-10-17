/* The settings store: record format, debounce of changes, recovery after a power cut at every event of a save. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "nv_mock.h"
#include "settings_store.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static display_settings_t defaults(void)
{
    display_settings_t d = {
        .brightness_pct = 100, .night_mode = false, .units_mph = false, .gauge_theme = 1, .center_shows_speed = false,
        .car_profile = 0, .car_bitrate = 0, .tank_capacity_l = 0.0f, .lamp_invert_mask = 0,
        .tach_enabled = false, .tach_pulses_per_rev = 4, .pulses_per_mile = 16000u, .display_heartbeat_seen = false,
    };
    return d;
}

static bool equal(const display_settings_t *a, const display_settings_t *b)
{
    return a->brightness_pct == b->brightness_pct && a->night_mode == b->night_mode && a->units_mph == b->units_mph &&
           a->gauge_theme == b->gauge_theme && a->car_profile == b->car_profile && a->car_bitrate == b->car_bitrate &&
           fabsf(a->tank_capacity_l - b->tank_capacity_l) < 0.01f && a->lamp_invert_mask == b->lamp_invert_mask &&
           a->tach_enabled == b->tach_enabled && a->tach_pulses_per_rev == b->tach_pulses_per_rev &&
           a->pulses_per_mile == b->pulses_per_mile;
}

static uint32_t t_ms;

static void run(settings_store_t *s, uint32_t ms)
{
    for (uint32_t i = 0; i < ms; i += 10) { t_ms += 10; nv_mock_tick(); settings_store_service(s, t_ms); }
}

static void test_format(void)
{
    display_settings_t d = defaults(), back = defaults();
    d.brightness_pct = 37; d.night_mode = true; d.units_mph = true; d.gauge_theme = 3; d.car_profile = 1; d.car_bitrate = 2;
    d.tank_capacity_l = 57.3f; d.lamp_invert_mask = 0x2A; d.tach_enabled = true; d.tach_pulses_per_rev = 6; d.pulses_per_mile = 8000u;
    d.center_shows_speed = true; d.display_heartbeat_seen = true;
    uint8_t rec[16];
    settings_pack(&d, rec);
    CHECK(settings_unpack(rec, &back));
    CHECK(equal(&d, &back));
    CHECK(!back.center_shows_speed && !back.display_heartbeat_seen);       /* not kept */
    uint8_t bad[16]; memcpy(bad, rec, 16);
    bad[0] = 9; CHECK(!settings_unpack(bad, &back));                       /* another version */
    memcpy(bad, rec, 16); bad[1] = 101; CHECK(!settings_unpack(bad, &back));
    memcpy(bad, rec, 16); bad[7] = 0; CHECK(!settings_unpack(bad, &back));
    memcpy(bad, rec, 16); bad[7] = 17; CHECK(!settings_unpack(bad, &back));
}

static void test_save_and_load(void)
{
    nv_mock_reset(21);
    settings_store_t s; display_settings_t cur = defaults();
    settings_store_init(&s, &nv_mock, 0, &cur);
    CHECK(equal(&cur, &(display_settings_t){ .brightness_pct = 100, .gauge_theme = 1, .tach_pulses_per_rev = 4, .pulses_per_mile = 16000u }));
    t_ms = 100000;
    settings_store_offer(&s, &cur, t_ms);
    run(&s, 10000);
    CHECK(nv_mock_programs == 0);                                          /* defaults nobody changed: nothing written */
    cur.units_mph = true;
    settings_store_offer(&s, &cur, t_ms);
    run(&s, 2000);
    CHECK(nv_mock_programs == 0);                                          /* not stable long enough yet */
    run(&s, 2000);
    CHECK(nv_mock_programs == 3u);                                         /* two payload phrases and the sequence/CRC phrase */
    CHECK(settings_store_idle(&s));
    display_settings_t loaded = defaults();
    settings_store_t s2;
    settings_store_init(&s2, &nv_mock, 0, &loaded);
    CHECK(loaded.units_mph && equal(&loaded, &cur));
    /* dragging a slider: 100 changes 50 ms apart are one write */
    unsigned before = nv_mock_programs;
    for (int i = 0; i < 100; i++) {
        cur.brightness_pct = (uint8_t)(100 - i);
        settings_store_offer(&s, &cur, t_ms);
        run(&s, 50);
    }
    CHECK(nv_mock_programs == before);
    run(&s, 4000);
    CHECK(nv_mock_programs == before + 3u);
    settings_store_init(&s2, &nv_mock, 0, &loaded);
    CHECK(loaded.brightness_pct == 1u);
    /* offering the same value again changes nothing */
    settings_store_offer(&s, &cur, t_ms);
    run(&s, 5000);
    CHECK(nv_mock_programs == before + 3u);
    CHECK(nv_mock_violations == 0);
}

/* a power cut at every event of one save: afterwards the old or the new settings are found, never anything else */
static void test_every_cut(void)
{
    long events = 0;
    for (long cut = 0; cut <= events + 1; cut++) {
        nv_mock_reset(33);
        settings_store_t s; display_settings_t cur = defaults(), old;
        settings_store_init(&s, &nv_mock, 0, &cur);
        t_ms = 5000;
        cur.units_mph = true; cur.gauge_theme = 2; cur.pulses_per_mile = 12345u;
        old = cur;                                                          /* first change: gets saved */
        settings_store_offer(&s, &cur, t_ms);
        run(&s, 4000);
        cur.brightness_pct = 20; cur.tank_capacity_l = 60.0f;               /* second change: the one that is cut */
        settings_store_offer(&s, &cur, t_ms);
        if (cut) nv_mock_cut_at(cut);
        long ev0 = nv_mock_events;
        run(&s, 8000);
        if (cut == 0) { events = nv_mock_events - ev0; CHECK(events == 3 * 3); continue; }     /* three commands, three events each */
        nv_mock_power_cycle();
        display_settings_t got = defaults();
        settings_store_t s2;
        settings_store_init(&s2, &nv_mock, 0, &got);
        bool is_old = equal(&got, &old), is_new = equal(&got, &cur);
        CHECK(is_old || is_new);
        if (cut <= 1) CHECK(is_old);
    }
    printf("settings: power cut at each event of a save: the old or the new settings every time\n");
}

int main(void)
{
    test_format();
    test_save_and_load();
    test_every_cut();
    if (failures) { printf("test_settings: %d FAILED\n", failures); return 1; }
    printf("test_settings: ok\n");
    return 0;
}
