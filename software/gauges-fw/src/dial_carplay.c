/*
 * The "carplay" theme: Apple-inspired. Pure black face, thin rings with rounded ends and a white knob where the
 * value is, light type, system colours (blue, orange, green, red) and grey secondary labels; the battery and oil
 * screen uses two full concentric rings in the manner of Apple's activity rings. Meant to sit next to a CarPlay
 * screen so the whole dash reads as one family.
 *
 * It borrows the look, not any Apple artwork or typeface: the digits are Inter (OFL), the colours are plain RGB
 * values close to Apple's published system colours. Whether Apple's design guidelines allow calling this "CarPlay"
 * in the product is a licensing question (PLAN.md B5), not decided here. Placeholder styling to tune with the owner.
 *
 * Layout (screens_layout(THEME_CARPLAY)): speed + fuel, rpm, battery + oil (two rings), coolant.
 */
#include <math.h>
#include <string.h>

#include "dial_internal.h"
#include "font.h"

#define CX DIAL_CX
#define CY DIAL_CY
#define START_DEG 135.0f
#define SWEEP_DEG 270.0f

#define R_OUT   108.0f
#define R_IN    100.0f
#define R_MID   ((R_OUT + R_IN) * 0.5f)
#define CAP_R   ((R_OUT - R_IN) * 0.5f)

/* two full rings, 14 px thick */
#define RING_TOP_DEG 270.0f
#define RO_OUT  106.0f
#define RO_IN    92.0f
#define RI_OUT   84.0f
#define RI_IN    70.0f

#define COL_BG       0x000000u
#define COL_TRACK    0x1F1F23u
#define COL_WHITE    0xFFFFFFu
#define COL_LABEL    0x8E8E93u
#define COL_BLUE     0x0A84FFu
#define COL_CYAN     0x64D2FFu
#define COL_YELLOW   0xFFD60Au
#define COL_ORANGE   0xFF9F0Au
#define COL_RED      0xFF453Au
#define COL_REDDIM   0x3A1713u
#define COL_GREEN0   0x28B84Cu
#define COL_GREEN1   0x8DF2A6u
#define COL_GREEN_D  0x0B2A13u
#define COL_ORNG0    0xE8820Cu
#define COL_ORNG1    0xFFC85Au
#define COL_ORNG_D   0x2E1D05u

static void put(olist_t *l, op_t o) { dial_olist_add(l, o); }

static void text(olist_t *l, const font_t *f, const char *s, int x, int baseline, text_align_t a, uint32_t c)
{
    dial_olist_text(l, f, s, x, baseline, a, c);
}

/* A big number with a small unit after it, centred as one line. */
static void number_unit(olist_t *l, const font_t *nf, const char *num, const font_t *uf, const char *unit, int cx, int baseline,
                        uint32_t ncol, uint32_t ucol)
{
    int wn = gfx_text_width(nf, num), wu = unit[0] ? gfx_text_width(uf, unit) + 3 : 0;
    int x0 = cx - (wn + wu) / 2;
    text(l, nf, num, x0, baseline, TEXT_LEFT, ncol);
    if (unit[0]) text(l, uf, unit, x0 + wn + 3, baseline, TEXT_LEFT, ucol);
}

/* ---------------------------------------------------------------- static parts */

static void static_ring_gauge(olist_t *l, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *g = &view->primary;
    dial_scale_t s = dial_scale_for(g->kind, imperial);
    float xa, ya, xb, yb;
    dial_polar(R_MID, START_DEG, &xa, &ya);
    dial_polar(R_MID, START_DEG + SWEEP_DEG, &xb, &yb);

    put(l, gfx_arc(CX, CY, R_IN, R_OUT, START_DEG, START_DEG + SWEEP_DEG, COL_TRACK));
    put(l, gfx_disc(xa, ya, CAP_R, COL_TRACK));
    if (s.red_from < s.max) {
        float f = dial_fraction(&s, s.red_from);
        put(l, gfx_arc(CX, CY, R_IN, R_OUT, START_DEG + SWEEP_DEG * f, START_DEG + SWEEP_DEG, COL_REDDIM));
        put(l, gfx_disc(xb, yb, CAP_R, COL_REDDIM));
    } else {
        put(l, gfx_disc(xb, yb, CAP_R, COL_TRACK));
    }

    switch (g->kind) {
    case GK_SPEED:
        text(l, &FONT_SMALL, "SPEED", 120, 74, TEXT_CENTER, COL_LABEL);
        text(l, &FONT_SMALL, g->unit, 120, 170, TEXT_CENTER, COL_LABEL);
        break;
    case GK_RPM:
        text(l, &FONT_SMALL, "RPM", 120, 74, TEXT_CENTER, COL_LABEL);
        text(l, &FONT_SMALL, "x1000", 120, 170, TEXT_CENTER, COL_LABEL);
        break;
    case GK_FUEL:
        text(l, &FONT_SMALL, "FUEL", 120, 74, TEXT_CENTER, COL_LABEL);
        text(l, &FONT_SMALL, "%", 120, 170, TEXT_CENTER, COL_LABEL);
        break;
    case GK_COOLANT:
        text(l, &FONT_SMALL, "COOLANT", 120, 74, TEXT_CENTER, COL_LABEL);
        text(l, &FONT_SMALL, g->unit[0] == 'F' ? DEG "F" : DEG "C", 120, 170, TEXT_CENTER, COL_LABEL);
        break;
    default:
        break;
    }
}

