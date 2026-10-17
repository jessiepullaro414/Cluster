/* The CAN link logic against a fake controller: the Haltech decode, the private-link messages in both directions (CRC, rolling
 * counter, freshness), the display heartbeat, the trip reset, reconfiguration, and the rule that nothing is ever sent on the car bus. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "can_hw.h"
#include "can_link.h"
#include "cluster_can.h"
#include "cluster_codec.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)
#define NEAR(a, b, tol) do { double _a = (a), _b = (b); if (fabs(_a - _b) > (tol)) { printf("FAIL %s:%d  %s = %g, want %g +- %g\n", __FILE__, __LINE__, #a, _a, _b, (double)(tol)); failures++; } } while (0)

/* ---- the fake controllers ------------------------------------------------------------------------------------ */
#define QN 128
static can_frame_t rxq[2][QN];
static int rx_head[2], rx_tail[2];
static can_frame_t txlog[2][QN];
static int ntx[2];
static can_config_t cfg[2];
static int starts[2];
static bool start_result[2] = { true, true };
static bool tx_busy;
static int car_tx_attempts;

static bool f_start(can_bus_t b, const can_config_t *c) { cfg[b] = *c; starts[b]++; return start_result[b]; }
static bool f_rx(can_bus_t b, can_frame_t *f)
{
    if (rx_head[b] == rx_tail[b]) return false;
    *f = rxq[b][rx_head[b]++ % QN];
    return true;
}
static bool f_tx(can_bus_t b, const can_frame_t *f)
{
    if (b == CAN_BUS_CAR) { car_tx_attempts++; return false; }
    if (tx_busy) return false;
    txlog[b][ntx[b]++ % QN] = *f;
    return true;
}
static bool f_off(can_bus_t b) { (void)b; return false; }
static const can_hw_t HW = { f_start, f_rx, f_tx, f_off };

static void inject(can_bus_t b, can_frame_t f) { rxq[b][rx_tail[b]++ % QN] = f; }

static void reset_world(void)
{
    memset(rx_head, 0, sizeof rx_head); memset(rx_tail, 0, sizeof rx_tail);
    memset(ntx, 0, sizeof ntx); memset(starts, 0, sizeof starts);
    memset(cfg, 0, sizeof cfg);
    start_result[0] = start_result[1] = true; tx_busy = false; car_tx_attempts = 0;
    display_settings_t d = { .brightness_pct = 100, .gauge_theme = 1, .tach_pulses_per_rev = 4, .pulses_per_mile = 16000u };
    can_link_load_settings(&d);
    can_link_init(&HW);
}

static void be16(uint8_t *d, unsigned off, unsigned v) { d[off] = (uint8_t)(v >> 8); d[off + 1] = (uint8_t)v; }

static uint32_t now;
static void tick(uint32_t ms) { for (uint32_t i = 0; i < ms; i += 10) { now += 10; can_link_poll(now); } }

static uint8_t ctr_settings;
static void send_settings(unsigned profile, unsigned bitrate, float tank, bool units_mph, unsigned theme, bool center)
{
    cluster_display_settings_t m = { 80, 0, units_mph, theme, center, profile, bitrate, tank, 0 };
    can_frame_t f = { CAN_ID_DISPLAYSETTINGS, 8, { 0 } };
    cluster_display_settings_pack(&m, ctr_settings++ & 15u, f.data);
    inject(CAN_BUS_LINK, f);
}

