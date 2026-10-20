#include <string.h>
#include "can_hw.h"
#include "bootcore.h"
#include "can_link.h"
#include "cluster_can.h"
#include "cluster_codec.h"

/* The two CAN buses of gauges/ (protocol/can_protocol.py is the single source of truth for every layout):
 *   CAN0, the car bus: LISTEN-ONLY. Nothing here ever calls tx() on it; the driver is also configured so that the controller
 *   cannot drive the bus (it does not even acknowledge). One receive mailbox per Haltech V2 identifier.
 *   CAN1, the private link to display/: 500 kbit/s, rolling counter and CRC-8 on every message in both directions. */

#define LINK_BITRATE 500000u
#define MAX_RX_PER_POLL 16u

enum { M_MOTION, M_FLUIDS, M_INDICATORS, M_POWER, M_STATUS, M_ODOMETER, M_SENDERS, M_COUNT };
static const uint16_t TX_ID[M_COUNT] = { CAN_ID_VEHICLEMOTION, CAN_ID_VEHICLEFLUIDS, CAN_ID_INDICATORS, CAN_ID_POWERSTATE,
                                         CAN_ID_GAUGESSTATUS, CAN_ID_ODOMETER, CAN_ID_SENDEROHMS };
static const uint16_t TX_PERIOD_MS[M_COUNT] = { CAN_PERIOD_MS_VEHICLEMOTION, CAN_PERIOD_MS_VEHICLEFLUIDS, CAN_PERIOD_MS_INDICATORS,
                                                CAN_PERIOD_MS_POWERSTATE, CAN_PERIOD_MS_GAUGESSTATUS, CAN_PERIOD_MS_ODOMETER,
                                                CAN_PERIOD_MS_SENDEROHMS };
enum { R_SETTINGS, R_CALIB, R_INPUT, R_TRIP, R_HEARTBEAT, R_UPDATE, R_COUNT };
static const uint16_t RX_ID[R_COUNT] = { CAN_ID_DISPLAYSETTINGS, CAN_ID_SPEEDCALIBRATION, CAN_ID_INPUTCONFIG, CAN_ID_TRIPCOMMAND,
                                         CAN_ID_DISPLAYHEARTBEAT, BOOT_ID_CMD };

static const can_hw_t *g_hw;
static uint32_t g_now;

static display_settings_t g_settings = {
    .brightness_pct = 100, .night_mode = false, .units_mph = false, .gauge_theme = 1, .center_shows_speed = false,
    .car_profile = 0, .car_bitrate = 0, .tank_capacity_l = 0.0f, .lamp_invert_mask = 0,
    .tach_enabled = false, .tach_pulses_per_rev = 4, .pulses_per_mile = 16000u, .display_heartbeat_seen = false,
};

static car_bus_t g_car;
static uint32_t g_car_last_ms;
static bool g_car_any;
static uint8_t g_car_profile_applied = 0xFFu, g_car_bitrate_applied = 0xFFu;
static bool g_link_ok;

static uint8_t g_rx_last_counter[R_COUNT];
static bool g_rx_seen[R_COUNT];
static uint32_t g_hb_ms;
static bool g_hb_seen;
static uint8_t g_trip_last;
static bool g_trip_known, g_trip_pending;
static bool g_update_requested;

static uint8_t g_tx_counter[M_COUNT];
static uint32_t g_tx_ms[M_COUNT];
static bool g_tx_sent[M_COUNT];
static uint8_t g_ind_last[8];
static bool g_ind_known;
static uint8_t g_pow_last[8];
static bool g_pow_known;

/* ---- start-up and configuration ------------------------------------------------------------------------------- */

static uint32_t car_bitrate_of(uint8_t code)
{
    switch (code) {
    case 1: return 1000000u;
    case 2: return 250000u;
    default: return 500000u;
    }
}

static const uint16_t HALTECH_IDS[] = { CAN_ID_HALTECHENGINE, CAN_ID_HALTECHPRESSURES, CAN_ID_HALTECHSPEED, CAN_ID_HALTECHBATTERY,
                                        CAN_ID_HALTECHTEMPS, CAN_ID_HALTECHFUELLEVEL };

static void start_car_bus(void)
{
    can_config_t c;
    memset(&c, 0, sizeof c);
    c.bitrate = car_bitrate_of(g_settings.car_bitrate);
    c.listen_only = true;                        /* never transmit on the car bus */
    if (g_settings.car_profile == 1u) {
        c.n_rx = (uint8_t)(sizeof HALTECH_IDS / sizeof HALTECH_IDS[0]);
        for (unsigned i = 0; i < c.n_rx; i++) c.rx_ids[i] = HALTECH_IDS[i];
    }
    if (g_hw != NULL) (void)g_hw->start(CAN_BUS_CAR, &c);
    g_car_profile_applied = g_settings.car_profile;
    g_car_bitrate_applied = g_settings.car_bitrate;
}

