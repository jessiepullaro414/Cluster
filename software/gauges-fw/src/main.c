#include <stdint.h>
#include "aggregate.h"
#include "aux_display.h"
#include "can_link.h"
#include "inputs.h"
#include "panel_hal.h"
#include "screens.h"
#include "power.h"
#include "senders.h"
#include "tick.h"
#include "cluster_can.h"

/* STUB main: the init order and the 10 ms task are the point; every module
 * except the clock and the tick (tick.c) is a stub. */

static void step(uint32_t now)
{
    power_poll(now);
    senders_poll(now);
    inputs_poll(now);
    can_link_poll(now);

    car_bus_t car = can_link_car();
    display_settings_t cfg = can_link_settings();

    chosen_t speed = agg_pick_speed(inputs_speed_kph(), car.speed_kph, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t rpm = agg_pick_rpm(inputs_rpm_from_tach(), cfg.tach_enabled, car.rpm, now,
                                CLUSTER_CAR_BUS_TIMEOUT_MS, 200u);
    chosen_t battery = agg_pick_car_first(car.battery_v, senders_battery_v(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t fuel = agg_pick_car_first(car.fuel_pct, senders_fuel_pct(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t coolant = agg_pick_car_first(car.coolant_c, senders_coolant_c(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t oil = agg_pick_car_first(car.oil_kpa, senders_oil_kpa(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);

    screen_values_t sv = { speed, rpm, battery, fuel, coolant, oil };
    aux_display_set_imperial(cfg.units_mph);
    theme_t theme = screens_theme_from_setting(cfg.gauge_theme);
    aux_display_set_theme(theme);
    const screen_cfg_t *layout = screens_layout_for(theme, cfg.center_shows_speed);
    for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
        screen_view_t view = screens_build(&layout[i], &sv, cfg.units_mph);
        aux_display_screen(i, &view);
    }
    /* Send what changed, a bounded amount per tick: at most 8000 bytes (plus the run that crosses the
     * limit), which is under 10 ms on the 9.6 MHz bus, so the blocking transfers never overrun the tick. */
    aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);

    can_link_send_motion(speed.value, rpm.value, battery.value, speed.valid, rpm.valid,
                         battery.valid, speed.src == SRC_LOCAL);
    can_link_send_fluids(fuel.value, coolant.value, oil.value, fuel.valid, coolant.valid, oil.valid);
    lamps_t l = inputs_lamps(cfg.lamp_invert_mask);
    can_link_send_indicators(l.turn_left, l.turn_right, l.high_beam, l.brake, l.alternator, l.oil,
                             inputs_dash_lights_on(), inputs_dimmer_pct());
    can_link_send_power(power_ignition_on(), false, 0);
    power_enter_stop_if_idle(now);
}

#ifndef HOST_BUILD
int main(void)
{
    power_init();
    senders_init();
    inputs_init();
    can_link_init();
    aux_display_init(panel_hal_board(), screens_theme_from_setting(can_link_settings().gauge_theme), can_link_settings().units_mph);
    for (;;) {
        step(now_ms());
        wait_for_tick_10ms();
    }
}
#else
/* host build only: lets `make stubs` compile-check step() without a main */
void host_step(uint32_t now) { step(now); }
#endif