/* ---- tests --------------------------------------------------------------------------------------------------- */
static void test_start(void)
{
    reset_world();
    CHECK(starts[CAN_BUS_LINK] == 1 && starts[CAN_BUS_CAR] == 1);
    CHECK(cfg[CAN_BUS_LINK].bitrate == 500000u && !cfg[CAN_BUS_LINK].listen_only);
    CHECK(cfg[CAN_BUS_LINK].n_rx == 6u && cfg[CAN_BUS_LINK].n_tx == 6u);
    CHECK(cfg[CAN_BUS_LINK].rx_ids[0] == 0x400u && cfg[CAN_BUS_LINK].rx_ids[4] == 0x4F0u && cfg[CAN_BUS_LINK].rx_ids[5] == 0x7C0u);
    CHECK(cfg[CAN_BUS_LINK].tx_ids[0] == 0x300u && cfg[CAN_BUS_LINK].tx_ids[5] == 0x304u);
    CHECK(cfg[CAN_BUS_CAR].listen_only);                                      /* the car bus listens only */
    CHECK(cfg[CAN_BUS_CAR].n_tx == 0u && cfg[CAN_BUS_CAR].n_rx == 0u);        /* profile 0: nothing to accept */
    can_link_init(0);                                                         /* no controllers at all is safe */
    can_link_poll(10);
    can_link_send_motion(50, 1000, 13, true, true, true, true);
    CHECK(!can_link_car().active && !can_link_settings().display_heartbeat_seen);
    reset_world();
}

static void test_haltech(void)
{
    reset_world(); now = 100000;
    send_settings(1, 1, 60.0f, true, 3, false);                               /* Haltech profile, 1 Mbit, 60 L tank */
    tick(20);
    CHECK(starts[CAN_BUS_CAR] == 2);
    CHECK(cfg[CAN_BUS_CAR].bitrate == 1000000u && cfg[CAN_BUS_CAR].listen_only && cfg[CAN_BUS_CAR].n_rx == 6u);
    CHECK(cfg[CAN_BUS_CAR].rx_ids[0] == 0x360u && cfg[CAN_BUS_CAR].rx_ids[5] == 0x3E2u);
    display_settings_t s = can_link_settings();
    CHECK(s.units_mph && s.gauge_theme == 3u && s.car_profile == 1u && s.car_bitrate == 1u);
    NEAR(s.tank_capacity_l, 60.0, 0.05);

    can_frame_t f = { 0, 8, { 0 } };
    f.id = 0x360; be16(f.data, 0, 3000); inject(CAN_BUS_CAR, f);              /* rpm */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x361; be16(f.data, 2, 4013); inject(CAN_BUS_CAR, f);     /* oil: (4013 * 0.1) - 101.3 = 300 kPa */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x370; be16(f.data, 0, 1000); inject(CAN_BUS_CAR, f);     /* speed 100.0 km/h */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x372; be16(f.data, 0, 138); inject(CAN_BUS_CAR, f);      /* 13.8 V */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x3E0; be16(f.data, 0, 3632); inject(CAN_BUS_CAR, f);     /* 363.2 K = 90.05 C */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x3E2; be16(f.data, 0, 300); inject(CAN_BUS_CAR, f);      /* 30 L of 60 L */
    tick(10);
    car_bus_t c = can_link_car();
    CHECK(c.active);
    CHECK(c.rpm.valid && c.speed_kph.valid && c.battery_v.valid && c.coolant_c.valid && c.oil_kpa.valid && c.fuel_pct.valid);
    NEAR(c.rpm.value, 3000, 0.5);
    NEAR(c.oil_kpa.value, 300.0, 0.2);
    NEAR(c.speed_kph.value, 100.0, 0.05);
    NEAR(c.battery_v.value, 13.8, 0.01);
    NEAR(c.coolant_c.value, 90.05, 0.1);
    NEAR(c.fuel_pct.value, 50.0, 0.1);
    CHECK(agg_fresh(c.speed_kph, now, 500) && c.speed_kph.stamp_ms == now);

    /* implausible values never get through; short frames are ignored */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x370; be16(f.data, 0, 5000); inject(CAN_BUS_CAR, f);    /* 500 km/h */
    memset(&f, 0, sizeof f); f.dlc = 4; f.id = 0x372; be16(f.data, 0, 99); inject(CAN_BUS_CAR, f);      /* DLC 4 */
    tick(10);
    c = can_link_car();
    NEAR(c.speed_kph.value, 100.0, 0.05);
    NEAR(c.battery_v.value, 13.8, 0.01);
    /* an unknown identifier on the car bus is dropped (it should never get past the mailboxes, but the logic does not trust that) */
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x123; inject(CAN_BUS_CAR, f);
    tick(10);
    /* no frames for over 500 ms: the bus is reported inactive and the samples age out */
    tick(600);
    c = can_link_car();
    CHECK(!c.active);
    CHECK(!agg_fresh(c.speed_kph, now, 500));
    /* a tank of unknown size makes no fuel percentage */
    send_settings(1, 1, 0.0f, true, 3, false);
    memset(&f, 0, sizeof f); f.dlc = 8; f.id = 0x3E2; be16(f.data, 0, 300); inject(CAN_BUS_CAR, f);
    tick(10);
    CHECK(!agg_fresh(can_link_car().fuel_pct, now, 500) || can_link_car().fuel_pct.stamp_ms != now);
    CHECK(car_tx_attempts == 0);
}

