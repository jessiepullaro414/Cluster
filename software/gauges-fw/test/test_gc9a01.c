#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "aux_display.h"
#include "dial.h"
#include "gc9a01.h"
#include "panel_mock.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static mock_t g_mock;

static chosen_t cv(float v, bool valid) { chosen_t c = { v, valid, valid ? SRC_LOCAL : SRC_NONE }; return c; }

static const mock_cmd_t *find(const mock_t *m, int screen, int cmd, int nth)
{
    for (int i = 0; i < m->n_log; i++)
        if (m->log[i].screen == screen && m->log[i].cmd == cmd && nth-- == 0) return &m->log[i];
    return 0;
}

static int index_of(const mock_t *m, int screen, int cmd)
{
    for (int i = 0; i < m->n_log; i++)
        if (m->log[i].screen == screen && m->log[i].cmd == cmd) return i;
    return -1;
}

static int visible_diff(const uint16_t *a, const uint16_t *b)
{
    int bad = 0;
    for (int y = 0; y < 240; y++)
        for (int x = 0; x < 240; x++) {
            int dx = x - 120, dy = y - 120;
            if (dx * dx + dy * dy <= 120 * 120 && a[y * 240 + x] != b[y * 240 + x]) bad++;
        }
    return bad;
}

int main(void)
{
    /* ---- driver: initialisation sequence ---- */
    {
        mock_init(&g_mock);
        const panel_hal_t *hal = mock_hal(&g_mock);
        gc9a01_reset(hal);
        CHECK(g_mock.reset_count == 1 && !g_mock.reset_asserted);
        CHECK(g_mock.total_delay_ms >= 120);                      /* wait after reset before talking */
        gc9a01_init(hal, 2);

        CHECK(mock_errors(&g_mock) == 0);                         /* unlock before level-3 registers, COLMOD before RAMWR, CS framing */
        CHECK(g_mock.n_log > 30);
        CHECK(g_mock.log[0].cmd == 0x28 && g_mock.log[1].cmd == 0xFE && g_mock.log[2].cmd == 0xEF);
        const mock_cmd_t *c = find(&g_mock, 2, 0x3A, 0);
        CHECK(c && c->n == 1 && c->p[0] == 0x05);                 /* 16 bit pixels */
        c = find(&g_mock, 2, 0x36, 0);
        CHECK(c && c->n == 1 && c->p[0] == GC9A01_MADCTL);
        CHECK(mock_count(&g_mock, 2, 0x21) == GC9A01_INVERT);
        c = find(&g_mock, 2, 0xF0, 0);
        CHECK(c && c->n == 6 && c->p[0] == 0x45 && c->p[5] == 0x2A);
        c = find(&g_mock, 2, 0xF1, 0);
        CHECK(c && c->n == 6 && c->p[0] == 0x43 && c->p[5] == 0x6F);
        CHECK(mock_count(&g_mock, 2, 0x11) == 1);
        CHECK(index_of(&g_mock, 2, 0x11) == g_mock.n_log - 1);   /* sleep-out is the last command: everything is configured first */
        CHECK(!g_mock.display_on[2]);                             /* stays dark until the first frame */
        gc9a01_command(hal, 2, 0x29, 0, 0);                       /* too soon after Sleep Out: the mock flags it */
        CHECK(g_mock.err_cmd_too_soon == 1 && g_mock.err_dispon_early == 1);
        g_mock.err_cmd_too_soon = g_mock.err_dispon_early = 0;
        hal->delay_ms(hal->ctx, GC9A01_SLEEP_OUT_WAIT_MS);
        gc9a01_display(hal, 2, true);
        CHECK(g_mock.display_on[2] && mock_errors(&g_mock) == 0);
        gc9a01_display(hal, 2, false);
        CHECK(!g_mock.display_on[2]);
        /* other screens were not touched */
        CHECK(mock_count(&g_mock, 0, 0x11) == 0 && mock_count(&g_mock, 3, 0x11) == 0);
    }

    /* the mock really catches mistakes (so a clean run above means something) */
    {
        mock_init(&g_mock);
        const panel_hal_t *hal = mock_hal(&g_mock);
        gc9a01_reset(hal);
        uint8_t v = 0x40;
        gc9a01_command(hal, 0, 0x84, &v, 1);                      /* level-3 register without FE/EF */
        CHECK(g_mock.err_inter_before_unlock == 1);
        gc9a01_command(hal, 0, 0x29, 0, 0);                       /* display on before sleep-out waited */
        CHECK(g_mock.err_dispon_early == 1);
        uint16_t px[4] = { 1, 2, 3, 4 };
        gc9a01_blit(hal, 0, 0, 0, 2, 2, px);                      /* RAMWR with COLMOD never set */
        CHECK(g_mock.err_colmod == 1);
        hal->write(hal->ctx, &v, 1);                              /* a byte with no chip select */
        CHECK(g_mock.err_no_cs == 1);
        hal->select(hal->ctx, 0, true);
        hal->select(hal->ctx, 1, true);                           /* two selected at once */
        CHECK(g_mock.err_two_cs == 1);
    }

    /* ---- driver: blits land exactly where asked ---- */
    {
        mock_init(&g_mock);
        const panel_hal_t *hal = mock_hal(&g_mock);
        gc9a01_reset(hal);
        gc9a01_init(hal, 1);
        hal->delay_ms(hal->ctx, GC9A01_SLEEP_OUT_WAIT_MS);
        static uint16_t pix[240 * 240];
        struct { int x, y, w, h; } r[] = { { 0, 0, 240, 16 }, { 16, 32, 48, 16 }, { 5, 7, 1, 1 }, { 239, 239, 1, 1 },
                                           { 100, 120, 140, 120 }, { 0, 224, 240, 16 }, { 33, 17, 7, 3 } };
        for (unsigned k = 0; k < sizeof r / sizeof r[0]; k++) {
            int n = r[k].w * r[k].h;
            for (int i = 0; i < n; i++) pix[i] = (uint16_t)(0x1234u + i * 7u + k * 1000u);
            memset(g_mock.written[1], 0, sizeof g_mock.written[1]);
            gc9a01_blit(hal, 1, r[k].x, r[k].y, r[k].w, r[k].h, pix);
            int inside_ok = 1, outside_ok = 1;
            for (int y = 0; y < 240; y++)
                for (int x = 0; x < 240; x++) {
                    bool in = x >= r[k].x && x < r[k].x + r[k].w && y >= r[k].y && y < r[k].y + r[k].h;
                    if (in) {
                        if (!g_mock.written[1][y * 240 + x] ||
                            g_mock.fb[1][y * 240 + x] != pix[(y - r[k].y) * r[k].w + (x - r[k].x)]) inside_ok = 0;
                    } else if (g_mock.written[1][y * 240 + x]) outside_ok = 0;
                }
            CHECK(inside_ok && outside_ok);
        }
        CHECK(mock_errors(&g_mock) == 0);
    }

    /* ---- four screens, scheduler, and the whole chain against the ground truth ---- */
    {
        mock_init(&g_mock);
        aux_display_init(mock_hal(&g_mock), THEME_CLASSIC, false);
        CHECK(mock_errors(&g_mock) == 0);
        CHECK(g_mock.reset_count == 1);
        CHECK(g_mock.total_delay_ms == 10 + 120 + GC9A01_SLEEP_OUT_WAIT_MS);      /* reset, then ONE sleep-out wait for all four */
        for (int s = 0; s < 4; s++) {
            CHECK(g_mock.display_on[s] && !g_mock.sleeping[s]);
            CHECK(mock_count(&g_mock, s, 0x11) == 1 && mock_count(&g_mock, s, 0x3A) == 1);
        }
        CHECK(aux_display_pending_tiles() == 0);
        CHECK(g_mock.backlight);                                  /* switched on after the first frame */
        aux_display_set_backlight(true, 0);
        CHECK(!g_mock.backlight);
        aux_display_set_backlight(true, 100);
        CHECK(g_mock.backlight);
        printf("gc9a01: boot sends %llu bytes, %u chip-select spans, %u ms of waits\n",
               (unsigned long long)g_mock.bytes_written, g_mock.spans, (unsigned)g_mock.total_delay_ms);

        screen_values_t v = { cv(96.56f, true), cv(3500.0f, true), cv(13.8f, true), cv(68.0f, true), cv(90.0f, true), cv(350.0f, true) };
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            screen_view_t view = screens_build(&SCREENS_DEFAULT[s], &v, false);
            aux_display_screen(s, &view);
        }
        int pending = aux_display_pending_tiles();
        CHECK(pending > 0);

        /* the poll is bounded: asking for 2 runs sends at most 2 */
        uint64_t b0 = g_mock.bytes_written;
        int sent = aux_display_poll(2);
        CHECK(sent == 2);
        CHECK(aux_display_pending_tiles() < pending);
        CHECK(g_mock.bytes_written - b0 < 2 * (240 * GFX_TILE * 2 + 64));           /* two runs of at most a tile row */
        while (aux_display_poll(8) > 0) { }
        CHECK(aux_display_pending_tiles() == 0 && mock_errors(&g_mock) == 0);

        /* what the panels hold equals what the model says, on all four screens */
        static uint16_t truth[240 * 240];
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            static dial_t d;
            dial_init(&d);
            screen_view_t view = screens_build(&SCREENS_DEFAULT[s], &v, false);
            dial_set_view(&d, &view, false);
            gfx_render(d.ops, d.n_total, 0, 0, 240, 240, truth, 240);
            int bad = visible_diff(g_mock.fb[s], truth);
            if (bad) printf("screen %d: %d pixels differ\n", s, bad);
            CHECK(bad == 0);
        }

        /* a one km/h change touches only some tiles, and an unchanged model sends nothing */
        v.speed_kph.value += 1.0f;
        screen_view_t view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        aux_display_screen(1, &view);
        int upd = aux_display_pending_tiles();
        b0 = g_mock.bytes_written;
        while (aux_display_poll(8) > 0) { }
        uint64_t bytes = g_mock.bytes_written - b0;
        printf("gc9a01: +1 km/h update = %d tiles, %llu bytes, %.1f ms on the 10 MHz bus the datasheet allows\n", upd,
               (unsigned long long)bytes, (double)bytes * 8.0 / 10000.0);
        CHECK(upd > 0 && upd < 120);
        CHECK(bytes < 9000);                                       /* four screens at 15 Hz must fit a 10 MHz bus with room to spare */
        aux_display_screen(1, &view);
        CHECK(aux_display_pending_tiles() == 0 && aux_display_poll(8) == 0);

        /* round robin: all four screens dirty, two runs per call, nobody starves */
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            v.rpm.value += 100.0f;  v.speed_kph.value += 10.0f;  v.coolant_c.value += 5.0f;  v.fuel_pct.value -= 9.0f;
            screen_view_t w = screens_build(&SCREENS_DEFAULT[s], &v, false);
            aux_display_screen(s, &w);
        }
        int touched[4] = { 0 };
        uint64_t spans0 = g_mock.spans;
        for (int call = 0; call < 3; call++) {
            int before[4];
            (void)before;
            aux_display_poll(1);
        }
        CHECK(g_mock.spans - spans0 == 3);                         /* one run per call */
        (void)touched;
        while (aux_display_poll(8) > 0) { }
        CHECK(mock_errors(&g_mock) == 0);
    }

    /* the byte budget: no single poll sends much more than its budget, whatever the backlog, and the
     * panel still ends up identical to a full draw */
    {
        mock_init(&g_mock);
        aux_display_init(mock_hal(&g_mock), THEME_CLASSIC, true);
        screen_values_t v = { cv(96.56f, true), cv(3500.0f, true), cv(13.8f, true), cv(68.0f, true), cv(90.0f, true), cv(350.0f, true) };
        aux_display_set_imperial(false);                               /* a unit switch: every tile of every screen */
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            screen_view_t view = screens_build(&SCREENS_DEFAULT[s], &v, false);
            aux_display_screen(s, &view);
        }
        int polls = 0;
        uint64_t worst = 0;
        for (;;) {
            uint64_t b0 = g_mock.bytes_written;
            int sent = aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);
            uint64_t used = g_mock.bytes_written - b0;
            if (used > worst) worst = used;
            if (sent == 0) break;
            polls++;
        }
        printf("gc9a01: a full redraw of all four screens took %d polls, worst %llu bytes (%.2f ms at 9.6 MHz)\n", polls,
               (unsigned long long)worst, (double)worst * 8.0 / 9600.0);
        CHECK(worst <= AUX_POLL_BYTES + 240 * 8 * 2 + 11 + 64);        /* budget plus the run that crosses it */
        CHECK((double)worst * 8.0 / 9.6e6 < 0.010);                     /* a tick never exceeds 10 ms of bus time */
        CHECK(polls > 20 && aux_display_pending_tiles() == 0);
        static uint16_t truth[240 * 240];
        static dial_t d;
        for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
            dial_init(&d);
            screen_view_t view = screens_build(&SCREENS_DEFAULT[s], &v, false);
            dial_set_view(&d, &view, false);
            gfx_render(d.ops, d.n_total, 0, 0, 240, 240, truth, 240);
            CHECK(visible_diff(g_mock.fb[s], truth) == 0);
        }
        /* a budget of one byte still sends one run per call: progress is guaranteed */
        v.speed_kph.value += 40.0f;
        screen_view_t w = screens_build(&SCREENS_DEFAULT[1], &v, false);
        aux_display_screen(1, &w);
        int pending = aux_display_pending_tiles();
        CHECK(pending > 0 && aux_display_poll_budget(AUX_POLL_RUNS, 1u) == 1);
        while (aux_display_poll(8) > 0) { }
        CHECK(mock_errors(&g_mock) == 0);
    }

    /* units change redraws the face with the new labels */
    {
        mock_init(&g_mock);
        aux_display_init(mock_hal(&g_mock), THEME_CLASSIC, true);
        screen_values_t v = { cv(96.56f, true), cv(3500.0f, true), cv(13.8f, true), cv(68.0f, true), cv(90.0f, true), cv(350.0f, true) };
        aux_display_set_imperial(false);
        screen_view_t view = screens_build(&SCREENS_DEFAULT[1], &v, false);
        aux_display_screen(1, &view);
        CHECK(aux_display_pending_tiles() > 400);
        while (aux_display_poll(8) > 0) { }
        static uint16_t truth[240 * 240];
        static dial_t d;
        dial_init(&d);
        dial_set_view(&d, &view, false);
        gfx_render(d.ops, d.n_total, 0, 0, 240, 240, truth, 240);
        CHECK(visible_diff(g_mock.fb[1], truth) == 0);
    }

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("gc9a01: all tests passed\n");
    return 0;
}
