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
    { '/', { 0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10 } },
    { '%', { 0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03 } },
    { '-', { 0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00 } },
    { '.', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C } },
    { ' ', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 } },
};

static const uint8_t *glyph_rows(char ch)
{
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

/* ---------------------------------------------------------------- render */

/* Can this op touch the rectangle at all? Arcs are tested against their annulus,
 * which removes the ring from every tile it does not cross. */
static bool op_touches(const op_t *o, int x0, int y0, int x1, int y1)
{
    if (o->x1 <= x0 || o->x0 >= x1 || o->y1 <= y0 || o->y0 >= y1) return false;
    if (o->kind == OP_ARC) {
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

    for (int y = 0; y < h; y++) {
        int py = y0 + y;
        int32_t qy = py * 16 + 8;
        for (int x = 0; x < w; x++) {
            int px = x0 + x;
            int32_t qx = px * 16 + 8;
            int r = 0, g = 0, b = 0;
            STAT(gfx_stat_pixels++);
            for (int k = 0; k < m; k++) {
                const op_t *o = &ops[sel[k]];
                if (px < o->x0 || px >= o->x1 || py < o->y0 || py >= o->y1) continue;
                STAT(gfx_stat_op_evals++);
                uint32_t c;
                switch (o->kind) {
                case OP_ARC:     c = cov_arc(o, qx, qy); break;
                case OP_CAPSULE: c = cov_capsule(o, qx, qy); break;
                case OP_DISC:    c = cov_disc(o, qx, qy); break;
                case OP_GLYPH:   c = cov_glyph(o, px, py, rows[k]); break;
                default:         c = 0; break;
                }
                if (c == 0) continue;
                int sr = (int)((o->color >> 16) & 0xFF), sg = (int)((o->color >> 8) & 0xFF), sb = (int)(o->color & 0xFF);
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
