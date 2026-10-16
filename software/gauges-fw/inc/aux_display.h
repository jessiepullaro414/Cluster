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

/* Reset and initialise all screens, draw the first frame of each in `theme` (values
 * shown as dashes), then switch the displays on. Blocks for the panel's reset and sleep-out
 * waits (about 0.3 s) plus the first full draw. */
void aux_display_init(const panel_hal_t *hal, theme_t theme, bool imperial);

/* on/off only (pct 0 = off): the backlight is a plain switch. */
void aux_display_set_backlight(bool on, uint8_t pct);

/* Present the model of one screen. Units follow the last aux_display_set_imperial(). */
void aux_display_screen(uint8_t index, const screen_view_t *view);
void aux_display_set_imperial(bool imperial);

/* The look of the screens. The caller builds views from screens_layout(theme); a change redraws every screen. */
void aux_display_set_theme(theme_t theme);

/* Per-tick budget used by main.c and the harness. A run is at most 240 x 8 pixels = 3851 bytes, and a
 * tick must stay under 10 ms of bus time (9.6 MHz = 12000 bytes per 10 ms), so a budget of 8000 bytes
 * plus the one run that may cross it keeps every tick at or below about 9.9 ms. */
/* The modern theme refreshes numbers at most every 8 calls (80 ms at the 10 ms tick): a number that changes
 * faster cannot be read, and each refresh redraws big digits. The arcs and bars still follow every change. */
#define AUX_TEXT_HOLD_TICKS 8

#define AUX_POLL_RUNS   32
#define AUX_POLL_BYTES  8000u

/* Send up to max_runs runs of dirty tiles, round robin over the screens. Returns the number sent. */
int  aux_display_poll(int max_runs);

/* As above, and stop once max_bytes have been sent (the run that crosses the limit is finished). */
int  aux_display_poll_budget(int max_runs, uint32_t max_bytes);

/* Tiles still waiting to be sent (for the host tests and the stats). */
int  aux_display_pending_tiles(void);
#endif
