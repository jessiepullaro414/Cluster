#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gfx.h"

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

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("gfx: all tests passed\n");
    return 0;
}
