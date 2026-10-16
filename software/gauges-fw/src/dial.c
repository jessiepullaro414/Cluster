#include "dial_internal.h"

#include <math.h>
#include <string.h>

/* ---- geometry (pixels) and colours: placeholder styling ---- */
#define CX 120.0f
#define CY 120.0f
#define R_TRACK_IN  106.0f
#define R_TRACK_OUT 112.0f
#define R_TICK_OUT  100.0f
#define R_TICK_MAJ   92.0f
#define R_TICK_MIN   95.0f
#define R_LABEL      70.0f
#define NEEDLE_LEN   94.0f
#define NEEDLE_TAIL  10.0f
#define START_DEG   135.0f
#define SWEEP_DEG   270.0f

#define COL_TRACK   0x2A2F36u
#define COL_ZONE    0xD03030u
#define COL_TICK    0xB8BEC6u
#define COL_LABEL   0xB8BEC6u
#define COL_NEEDLE  0xFF8A00u
#define COL_HUB     0x707780u
#define COL_DIGIT   0xFFFFFFu
#define COL_WARN    0xFF3030u
#define COL_UNIT    0x8A95A3u
#define COL_SEC     0xD0D6DEu

/* ---------------------------------------------------------------- formatting */

void dial_format(char *buf, float value, int decimals)
{
    int scale = decimals == 1 ? 10 : (decimals == 2 ? 100 : 1);
    long n = lroundf(value * (float)scale);
    bool neg = n < 0;
    if (neg) n = -n;
    char tmp[8];
    int k = 0;
    do { tmp[k++] = (char)('0' + n % 10); n /= 10; } while (n > 0 && k < 6);
    if (decimals > 0) {
        while (k <= decimals && k < 6) tmp[k++] = '0';
    }
    int o = 0;
    if (neg) buf[o++] = '-';
    while (k > 0) {
        k--;
        if (decimals > 0 && k == decimals - 1) buf[o++] = '.';
        buf[o++] = tmp[k];
    }
    buf[o] = 0;
}

/* ---------------------------------------------------------------- scales */

typedef struct {
    float min, max;                 /* in display units, matching the needle fraction */
    float major[8];                 /* values of the labelled majors */
    const char *label[8];           /* NULL: print the number */
    int n_major;
    int minor_per;                  /* subdivisions between majors */
    float zone_lo[2], zone_hi[2];   /* red zones as scale fractions; lo == hi: unused */
} scale_t;

static const scale_t *scale_for(gauge_kind_t k, bool imperial)
{
    static const scale_t SPEED_MPH = { 0, 120, { 0, 20, 40, 60, 80, 100, 120 }, {0}, 7, 2, {0}, {0} };
    static const scale_t SPEED_KPH = { 0, 200, { 0, 40, 80, 120, 160, 200 }, {0}, 6, 4, {0}, {0} };
    static const scale_t RPM = { 0, 7000, { 0, 1000, 2000, 3000, 4000, 5000, 6000, 7000 },
                                 { "0", "1", "2", "3", "4", "5", "6", "7" }, 8, 2, { 6.0f / 7.0f }, { 1.0f } };
    static const scale_t FUEL = { 0, 100, { 0, 50, 100 }, { "E", "1/2", "F" }, 3, 2, { 0.0f }, { 0.10f } };
    static const scale_t COOL_C = { 40, 130, { 40, 70, 100, 130 }, {0}, 4, 3, { (110.0f - 40.0f) / 90.0f }, { 1.0f } };
    static const scale_t COOL_F = { 104, 266, { 140, 180, 220, 260 }, {0}, 4, 4, { (230.0f - 104.0f) / 162.0f }, { 1.0f } };
    static const scale_t OIL_K = { 0, 700, { 0, 200, 400, 600 }, {0}, 4, 2, {0}, {0} };
    static const scale_t OIL_P = { 0, 101.526f, { 0, 25, 50, 75, 100 }, {0}, 5, 5, {0}, {0} };
    static const scale_t BATT = { 10, 16, { 10, 12, 14, 16 }, {0}, 4, 2, { 0.0f, 5.0f / 6.0f }, { 0.25f, 1.0f } };
    switch (k) {
    case GK_SPEED:   return imperial ? &SPEED_MPH : &SPEED_KPH;
    case GK_RPM:     return &RPM;
    case GK_FUEL:    return &FUEL;
    case GK_COOLANT: return imperial ? &COOL_F : &COOL_C;
    case GK_OIL:     return imperial ? &OIL_P : &OIL_K;
    case GK_BATTERY: return &BATT;
    default:         return 0;
    }
}

