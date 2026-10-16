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

/* ---- helpers shared by the arc themes (dial_modern.c, dial_carplay.c) ---- */

typedef struct { op_t *ops; int n, max; } olist_t;
void dial_olist_add(olist_t *l, op_t o);
void dial_olist_text(olist_t *l, const font_t *f, const char *s, int x, int baseline, text_align_t a, uint32_t color);
void dial_polar(float r, float deg, float *x, float *y);              /* a point on a circle around the face centre */

typedef struct {
    float min, max;                 /* in the units of the displayed value */
    float label_step, major_step, minor_step;
    float red_from;                 /* value where the red zone starts, or a number above max for none */
    bool  thousands;                /* the value is shown divided by 1000 (rpm) */
} dial_scale_t;
dial_scale_t dial_scale_for(gauge_kind_t k, bool imperial);
float        dial_fraction(const dial_scale_t *s, float v);
/* The number shown may lag the live value (the hold-off of dial_set_text_hold); arcs use the live one. */
gauge_view_t dial_held_view(dial_t *d, int idx, const gauge_view_t *g, const dial_scale_t *s);

/* Largest dynamic op list of an arc theme. */
#define DYN_MAX 40
/* Install a freshly built dynamic op list and mark the tiles that differ from the old one. */
void dial_apply_dynamic(dial_t *d, const op_t *fresh, int n_fresh, bool rebuilt);

/* The modern theme's counterpart of dial_set_view. */
void dial_modern_set_view(dial_t *d, const screen_view_t *view, bool imperial);
/* The CarPlay-inspired theme. */
void dial_carplay_set_view(dial_t *d, const screen_view_t *view, bool imperial);
/* The factory theme: printed faces of the 1966 Mustang gauges (face.h) with a needle drawn over them. */
void dial_factory_set_view(dial_t *d, const screen_view_t *view, bool imperial);
#endif
