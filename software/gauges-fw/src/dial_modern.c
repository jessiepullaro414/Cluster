/*
 * The "modern" theme: dark navy face, thick progress arcs that fill with a blue (to red) gradient,
 * proportional anti-aliased digits, small icons, and horizontal bars for volts and oil. Modelled on
 * the reference picture of the four small gauges the owner supplied (2026-10-16).
 *
 * Three kinds of screen, chosen by the primary gauge of the layout (screens_layout(THEME_MODERN)):
 *   speed, rpm, coolant   a 270 degree arc with a big value inside
 *   battery (+ oil)       two horizontal bars with their values
 * Placeholder styling: tune colours, sizes and positions together with the owner.
 */
#include <math.h>
#include <string.h>

#include "dial_internal.h"
#include "font.h"

#define CX DIAL_CX
#define CY DIAL_CY
#define START_DEG 135.0f
#define SWEEP_DEG 270.0f

#define R_ARC_OUT   104.0f
#define R_ARC_IN     93.0f
#define R_ARC_MID    ((R_ARC_OUT + R_ARC_IN) * 0.5f)
#define R_TICK_IN   108.0f
#define R_LABEL      78.0f

#define COL_BG      0x0B1626u
#define COL_TRACK   0x15233Au
#define COL_REDDIM  0x4A1A26u
#define COL_BLUE0   0x1A4FD8u
#define COL_BLUE1   0x3DB6FFu
#define COL_RED     0xE8364Au
#define COL_BAR     0x2B7BFFu
#define COL_WHITE   0xF4F7FFu
#define COL_LABEL   0xC9D6EEu
#define COL_MINOR   0x7F93B8u
#define COL_MAJOR   0xDCE6FAu
#define COL_WARN    0xFF4A4Au
#define COL_ICON    0xE6EEFFu

/* ---------------------------------------------------------------- lists */

typedef struct { op_t *ops; int n, max; } olist_t;

static void add(olist_t *l, op_t o)
{
    if (l->n < l->max) l->ops[l->n++] = o;
    else dial_note_overflow();
}

static void add_text(olist_t *l, const font_t *f, const char *s, int x, int baseline, text_align_t a, uint32_t color)
{
    op_t tmp[16];
    int n = gfx_text(tmp, 16, f, s, x, baseline, a, color);
    for (int i = 0; i < n; i++) add(l, tmp[i]);
}

static void polar(float r, float deg, float *x, float *y)
{
    float a = deg * 0.017453292519943295f;
    *x = CX + r * cosf(a);
    *y = CY + r * sinf(a);
}

/* ---------------------------------------------------------------- scales */

typedef struct {
    float min, max;                 /* in the units of the displayed value */
    float label_step, major_step, minor_step;
    float red_from;                 /* value where the red zone starts, or a number above max for none */
    bool  thousands;                /* the value is shown divided by 1000 (rpm) */
} mscale_t;

static mscale_t scale_for(gauge_kind_t k, bool imperial)
{
    switch (k) {
    case GK_SPEED:   return imperial ? (mscale_t){ 0, 160, 20, 20, 10, 1e9f, false }
                                     : (mscale_t){ 0, 260, 40, 20, 10, 1e9f, false };
    case GK_RPM:     return (mscale_t){ 0, 8000, 1000, 1000, 500, 6000, true };
    case GK_COOLANT: return imperial ? (mscale_t){ 104, 266, 0, 0, 0, 1e9f, false }
                                     : (mscale_t){ 40, 130, 0, 0, 0, 1e9f, false };
    case GK_BATTERY: return (mscale_t){ 10, 16, 0, 0, 0, 1e9f, false };
    case GK_OIL:     return imperial ? (mscale_t){ 0, 101.5f, 0, 0, 0, 1e9f, false }
                                     : (mscale_t){ 0, 700, 0, 0, 0, 1e9f, false };
    default:         return (mscale_t){ 0, 1, 0, 0, 0, 1e9f, false };
    }
}