static void static_rings(olist_t *l, const screen_view_t *view)
{
    put(l, gfx_arc(CX, CY, RO_IN, RO_OUT, RING_TOP_DEG, RING_TOP_DEG + 360.0f, COL_GREEN_D));
    put(l, gfx_arc(CX, CY, RI_IN, RI_OUT, RING_TOP_DEG, RING_TOP_DEG + 360.0f, COL_ORNG_D));
    text(l, &FONT_SMALL, "VOLTS", 120, 92, TEXT_CENTER, COL_GREEN1);
    text(l, &FONT_SMALL, view->secondary.kind == GK_OIL ? "OIL" : "", 120, 148, TEXT_CENTER, COL_ORNG1);
}

static void build_static(dial_t *d, const screen_view_t *view, bool imperial)
{
    olist_t l = { d->ops, 0, DIAL_MAX_OPS };
    put(&l, gfx_disc(CX, CY, 119.5f, COL_BG));
    if (view->primary.kind == GK_BATTERY) static_rings(&l, view);
    else static_ring_gauge(&l, view, imperial);
    d->n_static = (uint8_t)l.n;
}

/* ---------------------------------------------------------------- dynamic parts */

static void value_text(char *out, const gauge_view_t *g, const dial_scale_t *s)
{
    if (!g->valid) { strcpy(out, "--"); return; }
    if (s->thousands) dial_format(out, g->value / 1000.0f, 1);
    else dial_format(out, g->value, g->kind == GK_BATTERY ? 1 : 0);
}

/* The knob: a black gap around a white dot, so it reads as sitting on the ring. */
static void knob(olist_t *l, float x, float y)
{
    put(l, gfx_disc(x, y, CAP_R + 4.0f, COL_BG));
    put(l, gfx_disc(x, y, CAP_R + 0.5f, COL_WHITE));
}

static void dyn_ring_gauge(dial_t *d, olist_t *l, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *g = &view->primary;
    dial_scale_t s = dial_scale_for(g->kind, imperial);
    gauge_view_t shown = dial_held_view(d, 0, g, &s);
    float frac = g->valid ? dial_fraction(&s, g->value) : 0.0f;
    float vis = floorf(SWEEP_DEG * frac + 0.5f);               /* whole degrees */

    uint32_t c0 = COL_BLUE, c1 = COL_CYAN;
    if (g->kind == GK_RPM) { c0 = COL_YELLOW; c1 = COL_ORANGE; }
    if (g->kind == GK_FUEL) { c0 = g->warn ? COL_RED : COL_GREEN0; c1 = g->warn ? COL_RED : COL_GREEN1; }
    if (g->kind == GK_COOLANT) { c0 = c1 = g->warn ? COL_RED : COL_CYAN; }          /* a straight blend of cyan to red turns grey on the way */

    if (g->valid) {
        float xa, ya, xe, ye;
        dial_polar(R_MID, START_DEG, &xa, &ya);
        dial_polar(R_MID, START_DEG + vis, &xe, &ye);
        if (vis > 0.0f) {
            if (g->kind == GK_RPM) {
                float f_red = dial_fraction(&s, s.red_from);
                float lit = floorf(fminf(frac, f_red) * SWEEP_DEG + 0.5f);
                put(l, gfx_arc_gradient(CX, CY, R_IN, R_OUT, START_DEG, SWEEP_DEG, lit, c0, c1));
                if (frac > f_red)
                    put(l, gfx_arc_gradient(CX, CY, R_IN, R_OUT, START_DEG + SWEEP_DEG * f_red, SWEEP_DEG, vis - SWEEP_DEG * f_red,
                                            COL_RED, COL_RED));
            } else {
                put(l, gfx_arc_gradient(CX, CY, R_IN, R_OUT, START_DEG, SWEEP_DEG, vis, c0, c1));
            }
            put(l, gfx_disc(xa, ya, CAP_R, c0));
        }
        knob(l, xe, ye);
    }

    char txt[12];
    value_text(txt, &shown, &s);
    uint32_t col = (g->valid && g->warn) ? COL_RED : COL_WHITE;
    text(l, &FONT_BIG, txt, 120, 138, TEXT_CENTER, col);

    /* fuel under the speed */
    const gauge_view_t *sec = &view->secondary;
    if (sec->kind == GK_FUEL) {
        dial_scale_t s2 = dial_scale_for(GK_BATTERY, imperial);            /* only used for the hold-off span */
        gauge_view_t sh = dial_held_view(d, 1, sec, &s2);
        char t[10];
        if (sec->valid) dial_format(t, sh.value, 0); else strcpy(t, "--");
        number_unit(l, &FONT_MED, t, &FONT_SMALL, sec->valid ? "% FUEL" : "FUEL", 120, 206,
                    (sec->valid && sec->warn) ? COL_RED : COL_WHITE, COL_LABEL);
    }
}