static float frac_angle(float f) { return START_DEG + SWEEP_DEG * f; }

static void polar(float r, float deg, float *x, float *y)
{
    float a = deg * 0.017453292519943295f;
    *x = CX + r * cosf(a);
    *y = CY + r * sinf(a);
}

/* ---------------------------------------------------------------- op list */

typedef struct { op_t *ops; int n; } list_t;

static bool g_overflow;
bool dial_overflowed(void) { return g_overflow; }
void dial_note_overflow(void) { g_overflow = true; }

static void push(list_t *l, op_t o)
{
    if (l->n < DIAL_MAX_OPS) l->ops[l->n++] = o;
    else g_overflow = true;
}

static int text_width(const char *s, int scale) { return (int)strlen(s) * GFX_GLYPH_ADV * scale - scale; }

/* Glyph text with its centre at (cx, cy). */
static void push_text(list_t *l, const char *s, float cx, float cy, int scale, uint32_t color)
{
    int w = text_width(s, scale);
    int x = (int)lroundf(cx) - w / 2, y = (int)lroundf(cy) - (GFX_GLYPH_H * scale) / 2;
    for (; *s; s++) {
        push(l, gfx_glyph(x, y, *s, scale, color));
        x += GFX_GLYPH_ADV * scale;
    }
}

static const char *unit_text(const gauge_view_t *g) { return g->unit; }

static void build_static(dial_t *d, const screen_view_t *view, bool imperial)
{
    list_t l = { d->ops, 0 };
    const gauge_view_t *g = &view->primary;
    const scale_t *s = scale_for(g->kind, imperial);

    /* track and red zones */
    push(&l, gfx_arc(CX, CY, R_TRACK_IN, R_TRACK_OUT, START_DEG, START_DEG + SWEEP_DEG, COL_TRACK));
    if (s) {
        for (int z = 0; z < 2; z++) {
            if (s->zone_hi[z] > s->zone_lo[z])
                push(&l, gfx_arc(CX, CY, R_TRACK_IN, R_TRACK_OUT, frac_angle(s->zone_lo[z]),
                                 frac_angle(s->zone_hi[z]), COL_ZONE));
        }

        /* ticks and labels */
        float span = s->max - s->min;
        for (int m = 0; m < s->n_major; m++) {
            float f = (s->major[m] - s->min) / span, deg = frac_angle(f);
            float x0, y0, x1, y1;
            polar(R_TICK_OUT, deg, &x0, &y0);  polar(R_TICK_MAJ, deg, &x1, &y1);
            push(&l, gfx_capsule(x0, y0, x1, y1, 2.6f, COL_TICK));
            char buf[8];
            const char *txt = s->label[m];
            if (!txt) { dial_format(buf, s->major[m], 0); txt = buf; }
            float lx, ly;
            polar(R_LABEL, deg, &lx, &ly);
            push_text(&l, txt, lx, ly, 2, COL_LABEL);
            if (m + 1 < s->n_major && s->minor_per > 1) {
                for (int k = 1; k < s->minor_per; k++) {
                    float fm = f + ((s->major[m + 1] - s->major[m]) / span) * (float)k / (float)s->minor_per;
                    polar(R_TICK_OUT, frac_angle(fm), &x0, &y0);
                    polar(R_TICK_MIN, frac_angle(fm), &x1, &y1);
                    push(&l, gfx_capsule(x0, y0, x1, y1, 1.6f, COL_TICK));
                }
            }
        }
    }

    /* unit label under the digits */
    push_text(&l, unit_text(g), CX, 213.0f, 2, COL_UNIT);
    d->n_static = (uint8_t)l.n;
}

/* ---- big seven-segment digits ---- */

#define SEG_A 1
#define SEG_B 2
#define SEG_C 4
#define SEG_D 8
#define SEG_E 16
#define SEG_F 32
#define SEG_G 64
static const uint8_t SEGS[10] = {
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F,          /* 0 */
    SEG_B | SEG_C,                                          /* 1 */
    SEG_A | SEG_B | SEG_D | SEG_E | SEG_G,                  /* 2 */
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_G,                  /* 3 */
    SEG_B | SEG_C | SEG_F | SEG_G,                          /* 4 */
    SEG_A | SEG_C | SEG_D | SEG_F | SEG_G,                  /* 5 */
    SEG_A | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G,          /* 6 */
    SEG_A | SEG_B | SEG_C,                                  /* 7 */
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G,  /* 8 */
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_F | SEG_G,          /* 9 */
};

