#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dial.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static uint32_t rng = 12345u;
static uint32_t rnd(void) { rng = rng * 1664525u + 1013904223u; return rng >> 8; }
static float rndf(float lo, float hi) { return lo + (hi - lo) * (float)(rnd() & 0xFFFF) / 65535.0f; }

typedef struct { uint16_t px[GFX_SIZE * GFX_SIZE]; } frame_t;

/* draw every dirty run of d into f (what the panel would hold) */
static int drain(dial_t *d, frame_t *f)
{
    static uint16_t stage[GFX_SIZE * GFX_TILE];
    int row, col, n, tiles = 0;
    while (dial_next_run(d, &row, &col, &n)) {
        dial_render_run(d, row, col, n, stage);
        for (int y = 0; y < GFX_TILE; y++)
            memcpy(&f->px[(row * GFX_TILE + y) * GFX_SIZE + col * GFX_TILE], &stage[y * n * GFX_TILE],
                   (size_t)n * GFX_TILE * 2);
        tiles += n;
    }
    return tiles;
}

/* compare the visible (round) part of two frames */
static int diff_visible(const frame_t *a, const frame_t *b)
{
    int bad = 0;
    for (int y = 0; y < GFX_SIZE; y++)
        for (int x = 0; x < GFX_SIZE; x++) {
            int dx = x - 120, dy = y - 120;
            if (dx * dx + dy * dy > 120 * 120) continue;
            if (a->px[y * GFX_SIZE + x] != b->px[y * GFX_SIZE + x]) bad++;
        }
    return bad;
}

/* ground truth: every pixel straight from the op list, ignoring what was marked dirty */
static void truth(const dial_t *d, frame_t *f)
{
    gfx_render(d->ops, d->n_total, 0, 0, GFX_SIZE, GFX_SIZE, f->px, GFX_SIZE);
}

static chosen_t cv(float v, bool valid) { chosen_t c = { v, valid, valid ? SRC_LOCAL : SRC_NONE }; return c; }

static screen_values_t random_values(void)
{
    screen_values_t v;
    bool inv = (rnd() % 7) == 0;
    v.speed_kph = cv(rndf(-5.0f, 230.0f), !inv && (rnd() % 9));
    v.rpm = cv(rndf(0.0f, 8000.0f), rnd() % 9);
    v.battery_v = cv(rndf(8.0f, 17.0f), rnd() % 9);
    v.fuel_pct = cv(rndf(0.0f, 100.0f), rnd() % 9);
    v.coolant_c = cv(rndf(20.0f, 140.0f), rnd() % 9);
    v.oil_kpa = cv(rndf(0.0f, 800.0f), rnd() % 9);
    return v;
}

