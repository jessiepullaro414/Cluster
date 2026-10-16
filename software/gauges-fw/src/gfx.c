#include "gfx.h"

#include <math.h>
#include <string.h>

#ifdef GFX_STATS
uint32_t gfx_stat_pixels, gfx_stat_op_evals, gfx_stat_sqrt;
#define STAT(x) (x)
#else
#define STAT(x) ((void)0)
#endif

#define MAX_OPS 255

/* ---------------------------------------------------------------- font */

/* 5x7 glyphs, one byte per row (bit 4 = leftmost). Drawn by hand for this
 * project: digits, and the letters the unit labels and scales need. */
typedef struct { char ch; uint8_t row[7]; } glyph_t;

static const glyph_t FONT[] = {
    { '0', { 0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E } },
    { '1', { 0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E } },
    { '2', { 0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F } },
    { '3', { 0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E } },
    { '4', { 0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02 } },
    { '5', { 0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E } },
    { '6', { 0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E } },
    { '7', { 0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08 } },
    { '8', { 0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E } },
    { '9', { 0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C } },
    { 'A', { 0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11 } },
    { 'C', { 0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E } },
    { 'E', { 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F } },
    { 'F', { 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10 } },
    { 'H', { 0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11 } },
    { 'I', { 0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E } },
    { 'K', { 0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11 } },
    { 'M', { 0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11 } },
    { 'P', { 0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10 } },
    { 'R', { 0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11 } },
    { 'S', { 0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E } },
    { 'V', { 0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04 } },
    { 'X', { 0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11 } },
    { 'B', { 0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E } },
    { 'D', { 0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E } },
    { 'G', { 0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F } },
    { 'J', { 0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C } },
    { 'L', { 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F } },
    { 'N', { 0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11 } },
    { 'O', { 0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E } },
    { 'Q', { 0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D } },
    { 'T', { 0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04 } },
    { 'U', { 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E } },
    { 'W', { 0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A } },
    { 'Y', { 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04 } },
    { 'Z', { 0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F } },
    { ':', { 0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00 } },
    { '+', { 0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00 } },
    { '=', { 0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00 } },
    { '(', { 0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02 } },
    { ')', { 0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08 } },
    { ',', { 0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08 } },
    { '_', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F } },
    { '/', { 0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10 } },
    { '%', { 0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03 } },
    { '-', { 0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00 } },
    { '.', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C } },
    { ' ', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 } },
};

