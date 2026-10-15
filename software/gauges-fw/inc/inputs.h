#ifndef INPUTS_H
#define INPUTS_H
/* STUB. Pulse inputs, lamps, dimmer. */
#include <stdbool.h>
#include "aggregate.h"

typedef struct {
    bool turn_left, turn_right, high_beam, brake, alternator, oil;
} lamps_t;

void     inputs_init(void);
void     inputs_poll(uint32_t now_ms);           /* call every 10 ms */
sample_t inputs_speed_kph(void);                 /* from FTM1_CH4 capture and PulsesPerMile */
sample_t inputs_rpm_from_tach(void);             /* from FTM1_CH5 capture and TachPulsesPerRev */
lamps_t  inputs_lamps(uint8_t invert_mask);      /* bit n set = lamp n is active-low */
bool     inputs_dash_lights_on(void);
uint8_t  inputs_dimmer_pct(void);                /* 0..100 */
bool     inputs_ignition_on(void);
#endif