static void test_reconfigure(void)
{
    reset_world(); now = 200000;
    send_settings(0, 0, 0, false, 1, false); tick(20);
    CHECK(starts[CAN_BUS_CAR] == 1);                                          /* the same profile and rate: no restart */
    send_settings(0, 0, 0, true, 1, false); tick(20);
    CHECK(starts[CAN_BUS_CAR] == 1);
    send_settings(0, 2, 0, false, 1, false); tick(20);
    CHECK(starts[CAN_BUS_CAR] == 2 && cfg[CAN_BUS_CAR].bitrate == 250000u);
    send_settings(0, 0, 0, false, 1, false); tick(20);
    CHECK(starts[CAN_BUS_CAR] == 3 && cfg[CAN_BUS_CAR].bitrate == 500000u);
    CHECK(starts[CAN_BUS_LINK] == 1);                                         /* the private link is never disturbed */
    send_settings(0, 3, 0, false, 1, false); tick(20);
    CHECK(cfg[CAN_BUS_CAR].bitrate == 500000u);                               /* an unknown rate code falls back to 500k */
    CHECK(car_tx_attempts == 0);
}

static void test_link_rx(void)
{
    reset_world(); now = 300000; ctr_settings = 0;
    can_frame_t f = { CAN_ID_SPEEDCALIBRATION, 8, { 0 } };
    cluster_speed_calibration_t cal = { 8000u, 0 };
    cluster_speed_calibration_pack(&cal, 1, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 8000u);
    /* the same counter again with different content is a replay: ignored */
    cal.pulses_per_mile = 9000u; cluster_speed_calibration_pack(&cal, 1, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 8000u);
    cluster_speed_calibration_pack(&cal, 2, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 9000u);
    /* a bad CRC is ignored */
    cal.pulses_per_mile = 12345u; cluster_speed_calibration_pack(&cal, 3, f.data); f.data[7] ^= 0x55u; inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 9000u);
    /* a value outside the allowed range is ignored */
    cal.pulses_per_mile = 50u; cluster_speed_calibration_pack(&cal, 4, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 9000u);
    /* the wrong length is ignored */
    cal.pulses_per_mile = 7000u; cluster_speed_calibration_pack(&cal, 5, f.data); f.dlc = 7; inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().pulses_per_mile == 9000u);

    cluster_input_config_t ic = { 0x2Au | 0xC0u, 1, 6, 0 };
    can_frame_t g = { CAN_ID_INPUTCONFIG, 8, { 0 } };
    cluster_input_config_pack(&ic, 1, g.data); inject(CAN_BUS_LINK, g); tick(10);
    display_settings_t s = can_link_settings();
    CHECK(s.lamp_invert_mask == 0x2Au && s.tach_enabled && s.tach_pulses_per_rev == 6u);     /* only six lamp bits */
    ic.tach_pulses_per_rev = 0; ic.tach_enabled = 0; cluster_input_config_pack(&ic, 2, g.data); inject(CAN_BUS_LINK, g); tick(10);
    s = can_link_settings();
    CHECK(!s.tach_enabled && s.tach_pulses_per_rev == 6u);                    /* zero pulses per revolution is not accepted */
    send_settings(1, 0, 40.0f, true, 2, true); tick(10);
    s = can_link_settings();
    CHECK(s.center_shows_speed && s.gauge_theme == 2u && s.units_mph && s.brightness_pct == 80u);
    CHECK(car_tx_attempts == 0);
}

