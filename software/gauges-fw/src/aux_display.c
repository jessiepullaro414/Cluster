#include "aux_display.h"

/* TODO: LPSPI2 setup, GC9A01 init sequence (from Raystar's RFA401280B-AYW-DNF1
 * datasheet, not yet requested), framebuffer-less needle drawing or a DMA line
 * buffer, backlight via the BL_EN switch (gauges/ Q2). */
void aux_display_init(void) {}
void aux_display_set_backlight(bool on, uint8_t pct) { (void)on; (void)pct; }
void aux_display_screen(uint8_t index, const screen_view_t *view)
{ (void)index; (void)view; }
