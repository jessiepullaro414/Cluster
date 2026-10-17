#include <stdint.h>
#include "aggregate.h"
#include "aux_display.h"
#include "can_link.h"
#include "fault.h"
#include "inputs.h"
#include "panel_hal.h"
#include "screens.h"
#include "power.h"
#include "senders.h"
#include "status.h"
#include "tick.h"
#include "cluster_can.h"
#ifndef HOST_BUILD
#include "wdog.h"
#endif

/* STUB main: the init order and the 10 ms task are the point; senders, inputs, power and can_link are still
 * stubs. The fault handling around them is real (fault.c): each piece of work below runs as a TASK that the
 * watchdog policy can see, and a task that hangs twice is switched off while the rest keeps going. */

static fault_t g_fault;
#ifndef HOST_BUILD
static fault_retained_t g_retained __attribute__((section(".noinit")));   /* link/s32k144.ld keeps it across a watchdog reset */
#else
static fault_retained_t g_retained;
#endif

/* Run `body` as a fault-managed task; a quarantined task is skipped (its results fall back to "no data"). */
#define RUN_TASK(t, ...) do { if (fault_task_enabled(&g_fault, (t))) { \
        fault_task_begin(&g_fault, (t)); __VA_ARGS__; fault_task_end(&g_fault, (t)); } } while (0)

static sample_t no_sample(void) { sample_t s = {0.0f, false, 0u}; return s; }

static void step(uint32_t now)
{
    static bool ign_prev;
    static uint32_t status_due_ms;
    bool ign = true;                                  /* if the power task is switched off, behave as if the key is on */
    RUN_TASK(TASK_POWER, { power_poll(now); ign = power_ignition_on(); });
    if (ign && !ign_prev) fault_ignition_on(&g_fault);
    ign_prev = ign;

    uint8_t open_mask = 0u;
    sample_t fuel_l = no_sample(), coolant_l = no_sample(), oil_l = no_sample(), batt_l = no_sample();
    RUN_TASK(TASK_SENSORS, {
        senders_poll(now);
        fuel_l = senders_fuel_pct(); coolant_l = senders_coolant_c();
        oil_l = senders_oil_kpa(); batt_l = senders_battery_v();
        open_mask = senders_open_mask();
    });

    display_settings_t cfg = can_link_settings();
    sample_t speed_l = no_sample(), rpm_l = no_sample();
    lamps_t lamps = {0};
    bool dash_lights = false;
    uint8_t dimmer = 100u;
    RUN_TASK(TASK_INPUTS, {
        inputs_poll(now);
        speed_l = inputs_speed_kph(); rpm_l = inputs_rpm_from_tach();
        lamps = inputs_lamps(cfg.lamp_invert_mask);
        dash_lights = inputs_dash_lights_on(); dimmer = inputs_dimmer_pct();
    });

    car_bus_t car = {0};
    RUN_TASK(TASK_CAN, { can_link_poll(now); car = can_link_car(); cfg = can_link_settings(); });

    chosen_t speed = agg_pick_speed(speed_l, car.speed_kph, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t rpm = agg_pick_rpm(rpm_l, cfg.tach_enabled, car.rpm, now, CLUSTER_CAR_BUS_TIMEOUT_MS, 200u);
    chosen_t battery = agg_pick_car_first(car.battery_v, batt_l, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t fuel = agg_pick_car_first(car.fuel_pct, fuel_l, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t coolant = agg_pick_car_first(car.coolant_c, coolant_l, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t oil = agg_pick_car_first(car.oil_kpa, oil_l, now, CLUSTER_CAR_BUS_TIMEOUT_MS);

    RUN_TASK(TASK_SCREENS, {
        screen_values_t sv = { speed, rpm, battery, fuel, coolant, oil };
        aux_display_set_imperial(cfg.units_mph);
        theme_t theme = screens_theme_from_setting(cfg.gauge_theme);
        aux_display_set_theme(theme);
        const screen_cfg_t *layout = screens_layout_for(theme, screens_center_active(cfg.center_shows_speed, cfg.display_heartbeat_seen));
        for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
            screen_view_t view = screens_build(&layout[i], &sv, cfg.units_mph);
            aux_display_screen(i, &view);
        }
        /* Send what changed, a bounded amount per tick: at most 8000 bytes (plus the run that crosses the
         * limit), which is under 10 ms on the 9.6 MHz bus, so the blocking transfers never overrun the tick. */
        aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);
    });

    fault_facts_t facts = { cfg.display_heartbeat_seen, open_mask };
    limp_t limp = fault_level(&g_fault, &facts);
    RUN_TASK(TASK_CAN, {
        can_link_send_motion(speed.value, rpm.value, battery.value, speed.valid, rpm.valid,
                             battery.valid, speed.src == SRC_LOCAL);
        can_link_send_fluids(fuel.value, coolant.value, oil.value, fuel.valid, coolant.valid, oil.valid);
        can_link_send_indicators(lamps.turn_left, lamps.turn_right, lamps.high_beam, lamps.brake, lamps.alternator, lamps.oil,
                                 dash_lights, dimmer);
        can_link_send_power(ign, false, 0);
        if ((int32_t)(now - status_due_ms) >= 0) {
            status_due_ms = now + STATUS_PERIOD_MS;
            status_in_t in = { fuel, coolant, oil, battery, rpm.src == SRC_LOCAL, car.active, cfg.car_profile,
                               cfg.display_heartbeat_seen, open_mask, g_fault.cause, limp,
                               fault_quarantine_mask(&g_fault), fault_wdog_resets(&g_fault) };
            cluster_gauges_status_t st = status_build(&in);
            can_link_send_status(&st);
        }
    });

    RUN_TASK(TASK_POWER, power_enter_stop_if_idle(now));

    if (fault_service(&g_fault, now)) {
#ifndef HOST_BUILD
        wdog_kick();
#endif
    }
}

#ifndef HOST_BUILD
int main(void)
{
    /* Everything below runs with the watchdog off (startup.c turned it off to survive the SRAM fill); the first
     * pass of step() is the first time it is watched. Starting it last keeps a slow display init from tripping it. */
    fault_boot(&g_fault, &g_retained, rcm_reset_status(), now_ms());
    power_init();
    senders_init();
    inputs_init();
    can_link_init();
    aux_display_init(panel_hal_board(), screens_theme_from_setting(can_link_settings().gauge_theme), can_link_settings().units_mph);
    wdog_start(WDOG_TIMEOUT_MS);
    for (;;) {
        step(now_ms());
        wait_for_tick_10ms();
    }
}
#else
/* host build only: lets `make stubs` compile-check step() without a main */
void host_step(uint32_t now) { fault_boot(&g_fault, &g_retained, 0u, now); step(now); }
#endif
