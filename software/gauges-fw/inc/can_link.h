#ifndef CAN_LINK_H
#define CAN_LINK_H
/* STUB. CAN0 (car bus, LISTEN-ONLY, profile selectable: ecu-pcb native or
 * Haltech V2) and CAN1 (private link to display/). Message layouts, counters
 * and CRC come from ../../protocol/cluster_can.h (generated, do not copy). */
#include <stdbool.h>
#include "aggregate.h"

typedef struct {
    sample_t speed_kph, rpm, battery_v, fuel_pct, coolant_c, oil_kpa;
    bool     active;                 /* any car-bus frame seen within the timeout */
} car_bus_t;

typedef struct {
    uint8_t brightness_pct;
    bool    night_mode, units_mph;
    uint8_t gauge_theme;             /* theme_t, DisplaySettings.GaugeTheme */
    bool    center_shows_speed;      /* DisplaySettings.CenterShowsSpeed: speed is on the centre screen */
    uint8_t car_profile;             /* 0 none, 1 Haltech V2 */
    uint8_t car_bitrate;             /* 0 500k, 1 1M, 2 250k */
    float   tank_capacity_l;
    uint8_t lamp_invert_mask;
    bool    tach_enabled;
    uint8_t tach_pulses_per_rev;
    uint32_t pulses_per_mile;
    bool    display_heartbeat_seen;
} display_settings_t;

void       can_link_init(void);
void       can_link_poll(uint32_t now_ms);            /* drain RX, update tables */
car_bus_t  can_link_car(void);
display_settings_t can_link_settings(void);
/* private-link transmit (counter + CRC added inside): */
void can_link_send_motion(float kph, float rpm, float battery_v,
                          bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall);
void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa,
                          bool fuel_ok, bool coolant_ok, bool oil_ok);
void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil,
                              bool lights_on, uint8_t dimmer_pct);
void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s);
#endif