static const uint8_t *glyph_rows(char ch)
{
    if (ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');          /* one case is enough */
    for (unsigned i = 0; i < sizeof FONT / sizeof FONT[0]; i++)
        if (FONT[i].ch == ch) return FONT[i].row;
    return FONT[sizeof FONT / sizeof FONT[0] - 1].row;      /* unknown: blank */
}

/* ---------------------------------------------------------------- math */

uint32_t gfx_isqrt(uint32_t v)
{
    if (v == 0) return 0;
    uint32_t x = 1u << ((32u - (uint32_t)__builtin_clz(v) + 1u) >> 1);   /* upper bound */
    for (;;) {
        uint32_t y = (x + v / x) >> 1;
        if (y >= x) return x;
        x = y;
    }
}

static int16_t q14(float v) { return (int16_t)lroundf(v * 16384.0f); }

static int32_t fl_floor(float v) { return (int32_t)floorf(v); }
static int32_t fl_ceil(float v) { return (int32_t)ceilf(v); }

/* ---------------------------------------------------------------- building */

static void bbox_set(op_t *o, float x0, float y0, float x1, float y1)
{
    o->x0 = (int16_t)fl_floor(x0 - 1.0f);
    o->y0 = (int16_t)fl_floor(y0 - 1.0f);
    o->x1 = (int16_t)fl_ceil(x1 + 1.0f);
    o->y1 = (int16_t)fl_ceil(y1 + 1.0f);
}

op_t gfx_arc(float cx, float cy, float r_in, float r_out, float a0_deg, float a1_deg, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_ARC;
    o.color = color;
    float sweep = a1_deg - a0_deg;
    if (sweep < 0.0f) sweep += 360.0f;
    if (sweep >= 359.99f) o.flags |= 2;
    if (sweep > 180.0f) o.flags |= 1;
    const float d2r = 0.017453292519943295f;
    o.u.arc.cx = Q4(cx);  o.u.arc.cy = Q4(cy);
    o.u.arc.rin = Q4(r_in);  o.u.arc.rout = Q4(r_out);
    o.u.arc.sx = q14(cosf(a0_deg * d2r));  o.u.arc.sy = q14(sinf(a0_deg * d2r));
    o.u.arc.ex = q14(cosf(a1_deg * d2r));  o.u.arc.ey = q14(sinf(a1_deg * d2r));

    /* tight bounding box: sample both radii along the sweep */
    float minx = 1e9f, miny = 1e9f, maxx = -1e9f, maxy = -1e9f;
    int steps = (int)(sweep) + 1;
    for (int i = 0; i <= steps; i++) {
        float a = (a0_deg + sweep * (float)i / (float)steps) * d2r;
        for (int k = 0; k < 2; k++) {
            float r = k ? r_out : r_in;
            float x = cx + r * cosf(a), y = cy + r * sinf(a);
            minx = fminf(minx, x);  maxx = fmaxf(maxx, x);
            miny = fminf(miny, y);  maxy = fmaxf(maxy, y);
        }
    }
    bbox_set(&o, minx, miny, maxx, maxy);
    return o;
}

op_t gfx_capsule(float ax, float ay, float bx, float by, float thickness, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_CAPSULE;
    o.color = color;
    o.u.cap.ax = Q4(ax);  o.u.cap.ay = Q4(ay);
    o.u.cap.abx = Q4(bx) - Q4(ax);  o.u.cap.aby = Q4(by) - Q4(ay);
    o.u.cap.len2 = o.u.cap.abx * o.u.cap.abx + o.u.cap.aby * o.u.cap.aby;     /* Q8 */
    o.u.cap.inv = o.u.cap.len2 > 0 ? (int32_t)(4294967295.0 / (double)o.u.cap.len2) : 0;
    o.u.cap.r = Q4(thickness * 0.5f);
    float h = thickness * 0.5f;
    bbox_set(&o, fminf(ax, bx) - h, fminf(ay, by) - h, fmaxf(ax, bx) + h, fmaxf(ay, by) + h);
    return o;
}

op_t gfx_disc(float cx, float cy, float r, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_DISC;
    o.color = color;
    o.u.disc.cx = Q4(cx);  o.u.disc.cy = Q4(cy);  o.u.disc.r = Q4(r);
    bbox_set(&o, cx - r, cy - r, cx + r, cy + r);
    return o;
}

op_t gfx_glyph(int x, int y, char ch, int scale, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_GLYPH;
    o.color = color;
    if (scale < 1) scale = 1;
    if (scale > 8) scale = 8;
    o.u.glyph.x = (int16_t)x;  o.u.glyph.y = (int16_t)y;
    o.u.glyph.ch = (uint8_t)ch;  o.u.glyph.scale = (uint8_t)scale;
    o.x0 = (int16_t)x;  o.y0 = (int16_t)y;
    o.x1 = (int16_t)(x + GFX_GLYPH_W * scale);  o.y1 = (int16_t)(y + GFX_GLYPH_H * scale);
    return o;
}

/* ---------------------------------------------------------------- new builders */

uint32_t gfx_lerp_color(uint32_t c0, uint32_t c1, float t)
{
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    uint32_t out = 0;
    for (int sh = 16; sh >= 0; sh -= 8) {
        float a = (float)((c0 >> sh) & 255), b = (float)((c1 >> sh) & 255);
        out |= (uint32_t)(a + (b - a) * t + 0.5f) << sh;
    }
    return out;
}

static uint32_t turn_q16(float deg)
{
    float t = deg / 360.0f;
    t -= floorf(t);
    return (uint32_t)(t * 65536.0f + 0.5f) & 0xFFFFu;
}

static void arc_bbox(op_t *o, float cx, float cy, float r_in, float r_out, float a0_deg, float sweep)
{
    float minx = 1e9f, miny = 1e9f, maxx = -1e9f, maxy = -1e9f;
    const float d2r = 0.017453292519943295f;
    int steps = (int)sweep + 2;
    for (int i = 0; i <= steps; i++) {
        float a = (a0_deg + sweep * (float)i / (float)steps) * d2r;
        for (int k = 0; k < 2; k++) {
            float r = k ? r_out : r_in;
            float x = cx + r * cosf(a), y = cy + r * sinf(a);
            minx = fminf(minx, x);  maxx = fmaxf(maxx, x);
            miny = fminf(miny, y);  maxy = fmaxf(maxy, y);
        }
    }
    bbox_set(o, minx, miny, maxx, maxy);
}

op_t gfx_arc_gradient(float cx, float cy, float r_in, float r_out, float a0_deg, float full_deg,
                      float visible_deg, uint32_t color0, uint32_t color1)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_ARCG;
    o.color = color0;
    if (visible_deg < 0.0f) visible_deg = 0.0f;
    if (visible_deg > full_deg) visible_deg = full_deg;
    o.u.arcg.cx = Q4(cx);  o.u.arcg.cy = Q4(cy);
    o.u.arcg.rin = Q4(r_in);  o.u.arcg.rout = Q4(r_out);
    o.u.arcg.c1 = color1;
    o.u.arcg.a0q = (uint16_t)turn_q16(a0_deg);
    o.u.arcg.fullq = (uint32_t)(full_deg / 360.0f * 65536.0f + 0.5f);
    o.u.arcg.clipq = (uint32_t)(visible_deg / 360.0f * 65536.0f + 0.5f);
    if (o.u.arcg.fullq == 0) o.u.arcg.fullq = 1;
    arc_bbox(&o, cx, cy, r_in, r_out, a0_deg, visible_deg > 1.0f ? visible_deg : 1.0f);
    return o;
}