#define DIGIT_H   38.0f
#define DIGIT_T    5.0f
#define DIGIT_TOP 154.0f

static float digit_w(char c, float W) { return c == '.' ? 7.0f : W; }

static void push_digit(list_t *l, char c, float x, float W, uint32_t color)
{
    const float r = DIGIT_T * 0.5f, g = 1.6f;
    float y = DIGIT_TOP;
    float L = x + r, R = x + W - r, T = y + r, B = y + DIGIT_H - r, M = y + DIGIT_H * 0.5f;
    if (c == '.') { push(l, gfx_disc(x + 3.0f, B, 2.6f, color)); return; }
    if (c == '-') { push(l, gfx_capsule(L + g, M, R - g, M, DIGIT_T, color)); return; }
    if (c < '0' || c > '9') return;
    uint8_t s = SEGS[c - '0'];
    if (s & SEG_A) push(l, gfx_capsule(L + g, T, R - g, T, DIGIT_T, color));
    if (s & SEG_B) push(l, gfx_capsule(R, T + g, R, M - g, DIGIT_T, color));
    if (s & SEG_C) push(l, gfx_capsule(R, M + g, R, B - g, DIGIT_T, color));
    if (s & SEG_D) push(l, gfx_capsule(L + g, B, R - g, B, DIGIT_T, color));
    if (s & SEG_E) push(l, gfx_capsule(L, M + g, L, B - g, DIGIT_T, color));
    if (s & SEG_F) push(l, gfx_capsule(L, T + g, L, M - g, DIGIT_T, color));
    if (s & SEG_G) push(l, gfx_capsule(L + g, M, R - g, M, DIGIT_T, color));
}

/* Horizontal extent of the big text, centred on x = 120. */
static void big_extent(const char *s, float *x0, float *x1, float *W)
{
    int n = (int)strlen(s);
    *W = n >= 4 ? 16.0f : (n == 3 ? 20.0f : 24.0f);          /* keeps clear of the scale labels at the lower ends */
    const float gap = n >= 4 ? 4.0f : 5.0f;
    float w = 0.0f;
    for (int i = 0; i < n; i++) w += digit_w(s[i], *W) + (i ? gap : 0.0f);
    *x0 = CX - w * 0.5f;
    *x1 = *x0 + w;
}

static void push_big(list_t *l, const char *s, uint32_t color)
{
    float x0, x1, W;
    big_extent(s, &x0, &x1, &W);
    float x = x0;
    const float gap = strlen(s) >= 4 ? 4.0f : 5.0f;
    for (int i = 0; s[i]; i++) {
        push_digit(l, s[i], x, W, color);
        x += digit_w(s[i], W) + gap;
    }
}

/* ---------------------------------------------------------------- tile marking */

#define mark_rect dial_mark_rect

static void mark_tile(dial_t *d, int tx, int ty)
{
    if (tx < 0 || ty < 0 || tx >= GFX_TILES || ty >= GFX_TILES) return;
    /* tiles wholly outside the round panel are never drawn */
    int x0 = tx * GFX_TILE, y0 = ty * GFX_TILE;
    float nx = (float)(CX < x0 ? x0 : (CX > x0 + GFX_TILE ? x0 + GFX_TILE : CX));
    float ny = (float)(CY < y0 ? y0 : (CY > y0 + GFX_TILE ? y0 + GFX_TILE : CY));
    float dx = nx - CX, dy = ny - CY;
    if (dx * dx + dy * dy > 121.0f * 121.0f) return;
    d->dirty[ty] |= (uint32_t)(1u << tx);
}

void dial_mark_rect(dial_t *d, int x0, int y0, int x1, int y1)         /* pixels, x1/y1 exclusive */
{
    if (x1 <= x0 || y1 <= y0) return;
    int tx0 = x0 < 0 ? 0 : x0 / GFX_TILE, ty0 = y0 < 0 ? 0 : y0 / GFX_TILE;
    int tx1 = (x1 - 1) / GFX_TILE, ty1 = (y1 - 1) / GFX_TILE;
    for (int ty = ty0; ty <= ty1 && ty < GFX_TILES; ty++)
        for (int tx = tx0; tx <= tx1 && tx < GFX_TILES; tx++)
            mark_tile(d, tx, ty);
}

