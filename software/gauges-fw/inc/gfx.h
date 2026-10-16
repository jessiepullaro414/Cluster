#ifndef GFX_H
#define GFX_H
/*
 * Tile renderer for the 240x240 round screens. REAL, host-tested.
 *
 * Why this shape: one 240x240 RGB565 frame is 115 KB and the S32K144 has 60 KB
 * of RAM, so there is no framebuffer. A screen is a short list of drawing
 * operations (arcs, capsules, discs, glyphs); any 16x16 tile can be rendered
 * from that list on demand and sent to the panel. Only the tiles a change
 * touches are rendered and sent (see dial.c), which is what makes the update
 * workable over a 10 MHz SPI: a moving needle is a few dozen tiles, not the frame.
 *
 * Inner loops are integer-only: Q4 fixed point (1/16 px) for geometry, 8-bit
 * coverage for anti-aliasing, no divisions per pixel (reciprocals are
 * precomputed per operation), one integer square root only on edge pixels.
 */
#include <stdbool.h>
#include <stdint.h>

#define GFX_SIZE   240
/* 8 x 8 tiles (30 x 30). The S32K144's LPSPI is limited to 10 MHz in Run mode (datasheet, as
 * quoted for Rev 13), so the bytes sent per update decide the frame rate: smaller tiles send
 * fewer pixels around a thin needle and a changed digit. Per-run overhead is 11 command bytes. */
#define GFX_TILE   8
#define GFX_TILES  (GFX_SIZE / GFX_TILE)

#define Q4(px)     ((int32_t)((px) * 16))          /* pixels to Q4 */

typedef enum { OP_ARC = 1, OP_CAPSULE, OP_DISC, OP_GLYPH } op_kind_t;

typedef struct {
    uint8_t  kind;
    uint8_t  flags;                 /* ARC: bit0 = sweep over 180 degrees, bit1 = full ring */
    uint32_t color;                 /* 0x00RRGGBB */
    int16_t  x0, y0, x1, y1;        /* bounding box in pixels, x1/y1 exclusive */
    union {
        struct { int32_t cx, cy, rin, rout; int16_t sx, sy, ex, ey; } arc;      /* Q4; unit vectors Q14 */
        struct { int32_t ax, ay, abx, aby, len2, inv, r; } cap;                 /* Q4; len2 Q8, inv = 2^32/len2 */
        struct { int32_t cx, cy, r; } disc;                                     /* Q4 */
        struct { int16_t x, y; uint8_t ch, scale; } glyph;                      /* pixels */
    } u;
} op_t;

/* ---- building operations (float is fine here: once per change, not per pixel) ---- */

/* Ring segment, angles in degrees measured clockwise from 3 o'clock (screen y down),
 * sweeping clockwise from a0 to a1. */
op_t gfx_arc(float cx, float cy, float r_in, float r_out, float a0_deg, float a1_deg, uint32_t color);
/* Line segment with round caps and the given thickness, in pixels. */
op_t gfx_capsule(float ax, float ay, float bx, float by, float thickness, uint32_t color);
op_t gfx_disc(float cx, float cy, float r, uint32_t color);
/* One 5x7 glyph, top-left at (x, y), scaled by an integer 1..8. Cell is 5*scale wide. */
op_t gfx_glyph(int x, int y, char ch, int scale, uint32_t color);

#define GFX_GLYPH_W   5
#define GFX_GLYPH_H   7
#define GFX_GLYPH_ADV 6                 /* advance in glyph units, including 1 unit spacing */

/* ---- rendering ---- */

/* Render the w x h pixel rectangle at (x0, y0) from ops[0..n) (painter's order: later ops
 * on top) into out, row-major with the given stride in pixels, RGB565. Background is black. */
void gfx_render(const op_t *ops, int n, int x0, int y0, int w, int h, uint16_t *out, int stride);

static inline uint16_t gfx_rgb565(uint32_t rgb)
{
    return (uint16_t)(((rgb >> 8) & 0xF800u) | ((rgb >> 5) & 0x07E0u) | ((rgb >> 3) & 0x001Fu));
}

/* Integer square root of a 32-bit value. */
uint32_t gfx_isqrt(uint32_t v);

/* Counters for the host tests: how much work a render did. Compiled in with -DGFX_STATS. */
#ifdef GFX_STATS
extern uint32_t gfx_stat_pixels, gfx_stat_op_evals, gfx_stat_sqrt;
#endif
#endif
