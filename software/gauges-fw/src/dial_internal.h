#ifndef DIAL_INTERNAL_H
#define DIAL_INTERNAL_H
/* Shared between dial.c (the classic needle theme) and dial_modern.c (the progress-arc theme). */
#include "dial.h"

#define DIAL_CX 120.0f
#define DIAL_CY 120.0f

/* Mark every tile touched by the pixel rectangle [x0, x1) x [y0, y1) dirty (tiles outside the round panel are skipped). */
void dial_mark_rect(dial_t *d, int x0, int y0, int x1, int y1);

/* An op list ran out of room (see dial_overflowed). */
void dial_note_overflow(void);

/* The modern theme's counterpart of dial_set_view. */
void dial_modern_set_view(dial_t *d, const screen_view_t *view, bool imperial);
#endif
