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

#include "font.h"

#define GFX_SIZE   240
/* 8 x 8 tiles (30 x 30). The S32K144's LPSPI is limited to 10 MHz in Run mode (datasheet, as
 * quoted for Rev 13), so the bytes sent per update decide the frame rate: smaller tiles send
 * fewer pixels around a thin needle and a changed digit. Per-run overhead is 11 command bytes. */
#define GFX_TILE   8
#define GFX_TILES  (GFX_SIZE / GFX_TILE)

#define Q4(px)     ((int32_t)((px) * 16))          /* pixels to Q4 */

typedef enum { OP_ARC = 1, OP_CAPSULE, OP_DISC, OP_GLYPH, OP_ARCG, OP_TICKS, OP_RRECT, OP_BMP } op_kind_t;

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
        /* gradient arc: lit from a0 over clip, colour runs color -> c1 over full (angles in 1/65536 turn) */
        struct { int32_t cx, cy, rin, rout; uint32_t c1, clipq, fullq; uint16_t a0q; } arcg;
        /* ring of radial ticks every step over span, half width hw, one-pixel ramp aa (angle units) */
        struct { int32_t cx, cy, rin, rout; uint32_t spanq, stepq, hwq, aaq; uint16_t a0q; } ticks;
        /* rounded rectangle, centre and half sizes in Q4; stroke 0 = filled */
        struct { int32_t cx, cy, hw, hh, r, stroke; } rrect;
        /* 4-bit coverage bitmap (a font glyph) at x, y */
        struct { const uint8_t *bits; int16_t x, y; uint8_t w, h; } bmp;
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

/* Arc whose colour changes along it. The scale runs from a0 over full_deg and the colour goes
 * color0 -> color1 across that whole scale; only the first visible_deg of it is lit (a progress
 * bar). Ends are square: add discs for rounded ends. */
op_t gfx_arc_gradient(float cx, float cy, float r_in, float r_out, float a0_deg, float full_deg,
                      float visible_deg, uint32_t color0, uint32_t color1);
/* The colour of that gradient at a position (0..1 along the full scale), for matching end caps. */
uint32_t gfx_lerp_color(uint32_t c0, uint32_t c1, float t);

/* Radial tick marks every step_deg from a0 over span_deg (both ends included), thickness in
 * pixels measured at the middle radius, between r_in and r_out. */
op_t gfx_ticks(float cx, float cy, float r_in, float r_out, float a0_deg, float span_deg, float step_deg,
               float thickness, uint32_t color);

/* Rounded rectangle centred on (cx, cy). stroke 0 draws it filled, otherwise as an outline. */
op_t gfx_rrect(float cx, float cy, float w, float h, float radius, float stroke, uint32_t color);

/* One anti-aliased font glyph with its pen position (x, baseline). */
op_t gfx_bitmap(const font_t *f, char ch, int x, int baseline, uint32_t color);

typedef enum { TEXT_LEFT = 0, TEXT_CENTER, TEXT_RIGHT } text_align_t;
/* Pixel width of a string in a face. */
int  gfx_text_width(const font_t *f, const char *s);
/* Lay a string out into glyph ops, anchored at x on the baseline. Returns the number of ops written. */
int  gfx_text(op_t *out, int max, const font_t *f, const char *s, int x, int baseline, text_align_t align, uint32_t color);

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
