#ifndef DIAL_H
#define DIAL_H
/*
 * One round screen's picture and its change tracking. REAL, host-tested.
 *
 * dial_set_view() turns a screen_view_t (screens.h) into a drawing list
 * (gfx.h) and marks the 16x16 tiles that differ from what was last drawn.
 * dial_next_run() then hands out runs of dirty tiles for the panel driver to
 * render and send. Nothing here touches the bus.
 *
 * What is drawn: a 270 degree scale (open at the bottom) with ticks, labels
 * and red zones; a needle; the primary value as big seven-segment digits
 * below the pivot; the unit under it; and an optional small secondary line.
 * All of it is placeholder styling to be tuned together with the owner.
 */
#include <stdbool.h>
#include <stdint.h>
#include "gfx.h"
#include "screens.h"

#define DIAL_MAX_OPS 72

/* True if any dial ever ran out of op slots (ops are then dropped). Tests assert it stays false. */
bool dial_overflowed(void);

typedef struct {
    op_t     ops[DIAL_MAX_OPS];
    uint8_t  n_static;                 /* scale, ticks, labels, unit: fixed for a gauge kind and units */
    uint8_t  n_total;
    uint32_t dirty[GFX_TILES];         /* one row per tile row, bit i = tile column i */

    bool         built;
    bool         imperial;
    theme_t      theme;
    gauge_kind_t kind, secondary_kind;

    /* arc themes (modern, carplay): numbers are refreshed at most every hold_ticks calls (0 = always) */
    uint8_t hold_ticks, age[2];
    float   held[2];
    bool    held_ok[2];

    /* what is currently drawn, to diff against */
    bool    needle_shown, needle_warn;
    int16_t needle_deg;                /* quantised to whole degrees */
    char    big[8];
    bool    big_warn;
    char    sec[10];
    bool    sec_warn;
} dial_t;

void dial_init(dial_t *d);

/* Apply a new model in the given theme. Marks changed tiles dirty. Cheap when nothing changed.
 * Switching theme redraws the whole face. */
void dial_set_view_theme(dial_t *d, const screen_view_t *view, bool imperial, theme_t theme);

/* Refresh the numbers of the modern theme at most once per `ticks` calls of dial_set_view_theme (the
 * arc and bars still follow every change). A big jump, a change of validity or a warning goes through at once.
 * Default 0: every change is drawn, which is what the tests of the change tracking need. */
void dial_set_text_hold(dial_t *d, uint8_t ticks);

/* The classic theme (what the first tests use). */
void dial_set_view(dial_t *d, const screen_view_t *view, bool imperial);

/* Mark the whole round face dirty (first draw, or after the panel was reset). */
void dial_mark_all(dial_t *d);

/* Pop the next run of horizontally adjacent dirty tiles (row-major order) and clear
 * its bits. Returns false when nothing is dirty. */
bool dial_next_run(dial_t *d, int *tile_row, int *first_col, int *n_cols);

/* Render a run into out (stride = n_cols * 16 pixels). */
void dial_render_run(const dial_t *d, int tile_row, int first_col, int n_cols, uint16_t *out);

/* Number of dirty tiles right now. */
int dial_dirty_tiles(const dial_t *d);

/* Format helper exposed for tests: value with the given decimals into buf (>= 8 bytes). */
void dial_format(char *buf, float value, int decimals);
#endif
