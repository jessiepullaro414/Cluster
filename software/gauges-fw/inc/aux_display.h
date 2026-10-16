#ifndef AUX_DISPLAY_H
#define AUX_DISPLAY_H
/* STUB. Four GC9A01 round gauges (240x240) on LPSPI2 with GPIO chip selects
 * and D/C pins. Index 0..3 runs left to right on the board; what each screen
 * shows is decided by screens.h (speed and rpm are here: the centre display is
 * CarPlay maps). */
#include "aggregate.h"
#include "screens.h"

void aux_display_init(void);
void aux_display_set_backlight(bool on, uint8_t pct);
/* draw one screen from its model: needle and large number for the primary,
 * small number for the secondary; invalid gauges draw a dash, warn draws in
 * the warning colour */
void aux_display_screen(uint8_t index, const screen_view_t *view);
#endif