void can_link_init(const can_hw_t *hw)
{
    g_hw = hw;
    memset(&g_car, 0, sizeof g_car);
    g_car_any = false; g_hb_seen = false; g_trip_known = false; g_trip_pending = false; g_update_requested = false; g_ind_known = false; g_pow_known = false;
    memset(g_rx_seen, 0, sizeof g_rx_seen);
    memset(g_tx_sent, 0, sizeof g_tx_sent);
    memset(g_tx_counter, 0, sizeof g_tx_counter);
    if (g_hw == NULL) return;

    can_config_t l;
    memset(&l, 0, sizeof l);
    l.bitrate = LINK_BITRATE;
    l.listen_only = false;
    l.n_rx = R_COUNT; l.n_tx = M_COUNT;
    for (unsigned i = 0; i < R_COUNT; i++) l.rx_ids[i] = RX_ID[i];
    for (unsigned i = 0; i < M_COUNT; i++) l.tx_ids[i] = TX_ID[i];
    g_link_ok = g_hw->start(CAN_BUS_LINK, &l);
    start_car_bus();
}

/* ---- car bus -------------------------------------------------------------------------------------------------- */

static void car_sample(sample_t *s, float v, float lo, float hi)
{
    if (v < lo || v > hi) return;                /* implausible: keep the old value to age out, never show it */
    s->value = v; s->valid = true; s->stamp_ms = g_now;
}

static void car_frame(const can_frame_t *f)
{
    if (f->dlc < 8u) return;
    switch (f->id) {
    case CAN_ID_HALTECHENGINE:
        car_sample(&g_car.rpm, cluster_haltech_engine_rpm(f->data), 0.0f, AGG_RPM_MAX);
        break;
    case CAN_ID_HALTECHPRESSURES: {
        float kpa = cluster_haltech_pressures_oil_pressure_kpa(f->data);
        car_sample(&g_car.oil_kpa, kpa < 0.0f && kpa > -5.0f ? 0.0f : kpa, 0.0f, 1500.0f);       /* a zero gauge reading can sit a hair under 0 */
        break;
    }
    case CAN_ID_HALTECHSPEED:
        car_sample(&g_car.speed_kph, cluster_haltech_speed_vehicle_speed_kph(f->data), 0.0f, AGG_SPEED_MAX_KPH);
        break;
    case CAN_ID_HALTECHBATTERY:
        car_sample(&g_car.battery_v, cluster_haltech_battery_battery_v(f->data), 0.0f, 20.0f);
        break;
    case CAN_ID_HALTECHTEMPS:
        car_sample(&g_car.coolant_c, cluster_haltech_temps_coolant_temp_k(f->data) - 273.15f, -40.0f, 200.0f);
        break;
    case CAN_ID_HALTECHFUELLEVEL:
        if (g_settings.tank_capacity_l > 0.0f)
            car_sample(&g_car.fuel_pct, cluster_haltech_fuel_level_fuel_level_l(f->data) / g_settings.tank_capacity_l * 100.0f, 0.0f, 100.0f);
        break;
    default:
        return;
    }
    g_car_any = true;
    g_car_last_ms = g_now;
}

/* ---- private link, received ----------------------------------------------------------------------------------- */

/* A message counts only if its CRC is right (the unpack functions check it) and its rolling counter moved: the same counter
 * twice in a row is a frame repeated by something that is not the display. */
static bool fresh_counter(unsigned r, uint8_t counter)
{
    bool ok = !g_rx_seen[r] || counter != g_rx_last_counter[r];
    g_rx_seen[r] = true;
    g_rx_last_counter[r] = counter;
    return ok;
}

