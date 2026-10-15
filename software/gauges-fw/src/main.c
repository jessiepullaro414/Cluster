#include <stdint.h>
#include "aggregate.h"
#include "aux_display.h"
#include "can_link.h"
#include "inputs.h"
#include "power.h"
#include "senders.h"
#include "cluster_can.h"

/* STUB main: the init order and the 10 ms task are the point; every module is
 * a stub. now_ms() and the scheduler tick come from a SysTick/LPIT driver that
 * does not exist yet. */
extern uint32_t now_ms(void);
extern void     wait_for_tick_10ms(void);

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

    aux_display_gauge(0, fuel, 0.0f, 100.0f);
    aux_display_gauge(1, oil, 0.0f, 700.0f);
    aux_display_gauge(2, coolant, 40.0f, 130.0f);
    aux_display_gauge(3, battery, 10.0f, 16.0f);

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
    aux_display_init();
    for (;;) {
        step(now_ms());
        wait_for_tick_10ms();
    }
}
#else
/* host build only: lets `make stubs` compile-check step() without a main */
void host_step(uint32_t now) { step(now); }
#endif