static void test_heartbeat_and_trip(void)
{
    reset_world(); now = 400000;
    CHECK(!can_link_settings().display_heartbeat_seen);
    can_frame_t f = { CAN_ID_DISPLAYHEARTBEAT, 8, { 0 } };
    cluster_display_heartbeat_t hb = { 1, 0 };
    cluster_display_heartbeat_pack(&hb, 1, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().display_heartbeat_seen);
    tick(1400);
    CHECK(can_link_settings().display_heartbeat_seen);                        /* 1.4 s since: still alive */
    tick(200);
    CHECK(!can_link_settings().display_heartbeat_seen);                       /* past 1.5 s: Android is gone */
    cluster_display_heartbeat_pack(&hb, 2, f.data); inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_settings().display_heartbeat_seen);                        /* and it comes back */
    cluster_display_heartbeat_pack(&hb, 2, f.data); inject(CAN_BUS_LINK, f);  /* a stuck frame repeating its counter does not keep it alive */
    tick(1600);
    CHECK(!can_link_settings().display_heartbeat_seen);

    /* trip reset: once per change of TripResetCount; the first frame after power-up only records it */
    can_frame_t t = { CAN_ID_TRIPCOMMAND, 8, { 0 } };
    cluster_trip_command_t tc = { 5, 0 };
    cluster_trip_command_pack(&tc, 1, t.data); inject(CAN_BUS_LINK, t); tick(10);
    CHECK(!can_link_trip_reset_requested());
    tc.trip_reset_count = 5; cluster_trip_command_pack(&tc, 2, t.data); inject(CAN_BUS_LINK, t); tick(10);
    CHECK(!can_link_trip_reset_requested());                                  /* same count: nothing */
    tc.trip_reset_count = 6; cluster_trip_command_pack(&tc, 3, t.data); inject(CAN_BUS_LINK, t); tick(10);
    CHECK(can_link_trip_reset_requested());
    CHECK(!can_link_trip_reset_requested());                                  /* consumed */
    cluster_trip_command_pack(&tc, 4, t.data); inject(CAN_BUS_LINK, t); tick(10);
    CHECK(!can_link_trip_reset_requested());                                  /* repeated count, new counter: still once */
    tc.trip_reset_count = 0; cluster_trip_command_pack(&tc, 5, t.data); inject(CAN_BUS_LINK, t); tick(10);
    CHECK(can_link_trip_reset_requested());                                   /* the count wraps */
}

static void test_update_request(void)
{
    reset_world(); now = 700000;
    CHECK(!can_link_update_requested());
    can_frame_t f = { 0x7C0, 8, { 0x01, 'B', 'L', 0x01, 0x00, 0, 0, 0 } };
    inject(CAN_BUS_LINK, f); tick(10);
    CHECK(can_link_update_requested());
    CHECK(!can_link_update_requested());                                      /* once */
    f.data[3] = 0x02; inject(CAN_BUS_LINK, f); tick(10);                      /* another board */
    CHECK(!can_link_update_requested());
    f.data[3] = 0x01; f.data[1] = 'X'; inject(CAN_BUS_LINK, f); tick(10);     /* wrong magic */
    CHECK(!can_link_update_requested());
    f.data[1] = 'B'; f.data[0] = 0x02; inject(CAN_BUS_LINK, f); tick(10);     /* a different command: the bootloader's, not ours */
    CHECK(!can_link_update_requested());
    f.data[0] = 0x01; f.dlc = 4; inject(CAN_BUS_LINK, f); tick(10);
    CHECK(!can_link_update_requested());
    CHECK(car_tx_attempts == 0);
}