static void link_frame(const can_frame_t *f)
{
    if (f->dlc != 8u) return;
    switch (f->id) {
    case CAN_ID_DISPLAYSETTINGS: {
        cluster_display_settings_t m;
        if (cluster_display_settings_unpack(f->data, &m) != 0 || !fresh_counter(R_SETTINGS, m.counter)) return;
        if (m.brightness_pct <= 100u) g_settings.brightness_pct = (uint8_t)m.brightness_pct;
        g_settings.night_mode = m.night_mode != 0u;
        g_settings.units_mph = m.units_mph != 0u;
        g_settings.gauge_theme = (uint8_t)m.gauge_theme;
        g_settings.center_shows_speed = m.center_shows_speed != 0u;
        g_settings.car_profile = (uint8_t)m.car_profile;
        g_settings.car_bitrate = (uint8_t)m.car_bitrate;
        g_settings.tank_capacity_l = m.tank_capacity_l;
        break;
    }
    case CAN_ID_SPEEDCALIBRATION: {
        cluster_speed_calibration_t m;
        if (cluster_speed_calibration_unpack(f->data, &m) != 0 || !fresh_counter(R_CALIB, m.counter)) return;
        if (m.pulses_per_mile >= 100u && m.pulses_per_mile <= 200000u) g_settings.pulses_per_mile = m.pulses_per_mile;
        break;
    }
    case CAN_ID_INPUTCONFIG: {
        cluster_input_config_t m;
        if (cluster_input_config_unpack(f->data, &m) != 0 || !fresh_counter(R_INPUT, m.counter)) return;
        g_settings.lamp_invert_mask = (uint8_t)(m.lamp_invert_mask & 0x3Fu);
        g_settings.tach_enabled = m.tach_enabled != 0u;
        if (m.tach_pulses_per_rev >= 1u && m.tach_pulses_per_rev <= 16u) g_settings.tach_pulses_per_rev = (uint8_t)m.tach_pulses_per_rev;
        break;
    }
    case CAN_ID_TRIPCOMMAND: {
        cluster_trip_command_t m;
        if (cluster_trip_command_unpack(f->data, &m) != 0 || !fresh_counter(R_TRIP, m.counter)) return;
        uint8_t c = (uint8_t)(m.trip_reset_count & 0xFu);
        if (g_trip_known && c != g_trip_last) g_trip_pending = true;      /* the first frame after power-up only records the count */
        g_trip_last = c; g_trip_known = true;
        break;
    }
    case BOOT_ID_CMD:                                 /* a firmware tool (bootcore.h): ENTER 'B' 'L' board-id means reboot into the bootloader */
        if (f->data[0] == 0x01u && f->data[1] == 'B' && f->data[2] == 'L' &&
            (uint16_t)(f->data[3] | (f->data[4] << 8)) == BOARD_ID_GAUGES)
            g_update_requested = true;
        break;
    case CAN_ID_DISPLAYHEARTBEAT: {
        cluster_display_heartbeat_t m;
        if (cluster_display_heartbeat_unpack(f->data, &m) != 0 || !fresh_counter(R_HEARTBEAT, m.counter)) return;
        g_hb_ms = g_now; g_hb_seen = true;
        break;
    }
    default:
        break;
    }
}

void can_link_poll(uint32_t now_ms)
{
    g_now = now_ms;
    if (g_hw == NULL) return;
    can_frame_t f;
    for (unsigned n = 0; n < MAX_RX_PER_POLL && g_hw->rx(CAN_BUS_LINK, &f); n++) link_frame(&f);
    for (unsigned n = 0; n < MAX_RX_PER_POLL && g_hw->rx(CAN_BUS_CAR, &f); n++) car_frame(&f);
    /* a changed profile or bit rate reconfigures the car-bus controller (the identifiers to accept depend on the profile) */
    if (g_settings.car_profile != g_car_profile_applied || g_settings.car_bitrate != g_car_bitrate_applied) {
        memset(&g_car, 0, sizeof g_car);
        g_car_any = false;
        start_car_bus();
    }
    g_settings.display_heartbeat_seen = g_hb_seen && (uint32_t)(now_ms - g_hb_ms) <= CLUSTER_DISPLAY_TIMEOUT_MS;
}

car_bus_t can_link_car(void)
{
    car_bus_t c = g_car;
    c.active = g_car_any && (uint32_t)(g_now - g_car_last_ms) <= CLUSTER_CAR_BUS_TIMEOUT_MS;
    return c;
}

display_settings_t can_link_settings(void) { return g_settings; }

void can_link_load_settings(const display_settings_t *s)
{
    g_settings = *s;
    g_settings.center_shows_speed = false;       /* describes the display right now, not a preference */
    g_settings.display_heartbeat_seen = false;
}

bool can_link_update_requested(void)
{
    bool r = g_update_requested;
    g_update_requested = false;
    return r;
}

bool can_link_trip_reset_requested(void)
{
    bool r = g_trip_pending;
    g_trip_pending = false;
    return r;
}

/* ---- private link, sent ---------------------------------------------------------------------------------------- */

static bool due(unsigned m)
{
    return !g_tx_sent[m] || (uint32_t)(g_now - g_tx_ms[m]) >= TX_PERIOD_MS[m];
}

/* Send one frame on the link. The counter only advances if the controller took it, so a busy mailbox is retried with the same
 * counter on the next call instead of leaving a gap the display would read as a lost message. */
