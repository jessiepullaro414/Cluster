#ifndef AUX_DISPLAY_H
#define AUX_DISPLAY_H
/* STUB. Four GC9A01 round gauges (240x240) on LPSPI2 with GPIO chip selects
 * and D/C pins. Order on the board: fuel, oil, coolant temp, battery. */
#include "aggregate.h"

void aux_display_init(void);
void aux_display_set_backlight(bool on, uint8_t pct);
/* draw a needle gauge from a value in [lo, hi]; invalid values draw a dash */
void aux_display_gauge(uint8_t index, chosen_t v, float lo, float hi);
#endif