int main(void)
{
    /* number formatting */
    char b[12];
    dial_format(b, 68.0f, 0);   CHECK(strcmp(b, "68") == 0);
    dial_format(b, 13.84f, 1);  CHECK(strcmp(b, "13.8") == 0);
    dial_format(b, 0.0f, 0);    CHECK(strcmp(b, "0") == 0);
    dial_format(b, 0.04f, 1);   CHECK(strcmp(b, "0.0") == 0);
    dial_format(b, 7.96f, 1);   CHECK(strcmp(b, "8.0") == 0);
    dial_format(b, -5.4f, 0);   CHECK(strcmp(b, "-5") == 0);
    dial_format(b, 3500.4f, 0); CHECK(strcmp(b, "3500") == 0);
    dial_format(b, 2.5f, 2);    CHECK(strcmp(b, "2.50") == 0);

    /* every gauge kind, both unit systems, extreme values: the op list never overflows */
    int max_ops = 0;
    for (int imp = 0; imp < 2; imp++)
        for (int k = GK_SPEED; k < GK_COUNT; k++)
            for (int step = 0; step < 6; step++) {
                static dial_t d;
                dial_init(&d);
                screen_values_t v;
                float vals[6] = { 0.0f, 1.0f, 99.9f, 188.0f, 7777.0f, 888.8f };
                v.speed_kph = v.rpm = v.battery_v = v.fuel_pct = v.coolant_c = v.oil_kpa = cv(vals[step], true);
                screen_cfg_t cfg = { (gauge_kind_t)k, k == GK_FUEL ? GK_BATTERY : (k == GK_COOLANT ? GK_OIL : (k == GK_SPEED ? GK_FUEL : (k == GK_BATTERY ? GK_OIL : GK_NONE))) };
                screen_view_t view = screens_build(&cfg, &v, imp);
                dial_set_view_theme(&d, &view, imp, (theme_t)(step % THEME_COUNT));
                if (d.n_total > max_ops) max_ops = d.n_total;
            }
    CHECK(!dial_overflowed());
    printf("dial: largest op list %d of %d\n", max_ops, DIAL_MAX_OPS);
    CHECK(max_ops <= DIAL_MAX_OPS);

    /* nothing changes -> nothing dirty */
    {
        static dial_t d;
        static frame_t f;
        dial_init(&d);
        screen_values_t v = random_values();
        screen_view_t view = screens_build(&SCREENS_DEFAULT[1], &v, true);
        dial_set_view(&d, &view, true);
        int first = drain(&d, &f);
        CHECK(first > 400 && first < GFX_TILES * GFX_TILES);          /* the round face, not the corners */
        dial_set_view(&d, &view, true);
        CHECK(dial_dirty_tiles(&d) == 0);
    }

    /* THE property: patching only the dirty tiles gives exactly the picture a fresh full draw gives.
     * Random walks of views, every screen layout, both unit systems, valid and invalid inputs. */
    int pairs = 0, worst = 0;
    for (int trial = 0; trial < 240; trial++) {
        int s = trial % SCREEN_COUNT;
        theme_t th = (theme_t)((trial / SCREEN_COUNT) % THEME_COUNT);
        const screen_cfg_t *layout = screens_layout(th);
        bool imp = (rnd() & 1) != 0;
        static dial_t inc, ref;
        static frame_t fi, fr;
        dial_init(&inc);
        screen_values_t v = random_values();
        screen_view_t view = screens_build(&layout[s], &v, imp);
        dial_set_view_theme(&inc, &view, imp, th);
        drain(&inc, &fi);
        {
            static frame_t ft0;
            truth(&inc, &ft0);
            CHECK(diff_visible(&fi, &ft0) == 0);                    /* the first draw covers the whole visible face */
        }
        for (int step = 0; step < 12; step++) {
            if (step % 4 == 3) {                         /* small moves, the common case */
                v.speed_kph.value += rndf(-3.0f, 3.0f);
                v.rpm.value += rndf(-80.0f, 80.0f);
                v.coolant_c.value += rndf(-1.0f, 1.0f);
            } else {
                v = random_values();
            }
            view = screens_build(&layout[s], &v, imp);
            dial_set_view_theme(&inc, &view, imp, th);
            int tiles = drain(&inc, &fi);
            if (tiles > worst) worst = tiles;

            dial_init(&ref);
            dial_set_view_theme(&ref, &view, imp, th);
            memset(&fr, 0, sizeof fr);
            drain(&ref, &fr);
            int bad = diff_visible(&fi, &fr);
            static frame_t ft;
            truth(&inc, &ft);
            int bad_truth = diff_visible(&fi, &ft);                  /* what is on the panel vs what the model says */
            if (bad_truth) { printf("trial %d step %d screen %d: %d visible pixels differ from the model\n", trial, step, s, bad_truth); failures++; trial = 1000; break; }
            if (bad) { printf("trial %d step %d screen %d: %d pixels differ\n", trial, step, s, bad); failures++; trial = 1000; break; }
            pairs++;
        }
    }
    printf("dial: %d random updates reproduce a full draw exactly; largest update %d tiles\n", pairs, worst);
    CHECK(pairs >= 1200);

    /* unit switch redraws the whole face */
    {
        static dial_t d;
        static frame_t f, g;
        dial_init(&d);
        screen_values_t v = random_values();
        screen_view_t vi = screens_build(&SCREENS_DEFAULT[1], &v, true), vm = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &vi, true);
        drain(&d, &f);
        dial_set_view(&d, &vm, false);
        CHECK(dial_dirty_tiles(&d) > 400);
        drain(&d, &f);
        static dial_t r;
        dial_init(&r);
        dial_set_view(&r, &vm, false);
        drain(&r, &g);
        CHECK(diff_visible(&f, &g) == 0);
    }

    /* cost of the common updates, in tiles (225 tiles in the frame, about 177 of them visible) */
    {
        static dial_t d;
        static frame_t f;
        dial_init(&d);
        screen_values_t v = { cv(60.0f, true), cv(3000.0f, true), cv(13.8f, true), cv(68.0f, true), cv(90.0f, true), cv(300.0f, true) };
        screen_view_t view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        int full = drain(&d, &f);
        v.speed_kph.value = 61.0f;                                 /* 1 km/h: needle moves 0.4 deg, the number changes */
        view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        int t1 = drain(&d, &f);
        v.speed_kph.value = 61.1f;                                 /* rounds to the same number and the same whole degree */
        view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        int t2 = drain(&d, &f);
        v.speed_kph.value = 90.0f;                                 /* a big move */
        view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        int t3 = drain(&d, &f);
        printf("dial: full draw %d tiles; +1 km/h %d; no visible change %d; 60 -> 90 km/h %d\n", full, t1, t2, t3);
        CHECK(t1 < full / 2);
        CHECK(t2 == 0);
        CHECK(t3 < full);
    }

    /* switching a dial between themes (and layouts) redraws everything: the result equals a fresh draw */
    {
        static dial_t d, ref;
        static frame_t f, g;
        dial_init(&d);
        screen_values_t v = { cv(60.0f, true), cv(3000.0f, true), cv(13.8f, true), cv(50.0f, true), cv(90.0f, true), cv(300.0f, true) };
        for (int step = 0; step < 12; step++) {
            theme_t th = (theme_t)(step % THEME_COUNT);
            int scr = step % SCREEN_COUNT;
            screen_view_t view = screens_build(&screens_layout(th)[scr], &v, true);
            dial_set_view_theme(&d, &view, true, th);
            drain(&d, &f);
            dial_init(&ref);
            dial_set_view_theme(&ref, &view, true, th);
            memset(&g, 0, sizeof g);
            drain(&ref, &g);
            CHECK(diff_visible(&f, &g) == 0);
        }
        /* the same screen, same gauge kind, only the theme changes: classic speed to modern speed */
        screen_cfg_t speed = { GK_SPEED, GK_NONE };
        screen_view_t view = screens_build(&speed, &v, true);
        dial_init(&d);
        dial_set_view_theme(&d, &view, true, THEME_CLASSIC);
        drain(&d, &f);
        dial_set_view_theme(&d, &view, true, THEME_MODERN);
        CHECK(dial_dirty_tiles(&d) > 400);
        drain(&d, &f);
        dial_init(&ref);
        dial_set_view_theme(&ref, &view, true, THEME_MODERN);
        memset(&g, 0, sizeof g);
        drain(&ref, &g);
        CHECK(diff_visible(&f, &g) == 0);
        dial_set_view_theme(&d, &view, true, THEME_CLASSIC);          /* and back */
        drain(&d, &f);
        dial_init(&ref);
        dial_set_view_theme(&ref, &view, true, THEME_CLASSIC);
        memset(&g, 0, sizeof g);
        drain(&ref, &g);
        CHECK(diff_visible(&f, &g) == 0);
    }

    /* an unknown theme number from the bus falls back to the classic theme */
    CHECK(screens_theme_from_setting(0) == THEME_CLASSIC && screens_theme_from_setting(1) == THEME_MODERN);
    CHECK(screens_theme_from_setting(2) == THEME_CARPLAY && screens_theme_from_setting(3) == THEME_FACTORY &&
          screens_theme_from_setting(4) == THEME_CLASSIC && screens_theme_from_setting(15) == THEME_CLASSIC);
    CHECK(screens_layout(THEME_MODERN)[0].primary == GK_SPEED && screens_layout(THEME_MODERN)[2].primary == GK_BATTERY);
    CHECK(screens_layout(THEME_CLASSIC) == SCREENS_DEFAULT);
    CHECK(screens_layout(THEME_FACTORY)[0].primary == GK_FUEL && screens_layout(THEME_FACTORY)[1].primary == GK_SPEED &&
          screens_layout(THEME_FACTORY)[2].primary == GK_OIL && screens_layout(THEME_FACTORY)[3].primary == GK_COOLANT);
    CHECK(screens_layout(THEME_CARPLAY)[0].primary == GK_SPEED && screens_layout(THEME_CARPLAY)[2].primary == GK_BATTERY &&
          screens_layout(THEME_CARPLAY)[2].secondary == GK_OIL);

    /* the number hold-off: the numbers of the modern theme change at most once per hold, a big jump or a warning goes through at once */
    {
        static dial_t d, ref;
        static frame_t f, g;
        dial_init(&d);
        dial_set_text_hold(&d, 8);
        screen_values_t v = { cv(60.0f, true), cv(3000.0f, true), cv(13.8f, true), cv(50.0f, true), cv(90.0f, true), cv(300.0f, true) };
        screen_cfg_t speed = { GK_SPEED, GK_NONE };
        screen_view_t view = screens_build(&speed, &v, true);
        dial_set_view_theme(&d, &view, true, THEME_MODERN);
        drain(&d, &f);
        v.speed_kph.value += 3.0f;                                     /* 2 mph: the arc moves, the number waits */
        view = screens_build(&speed, &v, true);
        dial_set_view_theme(&d, &view, true, THEME_MODERN);
        int moved = drain(&d, &f);
        CHECK(moved > 0);                                              /* the arc followed */
        int calls = 1, number_changes = 0;
        for (; calls < 30; calls++) {
            dial_set_view_theme(&d, &view, true, THEME_MODERN);
            /* a text change shows as a block of tiles around the digits (middle of the face) */
            int t = drain(&d, &f);
            if (t > 0) number_changes++;
        }
        CHECK(number_changes == 1);                                    /* released once, after the hold, not on every call */
        dial_init(&ref);
        dial_set_view_theme(&ref, &view, true, THEME_MODERN);
        memset(&g, 0, sizeof g);
        drain(&ref, &g);
        CHECK(diff_visible(&f, &g) == 0);                              /* and then it shows the current value */
        v.speed_kph.value += 90.0f;                                    /* a big jump is not held back */
        view = screens_build(&speed, &v, true);
        dial_set_view_theme(&d, &view, true, THEME_MODERN);
        drain(&d, &f);
        dial_init(&ref);
        dial_set_view_theme(&ref, &view, true, THEME_MODERN);
        memset(&g, 0, sizeof g);
        drain(&ref, &g);
        CHECK(diff_visible(&f, &g) == 0);
    }

    /* an invalid input hides the needle and shows dashes */
    {
        static dial_t d;
        static frame_t f, g;
        dial_init(&d);
        screen_values_t v = { cv(60.0f, true), cv(3000.0f, true), cv(13.8f, true), cv(68.0f, true), cv(90.0f, true), cv(300.0f, true) };
        screen_view_t view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        drain(&d, &f);
        v.speed_kph = cv(60.0f, false);
        view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        dial_set_view(&d, &view, false);
        CHECK(dial_dirty_tiles(&d) > 0);
        drain(&d, &f);
        CHECK(!d.needle_shown && strcmp(d.big, "--") == 0);
        static dial_t r;
        dial_init(&r);
        dial_set_view(&r, &view, false);
        drain(&r, &g);
        CHECK(diff_visible(&f, &g) == 0);
    }

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("dial: all tests passed\n");
    return 0;
}