static bool send(unsigned m, const uint8_t data[8])
{
    if (g_hw == NULL || !g_link_ok) return false;
    can_frame_t f;
    f.id = TX_ID[m]; f.dlc = 8u;
    memcpy(f.data, data, 8);
    if (!g_hw->tx(CAN_BUS_LINK, &f)) return false;
    g_tx_sent[m] = true; g_tx_ms[m] = g_now;
    g_tx_counter[m] = (uint8_t)((g_tx_counter[m] + 1u) & 0xFu);
    return true;
}

void can_link_send_motion(float kph, float rpm, float battery_v, bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall)
{
    if (!due(M_MOTION)) return;
    cluster_vehicle_motion_t m = { kph_ok ? kph : 0.0f, rpm_ok ? (uint32_t)(rpm + 0.5f) : 0u, batt_ok ? battery_v : 0.0f,
                                   kph_ok, rpm_ok, batt_ok, from_hall && kph_ok, 0 };
    uint8_t d[8];
    cluster_vehicle_motion_pack(&m, g_tx_counter[M_MOTION], d);
    (void)send(M_MOTION, d);
}

void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa, bool fuel_ok, bool coolant_ok, bool oil_ok)
{
    if (!due(M_FLUIDS)) return;
    cluster_vehicle_fluids_t m = { fuel_ok ? fuel_pct : 0.0f, coolant_ok ? coolant_c : 0.0f, oil_ok ? oil_kpa : 0.0f,
                                   fuel_ok, coolant_ok, oil_ok, 0 };
    uint8_t d[8];
    cluster_vehicle_fluids_pack(&m, g_tx_counter[M_FLUIDS], d);
    (void)send(M_FLUIDS, d);
}

void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil, bool lights_on, uint8_t dimmer_pct)
{
    /* sent at once when a lamp changes (the turn signals flash) and otherwise on its period; the dimmer value alone is not urgent */
    cluster_indicators_t m = { l, r, hb, brake, alt, oil, lights_on, dimmer_pct, 0 };
    uint8_t d[8], key[8];
    cluster_indicators_pack(&m, 0, key);
    key[7] = 0;                                  /* the CRC depends on the counter; compare the content only */
    bool changed = !g_ind_known || memcmp(key, g_ind_last, 7) != 0;
    if (!changed && !due(M_INDICATORS)) return;
    cluster_indicators_pack(&m, g_tx_counter[M_INDICATORS], d);
    if (send(M_INDICATORS, d)) { memcpy(g_ind_last, key, 8); g_ind_known = true; }
}

void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s)
{
    cluster_power_state_t m = { ignition_on, suspend_request, suspend_in_s, 0 };
    uint8_t d[8], key[8];
    cluster_power_state_pack(&m, 0, key);
    key[7] = 0;
    bool changed = !g_pow_known || memcmp(key, g_pow_last, 7) != 0;
    if (!changed && !due(M_POWER)) return;
    cluster_power_state_pack(&m, g_tx_counter[M_POWER], d);
    if (send(M_POWER, d)) { memcpy(g_pow_last, key, 8); g_pow_known = true; }
}

void can_link_send_status(const cluster_gauges_status_t *s)
{
    uint8_t d[8];
    cluster_gauges_status_pack(s, d);            /* GaugesStatus carries no counter or CRC (protocol rev 2) */
    (void)send(M_STATUS, d);
}

void can_link_send_odometer(uint32_t odometer_m, uint32_t trip_m)
{
    if (!due(M_ODOMETER)) return;
    cluster_odometer_t m = { odometer_m, trip_m > 1048575u ? trip_m % 1048576u : trip_m, 0 };
    uint8_t d[8];
    cluster_odometer_pack(&m, g_tx_counter[M_ODOMETER], d);
    (void)send(M_ODOMETER, d);
}

/* SenderOhms, once a second: the live sender resistances, for measuring the curves in the car (docs/sender-calibration.md).
 * A negative value (no reading yet, open or shorted) goes out as 0 with its valid bit clear. */
void can_link_send_sender_ohms(float fuel_ohm, float oil_ohm, float coolant_ohm)
{
    if (!due(M_SENDERS)) return;
    cluster_sender_ohms_t m = { fuel_ohm > 0.0f ? fuel_ohm : 0.0f, oil_ohm > 0.0f ? oil_ohm : 0.0f,
                                coolant_ohm > 0.0f ? coolant_ohm : 0.0f,
                                fuel_ohm >= 0.0f, oil_ohm >= 0.0f, coolant_ohm >= 0.0f, 0 };
    uint8_t d[8];
    cluster_sender_ohms_pack(&m, g_tx_counter[M_SENDERS], d);
    (void)send(M_SENDERS, d);
}
