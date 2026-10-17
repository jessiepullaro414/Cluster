#ifndef STATUS_H
#define STATUS_H
/* Builds the GaugesStatus message (0x301) from what the main loop knows. Pure, host-tested. */
#include "aggregate.h"
#include "cluster_codec.h"
#include "fault.h"

#define FW_MAJOR 0u
#define FW_MINOR 1u
#define STATUS_PERIOD_MS 1000u

typedef struct {
    chosen_t fuel, coolant, oil, battery;
    bool     rpm_from_tach;
    bool     car_bus_active;
    uint8_t  car_profile;            /* display_settings_t.car_profile */
    bool     display_alive;
    uint8_t  sender_open_mask;       /* bit 0 fuel, 1 oil, 2 coolant (senders_open_mask()) */
    reset_cause_t reset_cause;
    limp_t   limp;
    uint8_t  quarantine;
    uint8_t  wdog_resets;
} status_in_t;

cluster_gauges_status_t status_build(const status_in_t *in);

#endif