static void needle_endpoints(int deg, float *tx_, float *ty_, float *hx, float *hy)
{
    float a = (float)deg * 0.017453292519943295f;
    *tx_ = CX + NEEDLE_LEN * cosf(a);  *ty_ = CY + NEEDLE_LEN * sinf(a);
    *hx = CX - NEEDLE_TAIL * cosf(a);  *hy = CY - NEEDLE_TAIL * sinf(a);
}

/* Tiles under a needle at the given angle (thickness 4 plus a margin). */
static void mark_needle(dial_t *d, int deg)
{
    float tx_, ty_, hx, hy;
    needle_endpoints(deg, &tx_, &ty_, &hx, &hy);
    float len = sqrtf((tx_ - hx) * (tx_ - hx) + (ty_ - hy) * (ty_ - hy));
    int steps = (int)(len / 2.0f) + 1;           /* a sample every 2 px so no stretch of the line is missed */
    for (int i = 0; i <= steps; i++) {
        float t = (float)i / (float)steps;
        int x = (int)lroundf(hx + (tx_ - hx) * t), y = (int)lroundf(hy + (ty_ - hy) * t);
        mark_rect(d, x - 3, y - 3, x + 4, y + 4);   /* half thickness 2 plus anti-aliasing */
    }
}

static void mark_text_box(dial_t *d, const char *s, bool big)
{
    if (!s[0]) return;
    if (big) {
        float x0, x1, W;
        big_extent(s, &x0, &x1, &W);
        mark_rect(d, (int)x0 - 2, (int)DIGIT_TOP - 2, (int)x1 + 3, (int)(DIGIT_TOP + DIGIT_H) + 3);
    } else {
        int w = text_width(s, 2);
        mark_rect(d, 120 - w / 2 - 2, 130, 120 + w / 2 + 3, 130 + 14 + 3);
    }
}

/* Only the characters that changed: a ones digit that ticks over is a small box, not the
 * whole number. If the length differs the layout shifts, so both boxes are redrawn whole. */
static void mark_big_diff(dial_t *d, const char *old, const char *neu, bool force_all)
{
    if (force_all || strlen(old) != strlen(neu)) {
        mark_text_box(d, old, true);
        mark_text_box(d, neu, true);
        return;
    }
    float x0, x1, W;
    big_extent(neu, &x0, &x1, &W);
    const float gap = strlen(neu) >= 4 ? 4.0f : 5.0f;
    float x = x0;
    for (int i = 0; neu[i]; i++) {
        float w = digit_w(neu[i], W);
        if (old[i] != neu[i])
            mark_rect(d, (int)x - 2, (int)DIGIT_TOP - 2, (int)(x + w) + 3, (int)(DIGIT_TOP + DIGIT_H) + 3);
        x += w + gap;
    }
}

static void mark_sec_diff(dial_t *d, const char *old, const char *neu, bool force_all)
{
    if (force_all || strlen(old) != strlen(neu)) {
        mark_text_box(d, old, false);
        mark_text_box(d, neu, false);
        return;
    }
    int x = 120 - text_width(neu, 2) / 2;
    for (int i = 0; neu[i]; i++, x += GFX_GLYPH_ADV * 2)
        if (old[i] != neu[i]) mark_rect(d, x - 1, 130, x + GFX_GLYPH_W * 2 + 1, 130 + 14 + 3);
}

/* ---------------------------------------------------------------- public */

void dial_init(dial_t *d)
{
    memset(d, 0, sizeof *d);
}

void dial_mark_all(dial_t *d)
{
    for (int ty = 0; ty < GFX_TILES; ty++)
        for (int tx = 0; tx < GFX_TILES; tx++)
            mark_tile(d, tx, ty);
}

static int needle_deg_for(const gauge_view_t *g)
{
    return (int)lroundf(START_DEG + SWEEP_DEG * g->needle);
}