/* Numbers are refreshed at most every hold_ticks calls (the arc and bars use the live value). */
static gauge_view_t held_view(dial_t *d, int idx, const gauge_view_t *g, const mscale_t *s)
{
    gauge_view_t out = *g;
    if (d->hold_ticks == 0 || !g->valid) { d->held_ok[idx] = false; d->age[idx] = 0; return out; }
    float jump = fabsf(g->value - d->held[idx]);
    if (!d->held_ok[idx] || d->age[idx] >= d->hold_ticks || jump > 0.15f * (s->max - s->min) || g->warn) {
        d->held[idx] = g->value;
        d->held_ok[idx] = true;
        d->age[idx] = 0;
    } else {
        d->age[idx]++;
        out.value = d->held[idx];
    }
    return out;
}

static float clamp01(float v) { return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v); }

static float fraction(const mscale_t *s, float v) { return clamp01((v - s->min) / (s->max - s->min)); }

/* ---------------------------------------------------------------- icons (small, built from primitives) */

static void icon_fuel(olist_t *l, float x, float y, uint32_t c)
{
    add(l, gfx_rrect(x - 2, y + 1, 10, 15, 2.0f, 0.0f, c));                 /* pump body */
    add(l, gfx_rrect(x - 2, y - 2, 6, 5, 1.0f, 0.0f, COL_BG));              /* window */
    add(l, gfx_capsule(x + 3.5f, y - 5, x + 8.5f, y - 5, 2.0f, c));         /* hose */
    add(l, gfx_capsule(x + 8.5f, y - 5, x + 8.5f, y + 4, 2.0f, c));
    add(l, gfx_capsule(x - 7, y + 9, x + 3, y + 9, 2.0f, c));               /* base */
}

static void icon_thermo(olist_t *l, float x, float y, uint32_t c, uint32_t fill)
{
    add(l, gfx_capsule(x, y - 6, x, y + 3, 6.0f, c));                       /* stem */
    add(l, gfx_disc(x, y + 6, 5.2f, c));                                    /* bulb */
    add(l, gfx_capsule(x, y - 5, x, y + 3, 2.4f, COL_BG));
    add(l, gfx_disc(x, y + 6, 2.6f, fill));
    add(l, gfx_capsule(x, y - 1, x, y + 4, 2.0f, fill));
}

static void icon_battery(olist_t *l, float x, float y, uint32_t c)
{
    add(l, gfx_rrect(x, y + 1, 19, 11, 2.5f, 1.8f, c));
    add(l, gfx_rrect(x - 5, y - 5, 3.5f, 2.5f, 0.5f, 0.0f, c));             /* terminals */
    add(l, gfx_rrect(x + 5, y - 5, 3.5f, 2.5f, 0.5f, 0.0f, c));
}

static void icon_oil(olist_t *l, float x, float y, uint32_t c)
{
    add(l, gfx_rrect(x, y + 3, 14, 8, 2.0f, 0.0f, c));                      /* can */
    add(l, gfx_capsule(x + 6, y, x + 12, y - 5, 2.4f, c));                  /* spout */
    add(l, gfx_capsule(x - 7, y + 1, x - 3, y - 2, 2.0f, c));               /* handle */
    add(l, gfx_disc(x + 11.0f, y + 2.5f, 1.6f, c));                         /* drop */
}

/* ---------------------------------------------------------------- static parts */

static const char *label_unit(const gauge_view_t *g)
{
    return g->unit;
}

