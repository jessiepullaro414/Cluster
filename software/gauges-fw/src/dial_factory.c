/*
 * The "factory" theme: the four small screens made to look like the original 1966 Mustang gauges (speedometer,
 * fuel, oil, temperature): matte black printed faces, white condensed type, a red-orange needle with a chrome
 * hub on the speedometer and a small dome on the others. There is no digital readout, as on the car.
 *
 * The faces are pictures (face.h, tools/gen_faces.py) drawn once as the bottom layer; the firmware only draws
 * the needle, the hub and, on the fuel screen, a small battery voltage under the marks (this car has no ammeter
 * and the voltage would otherwise be shown nowhere). A needle that has no valid value is not drawn at all,
 * like the dashes of the other themes.
 *
 * Layout (screens_layout(THEME_FACTORY)): fuel (+ volts), speed, oil, temperature. There is no tachometer: the
 * stock cluster has none. The odometer window of the speedometer is an empty box (no odometer data exists).
 * Placeholder styling to tune together with the owner.
 */
#include <math.h>
#include <string.h>

#include "dial_internal.h"
#include "face.h"
#include "font.h"

#define COL_NEEDLE   0xFF4A1Au
#define COL_CHROME   0xC9CDD3u
#define COL_HUB_DARK 0x1A1A1Au
#define COL_HUB_GLINT 0x6E7278u
#define COL_DOME     0x2C2C2Eu
#define COL_DOME_IN  0x0D0D0Du
#define COL_BLUE_OFF 0x0F2A9Eu
#define COL_VOLTS    0x9A9A9Au

typedef struct {
    const face_t *face;
    float px, py;                   /* pivot */
    float a_rest, a_full;           /* needle angle at the low and the high end, degrees clockwise from 3 o'clock */
    float len, tail;
    bool  chrome_hub;
} fgeom_t;

static fgeom_t geom_for(gauge_kind_t k, bool imperial)
{
    switch (k) {
    case GK_SPEED:   return (fgeom_t){ imperial ? &FACE_SPEED_MPH : &FACE_SPEED_KPH, 120.0f, 122.0f, 156.0f, 390.0f, 70.0f, 14.0f, true };
    case GK_OIL:     return (fgeom_t){ &FACE_OIL, 120.0f, 84.0f, 122.0f, 58.0f, 72.0f, 6.0f, false };
    case GK_COOLANT: return (fgeom_t){ &FACE_TEMP, 120.0f, 84.0f, 122.0f, 58.0f, 72.0f, 6.0f, false };
    default:         return (fgeom_t){ &FACE_FUEL, 120.0f, 104.0f, 122.0f, 58.0f, 80.0f, 6.0f, false };   /* fuel; also the fallback */
    }
}

/* The fraction of the scale for the needle. Speed scales are the printed ones (140 mph, 220 km/h). */
static float needle_fraction(const gauge_view_t *g, bool imperial)
{
    float f;
    switch (g->kind) {
    case GK_SPEED:   f = g->value / (imperial ? 140.0f : 220.0f); break;
    case GK_FUEL:    f = g->value / 100.0f; break;
    case GK_OIL:
    case GK_COOLANT: { dial_scale_t s = dial_scale_for(g->kind, imperial); f = dial_fraction(&s, g->value); break; }
    default:         f = 0.0f; break;
    }
    return f < 0.0f ? 0.0f : (f > 1.0f ? 1.0f : f);
}

static void tip_point(const fgeom_t *g, int deg, float r, float *x, float *y)
{
    float a = (float)deg * 0.017453292519943295f;
    *x = g->px + r * cosf(a);
    *y = g->py + r * sinf(a);
}

/* Tiles under a needle at a whole-degree angle (the thick part is 5 px, plus anti-aliasing). */
static void mark_needle(dial_t *d, const fgeom_t *g, int deg)
{
    float x0, y0, x1, y1;
    tip_point(g, deg, -g->tail, &x0, &y0);
    tip_point(g, deg, g->len, &x1, &y1);
    float len = g->len + g->tail;
    int steps = (int)(len / 2.0f) + 1;
    for (int i = 0; i <= steps; i++) {
        float t = (float)i / (float)steps;
        int x = (int)lroundf(x0 + (x1 - x0) * t), y = (int)lroundf(y0 + (y1 - y0) * t);
        dial_mark_rect(d, x - 4, y - 4, x + 5, y + 5);
    }
}

