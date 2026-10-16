#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gfx.h"
#include "face.h"

static int face_corner_index(const face_t *f)
{
    uint8_t row[GFX_SIZE];
    face_decode_row(f, 2, GFX_SIZE, row);
    return row[2];
}

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static uint16_t buf[GFX_SIZE * GFX_SIZE];

/* white coverage summed over the frame, in pixels of area: blue channel of RGB565 is 5 bits,
 * so use the green channel (6 bits) for a finer sum */
static double area(const uint16_t *b, int w, int h)
{
    double a = 0;
    for (int i = 0; i < w * h; i++) a += (double)((b[i] >> 5) & 63) / 63.0;
    return a;
}

static void render_all(const op_t *ops, int n)
{
    gfx_render(ops, n, 0, 0, GFX_SIZE, GFX_SIZE, buf, GFX_SIZE);
}

int main(void)
{
    /* integer square root is exact */
    for (uint32_t v = 0; v < 200000; v++) {
        uint32_t r = gfx_isqrt(v);
        if (!(r * r <= v && (r + 1) * (r + 1) > v)) { CHECK(0); break; }
    }
    uint32_t big[] = { 0xFFFFFFFFu, 0x40000000u, 0x3FFFFFFFu, 1u, 65535u * 65535u };
    for (unsigned i = 0; i < 5; i++) {
        uint64_t r = gfx_isqrt(big[i]);
        CHECK(r * r <= big[i] && (r + 1) * (r + 1) > big[i]);
    }

    /* colour packing */
    CHECK(gfx_rgb565(0xFFFFFF) == 0xFFFF && gfx_rgb565(0x000000) == 0 && gfx_rgb565(0xFF0000) == 0xF800);
    CHECK(gfx_rgb565(0x00FF00) == 0x07E0 && gfx_rgb565(0x0000FF) == 0x001F);

    /* disc: centre full, far black, area about pi r^2 */
    {
        op_t d = gfx_disc(100.0f, 100.0f, 20.0f, 0xFFFFFF);
        render_all(&d, 1);
        CHECK(buf[100 * GFX_SIZE + 100] == 0xFFFF);
        CHECK(buf[10 * GFX_SIZE + 10] == 0);
        double a = area(buf, GFX_SIZE, GFX_SIZE), want = 3.14159265 * 400.0;
        CHECK(fabs(a - want) / want < 0.01);
        CHECK(buf[100 * GFX_SIZE + 121] == 0);                 /* just outside the radius */
    }

    /* capsule: area = length * thickness + pi r^2 */
    {
        op_t c = gfx_capsule(40.0f, 120.0f, 200.0f, 120.0f, 8.0f, 0xFFFFFF);
        render_all(&c, 1);
        double want = 160.0 * 8.0 + 3.14159265 * 16.0;
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - want) / want < 0.01);
        CHECK(buf[120 * GFX_SIZE + 120] == 0xFFFF && buf[130 * GFX_SIZE + 120] == 0);
        CHECK(buf[120 * GFX_SIZE + 38] != 0 && buf[120 * GFX_SIZE + 30] == 0);      /* round cap, then nothing */
        /* diagonal capsule has the same area; exactly 45 degrees is the worst case (2.5% measured:
         * a one-pixel anti-aliasing ramp sampled on the pixel lattice), 0.7% at other angles */
        op_t e = gfx_capsule(40.0f, 40.0f, 40.0f + 113.137f, 40.0f + 113.137f, 8.0f, 0xFFFFFF);
        render_all(&e, 1);
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - want) / want < 0.03);
        /* zero-length capsule is a disc */
        op_t z = gfx_capsule(120.0f, 120.0f, 120.0f, 120.0f, 10.0f, 0xFFFFFF);
        render_all(&z, 1);
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - 3.14159265 * 25.0) / (3.14159265 * 25.0) < 0.02);
    }

    /* arcs: ring, quarter, 270 degrees */
    {
        double ring = 3.14159265 * (100.0 * 100.0 - 80.0 * 80.0);
        op_t full = gfx_arc(120.0f, 120.0f, 80.0f, 100.0f, 0.0f, 360.0f, 0xFFFFFF);
        render_all(&full, 1);
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - ring) / ring < 0.01);

        op_t q = gfx_arc(120.0f, 120.0f, 80.0f, 100.0f, 0.0f, 90.0f, 0xFFFFFF);   /* 3 o'clock to 6 o'clock */
        render_all(&q, 1);
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - ring / 4.0) / (ring / 4.0) < 0.02);
        CHECK(buf[(120 + 90) * GFX_SIZE + 120] != 0);          /* straight down, inside */
        CHECK(buf[120 * GFX_SIZE + 120 + 90] != 0);            /* straight right, inside */
        CHECK(buf[(120 - 90) * GFX_SIZE + 120] == 0);          /* straight up, outside */
        CHECK(buf[120 * GFX_SIZE + 120 - 90] == 0);

        /* the gauge sweep: 135 -> 45 clockwise, open at the bottom */
        op_t g = gfx_arc(120.0f, 120.0f, 80.0f, 100.0f, 135.0f, 45.0f, 0xFFFFFF);
        render_all(&g, 1);
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - ring * 0.75) / (ring * 0.75) < 0.02);
        CHECK(buf[(120 + 90) * GFX_SIZE + 120] == 0);          /* the gap at the bottom */
        CHECK(buf[(120 - 90) * GFX_SIZE + 120] != 0);          /* the top */
        CHECK(buf[120 * GFX_SIZE + 120 - 90] != 0);            /* left */
        CHECK(buf[120 * GFX_SIZE + 120 + 90] != 0);            /* right */
        CHECK(buf[(120 + 44) * GFX_SIZE + 120 - 77] != 0);     /* 150 degrees: lower left, inside the sweep */
        CHECK(buf[(120 + 77) * GFX_SIZE + 120 - 44] == 0);     /* 120 degrees: in the gap */
        CHECK(buf[(120 + 90) * GFX_SIZE + 120 - 10] == 0);     /* bottom, left of centre: still in the gap */
        /* radial edges are anti-aliased: some pixels are neither empty nor full */
        int partial = 0;
        for (int i = 0; i < GFX_SIZE * GFX_SIZE; i++) if (buf[i] != 0 && buf[i] != 0xFFFF) partial++;
        CHECK(partial > 200);
    }

    /* glyph: scale 2 'E' has its top bar and left stem, and nothing outside its 10 x 14 box */
    {
        op_t g = gfx_glyph(50, 60, 'E', 2, 0xFFFFFF);
        render_all(&g, 1);
        for (int x = 0; x < 10; x++) CHECK(buf[60 * GFX_SIZE + 50 + x] == 0xFFFF);      /* top bar */
        CHECK(buf[(60 + 4) * GFX_SIZE + 50] == 0xFFFF && buf[(60 + 4) * GFX_SIZE + 59] == 0);
        CHECK(buf[(60 + 14) * GFX_SIZE + 50] == 0 && buf[60 * GFX_SIZE + 49] == 0 && buf[60 * GFX_SIZE + 60] == 0);
        double a = area(buf, GFX_SIZE, GFX_SIZE);
        CHECK(a > 40.0 && a < 100.0);
    }

    /* the font: every glyph draws something, no two different characters draw the same picture,
     * and lower case maps to upper case */
    {
        const char *set = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:+=(),_/%-.";
        static uint16_t pic[64][GFX_GLYPH_W * GFX_GLYPH_H];
        int n = (int)strlen(set);
        for (int i = 0; i < n; i++) {
            op_t g = gfx_glyph(0, 0, set[i], 1, 0xFFFFFF);
            gfx_render(&g, 1, 0, 0, GFX_GLYPH_W, GFX_GLYPH_H, pic[i], GFX_GLYPH_W);
            int lit = 0;
            for (int k = 0; k < GFX_GLYPH_W * GFX_GLYPH_H; k++) lit += pic[i][k] != 0;
            CHECK(lit > 0);
            for (int j = 0; j < i; j++)
                if (memcmp(pic[i], pic[j], sizeof pic[i]) == 0) { printf("glyphs '%c' and '%c' are identical\n", set[i], set[j]); failures++; }
        }
        static uint16_t a[GFX_GLYPH_W * GFX_GLYPH_H], b2[GFX_GLYPH_W * GFX_GLYPH_H];
        op_t up = gfx_glyph(0, 0, 'K', 1, 0xFFFFFF), lo = gfx_glyph(0, 0, 'k', 1, 0xFFFFFF);
        gfx_render(&up, 1, 0, 0, GFX_GLYPH_W, GFX_GLYPH_H, a, GFX_GLYPH_W);
        gfx_render(&lo, 1, 0, 0, GFX_GLYPH_W, GFX_GLYPH_H, b2, GFX_GLYPH_W);
        CHECK(memcmp(a, b2, sizeof a) == 0);
    }

    /* rounded rectangle: filled area = w*h - (4 - pi) r^2, outline area = perimeter-ish * stroke */
    {
        op_t r = gfx_rrect(120.0f, 120.0f, 100.0f, 40.0f, 12.0f, 0.0f, 0xFFFFFF);
        render_all(&r, 1);
        double want = 100.0 * 40.0 - (4.0 - 3.14159265) * 144.0;
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - want) / want < 0.01);
        CHECK(buf[120 * GFX_SIZE + 120] == 0xFFFF && buf[120 * GFX_SIZE + 60] == 0 && buf[98 * GFX_SIZE + 120] == 0);
        CHECK(buf[101 * GFX_SIZE + 71] == 0);                              /* the rounded corner is cut */
        op_t o = gfx_rrect(120.0f, 120.0f, 100.0f, 40.0f, 12.0f, 4.0f, 0xFFFFFF);
        render_all(&o, 1);
        CHECK(buf[120 * GFX_SIZE + 120] == 0);                             /* hollow */
        CHECK(buf[101 * GFX_SIZE + 120] != 0 && buf[138 * GFX_SIZE + 120] != 0);   /* top and bottom edges drawn */
        double ring_want = (100.0 * 40.0 - (4.0 - 3.14159265) * 144.0) - (92.0 * 32.0 - (4.0 - 3.14159265) * 64.0);   /* outer minus inner */
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - ring_want) / ring_want < 0.04);
    }

    /* gradient arc: colour changes along the scale, and only the visible part is lit */
    {
        /* scale starts at 0 degrees (3 o'clock) and runs 180 degrees clockwise (through 6 o'clock to 9),
         * red at the start, blue at the end; visible 90 degrees */
        op_t g = gfx_arc_gradient(120.0f, 120.0f, 70.0f, 90.0f, 0.0f, 180.0f, 90.0f, 0xFF0000, 0x0000FF);
        render_all(&g, 1);
        uint16_t near_start = buf[(120 + 6) * GFX_SIZE + 120 + 80];         /* ~4 degrees */
        uint16_t half = buf[(120 + 57) * GFX_SIZE + 120 + 57];              /* 45 degrees: a quarter of the way along the scale */
        CHECK(((near_start >> 11) & 31) > 25 && (near_start & 31) < 4);     /* nearly pure red */
        int r = (half >> 11) & 31, b = half & 31;
        CHECK(r > 17 && r < 27 && b > 4 && b < 14);                         /* red, bluish: 25 % along */
        CHECK(buf[(120 + 60) * GFX_SIZE + 120 - 60] == 0);                  /* 135 degrees: beyond the visible 90 */
        CHECK(buf[(120 - 80) * GFX_SIZE + 120] == 0);                       /* top: outside the sweep */
        /* the edge of the lit part sits within about a degree of 90: at radius 80, 89 lit, 91 dark */
        const double d2r = 3.14159265 / 180.0;
        uint16_t a89 = buf[(int)(120 + 80 * sin(89 * d2r)) * GFX_SIZE + (int)(120 + 80 * cos(89 * d2r))];
        uint16_t a92 = buf[(int)(120 + 80 * sin(92 * d2r)) * GFX_SIZE + (int)(120 + 80 * cos(92 * d2r))];
        CHECK(a89 != 0 && a92 == 0);
        /* tighter: the lit part ends within a degree of 90 (the angle is computed to about 0.2 degree) */
        const double r8 = 80.0;
        uint16_t lit = buf[(int)lround(120 + r8 * sin(88.8 * d2r)) * GFX_SIZE + (int)lround(120 + r8 * cos(88.8 * d2r))];
        uint16_t dark = buf[(int)lround(120 + r8 * sin(91.4 * d2r)) * GFX_SIZE + (int)lround(120 + r8 * cos(91.4 * d2r))];
        CHECK(lit != 0 && dark == 0);
        /* gfx_lerp_color agrees with what is drawn at the ends */
        CHECK(gfx_lerp_color(0xFF0000, 0x0000FF, 0.0f) == 0xFF0000 && gfx_lerp_color(0xFF0000, 0x0000FF, 1.0f) == 0x0000FF);
        CHECK(gfx_lerp_color(0x000000, 0xFFFFFF, 0.5f) == 0x808080);
        /* a full-sweep gradient lights the whole ring */
        op_t full = gfx_arc_gradient(120.0f, 120.0f, 70.0f, 90.0f, 135.0f, 270.0f, 270.0f, 0x00FF00, 0xFF0000);
        render_all(&full, 1);
        double ring = 3.14159265 * (90.0 * 90.0 - 70.0 * 70.0) * 0.75 * 0.5;   /* the green channel fades linearly from full to none */
        CHECK(fabs(area(buf, GFX_SIZE, GFX_SIZE) - ring) / ring < 0.08);
    }

    /* ticks: the right number of marks, evenly spread, only inside the span */
    {
        op_t t = gfx_ticks(120.0f, 120.0f, 80.0f, 100.0f, 135.0f, 270.0f, 30.0f, 3.0f, 0xFFFFFF);   /* 10 ticks */
        render_all(&t, 1);
        int runs = 0, prev = 0, first = -1, last = -1;
        for (int a = 0; a < 3600; a++) {                                   /* walk the circle at radius 90 in 0.1 degree steps */
            double ang = a * 0.1 * 3.14159265 / 180.0;
            int x = (int)lround(120 + 90 * cos(ang)), y = (int)lround(120 + 90 * sin(ang));
            int on = buf[y * GFX_SIZE + x] > 0x4000;
            if (on && !prev) { runs++; if (first < 0) first = a; last = a; }
            prev = on;
        }
        CHECK(runs == 10);
        CHECK(first >= 0 && fabs((first / 10.0) - 0.0) < 140.0);           /* a tick near the start, none in the gap */
        CHECK(buf[(120 + 90) * GFX_SIZE + 120] == 0);                      /* 90 degrees (straight down) lies in the open gap */
        double a_start = 135.0 * 3.14159265 / 180.0;
        CHECK(buf[(int)lround(120 + 90 * sin(a_start)) * GFX_SIZE + (int)lround(120 + 90 * cos(a_start))] > 0x4000);   /* a tick at the start */
        double a_end = 45.0 * 3.14159265 / 180.0;
        CHECK(buf[(int)lround(120 + 90 * sin(a_end)) * GFX_SIZE + (int)lround(120 + 90 * cos(a_end))] > 0x4000);       /* and at the end */
        CHECK(buf[120 * GFX_SIZE + 120 + 70] == 0 && buf[120 * GFX_SIZE + 120 + 110] == 0);                           /* radial ends hold */
        (void)last;
    }

    /* font bitmaps */
    {
        CHECK(gfx_text_width(&FONT_BIG, "0") > 20 && gfx_text_width(&FONT_BIG, "00") == 2 * gfx_text_width(&FONT_BIG, "0"));
        CHECK(gfx_text_width(&FONT_SMALL, "MPH") > 20 && gfx_text_width(&FONT_SMALL, "MPH") < 60);
        op_t ops[8];
        int n = gfx_text(ops, 8, &FONT_BIG, "60", 100, 150, TEXT_LEFT, 0xFFFFFF);
        CHECK(n == 2);
        render_all(ops, n);
        double a = area(buf, GFX_SIZE, GFX_SIZE);
        CHECK(a > 400.0 && a < 1400.0);                                    /* two big digits */
        /* the glyph sits on the baseline and above it */
        int below = 0, above = 0;
        for (int y = 151; y < 165; y++) for (int x = 90; x < 160; x++) below += buf[y * GFX_SIZE + x] != 0;
        for (int y = 110; y < 150; y++) for (int x = 90; x < 160; x++) above += buf[y * GFX_SIZE + x] != 0;
        CHECK(above > 200 && below == 0);
        /* centred and right aligned text is placed by its width */
        op_t c[8], r[8], l[8];
        int nc = gfx_text(c, 8, &FONT_MED, "182", 120, 100, TEXT_CENTER, 0xFFFFFF);
        int nr = gfx_text(r, 8, &FONT_MED, "182", 120, 100, TEXT_RIGHT, 0xFFFFFF);
        int nl = gfx_text(l, 8, &FONT_MED, "182", 120, 100, TEXT_LEFT, 0xFFFFFF);
        int w = gfx_text_width(&FONT_MED, "182");
        CHECK(nc == 3 && nr == 3 && nl == 3);
        CHECK(l[0].x0 - c[0].x0 == w / 2 && l[0].x0 - r[0].x0 == w);
        /* every ASCII glyph of the medium face and the degree sign exist; digits differ from each other */
        static uint16_t pic[10][40 * 60];
        for (int d = 0; d < 10; d++) {
            op_t g = gfx_bitmap(&FONT_BIG, (char)('0' + d), 4, 50, 0xFFFFFF);
            gfx_render(&g, 1, 0, 0, 40, 60, pic[d], 40);
            int lit = 0;
            for (int k = 0; k < 40 * 60; k++) lit += pic[d][k] != 0;
            CHECK(lit > 200);
            for (int e = 0; e < d; e++) CHECK(memcmp(pic[d], pic[e], sizeof pic[d]) != 0);
        }
        op_t deg = gfx_bitmap(&FONT_MED, '\x7F', 5, 30, 0xFFFFFF);
        CHECK(deg.u.bmp.w > 3 && deg.u.bmp.h > 3);
        CHECK(FONT_SMALL.ascent > 8 && FONT_MED.ascent > FONT_SMALL.ascent && FONT_BIG.ascent > FONT_MED.ascent);
    }

    /* tile independence: rendering a scene whole equals rendering it tile by tile */
    {
        op_t ops[6];
        ops[0] = gfx_arc(120.0f, 120.0f, 100.0f, 112.0f, 135.0f, 405.0f, 0x2A2F36);
        ops[1] = gfx_capsule(120.0f, 120.0f, 180.0f, 60.0f, 4.0f, 0xFF8A00);
        ops[2] = gfx_disc(120.0f, 120.0f, 7.0f, 0x707780);
        ops[3] = gfx_glyph(100, 150, '8', 3, 0xFFFFFF);
        ops[4] = gfx_capsule(30.0f, 200.0f, 90.0f, 215.0f, 5.0f, 0xFF3030);
        ops[5] = gfx_disc(200.0f, 200.0f, 12.0f, 0x3D8BFF);
        static uint16_t whole[GFX_SIZE * GFX_SIZE], tiled[GFX_SIZE * GFX_SIZE], t[GFX_TILE * GFX_TILE];
        gfx_render(ops, 6, 0, 0, GFX_SIZE, GFX_SIZE, whole, GFX_SIZE);
        for (int ty = 0; ty < GFX_TILES; ty++)
            for (int tx = 0; tx < GFX_TILES; tx++) {
                gfx_render(ops, 6, tx * GFX_TILE, ty * GFX_TILE, GFX_TILE, GFX_TILE, t, GFX_TILE);
                for (int y = 0; y < GFX_TILE; y++)
                    memcpy(&tiled[(ty * GFX_TILE + y) * GFX_SIZE + tx * GFX_TILE], &t[y * GFX_TILE], GFX_TILE * 2);
            }
        CHECK(memcmp(whole, tiled, sizeof whole) == 0);
        /* a wide run of tiles (stride > 16) equals the whole too */
        static uint16_t row[GFX_SIZE * GFX_TILE];
        gfx_render(ops, 6, 0, 96, GFX_SIZE, GFX_TILE, row, GFX_SIZE);
        CHECK(memcmp(row, &whole[96 * GFX_SIZE], sizeof row) == 0);
    }

    /* later ops paint over earlier ones */
    {
        op_t ops[2] = { gfx_disc(100.0f, 100.0f, 30.0f, 0xFF0000), gfx_disc(100.0f, 100.0f, 10.0f, 0x0000FF) };
        render_all(ops, 2);
        CHECK(buf[100 * GFX_SIZE + 100] == 0x001F && buf[100 * GFX_SIZE + 120] == 0xF800);
    }

    /* printed faces: every face decodes to the pixels the generator checksummed, and the image op draws them */
    for (int f = 0; f < FACE_COUNT; f++) {
        uint32_t crc = ~0u;
        uint8_t row[GFX_SIZE];
        for (int y = 0; y < GFX_SIZE; y++) {
            face_decode_row(FACE_LIST[f], y, GFX_SIZE, row);
            for (int x = 0; x < GFX_SIZE; x++) {
                crc ^= row[x];
                for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1u));
            }
        }
        CHECK(~crc == FACE_CHECKS[f]);
        /* a partial decode is the start of the full one */
        uint8_t part[GFX_SIZE], full[GFX_SIZE];
        face_decode_row(FACE_LIST[f], 100, 77, part);
        face_decode_row(FACE_LIST[f], 100, GFX_SIZE, full);
        CHECK(memcmp(part, full, 77) == 0);
        /* the image op: whole frame vs a narrow run of tiles */
        op_t img[2] = { gfx_image(FACE_LIST[f]), gfx_disc(120.0f, 120.0f, 6.0f, 0xFF0000) };
        render_all(img, 2);
        static uint16_t whole2[GFX_SIZE * GFX_SIZE];
        memcpy(whole2, buf, sizeof whole2);
        uint16_t strip[3 * GFX_TILE * GFX_TILE];
        gfx_render(img, 2, 96, 112, 3 * GFX_TILE, GFX_TILE, strip, 3 * GFX_TILE);
        int same = 1;
        for (int y = 0; y < GFX_TILE; y++)
            for (int x = 0; x < 3 * GFX_TILE; x++) same &= strip[y * 3 * GFX_TILE + x] == whole2[(112 + y) * GFX_SIZE + 96 + x];
        CHECK(same);
        CHECK(whole2[120 * GFX_SIZE + 120] == 0xF800);                              /* ops over the face are painted over it */
        CHECK(whole2[2 * GFX_SIZE + 2] == gfx_rgb565(FACE_LIST[f]->pal[face_corner_index(FACE_LIST[f])]));
    }

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("gfx: all tests passed\n");
    return 0;
}