static void static_arc(olist_t *l, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *g = &view->primary;
    mscale_t s = scale_for(g->kind, imperial);
    float xa, ya, xb, yb;
    polar(R_ARC_MID, START_DEG, &xa, &ya);
    polar(R_ARC_MID, START_DEG + SWEEP_DEG, &xb, &yb);

    add(l, gfx_arc(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG, START_DEG + SWEEP_DEG, COL_TRACK));
    add(l, gfx_disc(xa, ya, (R_ARC_OUT - R_ARC_IN) * 0.5f, COL_TRACK));
    if (s.red_from < s.max) {
        float f = fraction(&s, s.red_from);
        add(l, gfx_arc(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG + SWEEP_DEG * f, START_DEG + SWEEP_DEG, COL_REDDIM));
        add(l, gfx_disc(xb, yb, (R_ARC_OUT - R_ARC_IN) * 0.5f, COL_REDDIM));
    } else {
        add(l, gfx_disc(xb, yb, (R_ARC_OUT - R_ARC_IN) * 0.5f, COL_TRACK));
    }

    if (s.major_step > 0) {
        float span = s.max - s.min;
        if (s.minor_step > 0)
            add(l, gfx_ticks(CX, CY, R_TICK_IN, R_TICK_IN + 4.0f, START_DEG, SWEEP_DEG, SWEEP_DEG * s.minor_step / span, 1.3f, COL_MINOR));
        add(l, gfx_ticks(CX, CY, R_TICK_IN, R_TICK_IN + 8.0f, START_DEG, SWEEP_DEG, SWEEP_DEG * s.major_step / span, 2.2f, COL_MAJOR));
        if (s.label_step > 0) {
            for (float v = s.min; v <= s.max + 0.01f; v += s.label_step) {
                char buf[8];
                dial_format(buf, s.thousands ? v / 1000.0f : v, 0);
                float lx, ly;
                polar(R_LABEL, START_DEG + SWEEP_DEG * fraction(&s, v), &lx, &ly);
                add_text(l, &FONT_SMALL, buf, (int)lroundf(lx), (int)lroundf(ly) + 5, TEXT_CENTER, COL_LABEL);
            }
        }
    }

    switch (g->kind) {
    case GK_SPEED:
        add_text(l, &FONT_SMALL, label_unit(g), 120, 164, TEXT_CENTER, COL_WHITE);
        icon_fuel(l, 84, 192, COL_ICON);
        break;
    case GK_RPM:
        add_text(l, &FONT_SMALL, "RPM", 120, 88, TEXT_CENTER, COL_WHITE);
        add_text(l, &FONT_SMALL, "x1000", 120, 166, TEXT_CENTER, COL_LABEL);
        icon_thermo(l, 84, 188, COL_ICON, COL_BLUE1);
        break;
    case GK_COOLANT:
        icon_thermo(l, 120, 58, COL_ICON, COL_BLUE1);
        add_text(l, &FONT_SMALL, "COOLANT", 120, 100, TEXT_CENTER, COL_WHITE);
        add_text(l, &FONT_SMALL, "C", 62, 192, TEXT_CENTER, COL_WHITE);
        add_text(l, &FONT_SMALL, "H", 178, 192, TEXT_CENTER, COL_WHITE);
        break;
    default:
        break;
    }
}

static void bar_label(olist_t *l, float y, const char *label, const char *unit)
{
    char buf[16];
    size_t n = strlen(label);
    memcpy(buf, label, n);
    if (unit && unit[0]) { buf[n++] = ' '; strcpy(buf + n, unit); } else buf[n] = 0;
    add_text(l, &FONT_SMALL, buf, 76, (int)y, TEXT_LEFT, COL_WHITE);
}

#define BAR_X0  46.0f
#define BAR_X1  128.0f
#define BAR_H   13.0f
#define BAR1_Y  100.0f
#define BAR2_Y  172.0f

static void static_bars(olist_t *l, const screen_view_t *view)
{
    icon_battery(l, 56, 74, COL_ICON);
    bar_label(l, 78, "VOLTS", "");
    add(l, gfx_rrect((BAR_X0 + BAR_X1) * 0.5f, BAR1_Y, BAR_X1 - BAR_X0, BAR_H, BAR_H * 0.5f, 0.0f, COL_TRACK));

    icon_oil(l, 52, 148, COL_ICON);
    bar_label(l, 154, "OIL", view->secondary.unit);
    add(l, gfx_rrect((BAR_X0 + BAR_X1) * 0.5f, BAR2_Y, BAR_X1 - BAR_X0, BAR_H, BAR_H * 0.5f, 0.0f, COL_TRACK));
}

