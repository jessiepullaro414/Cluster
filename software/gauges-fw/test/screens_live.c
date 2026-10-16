/*
 * Live host run of the real screen chain, for development.
 *
 * Reads vehicle-state lines on stdin (the "CL1 ..." text the Android app sends, see
 * ../../android/cluster-app/.../core/Telemetry.java), runs the SAME code the firmware uses
 * (screens.c -> dial.c -> gfx.c -> gc9a01.c -> aux_display.c) in the firmware's loop shape
 * (a 10 ms tick, a bounded number of tile runs per tick) into the mock panel, and writes what
 * the four panels hold to stdout as binary frames for tools/live_screens.py to display.
 *
 * Like the firmware, it never shows a stale number: if no line arrives for one second every
 * input becomes invalid and the screens show dashes.
 *
 * Frame: "CLF1", 8 x uint32 stats, then 4 x 240 x 240 RGB565 (little endian), screen 0..3.
 *   stats: bytes_lo, bytes_hi, runs, pending_tiles, rx_lines, alive, last_rx_age_ms, ticks
 */
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "aux_display.h"
#include "panel_mock.h"

#define AUX_RUNS_PER_TICK 12            /* same as src/main.c */
#define STALE_MS          1000

static mock_t g_mock;

static uint64_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
}

typedef struct {
    chosen_t speed_kph, rpm, battery_v, fuel_pct, coolant_c, oil_kpa;
    bool imperial;
} state_t;

static void set(chosen_t *c, const char *v)
{
    if (v[0] == '-' && v[1] == 0) { c->valid = false; c->value = 0.0f; c->src = SRC_NONE; return; }
    c->value = strtof(v, 0);
    c->valid = true;
    c->src = SRC_LOCAL;
}

/* "CL1 imperial=1 speed=96.56 rpm=3500 ..." ; unknown keys are ignored. Returns false if not a CL1 line. */
static bool parse(char *line, state_t *s)
{
    char *save = 0;
    char *tok = strtok_r(line, " \r\t", &save);
    if (!tok || strcmp(tok, "CL1") != 0) return false;
    while ((tok = strtok_r(0, " \r\t", &save)) != 0) {
        char *eq = strchr(tok, '=');
        if (!eq) continue;
        *eq = 0;
        const char *k = tok, *v = eq + 1;
        if (!strcmp(k, "imperial")) s->imperial = v[0] == '1';
        else if (!strcmp(k, "speed")) set(&s->speed_kph, v);
        else if (!strcmp(k, "rpm")) set(&s->rpm, v);
        else if (!strcmp(k, "batt")) set(&s->battery_v, v);
        else if (!strcmp(k, "fuel")) set(&s->fuel_pct, v);
        else if (!strcmp(k, "cool")) set(&s->coolant_c, v);
        else if (!strcmp(k, "oil")) set(&s->oil_kpa, v);
    }
    return true;
}

static void put32(uint32_t v) { fwrite(&v, 4, 1, stdout); }

static void send_frame(uint64_t bytes, uint32_t runs, uint32_t rx, bool alive, uint64_t age, uint32_t ticks)
{
    fwrite("CLF1", 1, 4, stdout);
    put32((uint32_t)bytes); put32((uint32_t)(bytes >> 32)); put32(runs);
    put32((uint32_t)aux_display_pending_tiles()); put32(rx); put32(alive ? 1u : 0u);
    put32((uint32_t)age); put32(ticks);
    for (int s = 0; s < 4; s++) fwrite(g_mock.fb[s], 2, 240 * 240, stdout);
    fflush(stdout);
}

int main(void)
{
    state_t st;
    memset(&st, 0, sizeof st);
    st.imperial = true;

    mock_init(&g_mock);
    aux_display_init(mock_hal(&g_mock), SCREENS_DEFAULT, st.imperial);
    if (mock_errors(&g_mock)) fprintf(stderr, "screens_live: panel protocol errors at init: %d\n", mock_errors(&g_mock));

    char buf[4096];
    size_t have = 0;
    uint64_t last_rx = 0, last_frame = 0, next_tick = now_ms();
    uint32_t rx_lines = 0, ticks = 0, runs_total = 0;
    bool had_data = false, eof = false;

    send_frame(g_mock.bytes_written, 0, 0, false, 0, 0);
    last_frame = now_ms();

    while (!eof) {
        uint64_t t = now_ms();
        if (t < next_tick) {
            struct timespec nap = { 0, (long)(next_tick - t) * 1000000L };
            nanosleep(&nap, 0);
            t = now_ms();
        }
        next_tick += 10;
        if (next_tick + 100 < t) next_tick = t;                 /* fell behind: do not burst */
        ticks++;

        /* new data */
        struct pollfd pfd = { 0, POLLIN, 0 };
        while (poll(&pfd, 1, 0) > 0 && (pfd.revents & (POLLIN | POLLHUP))) {
            ssize_t n = read(0, buf + have, sizeof buf - 1 - have);
            if (n <= 0) { if (n == 0 || errno != EINTR) eof = true; break; }
            have += (size_t)n;
            buf[have] = 0;
            char *start = buf, *nl;
            while ((nl = strchr(start, '\n')) != 0) {
                *nl = 0;
                if (parse(start, &st)) { rx_lines++; last_rx = t; had_data = true; }
                start = nl + 1;
            }
            have = (size_t)(buf + have - start);
            memmove(buf, start, have);
            if (have > sizeof buf - 64) have = 0;               /* garbage without newlines */
        }

        bool alive = had_data && (t - last_rx) <= STALE_MS;
        screen_values_t v;
        if (alive) {
            v.speed_kph = st.speed_kph; v.rpm = st.rpm; v.battery_v = st.battery_v;
            v.fuel_pct = st.fuel_pct; v.coolant_c = st.coolant_c; v.oil_kpa = st.oil_kpa;
        } else {
            chosen_t none = { 0.0f, false, SRC_NONE };
            v.speed_kph = v.rpm = v.battery_v = v.fuel_pct = v.coolant_c = v.oil_kpa = none;
        }
        aux_display_set_imperial(st.imperial);
        for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
            screen_view_t view = screens_build(&SCREENS_DEFAULT[i], &v, st.imperial);
            aux_display_screen(i, &view);
        }
        uint64_t before = g_mock.bytes_written;
        int sent = aux_display_poll(AUX_RUNS_PER_TICK);
        runs_total += (uint32_t)sent;
        bool changed = g_mock.bytes_written != before;

        t = now_ms();
        if ((changed && t - last_frame >= 33) || t - last_frame >= 500) {
            send_frame(g_mock.bytes_written, runs_total, rx_lines, alive, had_data ? t - last_rx : 0, ticks);
            last_frame = t;
        }
    }
    return 0;
}
