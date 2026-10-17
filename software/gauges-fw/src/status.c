#include "status.h"

cluster_gauges_status_t status_build(const status_in_t *in)
{
    cluster_gauges_status_t m = {0};
    m.fw_major = FW_MAJOR;
    m.fw_minor = FW_MINOR;
    m.fuel_sender_open = (in->sender_open_mask & 1u) != 0u;
    m.oil_sender_open = (in->sender_open_mask & 2u) != 0u;
    m.temp_sender_open = (in->sender_open_mask & 4u) != 0u;
    m.car_bus_active = in->car_bus_active;
    m.fuel_from_car = in->fuel.valid && in->fuel.src == SRC_CAR;
    m.coolant_from_car = in->coolant.valid && in->coolant.src == SRC_CAR;
    m.oil_from_car = in->oil.valid && in->oil.src == SRC_CAR;
    m.battery_from_car = in->battery.valid && in->battery.src == SRC_CAR;
    m.active_profile = in->car_bus_active ? in->car_profile : 0u;
    m.display_offline = !in->display_alive;
    m.rpm_from_tach = in->rpm_from_tach;
    m.reset_cause = (uint32_t)in->reset_cause;
    m.limp_level = (uint32_t)in->limp;
    m.quarantine_mask = in->quarantine;
    m.watchdog_resets = in->wdog_resets;
    m.nv_storage_ok = in->nv_ok;
    return m;
}