static void build_static(dial_t *d, const screen_view_t *view, bool imperial)
{
    olist_t l = { d->ops, 0, DIAL_MAX_OPS };
    add(&l, gfx_disc(CX, CY, 119.5f, COL_BG));
    if (view->primary.kind == GK_BATTERY) static_bars(&l, view);
    else static_arc(&l, view, imperial);
    d->n_static = (uint8_t)l.n;
}

/* ---------------------------------------------------------------- dynamic parts */

#define DYN_MAX 40

static void value_text(char *out, const gauge_view_t *g, const mscale_t *s)
{
    if (!g->valid) { strcpy(out, "--"); return; }
    if (s->thousands) dial_format(out, g->value / 1000.0f, 1);
    else dial_format(out, g->value, g->kind == GK_BATTERY ? 1 : 0);
}

static void dyn_arc(dial_t *d, olist_t *l, const screen_view_t *view, bool imperial)
{
    mscale_t s = scale_for(view->primary.kind, imperial);
    const gauge_view_t *g = &view->primary;
    gauge_view_t shown = held_view(d, 0, g, &s);       /* the numbers; the arc below uses g */
    float frac = g->valid ? fraction(&s, g->value) : 0.0f;
    float vis = floorf(SWEEP_DEG * frac + 0.5f);              /* whole degrees: a smaller move would only redraw the same pixels */
    uint32_t endcol = COL_BLUE1;

    if (g->valid && vis > 0.0f) {
        const float cap = (R_ARC_OUT - R_ARC_IN) * 0.5f;
        float xa, ya, xe, ye;
        polar(R_ARC_MID, START_DEG, &xa, &ya);
        polar(R_ARC_MID, START_DEG + vis, &xe, &ye);
        if (g->kind == GK_RPM) {
            /* blue up to the red line, red beyond it (a hard change, like the reference) */
            float f_red = fraction(&s, s.red_from);
            float blue_vis = floorf(fminf(frac, f_red) * SWEEP_DEG + 0.5f);
            add(l, gfx_arc_gradient(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG, SWEEP_DEG, blue_vis, COL_BLUE0, COL_BLUE1));
            add(l, gfx_disc(xa, ya, cap, COL_BLUE0));
            endcol = gfx_lerp_color(COL_BLUE0, COL_BLUE1, f_red > 0 ? fminf(frac, f_red) / f_red : 0.0f);
            if (frac > f_red) {
                add(l, gfx_arc_gradient(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG + SWEEP_DEG * f_red, SWEEP_DEG, vis - SWEEP_DEG * f_red,
                                        COL_RED, COL_RED));
                endcol = COL_RED;
            }
        } else if (g->kind == GK_COOLANT) {
            add(l, gfx_arc_gradient(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG, SWEEP_DEG, vis, COL_BLUE0, COL_RED));
            add(l, gfx_disc(xa, ya, cap, COL_BLUE0));
            endcol = gfx_lerp_color(COL_BLUE0, COL_RED, frac);
        } else {
            add(l, gfx_arc_gradient(CX, CY, R_ARC_IN, R_ARC_OUT, START_DEG, SWEEP_DEG, vis, COL_BLUE0, COL_BLUE1));
            add(l, gfx_disc(xa, ya, cap, COL_BLUE0));
            endcol = gfx_lerp_color(COL_BLUE0, COL_BLUE1, frac);
        }
        add(l, gfx_disc(xe, ye, cap, endcol));
    }

    /* the value */
    char txt[12];
    value_text(txt, &shown, &s);
    uint32_t col = (g->valid && g->warn) ? COL_WARN : COL_WHITE;
    switch (g->kind) {
    case GK_SPEED:
        add_text(l, &FONT_BIG, txt, 120, 142, TEXT_CENTER, col);
        break;
    case GK_RPM:
        add_text(l, &FONT_BIG, txt, 120, 144, TEXT_CENTER, col);
        break;
    case GK_COOLANT: {
        add_text(l, &FONT_BIG, txt, 112, 152, TEXT_CENTER, col);
        if (g->valid) {
            int w = gfx_text_width(&FONT_BIG, txt);
            add_text(l, &FONT_SMALL, g->unit[0] == 'F' ? DEG "F" : DEG "C", 112 + w / 2 + 3, 124, TEXT_LEFT, COL_WHITE);
        }
        break;
    }
    default:
        break;
    }

    /* the small line at the bottom: fuel under speed, coolant under rpm */
    const gauge_view_t *sec = &view->secondary;
    if (sec->kind == GK_FUEL || sec->kind == GK_COOLANT) {
        mscale_t s2 = scale_for(sec->kind == GK_FUEL ? GK_BATTERY : GK_COOLANT, imperial);     /* only its span is used */
        gauge_view_t sh2 = held_view(d, 1, sec, &s2);
        char t2[10];
        if (sec->valid) dial_format(t2, sh2.value, 0); else strcpy(t2, "--");
        uint32_t c2 = (sec->valid && sec->warn) ? COL_WARN : COL_WHITE;
        add_text(l, &FONT_MED, t2, 102, 198, TEXT_LEFT, c2);
        if (sec->valid) {
            int w = gfx_text_width(&FONT_MED, t2);
            const char *u = sec->kind == GK_FUEL ? "%" : (sec->unit[0] == 'F' ? DEG "F" : DEG "C");
            add_text(l, &FONT_SMALL, u, 102 + w + 3, 198, TEXT_LEFT, COL_LABEL);
        }
    }
}