static void mark_volts(dial_t *d, const char *s)
{
    if (!s[0]) return;
    int w = gfx_text_width(&FONT_SMALL, s);
    dial_mark_rect(d, 120 - w / 2 - 2, 208, 120 + w / 2 + 3, 232);
}

static void build_static(dial_t *d, const gauge_view_t *p, bool imperial)
{
    fgeom_t g = geom_for(p->kind, imperial);
    olist_t l = { d->ops, 0, DIAL_MAX_OPS };
    dial_olist_add(&l, gfx_image(g.face));
    if (p->kind == GK_SPEED) dial_olist_add(&l, gfx_disc(120.0f, 86.0f, 5.5f, COL_BLUE_OFF));   /* the high-beam lens, unlit */
    d->n_static = (uint8_t)l.n;
}

void dial_factory_set_view(dial_t *d, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *p = &view->primary, *sec = &view->secondary;
    bool rebuild = !d->built || d->theme != THEME_FACTORY || d->kind != p->kind || d->imperial != imperial ||
                   d->secondary_kind != sec->kind;
    if (rebuild) {
        build_static(d, p, imperial);
        d->built = true;
        d->theme = THEME_FACTORY;
        d->kind = p->kind;
        d->secondary_kind = sec->kind;
        d->imperial = imperial;
        d->needle_shown = false;  d->needle_deg = 0;  d->needle_warn = false;
        d->sec[0] = 0;
        d->n_total = d->n_static;
        dial_mark_all(d);
    }

    fgeom_t g = geom_for(p->kind, imperial);
    bool needle = p->valid && (p->kind == GK_SPEED || p->kind == GK_FUEL || p->kind == GK_OIL || p->kind == GK_COOLANT);
    int deg = 0;
    if (needle) deg = (int)lroundf(g.a_rest + (g.a_full - g.a_rest) * needle_fraction(p, imperial));

    char volts[10];
    volts[0] = 0;
    if (sec->kind == GK_BATTERY) {
        if (sec->valid) {
            char num[8];
            dial_format(num, sec->value, 1);
            strcpy(volts, num);
            strcat(volts, " V");
        } else {
            strcpy(volts, "-- V");
        }
    }

    bool changed = false;
    if (needle != d->needle_shown || (needle && deg != d->needle_deg)) {
        if (d->needle_shown) mark_needle(d, &g, d->needle_deg);
        if (needle) mark_needle(d, &g, deg);
        changed = true;
    }
    if (strcmp(volts, d->sec) != 0) {
        mark_volts(d, d->sec);
        mark_volts(d, volts);
        changed = true;
    }
    if (!changed && !rebuild) return;

    d->needle_shown = needle;  d->needle_deg = (int16_t)deg;
    strcpy(d->sec, volts);

    olist_t l = { d->ops, d->n_static, DIAL_MAX_OPS };
    if (needle) {
        float tx, ty, bx, by, hx, hy;
        tip_point(&g, deg, g.len, &tx, &ty);
        tip_point(&g, deg, g.len * 0.28f, &bx, &by);
        tip_point(&g, deg, -g.tail, &hx, &hy);
        dial_olist_add(&l, gfx_capsule(hx, hy, bx, by, 5.2f, COL_NEEDLE));      /* the wide root ... */
        dial_olist_add(&l, gfx_capsule(bx, by, tx, ty, 2.8f, COL_NEEDLE));      /* ... and the fine tip */
    }
    if (g.chrome_hub) {
        dial_olist_add(&l, gfx_disc(g.px, g.py, 13.0f, COL_CHROME));
        dial_olist_add(&l, gfx_disc(g.px, g.py, 9.0f, COL_HUB_DARK));
        dial_olist_add(&l, gfx_disc(g.px - 2.0f, g.py - 2.0f, 2.6f, COL_HUB_GLINT));
    } else {
        dial_olist_add(&l, gfx_disc(g.px, g.py, 9.5f, COL_DOME));
        dial_olist_add(&l, gfx_disc(g.px, g.py, 6.0f, COL_DOME_IN));
    }
    if (volts[0]) dial_olist_text(&l, &FONT_SMALL, volts, 120, 226, TEXT_CENTER, COL_VOLTS);
    d->n_total = (uint8_t)l.n;
}