op_t gfx_ticks(float cx, float cy, float r_in, float r_out, float a0_deg, float span_deg, float step_deg,
               float thickness, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_TICKS;
    o.color = color;
    float rmid = 0.5f * (r_in + r_out);
    float pxq = 65536.0f / (6.283185307f * rmid);              /* angle units per pixel at the middle radius */
    o.u.ticks.cx = Q4(cx);  o.u.ticks.cy = Q4(cy);
    o.u.ticks.rin = Q4(r_in);  o.u.ticks.rout = Q4(r_out);
    o.u.ticks.a0q = (uint16_t)turn_q16(a0_deg);
    o.u.ticks.spanq = (uint32_t)(span_deg / 360.0f * 65536.0f + 0.5f);
    o.u.ticks.stepq = (uint32_t)(step_deg / 360.0f * 65536.0f + 0.5f);
    if (o.u.ticks.stepq == 0) o.u.ticks.stepq = 1;
    o.u.ticks.hwq = (uint32_t)(thickness * 0.5f * pxq + 0.5f);
    o.u.ticks.aaq = (uint32_t)(pxq + 0.5f);
    if (o.u.ticks.aaq == 0) o.u.ticks.aaq = 1;
    arc_bbox(&o, cx, cy, r_in, r_out, a0_deg - 1.0f, span_deg + 2.0f);
    return o;
}

op_t gfx_rrect(float cx, float cy, float w, float h, float radius, float stroke, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_RRECT;
    o.color = color;
    float r = fminf(radius, fminf(w, h) * 0.5f);
    o.u.rrect.cx = Q4(cx);  o.u.rrect.cy = Q4(cy);
    o.u.rrect.hw = Q4(w * 0.5f);  o.u.rrect.hh = Q4(h * 0.5f);
    o.u.rrect.r = Q4(r);
    o.u.rrect.stroke = Q4(stroke);
    bbox_set(&o, cx - w * 0.5f, cy - h * 0.5f, cx + w * 0.5f, cy + h * 0.5f);
    return o;
}

op_t gfx_image(const face_t *f)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_IMG;
    o.u.img.face = f;
    o.x0 = 0;  o.y0 = 0;  o.x1 = GFX_SIZE;  o.y1 = GFX_SIZE;
    return o;
}

op_t gfx_bitmap(const font_t *f, char ch, int x, int baseline, uint32_t color)
{
    op_t o;
    memset(&o, 0, sizeof o);
    o.kind = OP_BMP;
    o.color = color;
    unsigned c = (unsigned char)ch;
    if (c < f->first || c > f->last) c = ' ';
    const fglyph_t *g = &f->glyphs[c - f->first];
    o.u.bmp.bits = f->bits + g->off;
    o.u.bmp.x = (int16_t)(x + g->bx);
    o.u.bmp.y = (int16_t)(baseline + g->by);
    o.u.bmp.w = g->w;
    o.u.bmp.h = g->h;
    o.x0 = o.u.bmp.x;  o.y0 = o.u.bmp.y;
    o.x1 = (int16_t)(o.x0 + g->w);  o.y1 = (int16_t)(o.y0 + g->h);
    return o;
}