static void bar_value(dial_t *d, int idx, olist_t *l, float y_center, const gauge_view_t *g, const mscale_t *s, int decimals,
                      const char *unit, uint32_t c)
{
    gauge_view_t shown = held_view(d, idx, g, s);
    float frac = g->valid ? fraction(s, g->value) : 0.0f;
    if (g->valid && frac > 0.0f) {
        float w = (BAR_X1 - BAR_X0) * frac;
        if (w < BAR_H) w = BAR_H;
        add(l, gfx_rrect(BAR_X0 + w * 0.5f, y_center, w, BAR_H, BAR_H * 0.5f, 0.0f, g->warn ? COL_RED : COL_BAR));
    }
    char t[10];
    if (g->valid) dial_format(t, shown.value, decimals); else strcpy(t, "--");
    add_text(l, &FONT_MED, t, 186, (int)y_center + 9, TEXT_RIGHT, g->valid && g->warn ? COL_WARN : c);
    if (g->valid) add_text(l, &FONT_SMALL, unit, 189, (int)y_center + 9, TEXT_LEFT, COL_LABEL);
}

static void dyn_bars(dial_t *d, olist_t *l, const screen_view_t *view, bool imperial)
{
    mscale_t sb = scale_for(GK_BATTERY, imperial), so = scale_for(GK_OIL, imperial);
    bar_value(d, 0, l, BAR1_Y, &view->primary, &sb, 1, "v", COL_WHITE);
    bar_value(d, 1, l, BAR2_Y, &view->secondary, &so, 0, view->secondary.unit[0] == 'K' ? "kPa" : "PSI", COL_WHITE);
}

/* ---------------------------------------------------------------- change tracking */

static void mark_op(dial_t *d, const op_t *o)
{
    dial_mark_rect(d, o->x0 - 1, o->y0 - 1, o->x1 + 1, o->y1 + 1);
}

/* Tiles under the part of the ring between two sweep fractions. */
static void mark_arc_band(dial_t *d, float from_deg, float to_deg)
{
    if (to_deg < from_deg) { float t = from_deg; from_deg = to_deg; to_deg = t; }
    int steps = (int)((to_deg - from_deg) / 2.0f) + 2;
    for (int i = 0; i <= steps; i++) {
        float a = START_DEG + from_deg + (to_deg - from_deg) * (float)i / (float)steps;
        float x, y;
        polar(R_ARC_MID, a, &x, &y);
        dial_mark_rect(d, (int)x - 9, (int)y - 9, (int)x + 10, (int)y + 10);
    }
}

