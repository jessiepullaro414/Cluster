#ifndef CAN_LINK_H
#define CAN_LINK_H
/* CAN0 (car bus, LISTEN-ONLY, profile selectable: 0 none, 1 Haltech V2) and CAN1 (private link to display/). REAL logic, host-tested
 * against a fake controller (test/test_can_link.c); the FlexCAN register driver is flexcan_s32k.c. Message layouts, counters and
 * CRC come from ../../protocol/cluster_can.h and cluster_codec.h (generated, do not copy). */
#include <stdbool.h>
#include "aggregate.h"
#include "can_hw.h"
#include "cluster_codec.h"

typedef struct {
    sample_t speed_kph, rpm, battery_v, fuel_pct, coolant_c, oil_kpa;
    bool     active;                 /* any car-bus frame seen within the timeout */
} car_bus_t;

typedef struct {
    uint8_t brightness_pct;
    bool    night_mode, units_mph;
    uint8_t gauge_theme;             /* theme_t, DisplaySettings.GaugeTheme */
    bool    center_shows_speed;      /* DisplaySettings.CenterShowsSpeed: speed is on the centre screen. NOT kept in flash: false at boot */
    uint8_t car_profile;             /* 0 none, 1 Haltech V2 */
    uint8_t car_bitrate;             /* 0 500k, 1 1M, 2 250k */
    float   tank_capacity_l;
    uint8_t lamp_invert_mask;
    bool    tach_enabled;
    uint8_t tach_pulses_per_rev;
    uint32_t pulses_per_mile;
    bool    display_heartbeat_seen;  /* true only while DisplayHeartbeat arrives within its timeout (Android is alive) */
} display_settings_t;

void       can_link_init(const can_hw_t *hw);     /* null: no controllers (everything silent, the car bus inactive) */
void       can_link_poll(uint32_t now_ms);            /* drain RX, update tables */
car_bus_t  can_link_car(void);
display_settings_t can_link_settings(void);
void       can_link_load_settings(const display_settings_t *s);   /* the copy kept in flash, installed at boot before the display speaks */
/* private-link transmit (counter + CRC added inside): */
void can_link_send_motion(float kph, float rpm, float battery_v,
                          bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall);
void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa,
                          bool fuel_ok, bool coolant_ok, bool oil_ok);
void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil,
                              bool lights_on, uint8_t dimmer_pct);
void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s);
void can_link_send_status(const cluster_gauges_status_t *s);   /* GaugesStatus, once a second */
void can_link_send_odometer(uint32_t odometer_m, uint32_t trip_m);   /* Odometer, once a second */
void can_link_send_sender_ohms(float fuel_ohm, float oil_ohm, float coolant_ohm);   /* SenderOhms, once a second; < 0 = no reading */
bool can_link_update_requested(void);       /* true once for each valid ENTER command (0x7C0) addressed to this board */
bool can_link_trip_reset_requested(void);   /* true once for each TripCommand with a new TripResetCount */
#endif