static unsigned count_id(unsigned id)
{
    unsigned n = 0;
    for (int i = 0; i < ntx[CAN_BUS_LINK]; i++) if (txlog[CAN_BUS_LINK][i % QN].id == id) n++;
    return n;
}

static can_frame_t last_of(unsigned id)
{
    can_frame_t r = { 0, 0, { 0 } };
    for (int i = 0; i < ntx[CAN_BUS_LINK]; i++) if (txlog[CAN_BUS_LINK][i % QN].id == id) r = txlog[CAN_BUS_LINK][i % QN];
    return r;
}

static void test_transmit(void)
{
    reset_world(); now = 500000;
    for (int i = 0; i < 100; i++) {                                           /* one second at the 10 ms loop rate */
        tick(10);
        can_link_send_motion(88.5f, 3000.4f, 13.82f, true, true, true, true);
        can_link_send_fluids(55.5f, 91.0f, 310.0f, true, true, false);
        can_link_send_indicators(false, false, false, false, false, false, true, 70);
        can_link_send_power(true, false, 0);
    }
    CHECK(count_id(CAN_ID_VEHICLEMOTION) >= 19u && count_id(CAN_ID_VEHICLEMOTION) <= 21u);         /* every 50 ms */
    CHECK(count_id(CAN_ID_VEHICLEFLUIDS) >= 9u && count_id(CAN_ID_VEHICLEFLUIDS) <= 11u);          /* every 100 ms */
    CHECK(count_id(CAN_ID_INDICATORS) >= 9u && count_id(CAN_ID_INDICATORS) <= 11u);                /* unchanged: its period */
    CHECK(count_id(CAN_ID_POWERSTATE) >= 2u && count_id(CAN_ID_POWERSTATE) <= 3u);                 /* every 500 ms */

    can_frame_t f = last_of(CAN_ID_VEHICLEMOTION);
    cluster_vehicle_motion_t m = {0};
    CHECK(f.dlc == 8u && cluster_vehicle_motion_unpack(f.data, &m) == 0);     /* the CRC is right */
    NEAR(m.speed_kph, 88.5, 0.06); CHECK(m.rpm == 3000u); NEAR(m.battery_v, 13.82, 0.006);
    CHECK(m.speed_valid && m.rpm_valid && m.battery_valid && m.speed_from_hall);
    /* the rolling counter counts up by one for each frame of a message and wraps at 16 */
    unsigned prev = 99; bool ok = true;
    for (int i = 0; i < ntx[CAN_BUS_LINK]; i++) {
        can_frame_t g = txlog[CAN_BUS_LINK][i % QN];
        if (g.id != CAN_ID_VEHICLEMOTION) continue;
        cluster_vehicle_motion_t mm = {0};
        if (cluster_vehicle_motion_unpack(g.data, &mm) != 0) ok = false;
        if (prev != 99u && mm.counter != ((prev + 1u) & 15u)) ok = false;
        prev = mm.counter;
    }
    CHECK(ok);
    cluster_vehicle_fluids_t fl = {0};
    f = last_of(CAN_ID_VEHICLEFLUIDS);
    CHECK(cluster_vehicle_fluids_unpack(f.data, &fl) == 0 && fl.fuel_valid && fl.coolant_valid && !fl.oil_valid);
    NEAR(fl.fuel_pct, 55.5, 0.02); NEAR(fl.coolant_c, 91.0, 0.06);
    CHECK(fl.oil_kpa == 0.0f);                                                 /* a value that is not valid is sent as zero */

    /* a lamp change goes out at once, not at the next period */
    unsigned before = count_id(CAN_ID_INDICATORS);
    tick(10);
    can_link_send_indicators(true, false, false, false, false, false, true, 70);
    CHECK(count_id(CAN_ID_INDICATORS) == before + 1u);
    cluster_indicators_t ind = {0};
    f = last_of(CAN_ID_INDICATORS);
    CHECK(cluster_indicators_unpack(f.data, &ind) == 0 && ind.turn_left && !ind.turn_right && ind.dash_lights_on && ind.dash_dimmer_pct == 70u);
    tick(10);
    can_link_send_indicators(false, false, false, false, false, false, true, 70);
    CHECK(count_id(CAN_ID_INDICATORS) == before + 2u);
    before = count_id(CAN_ID_POWERSTATE);
    tick(10);
    can_link_send_power(false, true, 30);                                      /* ignition off: at once */
    CHECK(count_id(CAN_ID_POWERSTATE) == before + 1u);
    cluster_power_state_t pw = {0};
    f = last_of(CAN_ID_POWERSTATE);
    CHECK(cluster_power_state_unpack(f.data, &pw) == 0 && !pw.ignition_on && pw.suspend_request && pw.suspend_in_seconds == 30u);

    /* status and odometer */
    cluster_gauges_status_t st = { .fw_major = 0, .fw_minor = 1, .reset_cause = 2, .limp_level = 1, .quarantine_mask = 16, .watchdog_resets = 7, .nv_storage_ok = 1 };
    can_link_send_status(&st);
    f = last_of(CAN_ID_GAUGESSTATUS);
    cluster_gauges_status_t sb = {0};
    CHECK(cluster_gauges_status_unpack(f.data, &sb) == 0 && sb.reset_cause == 2u && sb.quarantine_mask == 16u && sb.watchdog_resets == 7u);
    can_link_send_odometer(123456789u, 54321u);
    f = last_of(CAN_ID_ODOMETER);
    cluster_odometer_t od = {0};
    CHECK(cluster_odometer_unpack(f.data, &od) == 0 && od.odometer_m == 123456789u && od.trip_m == 54321u);
    CHECK(car_tx_attempts == 0);                                               /* NOTHING was offered to the car bus */
}