static void ring_value(dial_t *d, olist_t *l, int idx, const gauge_view_t *g, float rin, float rout, uint32_t c0, uint32_t c1, int decimals)
{
    dial_scale_t s = dial_scale_for(g->kind, d->imperial);
    float frac = g->valid ? dial_fraction(&s, g->value) : 0.0f;
    float vis = floorf(360.0f * frac + 0.5f);
    (void)idx;
    if (g->valid && vis > 0.0f) {
        float rmid = (rin + rout) * 0.5f, cap = (rout - rin) * 0.5f, xa, ya, xe, ye;
        dial_polar(rmid, RING_TOP_DEG, &xa, &ya);
        dial_polar(rmid, RING_TOP_DEG + vis, &xe, &ye);
        uint32_t a = g->warn ? COL_RED : c0, b = g->warn ? COL_RED : c1;
        put(l, gfx_arc_gradient(CX, CY, rin, rout, RING_TOP_DEG, 360.0f, vis, a, b));
        put(l, gfx_disc(xa, ya, cap, a));
        put(l, gfx_disc(xe, ye, cap, gfx_lerp_color(a, b, vis / 360.0f)));
    }
    (void)decimals;
}

static void dyn_rings(dial_t *d, olist_t *l, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *v = &view->primary, *o = &view->secondary;
    dial_scale_t sv = dial_scale_for(GK_BATTERY, imperial), so = dial_scale_for(GK_OIL, imperial);
    gauge_view_t shv = dial_held_view(d, 0, v, &sv), sho = dial_held_view(d, 1, o, &so);

    ring_value(d, l, 0, v, RO_IN, RO_OUT, COL_GREEN0, COL_GREEN1, 1);
    ring_value(d, l, 1, o, RI_IN, RI_OUT, COL_ORNG0, COL_ORNG1, 0);

    char t[10];
    if (v->valid) dial_format(t, shv.value, 1); else strcpy(t, "--");
    number_unit(l, &FONT_MED, t, &FONT_SMALL, v->valid ? "V" : "", 120, 122, (v->valid && v->warn) ? COL_RED : COL_WHITE, COL_LABEL);
    if (o->kind == GK_OIL) {
        if (o->valid) dial_format(t, sho.value, 0); else strcpy(t, "--");
        number_unit(l, &FONT_MED, t, &FONT_SMALL, o->valid ? (o->unit[0] == 'K' ? "kPa" : "PSI") : "", 120, 178,
                    (o->valid && o->warn) ? COL_RED : COL_WHITE, COL_LABEL);
    }
}

void dial_carplay_set_view(dial_t *d, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *p = &view->primary, *sec = &view->secondary;
    bool rebuild = !d->built || d->theme != THEME_CARPLAY || d->kind != p->kind || d->imperial != imperial ||
                   d->secondary_kind != sec->kind;
    if (rebuild) {
        build_static(d, view, imperial);
        d->built = true;
        d->theme = THEME_CARPLAY;
        d->kind = p->kind;
        d->secondary_kind = sec->kind;
        d->imperial = imperial;
        d->n_total = d->n_static;
        d->held_ok[0] = d->held_ok[1] = false;
        dial_mark_all(d);
    }

    static op_t fresh[DYN_MAX];
    olist_t l = { fresh, 0, DYN_MAX };
    if (p->kind == GK_BATTERY) dyn_rings(d, &l, view, imperial);
    else dyn_ring_gauge(d, &l, view, imperial);
    dial_apply_dynamic(d, fresh, l.n, rebuild);
}
