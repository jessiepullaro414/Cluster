#ifndef AUX_DISPLAY_H
#define AUX_DISPLAY_H
/*
 * The four GC9A01 round screens (240x240) on LPSPI2, each with its own CS and
 * D/C pin. Index 0..3 runs left to right on the board; what each shows is decided
 * by screens.h. REAL, host-tested against a mock panel; the S32K144 bus layer
 * (panel_hal_s32k.c) has not run on hardware.
 *
 * Flow: aux_display_screen() is cheap and may be called every tick; it only
 * marks the tiles that changed. aux_display_poll() then renders and sends at
 * most `max_runs` runs of changed tiles, so the time spent per call is bounded
 * and the main loop stays at 10 ms.
 */
#include <stdbool.h>
#include <stdint.h>
#include "panel_hal.h"
#include "screens.h"

/* Reset and initialise all screens, draw the first frame of each from `layout` (values
 * shown as dashes), then switch the displays on. Blocks for the panel's reset and sleep-out
 * waits (about 0.3 s) plus the first full draw. */
void aux_display_init(const panel_hal_t *hal, const screen_cfg_t layout[SCREEN_COUNT], bool imperial);

/* on/off only (pct 0 = off): the backlight is a plain switch. */
void aux_display_set_backlight(bool on, uint8_t pct);

/* Present the model of one screen. Units follow the last aux_display_set_imperial(). */
void aux_display_screen(uint8_t index, const screen_view_t *view);
void aux_display_set_imperial(bool imperial);

/* Send up to max_runs runs of dirty tiles, round robin over the screens. Returns the number sent. */
int  aux_display_poll(int max_runs);

/* Tiles still waiting to be sent (for the host tests and the stats). */
int  aux_display_pending_tiles(void);
#endif
