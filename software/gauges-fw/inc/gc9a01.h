#ifndef GC9A01_H
#define GC9A01_H
/*
 * GC9A01 round TFT driver (240 x 240, 4-line SPI, RGB565).
 *
 * Sources, kept separate on purpose:
 *  - DOCUMENTED: GalaxyCore GC9A01 datasheet V1.0 Preliminary (LCD-DST-3014):
 *    command list 6.1 (SLPOUT 11h, INVON 21h, DISPON 29h, CASET 2Ah, RASET 2Bh,
 *    RAMWR 2Ch, MADCTL 36h, COLMOD 3Ah), 4-line SPI protocol 4.1.8/4.1.9, SPI
 *    timing 7.3.4 (write cycle >= 10 ns, so the controller is never the limit),
 *    inter-register enable FEh/EFh 6.4.8/6.4.9, power control C3h/C4h/C9h
 *    6.4.4-6.4.6, gamma F0h-F3h 6.4.10-6.4.13, frame rate E8h 6.4.1.
 *  - NOT IN THE DATASHEET: the "vendor block" of undocumented registers
 *    (84h-8Fh, 90h, ..., 98h) that every public driver sends. The values here
 *    are the ones in Zephyr's display_gc9x01x.c (Apache-2.0), which says they come
 *    from the manufacturer sample code. Raystar's module may need different
 *    values: ask Raystar for the RFA401280B-AYW-DNF1 init code (docs/rfq-drafts.md)
 *    and replace gc9a01_vendor_block in gc9a01.c.
 *  - Module-specific, UNVERIFIED on hardware: MADCTL (orientation and RGB/BGR
 *    order) and display inversion. Defaults follow Zephyr's Waveshare example.
 */
#include <stdbool.h>
#include <stdint.h>
#include "panel_hal.h"

#ifndef GC9A01_MADCTL
#define GC9A01_MADCTL   0x08u       /* BGR order, no mirroring */
#endif
#ifndef GC9A01_INVERT
#define GC9A01_INVERT   1           /* send INVON (21h) */
#endif

#define GC9A01_WIDTH    240
#define GC9A01_HEIGHT   240

/* Shared hardware reset for all four screens, then wait for the controllers. */
void gc9a01_reset(const panel_hal_t *hal);

/* Time to wait after gc9a01_init() before sending that screen anything else. The datasheet
 * (6.2.4, Sleep Out) requires 5 ms; 150 ms is the open-source driver's margin and is used
 * before the display is switched on. All screens can share one wait. */
#define GC9A01_SLEEP_OUT_WAIT_MS 150u

/* Full init of one screen, ending with Sleep Out. The display is left OFF (garbage-free
 * first frame): wait GC9A01_SLEEP_OUT_WAIT_MS, draw, then gc9a01_display(..., true). */
void gc9a01_init(const panel_hal_t *hal, uint8_t screen);

void gc9a01_display(const panel_hal_t *hal, uint8_t screen, bool on);

/* Write a w x h block of RGB565 pixels (host byte order, row-major, stride = w)
 * with its top-left at (x, y). The window must lie inside 240 x 240. */
void gc9a01_blit(const panel_hal_t *hal, uint8_t screen, int x, int y, int w, int h, const uint16_t *pix);

/* Low level, exposed for tests. */
void gc9a01_command(const panel_hal_t *hal, uint8_t screen, uint8_t cmd, const uint8_t *params, uint32_t n);
#endif