int gfx_text_width(const font_t *f, const char *s)
{
    int w = 0;
    for (; *s; s++) {
        unsigned c = (unsigned char)*s;
        if (c < f->first || c > f->last) c = ' ';
        w += f->glyphs[c - f->first].adv;
    }
    return w;
}

int gfx_text(op_t *out, int max, const font_t *f, const char *s, int x, int baseline, text_align_t align, uint32_t color)
{
    int w = gfx_text_width(f, s);
    if (align == TEXT_CENTER) x -= w / 2;
    else if (align == TEXT_RIGHT) x -= w;
    int n = 0;
    for (; *s && n < max; s++) {
        unsigned c = (unsigned char)*s;
        if (c < f->first || c > f->last) c = ' ';
        const fglyph_t *g = &f->glyphs[c - f->first];
        if (g->w) out[n++] = gfx_bitmap(f, (char)c, x, baseline, color);
        x += g->adv;
    }
    return n;
}

/* ---------------------------------------------------------------- coverage */

/* Edge ramp is one pixel wide (Q4: +-8). All return 0..255. */

static inline uint32_t ramp(int32_t outer_minus_d)      /* 0..16 -> 0..255 */
{
    if (outer_minus_d <= 0) return 0;
    if (outer_minus_d >= 16) return 255;
    return (uint32_t)(outer_minus_d * 255) >> 4;
}

static inline int64_t cross(int32_t ax, int32_t ay, int32_t bx, int32_t by)
{
    return (int64_t)ax * by - (int64_t)ay * bx;
}

static uint32_t cov_arc(const op_t *o, int32_t px, int32_t py)
{
    int32_t dx = px - o->u.arc.cx, dy = py - o->u.arc.cy;
    int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;           /* Q8 */
    int32_t rin = o->u.arc.rin, rout = o->u.arc.rout;
    int64_t lo = rin - 8 > 0 ? (int64_t)(rin - 8) * (rin - 8) : 0, hi = (int64_t)(rout + 8) * (rout + 8);
    if (d2 < lo || d2 > hi) return 0;

    if (!(o->flags & 2)) {                                      /* angular test, no atan */
        int64_t a = cross(o->u.arc.sx, o->u.arc.sy, dx, dy);    /* >= 0: clockwise of start */
        int64_t b = cross(dx, dy, o->u.arc.ex, o->u.arc.ey);    /* >= 0: before the end */
        bool in;
        if (o->flags & 1) {
            int64_t c = cross(o->u.arc.ex, o->u.arc.ey, dx, dy);   /* complement wedge */
            int64_t d = cross(dx, dy, o->u.arc.sx, o->u.arc.sy);
            in = !(c >= 0 && d >= 0);
        } else {
            in = a >= 0 && b >= 0;
        }
        if (!in) return 0;
    }

    int64_t full_lo = (int64_t)(rin + 8) * (rin + 8), full_hi = rout - 8 > 0 ? (int64_t)(rout - 8) * (rout - 8) : 0;
    if (d2 >= full_lo && d2 <= full_hi) return 255;
    STAT(gfx_stat_sqrt++);
    int32_t d = (int32_t)gfx_isqrt((uint32_t)d2);
    uint32_t c_in = ramp(d - (rin - 8)), c_out = ramp((rout + 8) - d);
    return c_in < c_out ? c_in : c_out;
}

static uint32_t cov_capsule(const op_t *o, int32_t px, int32_t py)
{
    int32_t apx = px - o->u.cap.ax, apy = py - o->u.cap.ay;
    int32_t qx, qy;
    if (o->u.cap.len2 == 0) {
        qx = 0;  qy = 0;
    } else {
        int64_t dot = (int64_t)apx * o->u.cap.abx + (int64_t)apy * o->u.cap.aby;    /* Q8 */
        int64_t t;                                                                 /* Q16 */
        if (dot <= 0) t = 0;
        else if (dot >= o->u.cap.len2) t = 65536;
        else t = (dot * (uint32_t)o->u.cap.inv) >> 16;
        qx = (int32_t)((o->u.cap.abx * t) >> 16);
        qy = (int32_t)((o->u.cap.aby * t) >> 16);
    }
    int32_t dx = apx - qx, dy = apy - qy;
    int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;
    int32_t r = o->u.cap.r;
    int64_t in = r - 8 > 0 ? (int64_t)(r - 8) * (r - 8) : 0, out = (int64_t)(r + 8) * (r + 8);
    if (d2 >= out) return 0;
    if (d2 <= in) return 255;
    STAT(gfx_stat_sqrt++);
    return ramp((r + 8) - (int32_t)gfx_isqrt((uint32_t)d2));
}