static void classic_set_view(dial_t *d, const screen_view_t *view, bool imperial)
{
    const gauge_view_t *p = &view->primary, *sec = &view->secondary;

    bool rebuild_static = !d->built || d->theme != THEME_CLASSIC || d->kind != p->kind || d->imperial != imperial ||
                          d->secondary_kind != sec->kind;
    if (rebuild_static) {
        build_static(d, view, imperial);
        d->built = true;
        d->theme = THEME_CLASSIC;
        d->kind = p->kind;
        d->secondary_kind = sec->kind;
        d->imperial = imperial;
        d->needle_shown = false;  d->needle_deg = 0;  d->needle_warn = false;
        d->big[0] = 0;  d->sec[0] = 0;
        dial_mark_all(d);
    }

    /* new dynamic state */
    char big[8], secs[10];
    bool needle = p->valid;
    int deg = needle ? needle_deg_for(p) : 0;
    if (p->valid) dial_format(big, p->value, p->kind == GK_BATTERY ? 1 : 0);
    else { big[0] = '-'; big[1] = '-'; big[2] = 0; }
    secs[0] = 0;
    if (sec->kind != GK_NONE) {
        if (sec->valid) {
            char num[8];
            dial_format(num, sec->value, sec->kind == GK_BATTERY ? 1 : 0);
            size_t n = strlen(num);
            memcpy(secs, num, n);
            const char *u = sec->unit;
            size_t k = 0;
            if (u[0] && sec->kind != GK_BATTERY && sec->kind != GK_FUEL) secs[n++] = ' ';
            while (u[k] && n < sizeof secs - 1) secs[n++] = u[k++];
            secs[n] = 0;
        } else {
            secs[0] = '-'; secs[1] = '-'; secs[2] = 0;
        }
    }
    bool nwarn = p->valid && p->warn, bwarn = nwarn, swarn = sec->valid && sec->warn;

    bool changed = false;
    if (needle != d->needle_shown || (needle && (deg != d->needle_deg || nwarn != d->needle_warn))) {
        if (d->needle_shown) mark_needle(d, d->needle_deg);
        if (needle) mark_needle(d, deg);
        changed = true;
    }
    if (strcmp(big, d->big) != 0 || bwarn != d->big_warn) {
        mark_big_diff(d, d->big, big, bwarn != d->big_warn);
        changed = true;
    }
    if (strcmp(secs, d->sec) != 0 || swarn != d->sec_warn) {
        mark_sec_diff(d, d->sec, secs, swarn != d->sec_warn);
        changed = true;
    }
    if (!changed && !rebuild_static) return;

    d->needle_shown = needle;  d->needle_deg = (int16_t)deg;  d->needle_warn = nwarn;
    strcpy(d->big, big);  d->big_warn = bwarn;
    strcpy(d->sec, secs);  d->sec_warn = swarn;

    /* rebuild the dynamic part of the list: needle, hub, digits, secondary */
    list_t l = { d->ops, d->n_static };
    if (needle) {
        float tx_, ty_, hx, hy;
        needle_endpoints(deg, &tx_, &ty_, &hx, &hy);
        push(&l, gfx_capsule(hx, hy, tx_, ty_, 4.0f, nwarn ? COL_WARN : COL_NEEDLE));
    }
    push(&l, gfx_disc(CX, CY, 7.0f, COL_HUB));
    push_big(&l, big, bwarn ? COL_WARN : COL_DIGIT);
    if (secs[0]) push_text(&l, secs, CX, 137.0f, 2, swarn ? COL_WARN : COL_SEC);
    d->n_total = (uint8_t)l.n;
}

void dial_set_text_hold(dial_t *d, uint8_t ticks) { d->hold_ticks = ticks; }

void dial_set_view_theme(dial_t *d, const screen_view_t *view, bool imperial, theme_t theme)
{
    if (theme == THEME_MODERN) dial_modern_set_view(d, view, imperial);
    else classic_set_view(d, view, imperial);
}

void dial_set_view(dial_t *d, const screen_view_t *view, bool imperial)
{
    classic_set_view(d, view, imperial);
}

bool dial_next_run(dial_t *d, int *tile_row, int *first_col, int *n_cols)
{
    for (int ty = 0; ty < GFX_TILES; ty++) {
        uint32_t row = d->dirty[ty];
        if (!row) continue;
        int tx = 0;
        while (!((row >> tx) & 1u)) tx++;
        int n = 0;
        while (tx + n < GFX_TILES && ((row >> (tx + n)) & 1u)) n++;
        d->dirty[ty] &= ~(((1u << n) - 1u) << tx);
        *tile_row = ty;  *first_col = tx;  *n_cols = n;
        return true;
    }
    return false;
}

void dial_render_run(const dial_t *d, int tile_row, int first_col, int n_cols, uint16_t *out)
{
    gfx_render(d->ops, d->n_total, first_col * GFX_TILE, tile_row * GFX_TILE,
               n_cols * GFX_TILE, GFX_TILE, out, n_cols * GFX_TILE);
}

int dial_dirty_tiles(const dial_t *d)
{
    int n = 0;
    for (int ty = 0; ty < GFX_TILES; ty++)
        for (int tx = 0; tx < GFX_TILES; tx++)
            n += (d->dirty[ty] >> tx) & 1;
    return n;
}