static void test_busy_mailbox(void)
{
    reset_world(); now = 600000;
    tick(10);
    tx_busy = true;
    for (int i = 0; i < 10; i++) { tick(10); can_link_send_motion(10, 1000, 12, true, true, true, false); }
    CHECK(count_id(CAN_ID_VEHICLEMOTION) == 0u);
    tx_busy = false;
    tick(10);
    can_link_send_motion(10, 1000, 12, true, true, true, false);
    CHECK(count_id(CAN_ID_VEHICLEMOTION) == 1u);
    cluster_vehicle_motion_t m = {0};
    can_frame_t f = last_of(CAN_ID_VEHICLEMOTION);
    CHECK(cluster_vehicle_motion_unpack(f.data, &m) == 0 && m.counter == 0u);  /* the counter did not advance while frames were refused */
    /* a link that failed to start sends nothing */
    reset_world();
    start_result[CAN_BUS_LINK] = false;
    can_link_init(&HW);
    tick(10);
    can_link_send_motion(10, 1000, 12, true, true, true, false);
    CHECK(count_id(CAN_ID_VEHICLEMOTION) == 0u);
    CHECK(car_tx_attempts == 0);
}

int main(void)
{
    test_start();
    test_haltech();
    test_reconfigure();
    test_link_rx();
    test_heartbeat_and_trip();
    test_update_request();
    test_transmit();
    test_busy_mailbox();
    if (failures) { printf("test_can_link: %d FAILED\n", failures); return 1; }
    printf("test_can_link: ok\n");
    return 0;
}