static uint32_t cov_disc(const op_t *o, int32_t px, int32_t py)
{
    int32_t dx = px - o->u.disc.cx, dy = py - o->u.disc.cy;
    int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;
    int32_t r = o->u.disc.r;
    int64_t in = r - 8 > 0 ? (int64_t)(r - 8) * (r - 8) : 0, out = (int64_t)(r + 8) * (r + 8);
    if (d2 >= out) return 0;
    if (d2 <= in) return 255;
    STAT(gfx_stat_sqrt++);
    return ramp((r + 8) - (int32_t)gfx_isqrt((uint32_t)d2));
}

static uint32_t cov_glyph(const op_t *o, int px, int py, const uint8_t *rows)
{
    int s = o->u.glyph.scale;
    int gx = (px - o->u.glyph.x) / s, gy = (py - o->u.glyph.y) / s;
    if (gx < 0 || gx >= GFX_GLYPH_W || gy < 0 || gy >= GFX_GLYPH_H) return 0;
    return ((rows[gy] >> (GFX_GLYPH_W - 1 - gx)) & 1u) ? 255u : 0u;
}

/* Angle of a pixel offset as 1/65536 of a turn, clockwise from 3 o'clock in screen coordinates (y down).
 * An atan approximation good to about 0.2 degree: atan(z) = z * (pi/4 + 0.273 (1 - z)) on 0..1. */
static uint32_t angle_q16(int32_t dx, int32_t dy)
{
    uint32_t ax = (uint32_t)(dx < 0 ? -dx : dx), ay = (uint32_t)(dy < 0 ? -dy : dy);
    if (ax == 0 && ay == 0) return 0;
    uint32_t hi = ax > ay ? ax : ay, lo = ax > ay ? ay : ax;
    uint32_t z = (uint32_t)(((uint64_t)lo << 12) / hi);                     /* 0..4096 */
    uint32_t base = (uint32_t)(((uint64_t)z * (8192u * 4096u + 2847u * (4096u - z))) >> 24);   /* 0..8192 */
    uint32_t a = ay <= ax ? base : 16384u - base;                           /* first quadrant */
    if (dx >= 0) return dy >= 0 ? a : (65536u - a) & 0xFFFFu;
    return dy >= 0 ? 32768u - a : 32768u + a;
}

static uint32_t cov_arcg(const op_t *o, int32_t px, int32_t py, uint32_t *color)
{
    int32_t dx = px - o->u.arcg.cx, dy = py - o->u.arcg.cy;
    int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;
    int32_t rin = o->u.arcg.rin, rout = o->u.arcg.rout;
    int64_t lo = rin - 8 > 0 ? (int64_t)(rin - 8) * (rin - 8) : 0, hi = (int64_t)(rout + 8) * (rout + 8);
    if (d2 < lo || d2 > hi) return 0;
    uint32_t rel = (angle_q16(dx, dy) - o->u.arcg.a0q) & 0xFFFFu;
    if (rel > o->u.arcg.clipq) return 0;
    uint32_t t = (uint32_t)(((uint64_t)rel * 255u) / o->u.arcg.fullq);
    if (t > 255u) t = 255u;
    uint32_t c0 = o->color, c1 = o->u.arcg.c1, out = 0;
    for (int sh = 16; sh >= 0; sh -= 8) {
        int a = (int)((c0 >> sh) & 255), b = (int)((c1 >> sh) & 255);
        out |= (uint32_t)(a + (((b - a) * (int)t + 127) / 255)) << sh;
    }
    *color = out;
    int64_t full_lo = (int64_t)(rin + 8) * (rin + 8), full_hi = rout - 8 > 0 ? (int64_t)(rout - 8) * (rout - 8) : 0;
    if (d2 >= full_lo && d2 <= full_hi) return 255;
    STAT(gfx_stat_sqrt++);
    int32_t d = (int32_t)gfx_isqrt((uint32_t)d2);
    uint32_t c_in = ramp(d - (rin - 8)), c_out = ramp((rout + 8) - d);
    return c_in < c_out ? c_in : c_out;
}

