#ifndef INPUTS_H
#define INPUTS_H
/* Pulse inputs (Hall speed, tach), the six lamp inputs, the dash dimmer and the ignition sense. REAL logic, host-tested
 * against a fake hardware layer (test/test_inputs.c); the register code is inputs_hw_s32k.c and adc_s32k.c, written from the
 * RM and never run on a part.
 *
 * Choices that are policy, not physics:
 *  - A speed sender that has produced two edges since boot is "present". While it is present and standing still it reports a
 *    valid 0 km/h, so a stopped car shows 0 rather than dashes. A sender that has never produced pulses is "absent": invalid,
 *    so the aggregator falls back to the car bus. (aggregate.c cross-checks a Hall 0 against a moving car-bus speed.)
 *  - The tach behaves the same way, but is only used when the display setting enables it.
 *  - A lamp has to hold a new state for 20 ms (the turn signals flash at about 1.5 Hz). */
#include <stdbool.h>
#include "adc.h"
#include "aggregate.h"
#include "inputs_hw.h"

typedef struct {
    bool turn_left, turn_right, high_beam, brake, alternator, oil;
} lamps_t;

void     inputs_init(const inputs_hw_t *hw, const adc_ops_t *adc);   /* null pointers give a dead input set (invalid, lamps off) */
void     inputs_configure(uint32_t pulses_per_mile, uint8_t tach_pulses_per_rev);   /* DisplaySettings / SpeedCalibration values */
void     inputs_poll(uint32_t now_ms);           /* call every 10 ms */
sample_t inputs_speed_kph(void);                 /* from FTM1_CH4 capture and PulsesPerMile */
sample_t inputs_rpm_from_tach(void);             /* from FTM1_CH5 capture and TachPulsesPerRev */
lamps_t  inputs_lamps(uint8_t invert_mask);      /* bit n set = lamp n is active-low */
bool     inputs_dash_lights_on(void);
uint8_t  inputs_dimmer_pct(void);                /* 0..100 */
bool     inputs_ignition_on(void);
#endif
