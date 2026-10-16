#ifndef FONT_H
#define FONT_H
/* Anti-aliased bitmap fonts (4 bits per pixel), generated from Inter by tools/gen_font.py. */
#include <stdint.h>

typedef struct {
    uint16_t off;           /* byte offset of the bitmap in the face's bit array */
    uint8_t  w, h;          /* bitmap size in pixels (0 for a blank glyph such as the space) */
    int8_t   bx, by;        /* top-left of the bitmap relative to the pen on the baseline (by is negative above it) */
    uint8_t  adv;           /* pen advance */
} fglyph_t;

typedef struct {
    const fglyph_t *glyphs; /* indexed by (char - first) */
    const uint8_t  *bits;
    uint8_t first, last;    /* character range present */
    uint8_t ascent;         /* pixels above the baseline of the tallest glyph */
    uint8_t size;           /* nominal pixel size */
} font_t;

extern const font_t FONT_BIG;       /* 60 px: digits - . and space */
extern const font_t FONT_MED;       /* 28 px: ASCII and the degree sign */
extern const font_t FONT_SMALL;     /* 15 px: ASCII and the degree sign */

/* The degree sign is character 0x7F (a plain string can carry it). */
#define DEG "\x7F"
#endif