static const op_t *find_arcg(const op_t *ops, int n, int nth)
{
    for (int i = 0; i < n; i++)
        if (ops[i].kind == OP_ARCG && nth-- == 0) return &ops[i];
    return 0;
}

static float arcg_end_deg(const op_t *o) { return o ? (float)o->u.arcg.clipq * 360.0f / 65536.0f : 0.0f; }

void dial_modern_set_view(dial_t *d, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *p = &view->primary, *sec = &view->secondary;
    bool rebuild = !d->built || d->theme != THEME_MODERN || d->kind != p->kind || d->imperial != imperial ||
                   d->secondary_kind != sec->kind;
    if (rebuild) {
        build_static(d, view, imperial);
        d->built = true;
        d->theme = THEME_MODERN;
        d->kind = p->kind;
        d->secondary_kind = sec->kind;
        d->imperial = imperial;
        d->n_total = d->n_static;
        d->held_ok[0] = d->held_ok[1] = false;
        dial_mark_all(d);
    }

    /* new dynamic list into scratch, old one copied aside, then diffed */
    static op_t fresh[DYN_MAX], old[DYN_MAX];
    olist_t l = { fresh, 0, DYN_MAX };
    if (p->kind == GK_BATTERY) dyn_bars(d, &l, view, imperial);
    else dyn_arc(d, &l, view, imperial);

    int n_old = d->n_total - d->n_static;
    if (n_old > DYN_MAX) n_old = DYN_MAX;
    memcpy(old, &d->ops[d->n_static], (size_t)n_old * sizeof(op_t));

    bool changed = false;
    /* progress arcs: only the band between the old and new end moves */
    for (int k = 0; k < 2; k++) {
        const op_t *a = find_arcg(old, n_old, k), *b = find_arcg(fresh, l.n, k);
        if ((a ? a->u.arcg.clipq : 0u) != (b ? b->u.arcg.clipq : 0u) || (a && b && (a->color != b->color || a->u.arcg.c1 != b->u.arcg.c1))) {
            float lo = a ? (float)a->u.arcg.a0q * 360.0f / 65536.0f : (b ? (float)b->u.arcg.a0q * 360.0f / 65536.0f : START_DEG);
            float s_old = arcg_end_deg(a), s_new = arcg_end_deg(b);
            float base = lo - START_DEG;
            if (base < -1.0f) base += 360.0f;
            mark_arc_band(d, base + (s_old < s_new ? s_old : s_new) - 2.0f, base + (s_old > s_new ? s_old : s_new) + 2.0f);
            changed = true;
        }
    }
    /* everything else: an op that exists on one side only (or differs) is redrawn where it was and where it is */
    for (int i = 0; i < n_old; i++) {
        if (old[i].kind == OP_ARCG) continue;
        bool kept = false;
        for (int j = 0; j < l.n && !kept; j++) kept = fresh[j].kind == old[i].kind && memcmp(&fresh[j], &old[i], sizeof(op_t)) == 0;
        if (!kept) { mark_op(d, &old[i]); changed = true; }
    }
    for (int j = 0; j < l.n; j++) {
        if (fresh[j].kind == OP_ARCG) continue;
        bool kept = false;
        for (int i = 0; i < n_old && !kept; i++) kept = old[i].kind == fresh[j].kind && memcmp(&fresh[j], &old[i], sizeof(op_t)) == 0;
        if (!kept) { mark_op(d, &fresh[j]); changed = true; }
    }
    if (!changed && !rebuild) return;

    if (d->n_static + l.n > DIAL_MAX_OPS) { dial_note_overflow(); l.n = DIAL_MAX_OPS - d->n_static; }
    memcpy(&d->ops[d->n_static], fresh, (size_t)l.n * sizeof(op_t));
    d->n_total = (uint8_t)(d->n_static + l.n);
}