static uint32_t cov_ticks(const op_t *o, int32_t px, int32_t py)
{
    int32_t dx = px - o->u.ticks.cx, dy = py - o->u.ticks.cy;
    int64_t d2 = (int64_t)dx * dx + (int64_t)dy * dy;
    int32_t rin = o->u.ticks.rin, rout = o->u.ticks.rout;
    int64_t lo = rin - 8 > 0 ? (int64_t)(rin - 8) * (rin - 8) : 0, hi = (int64_t)(rout + 8) * (rout + 8);
    if (d2 < lo || d2 > hi) return 0;
    int32_t rel = (int32_t)((angle_q16(dx, dy) - o->u.ticks.a0q) & 0xFFFFu);
    int32_t step = (int32_t)o->u.ticks.stepq, half = step / 2;
    if (rel > 65536 - step) rel -= 65536;                                   /* within one step before the first tick */
    int32_t k = (rel + half) >= 0 ? (rel + half) / step : -1;
    if (k < 0 || (uint32_t)k * (uint32_t)step > o->u.ticks.spanq + (uint32_t)step / 2u) return 0;
    int32_t phase = rel - k * step;
    if (phase < 0) phase = -phase;
    int32_t aa = (int32_t)o->u.ticks.aaq, hw = (int32_t)o->u.ticks.hwq;
    int32_t over = hw + aa / 2 - phase;                                     /* > 0 inside the ramp */
    if (over <= 0) return 0;
    uint32_t c = over >= aa ? 255u : (uint32_t)(over * 255 / aa);
    /* soften the radial ends by one pixel as well */
    int32_t d = (int32_t)gfx_isqrt((uint32_t)d2);
    uint32_t r_in = ramp(d - (rin - 8)), r_out = ramp((rout + 8) - d);
    uint32_t r = r_in < r_out ? r_in : r_out;
    return c * r / 255u;
}

static uint32_t cov_rrect(const op_t *o, int32_t px, int32_t py)
{
    int32_t qx = (px > o->u.rrect.cx ? px - o->u.rrect.cx : o->u.rrect.cx - px) - (o->u.rrect.hw - o->u.rrect.r);
    int32_t qy = (py > o->u.rrect.cy ? py - o->u.rrect.cy : o->u.rrect.cy - py) - (o->u.rrect.hh - o->u.rrect.r);
    int32_t mx = qx > 0 ? qx : 0, my = qy > 0 ? qy : 0;
    int32_t outside = (mx || my) ? (int32_t)gfx_isqrt((uint32_t)((int64_t)mx * mx + (int64_t)my * my)) : 0;
    int32_t inside = (qx > qy ? qx : qy);
    if (inside > 0) inside = 0;
    int32_t d = outside + inside - o->u.rrect.r;                            /* signed distance, Q4, negative inside */
    if (o->u.rrect.stroke == 0) return ramp(8 - d);
    int32_t half = o->u.rrect.stroke / 2;
    int32_t m = d + half;                                                    /* distance from the stroke's centre line */
    if (m < 0) m = -m;
    return ramp(half + 8 - m);
}

static uint32_t cov_bmp(const op_t *o, int px, int py)
{
    int lx = px - o->u.bmp.x, ly = py - o->u.bmp.y;
    if (lx < 0 || ly < 0 || lx >= o->u.bmp.w || ly >= o->u.bmp.h) return 0;
    int i = ly * o->u.bmp.w + lx;
    uint8_t b = o->u.bmp.bits[i >> 1];
    uint32_t a = (i & 1) ? (b & 0x0Fu) : (b >> 4);
    return a * 17u;
}

static uint32_t cov_img(const op_t *o, int px, int py, const uint8_t *line, uint32_t *color)
{
    (void)py;
    *color = o->u.img.face->pal[line[px - o->x0] & 15u];
    return 255;
}

/* ---------------------------------------------------------------- render */

/* Can this op touch the rectangle at all? Arcs are tested against their annulus,
 * which removes the ring from every tile it does not cross. */
static bool op_touches(const op_t *o, int x0, int y0, int x1, int y1)
{
    if (o->x1 <= x0 || o->x0 >= x1 || o->y1 <= y0 || o->y0 >= y1) return false;
    if (o->kind == OP_ARC || o->kind == OP_ARCG || o->kind == OP_TICKS) {
        /* cx, cy, rin, rout are the first four fields of all three ring ops */
        int32_t cx = o->u.arc.cx, cy = o->u.arc.cy;
        int32_t rx0 = x0 * 16, rx1 = x1 * 16, ry0 = y0 * 16, ry1 = y1 * 16;
        int32_t nx = cx < rx0 ? rx0 : (cx > rx1 ? rx1 : cx), ny = cy < ry0 ? ry0 : (cy > ry1 ? ry1 : cy);
        int32_t fx = (cx - rx0 > rx1 - cx) ? rx0 : rx1, fy = (cy - ry0 > ry1 - cy) ? ry0 : ry1;
        int64_t near2 = (int64_t)(nx - cx) * (nx - cx) + (int64_t)(ny - cy) * (ny - cy);
        int64_t far2 = (int64_t)(fx - cx) * (fx - cx) + (int64_t)(fy - cy) * (fy - cy);
        int64_t ro = o->u.arc.rout + 8, ri = o->u.arc.rin - 8;
        if (near2 > ro * ro) return false;
        if (ri > 0 && far2 < ri * ri) return false;
    }
    return true;
}

void gfx_render(const op_t *ops, int n, int x0, int y0, int w, int h, uint16_t *out, int stride)
{
    uint8_t sel[MAX_OPS];
    const uint8_t *rows[MAX_OPS];
    int m = 0;
    if (n > MAX_OPS) n = MAX_OPS;
    for (int i = 0; i < n; i++) {
        if (op_touches(&ops[i], x0, y0, x0 + w, y0 + h)) {
            sel[m] = (uint8_t)i;
            rows[m] = ops[i].kind == OP_GLYPH ? glyph_rows((char)ops[i].u.glyph.ch) : 0;
            m++;
        }
    }

    int img_k = -1;                                  /* the face, if the list has one */
    for (int k = 0; k < m; k++)
        if (ops[sel[k]].kind == OP_IMG) { img_k = k; break; }
    uint8_t img_line[GFX_SIZE];

    for (int y = 0; y < h; y++) {
        int py = y0 + y;
        int32_t qy = py * 16 + 8;
        bool img_row = false;
        if (img_k >= 0 && py >= 0 && py < GFX_SIZE) {
            int xe = x0 + w > GFX_SIZE ? GFX_SIZE : x0 + w;
            if (xe > 0) { face_decode_row(ops[sel[img_k]].u.img.face, py, xe, img_line); img_row = true; }
        }
        for (int x = 0; x < w; x++) {
            int px = x0 + x;
            int32_t qx = px * 16 + 8;
            int r = 0, g = 0, b = 0;
            STAT(gfx_stat_pixels++);
            for (int k = 0; k < m; k++) {
                const op_t *o = &ops[sel[k]];
                if (px < o->x0 || px >= o->x1 || py < o->y0 || py >= o->y1) continue;
                STAT(gfx_stat_op_evals++);
                uint32_t c, col = o->color;
                switch (o->kind) {
                case OP_ARC:     c = cov_arc(o, qx, qy); break;
                case OP_CAPSULE: c = cov_capsule(o, qx, qy); break;
                case OP_DISC:    c = cov_disc(o, qx, qy); break;
                case OP_GLYPH:   c = cov_glyph(o, px, py, rows[k]); break;
                case OP_ARCG:    c = cov_arcg(o, qx, qy, &col); break;
                case OP_TICKS:   c = cov_ticks(o, qx, qy); break;
                case OP_RRECT:   c = cov_rrect(o, qx, qy); break;
                case OP_BMP:     c = cov_bmp(o, px, py); break;
                case OP_IMG:     c = img_row ? cov_img(o, px, py, img_line, &col) : 0; break;
                default:         c = 0; break;
                }
                if (c == 0) continue;
                int sr = (int)((col >> 16) & 0xFF), sg = (int)((col >> 8) & 0xFF), sb = (int)(col & 0xFF);
                if (c == 255) { r = sr; g = sg; b = sb; }
                else {
                    int f = (int)c + 1;                         /* 2..255 -> blend factor out of 256 */
                    r += ((sr - r) * f) >> 8;
                    g += ((sg - g) * f) >> 8;
                    b += ((sb - b) * f) >> 8;
                }
            }
            out[y * stride + x] = gfx_rgb565(((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b);
        }
    }
}
