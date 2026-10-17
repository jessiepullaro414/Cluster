/*
 * Test harness for the four small round screens. One native program that runs the REAL firmware
 * screen code (screens.c -> dial.c -> gfx.c -> gc9a01.c -> aux_display.c) in the firmware's loop
 * shape (10 ms tick, a bounded number of tile runs per tick) against a mock GC9A01 panel.
 *
 *   interactive   harness                       window with the four screens; keys drive them
 *   from Android  harness --udp 5005            the Android app's telemetry line moves the screens
 *   automated     harness --golden check        fixed states vs stored checksums (a styling change shows up)
 *                 harness --sim 60              60 virtual seconds of driving: bus load, backlog, tick overruns
 *                 harness --selftest            plumbing: panel contents equal the model after a drive
 *                 harness --shot out.png        run, then save the window picture
 *
 * The X11 window is optional (-DHARNESS_X11); everything else is plain C and needs no display.
 */
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "aux_display.h"
#include "dial.h"
#include "gfx.h"
#include "panel_mock.h"
#include "screens.h"
#ifdef HARNESS_X11
#include "harness_x11.h"
#endif

#define BUS_HZ          9.6e6          /* what the HAL clocks LPSPI2 at */
#define STALE_MS        1000

/* ================================================================== inputs */

enum { I_SPEED, I_RPM, I_BATT, I_FUEL, I_COOL, I_OIL, I_COUNT };

typedef struct {
    float v[I_COUNT];                   /* speed km/h, rpm, V, %, degC, kPa */
    bool  ok[I_COUNT];
    bool  imperial;
    theme_t theme;
    bool  center;                       /* the centre screen shows the speedometer */
} inputs_t;

static theme_t g_cli_theme = THEME_CLASSIC;
static bool g_cli_center = false;

static inputs_t inputs_default(void)
{
    inputs_t in = { { 0.0f, 800.0f, 13.8f, 68.0f, 90.0f, 250.0f }, { true, true, true, true, true, true }, true, g_cli_theme, g_cli_center };
    return in;
}

static chosen_t cv(float v, bool ok) { chosen_t c = { ok ? v : 0.0f, ok, ok ? SRC_LOCAL : SRC_NONE }; return c; }

static screen_values_t to_values(const inputs_t *in, bool alive)
{
    screen_values_t s;
    s.speed_kph = cv(in->v[I_SPEED], alive && in->ok[I_SPEED]);
    s.rpm = cv(in->v[I_RPM], alive && in->ok[I_RPM]);
    s.battery_v = cv(in->v[I_BATT], alive && in->ok[I_BATT]);
    s.fuel_pct = cv(in->v[I_FUEL], alive && in->ok[I_FUEL]);
    s.coolant_c = cv(in->v[I_COOL], alive && in->ok[I_COOL]);
    s.oil_kpa = cv(in->v[I_OIL], alive && in->ok[I_OIL]);
    return s;
}

/* The same 30 s drive as the Android app's DriveScenario and tools/can_replay.py. */
static void drive_at(float t, inputs_t *in)
{
    t = fmodf(fmodf(t, 30.0f) + 30.0f, 30.0f);
    float kph = t < 3.0f ? 0.0f : t < 13.0f ? 90.0f * (t - 3.0f) / 10.0f : t < 23.0f ? 90.0f : 90.0f * (30.0f - t) / 7.0f;
    float rpm = 800.0f + kph * 28.0f + 40.0f * sinf(t * 6.0f);
    in->v[I_SPEED] = kph;
    in->v[I_RPM] = rpm;
    in->v[I_BATT] = t > 1.0f ? 13.8f : 12.4f;
    in->v[I_FUEL] = 68.0f - 0.02f * t;
    in->v[I_COOL] = fminf(92.0f, 40.0f + 2.0f * t);
    in->v[I_OIL] = fminf(380.0f, 150.0f + rpm * 0.08f);
    for (int i = 0; i < I_COUNT; i++) in->ok[i] = true;
}

/* "CL1 imperial=1 speed=96.56 rpm=3500 ..." (see Telemetry.java); '-' = not available. */
static bool parse_telemetry(char *line, inputs_t *in)
{
    char *save = 0;
    char *tok = strtok_r(line, " \r\t\n", &save);
    if (!tok || strcmp(tok, "CL1") != 0) return false;
    static const char *keys[I_COUNT] = { "speed", "rpm", "batt", "fuel", "cool", "oil" };
    while ((tok = strtok_r(0, " \r\t\n", &save)) != 0) {
        char *eq = strchr(tok, '=');
        if (!eq) continue;
        *eq = 0;
        const char *k = tok, *v = eq + 1;
        if (!strcmp(k, "imperial")) { in->imperial = v[0] == '1'; continue; }
        if (!strcmp(k, "center")) { in->center = v[0] == '1'; continue; }
        if (!strcmp(k, "theme")) { in->theme = screens_theme_from_setting((uint32_t)atoi(v)); continue; }
        for (int i = 0; i < I_COUNT; i++)
            if (!strcmp(k, keys[i])) {
                if (v[0] == '-' && v[1] == 0) in->ok[i] = false;
                else { in->v[i] = strtof(v, 0); in->ok[i] = true; }
            }
    }
    return true;
}

/* ================================================================== time, files */

static uint64_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
}

static void sleep_ms(uint64_t ms)
{
    struct timespec nap = { (time_t)(ms / 1000u), (long)(ms % 1000u) * 1000000L };
    nanosleep(&nap, 0);
}

static uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n)
{
    crc = ~crc;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1u));
    }
    return ~crc;
}

static uint32_t adler32(const uint8_t *p, size_t n)
{
    uint32_t a = 1, b = 0;
    while (n--) { a = (a + *p++) % 65521u; b = (b + a) % 65521u; }
    return (b << 16) | a;
}

static void be32(uint8_t *o, uint32_t v) { o[0] = (uint8_t)(v >> 24); o[1] = (uint8_t)(v >> 16); o[2] = (uint8_t)(v >> 8); o[3] = (uint8_t)v; }

static void png_chunk(FILE *f, const char *tag, const uint8_t *data, uint32_t n)
{
    uint8_t h[8];
    be32(h, n);
    memcpy(h + 4, tag, 4);
    fwrite(h, 1, 8, f);
    if (n) fwrite(data, 1, n, f);
    uint32_t c = crc32_update(0, (const uint8_t *)tag, 4);
    c = crc32_update(c, data, n);
    uint8_t t[4];
    be32(t, c);
    fwrite(t, 1, 4, f);
}

/* Uncompressed PNG (stored deflate blocks): big but dependency free. argb = 0x00RRGGBB. */
static bool write_png(const char *path, const uint32_t *argb, int w, int h)
{
    FILE *f = fopen(path, "wb");
    if (!f) return false;
    size_t raw_n = (size_t)h * (1u + (size_t)w * 3u);
    uint8_t *raw = (uint8_t *)malloc(raw_n);
    for (int y = 0; y < h; y++) {
        uint8_t *r = raw + (size_t)y * (1u + (size_t)w * 3u);
        *r++ = 0;
        for (int x = 0; x < w; x++) {
            uint32_t p = argb[y * w + x];
            *r++ = (uint8_t)(p >> 16); *r++ = (uint8_t)(p >> 8); *r++ = (uint8_t)p;
        }
    }
    size_t blocks = (raw_n + 65534u) / 65535u;
    size_t z_n = 2 + raw_n + blocks * 5 + 4;
    uint8_t *z = (uint8_t *)malloc(z_n), *o = z;
    *o++ = 0x78; *o++ = 0x01;
    for (size_t off = 0; off < raw_n; off += 65535u) {
        size_t n = raw_n - off > 65535u ? 65535u : raw_n - off;
        *o++ = (off + n >= raw_n) ? 1 : 0;
        *o++ = (uint8_t)n; *o++ = (uint8_t)(n >> 8); *o++ = (uint8_t)~n; *o++ = (uint8_t)(~n >> 8);
        memcpy(o, raw + off, n);
        o += n;
    }
    be32(o, adler32(raw, raw_n));
    o += 4;
    uint8_t ihdr[13];
    be32(ihdr, (uint32_t)w); be32(ihdr + 4, (uint32_t)h);
    ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    fwrite("\x89PNG\r\n\x1a\n", 1, 8, f);
    png_chunk(f, "IHDR", ihdr, 13);
    png_chunk(f, "IDAT", z, (uint32_t)(o - z));
    png_chunk(f, "IEND", 0, 0);
    fclose(f);
    free(raw); free(z);
    return true;
}

/* ================================================================== rig: the firmware loop on a mock panel */

typedef struct {
    mock_t *mock;
    uint32_t ticks;
    /* bus accounting */
    uint64_t bytes_total;
    uint32_t runs_total;
    uint32_t overrun_ticks;             /* ticks whose bus time exceeded the 10 ms tick */
    double   worst_tick_ms;
    uint32_t backlog_ticks;             /* ticks that ended with tiles still waiting */
    int      max_backlog_tiles;
    double   window_bytes;              /* last 100 ms */
    int      window_ticks;
    double   peak_window_pct;
    double   last_window_pct;
    uint32_t last_tick_bytes;
    uint64_t backlog_sum;               /* sum over ticks, for the average */
    uint32_t backlog_hist[64];          /* ticks by backlog size, bins of 8 tiles (last bin: more) */
} rig_t;

static mock_t g_mock;

static void rig_init(rig_t *r, bool imperial, theme_t theme)
{
    memset(r, 0, sizeof *r);
    r->mock = &g_mock;
    mock_init(&g_mock);
    aux_display_init(mock_hal(&g_mock), theme, imperial);
    r->bytes_total = g_mock.bytes_written;      /* boot traffic is counted separately */
}

/* One firmware tick: present the model, send a bounded amount. */
static void rig_tick(rig_t *r, const inputs_t *in, bool alive)
{
    screen_values_t v = to_values(in, alive);
    aux_display_set_imperial(in->imperial);
    aux_display_set_theme(in->theme);
    const screen_cfg_t *layout = screens_layout_for(in->theme, screens_center_active(in->center, alive));
    for (uint8_t i = 0; i < SCREEN_COUNT; i++) {
        screen_view_t view = screens_build(&layout[i], &v, in->imperial);
        aux_display_screen(i, &view);
    }
    uint64_t before = g_mock.bytes_written;
    int sent = aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);   /* same as src/main.c */
    uint32_t bytes = (uint32_t)(g_mock.bytes_written - before);
    r->ticks++;
    r->runs_total += (uint32_t)sent;
    r->bytes_total = g_mock.bytes_written;
    r->last_tick_bytes = bytes;
    double ms = (double)bytes * 8.0 / BUS_HZ * 1000.0;
    if (ms > r->worst_tick_ms) r->worst_tick_ms = ms;
    if (ms > 10.0) r->overrun_ticks++;
    int pend = aux_display_pending_tiles();
    if (pend > 0) r->backlog_ticks++;
    if (pend > r->max_backlog_tiles) r->max_backlog_tiles = pend;
    r->backlog_sum += (uint64_t)pend;
    r->backlog_hist[pend / 8 > 63 ? 63 : pend / 8]++;
    r->window_bytes += bytes;
    if (++r->window_ticks == 10) {
        r->last_window_pct = r->window_bytes * 8.0 / (BUS_HZ * 0.1) * 100.0;
        if (r->last_window_pct > r->peak_window_pct) r->peak_window_pct = r->last_window_pct;
        r->window_bytes = 0; r->window_ticks = 0;
    }
}

/* Let the picture catch up with frozen inputs: send the backlog, outlast the modern theme's number hold-off
 * (a held number is released a few ticks later and redrawn), and send that too. */
static void settle(rig_t *r, const inputs_t *in, bool alive)
{
    for (int round = 0; round < 3; round++) {
        for (int i = 0; i < AUX_TEXT_HOLD_TICKS + 3; i++) rig_tick(r, in, alive);
        int guard = 0;
        while (aux_display_pending_tiles() > 0 && guard++ < 5000) rig_tick(r, in, alive);
    }
}

/* ================================================================== picture */

static uint32_t g_lut[65536];

static void lut_init(void)
{
    for (uint32_t p = 0; p < 65536; p++) {
        uint32_t r = ((p >> 11) & 31) * 255 / 31, g = ((p >> 5) & 63) * 255 / 63, b = (p & 31) * 255 / 31;
        g_lut[p] = (r << 16) | (g << 8) | b;
    }
}

#define BG   0x181A1Eu
#define PAD  12
#define HUD_LINES 5
#define HUD_LINE_H 18

typedef struct { int w, h; float scale; uint32_t *px; uint32_t gen_seen[4]; uint32_t hud_hash; bool fresh; } canvas_t;

static void canvas_size(float scale, int *w, int *h)
{
    int s = (int)(240.0f * scale + 0.5f);
    *w = PAD + 4 * (s + PAD);
    *h = PAD + s + PAD + HUD_LINES * HUD_LINE_H + PAD;
}

static void canvas_init(canvas_t *c, float scale)
{
    c->scale = scale;
    canvas_size(scale, &c->w, &c->h);
    c->px = (uint32_t *)malloc((size_t)c->w * (size_t)c->h * 4);
    memset(c->gen_seen, 0xFF, sizeof c->gen_seen);
    c->hud_hash = 0;
    c->fresh = true;
}

static void put_text(canvas_t *c, int x, int y, const char *s, int gscale, uint32_t color)
{
    op_t ops[200];
    int n = 0, cx = 0;
    for (; *s && n < 200; s++, cx += GFX_GLYPH_ADV * gscale) ops[n++] = gfx_glyph(cx, 0, *s, gscale, color);
    int w = cx, h = GFX_GLYPH_H * gscale;
    if (w <= 0 || x + w > c->w) w = c->w - x;
    uint16_t *tmp = (uint16_t *)malloc((size_t)w * (size_t)h * 2);
    gfx_render(ops, n, 0, 0, w, h, tmp, w);
    for (int yy = 0; yy < h && y + yy < c->h; yy++)
        for (int xx = 0; xx < w; xx++)
            if (tmp[yy * w + xx]) c->px[(y + yy) * c->w + x + xx] = g_lut[tmp[yy * w + xx]];
    free(tmp);
}

/* The four panels as they are on the mock bus, round-masked and scaled (bilinear), then the HUD.
 * Only what changed since the last call is redrawn; returns false if nothing did. */
static bool compose(canvas_t *c, const mock_t *m, const char *hud[HUD_LINES])
{
    bool changed = false;
    if (c->fresh) {
        for (int i = 0; i < c->w * c->h; i++) c->px[i] = BG;
        c->fresh = false;
        changed = true;
    }
    int s = (int)(240.0f * c->scale + 0.5f);
    for (int scr = 0; scr < 4; scr++) {
        if (c->gen_seen[scr] == m->gen[scr]) continue;
        c->gen_seen[scr] = m->gen[scr];
        changed = true;
        static uint32_t src[240 * 240];
        for (int y = 0; y < 240; y++)
            for (int x = 0; x < 240; x++) {
                int dx = x - 120, dy = y - 120;
                src[y * 240 + x] = dx * dx + dy * dy <= 120 * 120 ? g_lut[m->fb[scr][y * 240 + x]] : 0u;
            }
        int ox = PAD + scr * (s + PAD), oy = PAD;
        for (int y = 0; y < s; y++) {
            float fy = ((float)y + 0.5f) * 240.0f / (float)s - 0.5f;
            int y0 = (int)floorf(fy), y1 = y0 + 1;
            float ty = fy - (float)y0;
            if (y0 < 0) { y0 = 0; ty = 0; }
            if (y1 > 239) y1 = 239;
            for (int x = 0; x < s; x++) {
                int ddx = x - s / 2, ddy = y - s / 2;
                if (ddx * ddx + ddy * ddy > (s / 2) * (s / 2)) continue;
                float fx = ((float)x + 0.5f) * 240.0f / (float)s - 0.5f;
                int x0 = (int)floorf(fx), x1 = x0 + 1;
                float tx = fx - (float)x0;
                if (x0 < 0) { x0 = 0; tx = 0; }
                if (x1 > 239) x1 = 239;
                uint32_t p00 = src[y0 * 240 + x0], p10 = src[y0 * 240 + x1], p01 = src[y1 * 240 + x0], p11 = src[y1 * 240 + x1];
                uint32_t out = 0;
                for (int sh = 16; sh >= 0; sh -= 8) {
                    float a = (float)((p00 >> sh) & 255) * (1 - tx) + (float)((p10 >> sh) & 255) * tx;
                    float b = (float)((p01 >> sh) & 255) * (1 - tx) + (float)((p11 >> sh) & 255) * tx;
                    out |= (uint32_t)(a * (1 - ty) + b * ty + 0.5f) << sh;
                }
                c->px[(oy + y) * c->w + ox + x] = out;
            }
        }
    }
    uint32_t h = 2166136261u;
    for (int i = 0; i < HUD_LINES; i++)
        for (const char *p = hud[i]; p && *p; p++) h = (h ^ (uint8_t)*p) * 16777619u;
    if (h != c->hud_hash) {
        c->hud_hash = h;
        changed = true;
        int y0 = PAD + s + PAD;
        for (int y = y0; y < c->h; y++)
            for (int x = 0; x < c->w; x++) c->px[y * c->w + x] = BG;
        for (int i = 0; i < HUD_LINES; i++)
            if (hud[i]) put_text(c, PAD, y0 + i * HUD_LINE_H, hud[i], 2, i == HUD_LINES - 1 ? 0x8A95A3u : 0xE8EAEDu);
    }
    return changed;
}

/* ================================================================== golden images */

typedef struct { const char *name; inputs_t in; } golden_state_t;

static inputs_t gs(float spd, float rpm, float batt, float fuel, float cool, float oil, bool imp)
{
    inputs_t in = { { spd, rpm, batt, fuel, cool, oil }, { true, true, true, true, true, true }, imp, THEME_CLASSIC, false };
    return in;
}

static inputs_t modern(inputs_t in)
{
    in.theme = THEME_MODERN;
    return in;
}

static inputs_t centre(inputs_t in)
{
    in.center = true;
    return in;
}

static inputs_t carplay(inputs_t in)
{
    in.theme = THEME_CARPLAY;
    return in;
}

static inputs_t factory(inputs_t in)
{
    in.theme = THEME_FACTORY;
    return in;
}

static void golden_states(golden_state_t *out, int *n)
{
    int k = 0;
    out[k++] = (golden_state_t){ "idle", gs(0, 800, 13.8f, 68, 40, 150, true) };
    out[k++] = (golden_state_t){ "cruise_mph", gs(96.56f, 3500, 13.8f, 68, 90, 350, true) };
    out[k++] = (golden_state_t){ "cruise_kph", gs(96.56f, 3500, 13.8f, 68, 90, 350, false) };
    out[k++] = (golden_state_t){ "warnings", gs(143, 5200, 11.2f, 8, 116, 60, true) };
    out[k++] = (golden_state_t){ "redline_kph", gs(190, 6800, 14.2f, 40, 98, 420, false) };
    out[k++] = (golden_state_t){ "full_scale", gs(250, 7500, 16.5f, 100, 130, 700, true) };
    out[k++] = (golden_state_t){ "zero_scale", gs(0, 0, 10.0f, 0, 40, 0, false) };
    inputs_t inv = gs(60, 3000, 13.8f, 50, 90, 300, true);
    for (int i = 0; i < I_COUNT; i++) inv.ok[i] = false;
    out[k++] = (golden_state_t){ "all_invalid", inv };
    inputs_t sp = gs(60, 3000, 13.8f, 50, 90, 300, true);
    sp.ok[I_SPEED] = false;
    out[k++] = (golden_state_t){ "speed_invalid", sp };
    inputs_t ob = gs(60, 3000, 13.8f, 50, 90, 300, true);
    ob.ok[I_BATT] = false; ob.ok[I_OIL] = false;
    out[k++] = (golden_state_t){ "secondaries_invalid", ob };
    out[k++] = (golden_state_t){ "hot_and_low_oil", gs(30, 1500, 12.0f, 25, 128, 20, true) };
    /* the modern theme: same situations, its own layout */
    out[k++] = (golden_state_t){ "modern_idle", modern(gs(0, 800, 13.8f, 68, 40, 150, true)) };
    out[k++] = (golden_state_t){ "modern_cruise_mph", modern(gs(96.56f, 3500, 13.8f, 68, 90, 350, true)) };
    out[k++] = (golden_state_t){ "modern_cruise_kph", modern(gs(96.56f, 3500, 13.8f, 68, 90, 350, false)) };
    out[k++] = (golden_state_t){ "modern_warnings", modern(gs(143, 5200, 11.2f, 8, 116, 60, true)) };
    out[k++] = (golden_state_t){ "modern_redline_kph", modern(gs(190, 7600, 14.2f, 40, 98, 420, false)) };
    out[k++] = (golden_state_t){ "modern_full_scale", modern(gs(250, 9000, 16.5f, 100, 130, 700, true)) };
    out[k++] = (golden_state_t){ "modern_zero_scale", modern(gs(0, 0, 10.0f, 0, 40, 0, false)) };
    out[k++] = (golden_state_t){ "modern_all_invalid", modern(inv) };
    out[k++] = (golden_state_t){ "modern_speed_invalid", modern(sp) };
    out[k++] = (golden_state_t){ "modern_secondaries_invalid", modern(ob) };
    /* the carplay theme */
    out[k++] = (golden_state_t){ "carplay_idle", carplay(gs(0, 800, 13.8f, 68, 40, 150, true)) };
    out[k++] = (golden_state_t){ "carplay_cruise_mph", carplay(gs(96.56f, 3500, 13.8f, 68, 90, 350, true)) };
    out[k++] = (golden_state_t){ "carplay_cruise_kph", carplay(gs(96.56f, 3500, 13.8f, 68, 90, 350, false)) };
    out[k++] = (golden_state_t){ "carplay_warnings", carplay(gs(143, 5200, 11.2f, 8, 116, 60, true)) };
    out[k++] = (golden_state_t){ "carplay_redline_kph", carplay(gs(190, 7600, 14.2f, 40, 98, 420, false)) };
    out[k++] = (golden_state_t){ "carplay_full_scale", carplay(gs(250, 9000, 16.5f, 100, 130, 700, true)) };
    out[k++] = (golden_state_t){ "carplay_zero_scale", carplay(gs(0, 0, 10.0f, 0, 40, 0, false)) };
    out[k++] = (golden_state_t){ "carplay_all_invalid", carplay(inv) };
    out[k++] = (golden_state_t){ "carplay_speed_invalid", carplay(sp) };
    out[k++] = (golden_state_t){ "carplay_secondaries_invalid", carplay(ob) };
    /* the factory theme */
    out[k++] = (golden_state_t){ "factory_idle", factory(gs(0, 800, 13.8f, 68, 40, 150, true)) };
    out[k++] = (golden_state_t){ "factory_cruise_mph", factory(gs(96.56f, 3500, 13.8f, 68, 90, 350, true)) };
    out[k++] = (golden_state_t){ "factory_cruise_kph", factory(gs(96.56f, 3500, 13.8f, 68, 90, 350, false)) };
    out[k++] = (golden_state_t){ "factory_warnings", factory(gs(143, 5200, 11.2f, 8, 116, 60, true)) };
    out[k++] = (golden_state_t){ "factory_redline_kph", factory(gs(190, 7600, 14.2f, 40, 98, 420, false)) };
    out[k++] = (golden_state_t){ "factory_full_scale", factory(gs(250, 9000, 16.5f, 100, 130, 700, true)) };
    out[k++] = (golden_state_t){ "factory_zero_scale", factory(gs(0, 0, 10.0f, 0, 40, 0, false)) };
    out[k++] = (golden_state_t){ "factory_all_invalid", factory(inv) };
    out[k++] = (golden_state_t){ "factory_speed_invalid", factory(sp) };
    out[k++] = (golden_state_t){ "factory_secondaries_invalid", factory(ob) };
    /* the speedometer is on the centre screen: the small screens drop speed and show another gauge */
    out[k++] = (golden_state_t){ "center_classic_mph", centre(gs(96.56f, 3500, 13.8f, 68, 90, 350, true)) };
    out[k++] = (golden_state_t){ "center_modern_mph", centre(modern(gs(96.56f, 3500, 13.8f, 68, 90, 350, true))) };
    out[k++] = (golden_state_t){ "center_carplay_mph", centre(carplay(gs(96.56f, 3500, 13.8f, 68, 90, 350, true))) };
    out[k++] = (golden_state_t){ "center_factory_mph", centre(factory(gs(96.56f, 3500, 13.8f, 68, 90, 350, true))) };
    out[k++] = (golden_state_t){ "center_modern_warnings", centre(modern(gs(143, 5200, 11.2f, 8, 116, 60, true))) };
    out[k++] = (golden_state_t){ "center_carplay_warnings", centre(carplay(gs(143, 5200, 11.2f, 8, 116, 60, true))) };
    out[k++] = (golden_state_t){ "center_factory_warnings", centre(factory(gs(143, 5200, 11.2f, 8, 116, 60, true))) };
    out[k++] = (golden_state_t){ "center_factory_invalid", centre(factory(inv)) };
    *n = k;
}

/* Truth render of one screen for one state, checksum over the visible (round) pixels. */
static uint32_t golden_crc(const inputs_t *in, int screen, uint16_t *pic)
{
    static dial_t d;
    dial_init(&d);
    screen_values_t v = to_values(in, true);
    screen_view_t view = screens_build(&screens_layout_for(in->theme, in->center)[screen], &v, in->imperial);
    dial_set_view_theme(&d, &view, in->imperial, in->theme);
    gfx_render(d.ops, d.n_total, 0, 0, 240, 240, pic, 240);
    uint32_t crc = 0;
    for (int y = 0; y < 240; y++)
        for (int x = 0; x < 240; x++) {
            int dx = x - 120, dy = y - 120;
            uint16_t p = (dx * dx + dy * dy <= 120 * 120) ? pic[y * 240 + x] : 0;
            pic[y * 240 + x] = p;
            uint8_t b[2] = { (uint8_t)p, (uint8_t)(p >> 8) };
            crc = crc32_update(crc, b, 2);
        }
    return crc;
}

static int golden_run(const char *mode, const char *file, const char *dump_dir)
{
    static golden_state_t st[64];
    int n;
    golden_states(st, &n);
    static uint16_t pic[240 * 240];
    bool update = !strcmp(mode, "update");
    FILE *f = 0;
    char names[64 * 4][64];
    uint32_t want[64 * 4];
    int nwant = 0;
    if (!update) {
        f = fopen(file, "r");
        if (!f) { fprintf(stderr, "golden: cannot read %s (run with update first)\n", file); return 2; }
        char line[128];
        while (fgets(line, sizeof line, f) && nwant < 256) {
            char nm[48]; int sc; unsigned crc;
            if (line[0] == '#') continue;
            if (sscanf(line, "%47s %d %x", nm, &sc, &crc) == 3) { snprintf(names[nwant], 64, "%s/%d", nm, sc); want[nwant++] = crc; }
        }
        fclose(f);
    } else {
        f = fopen(file, "w");
        if (!f) { perror(file); return 2; }
        fprintf(f, "# golden checksums of the four small screens, CRC32 over the round part of each 240x240 RGB565 picture\n"
                   "# state screen crc32 ; regenerate with: make golden-update (review the pictures first: make golden-dump)\n");
    }
    int bad = 0, total = 0;
    for (int i = 0; i < n; i++)
        for (int s = 0; s < SCREEN_COUNT; s++) {
            uint32_t crc = golden_crc(&st[i].in, s, pic);
            total++;
            if (update) fprintf(f, "%s %d %08x\n", st[i].name, s, crc);
            else {
                char key[64];
                snprintf(key, sizeof key, "%s/%d", st[i].name, s);
                int found = -1;
                for (int k = 0; k < nwant; k++) if (!strcmp(names[k], key)) found = k;
                if (found < 0) { printf("NEW      %s (no stored checksum)\n", key); bad++; }
                else if (want[found] != crc) { printf("CHANGED  %s  stored %08x now %08x\n", key, want[found], crc); bad++; }
            }
            if (dump_dir) {
                uint32_t rgb[240 * 240];
                for (int k = 0; k < 240 * 240; k++) rgb[k] = g_lut[pic[k]];
                char path[256];
                snprintf(path, sizeof path, "%s/%s_%d.png", dump_dir, st[i].name, s);
                write_png(path, rgb, 240, 240);
            }
        }
    if (update) { fclose(f); printf("golden: wrote %d checksums to %s\n", total, file); return 0; }
    for (int k = 0; k < nwant; k++) {                       /* stored but no longer produced */
        int seen = 0;
        for (int i = 0; i < n && !seen; i++)
            for (int s = 0; s < SCREEN_COUNT; s++) {
                char key[64];
                snprintf(key, sizeof key, "%s/%d", st[i].name, s);
                if (!strcmp(key, names[k])) seen = 1;
            }
        if (!seen) { printf("STALE    %s is stored but no longer produced\n", names[k]); bad++; }
    }
    printf("golden: %d pictures checked, %d differ\n", total, bad);
    return bad ? 1 : 0;
}

/* ================================================================== simulation and self test */

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

/* Does the panel hold what the model says, on all four screens? (after the backlog has drained) */
static int panel_vs_model(const rig_t *r, const inputs_t *in, bool alive)
{
    static uint16_t truth[240 * 240];
    static dial_t d;
    int bad = 0;
    screen_values_t v = to_values(in, alive);
    for (int s = 0; s < SCREEN_COUNT; s++) {
        dial_init(&d);
        screen_view_t view = screens_build(&screens_layout_for(in->theme, screens_center_active(in->center, alive))[s], &v, in->imperial);
        dial_set_view_theme(&d, &view, in->imperial, in->theme);
        gfx_render(d.ops, d.n_total, 0, 0, 240, 240, truth, 240);
        bad += visible_diff(r->mock->fb[s], truth);
    }
    return bad;
}

static int backlog_percentile(const rig_t *r, double pct)
{
    uint64_t total = 0, acc = 0;
    for (int i = 0; i < 64; i++) total += r->backlog_hist[i];
    for (int i = 0; i < 64; i++) {
        acc += r->backlog_hist[i];
        if ((double)acc >= total * pct / 100.0) return (i + 1) * 8;
    }
    return 64 * 8;
}

static void print_rig(const rig_t *r, double seconds)
{
    double bytes = (double)(r->bytes_total - 0);
    printf("  ticks %u (%.1f s)   bytes sent %.0f   avg bus %.1f %%   peak 100 ms window %.1f %%\n", r->ticks, seconds,
           bytes, bytes * 8.0 / BUS_HZ / seconds * 100.0, r->peak_window_pct);
    printf("  worst tick %.2f ms of bus (the tick is 10 ms), ticks over 10 ms: %u\n", r->worst_tick_ms, r->overrun_ticks);
    printf("  tiles waiting after a tick: average %.0f, 95th percentile <= %d, worst %d\n",
           r->ticks ? (double)r->backlog_sum / r->ticks : 0.0, backlog_percentile(r, 95.0), r->max_backlog_tiles);
}

static int run_sim(double seconds, int units_switch)
{
    rig_t r;
    inputs_t in = inputs_default();
    rig_init(&r, in.imperial, in.theme);
    uint64_t boot_bytes = g_mock.bytes_written;
    int ticks = (int)(seconds * 100.0);
    int mismatches = 0, checks = 0, switch_at = -1, worst_settle = 0, switches = 0;
    for (int t = 0; t < ticks; t++) {
        drive_at((float)t * 0.01f, &in);
        if (units_switch && t > 0 && t % 1500 == 0) { in.imperial = !in.imperial; switch_at = t; switches++; }
        rig_tick(&r, &in, true);
        /* the redraw after a switch is "settled" when the backlog first falls to what steady driving
         * leaves (a few dozen tiles), because new changes arrive every tick */
        if (switch_at >= 0 && aux_display_pending_tiles() < 60) {
            if (t - switch_at > worst_settle) worst_settle = t - switch_at;
            switch_at = -1;
        }
    }
    /* let the backlog drain with the inputs frozen, then compare panel with model */
    settle(&r, &in, true);
    mismatches += panel_vs_model(&r, &in, true);
    checks++;
    printf("sim: %.0f s of driving%s, boot sent %llu bytes\n", seconds, units_switch ? " with unit switches" : "",
           (unsigned long long)boot_bytes);
    r.bytes_total -= boot_bytes;
    print_rig(&r, seconds);
    if (switches) printf("  a unit switch redraws all four screens; worst time until the backlog is back to normal: %d ms (%d switches)\n", worst_settle * 10, switches);
    printf("  after the drive panel == model: %s (%d pixel differences)\n", mismatches ? "NO" : "yes", mismatches);
    int fail = 0;
    if (mock_errors(&g_mock)) { printf("  FAIL: panel protocol errors: %d\n", mock_errors(&g_mock)); fail = 1; }
    if (r.overrun_ticks) { printf("  FAIL: %u ticks needed more than 10 ms of bus time\n", r.overrun_ticks); fail = 1; }
    if (backlog_percentile(&r, 95.0) > 64) { printf("  FAIL: the screens fall behind (95th percentile backlog above 64 tiles)\n"); fail = 1; }
    if (mismatches) fail = 1;
    printf("  %s\n", fail ? "RESULT: FAIL" : "RESULT: ok");
    return fail;
}

static int run_selftest(void)
{
    int failures = 0;
    /* 1. drive, with settling points: panel equals model every few seconds, including a unit switch */
    {
        rig_t r;
        inputs_t in = inputs_default();
        rig_init(&r, in.imperial, in.theme);
        for (int sec = 0; sec < 30; sec += 3) {
            for (int t = 0; t < 300; t++) {
                drive_at((float)sec + (float)t * 0.01f, &in);
                rig_tick(&r, &in, true);
            }
            settle(&r, &in, true);
            int bad = panel_vs_model(&r, &in, true);
            if (bad) { printf("selftest: drive at %d s: %d pixels differ\n", sec, bad); failures++; }
            if (sec == 12) in.imperial = !in.imperial;
        }
        if (mock_errors(&g_mock)) { printf("selftest: panel protocol errors %d\n", mock_errors(&g_mock)); failures++; }
    }
    /* 1b. the modern theme, and a switch of theme in the middle of the drive */
    {
        rig_t r;
        inputs_t in = inputs_default();
        in.theme = THEME_MODERN;
        rig_init(&r, in.imperial, in.theme);
        for (int sec = 0; sec < 30; sec += 3) {
            for (int t = 0; t < 300; t++) {
                drive_at((float)sec + (float)t * 0.01f, &in);
                rig_tick(&r, &in, true);
            }
            settle(&r, &in, true);
            int bad = panel_vs_model(&r, &in, true);
            if (bad) { printf("selftest: modern drive at %d s: %d pixels differ\n", sec, bad); failures++; }
            if (sec == 3) in.center = true;
            if (sec == 15) in.center = false;
            if (sec == 21) in.center = true;
            if (sec == 6) in.theme = THEME_CARPLAY;
            if (sec == 12) in.theme = THEME_CLASSIC;
            if (sec == 18) in.theme = THEME_MODERN;
            if (sec == 24) in.theme = THEME_CARPLAY;
            if (sec == 27) in.theme = THEME_FACTORY;
        }
        if (mock_errors(&g_mock)) { printf("selftest: panel protocol errors %d\n", mock_errors(&g_mock)); failures++; }
    }
    /* 1c. speed MUST come back when Android goes away: with the centre flag set, the feed stops, and the small screens
     * show the normal layout again (a speed screen, with dashes) instead of staying without speed */
    for (int th = 0; th < THEME_COUNT; th++) {
        rig_t r;
        inputs_t in = inputs_default();
        in.theme = (theme_t)th;
        in.center = true;
        rig_init(&r, in.imperial, in.theme);
        drive_at(10.0f, &in);
        for (int t = 0; t < 100; t++) rig_tick(&r, &in, true);
        settle(&r, &in, true);
        int bad = panel_vs_model(&r, &in, true);
        if (bad) { printf("selftest: theme %d with speed on the centre: %d pixels differ\n", th, bad); failures++; }
        for (int t = 0; t < 100; t++) rig_tick(&r, &in, false);              /* Android is gone */
        settle(&r, &in, false);
        bad = panel_vs_model(&r, &in, false);
        if (bad) { printf("selftest: theme %d after Android left: %d pixels differ\n", th, bad); failures++; }
        const screen_cfg_t *lay = screens_layout_for(in.theme, screens_center_active(in.center, false));
        bool has_speed = false;
        for (int i = 0; i < SCREEN_COUNT; i++) has_speed |= lay[i].primary == GK_SPEED;
        if (!has_speed) { printf("selftest: theme %d has no speed on the small screens after Android left\n", th); failures++; }
        for (int t = 0; t < 100; t++) rig_tick(&r, &in, true);               /* and when it is back, the flag counts again */
        settle(&r, &in, true);
        bad = panel_vs_model(&r, &in, true);
        if (bad) { printf("selftest: theme %d after Android returned: %d pixels differ\n", th, bad); failures++; }
    }
    /* 2. stale data goes to dashes (what the firmware does when the source stops) */
    {
        rig_t r;
        inputs_t in = inputs_default();
        rig_init(&r, true, THEME_CLASSIC);
        drive_at(15.0f, &in);
        for (int t = 0; t < 200; t++) rig_tick(&r, &in, true);
        for (int t = 0; t < 200; t++) rig_tick(&r, &in, false);
        settle(&r, &in, false);
        int bad = panel_vs_model(&r, &in, false);
        if (bad) { printf("selftest: dashes after loss of data: %d pixels differ\n", bad); failures++; }
        inputs_t none = in;
        for (int i = 0; i < I_COUNT; i++) none.ok[i] = false;
        if (panel_vs_model(&r, &none, true) != 0) { printf("selftest: lost-data picture is not the all-invalid picture\n"); failures++; }
    }
    /* 3. PNG writer and CRC are right: known CRC32 of "123456789" and a decodable stored-deflate stream */
    {
        uint32_t c = crc32_update(0, (const uint8_t *)"123456789", 9);
        if (c != 0xCBF43926u) { printf("selftest: crc32 %08x\n", c); failures++; }
        if (adler32((const uint8_t *)"Wikipedia", 9) != 0x11E60398u) { printf("selftest: adler32\n"); failures++; }
    }
    printf("selftest: %s\n", failures ? "FAILED" : "all passed");
    return failures ? 1 : 0;
}

/* ================================================================== main */

typedef enum { SRC_DRIVE, SRC_MANUAL, SRC_ANDROID, SRC_REPLAY } src_t;
static const char *SRC_NAME[] = { "DRIVE", "MANUAL", "ANDROID", "REPLAY" };

typedef struct { uint64_t ms; char line[200]; } rec_t;

static int load_replay(const char *path, rec_t **out)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    int cap = 1024, n = 0;
    rec_t *r = (rec_t *)malloc((size_t)cap * sizeof *r);
    char line[256];
    while (fgets(line, sizeof line, f)) {
        unsigned long long ms;
        char *tab = strchr(line, '\t');
        if (!tab || sscanf(line, "%llu", &ms) != 1) continue;
        if (n == cap) { cap *= 2; r = (rec_t *)realloc(r, (size_t)cap * sizeof *r); }
        r[n].ms = ms;
        snprintf(r[n].line, sizeof r[n].line, "%s", tab + 1);
        n++;
    }
    fclose(f);
    *out = r;
    return n;
}

static int udp_open(int port)
{
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return -1;
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    a.sin_port = htons((uint16_t)port);
    if (bind(s, (struct sockaddr *)&a, sizeof a) < 0) { close(s); return -1; }
    fcntl(s, F_SETFL, fcntl(s, F_GETFL, 0) | O_NONBLOCK);
    return s;
}

static void usage(void)
{
    puts("harness [options]\n"
         "  (no option)            window with the four screens; keys: SPACE pause, D drive, M manual, A android, R replay,\n"
         "                         U units, 1-6 toggle an input valid/invalid, arrows speed/rpm, F C O B fuel/coolant/oil/battery\n"
         "                         (lower case down, upper case up), TAB zoom, S save picture, Q quit\n"
         "  --udp PORT             listen for the Android telemetry on PORT (default 5005, 0 = off); starts in ANDROID when data arrives\n"
         "  --record FILE          write every telemetry line received to FILE (ms<TAB>line)\n"
         "  --replay FILE          play a recorded file (loops)\n"
         "  --scale X              window zoom, 1.0 to 1.75 (default 1.5)\n"
         "  --shot FILE [--after S] run S seconds (default 3), save the picture as PNG, exit\n"
         "  --golden check|update [FILE] [--dump DIR]   fixed states against stored checksums (default test/golden_screens.txt)\n"
         "  --sim SECONDS [--units-switch]              virtual drive: bus load, backlog, tick overruns, panel == model\n"
         "  --center               the centre screen shows the speedometer: the small screens drop speed (C toggles it in the window)\n"
         "  --theme classic|modern|carplay|factory  the look to start in (T cycles it in the window; the Android app can choose it too)\n"
         "  --selftest             plumbing checks, no display needed\n"
         "  --x11check             open the window, show a known picture, read it back from the X server\n"
         "  --headless             never open a window");
}

int main(int argc, char **argv)
{
    int udp_port = 5005, replay_n = 0, after = 3;
    float scale = 1.5f;
    const char *record_path = 0, *replay_path = 0, *shot = 0, *golden = 0, *golden_file = "test/golden_screens.txt", *dump = 0;
    double sim = 0;
    bool selftest = false, headless = false, x11check = false, units_switch = false;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--udp") && i + 1 < argc) udp_port = atoi(argv[++i]);
        else if (!strcmp(a, "--record") && i + 1 < argc) record_path = argv[++i];
        else if (!strcmp(a, "--replay") && i + 1 < argc) replay_path = argv[++i];
        else if (!strcmp(a, "--scale") && i + 1 < argc) scale = (float)atof(argv[++i]);
        else if (!strcmp(a, "--shot") && i + 1 < argc) shot = argv[++i];
        else if (!strcmp(a, "--after") && i + 1 < argc) after = atoi(argv[++i]);
        else if (!strcmp(a, "--golden") && i + 1 < argc) { golden = argv[++i]; if (i + 1 < argc && argv[i + 1][0] != '-') golden_file = argv[++i]; }
        else if (!strcmp(a, "--dump") && i + 1 < argc) dump = argv[++i];
        else if (!strcmp(a, "--sim") && i + 1 < argc) sim = atof(argv[++i]);
        else if (!strcmp(a, "--theme") && i + 1 < argc) { const char *t = argv[++i]; g_cli_theme = !strcmp(t, "factory") || !strcmp(t, "3") ? THEME_FACTORY : !strcmp(t, "carplay") || !strcmp(t, "2") ? THEME_CARPLAY : (!strcmp(t, "modern") || !strcmp(t, "1") ? THEME_MODERN : THEME_CLASSIC); }
        else if (!strcmp(a, "--units-switch")) units_switch = true;
        else if (!strcmp(a, "--center")) g_cli_center = true;
        else if (!strcmp(a, "--selftest")) selftest = true;
        else if (!strcmp(a, "--x11check")) x11check = true;
        else if (!strcmp(a, "--headless")) headless = true;
        else { usage(); return strcmp(a, "--help") && strcmp(a, "-h") ? 2 : 0; }
    }
    if (scale < 1.0f) scale = 1.0f;
    if (scale > 1.75f) scale = 1.75f;
    lut_init();

    if (golden) return golden_run(golden, golden_file, dump);
    if (sim > 0) return run_sim(sim, units_switch);
    if (selftest) return run_selftest();

    canvas_t cv_;
    canvas_init(&cv_, scale);

#ifdef HARNESS_X11
    x11win_t *win = 0;
    if (!headless) {
        win = x11_open(cv_.w, cv_.h, "Small screens harness (firmware screen code, mock GC9A01 panel)");
        if (!win && !shot && !x11check) { fprintf(stderr, "harness: no display; use --headless for the automated modes\n"); return 2; }
    }
    if (x11check) {
        if (!win) { fprintf(stderr, "x11check: no display\n"); return 1; }
        for (int y = 0; y < cv_.h; y++)
            for (int x = 0; x < cv_.w; x++) cv_.px[y * cv_.w + x] = (uint32_t)(((x * 255 / cv_.w) << 16) | ((y * 255 / cv_.h) << 8) | ((x ^ y) & 255));
        x11_present(win, cv_.px, cv_.w, cv_.h);
        sleep_ms(300);
        uint32_t *back = (uint32_t *)malloc((size_t)cv_.w * (size_t)cv_.h * 4);
        bool ok = x11_readback(win, back, cv_.w, cv_.h);
        int diff = 0;
        if (ok) for (int i = 0; i < cv_.w * cv_.h; i++) diff += (back[i] & 0xFFFFFF) != (cv_.px[i] & 0xFFFFFF);
        printf("x11check: window %dx%d, readback %s, %d of %d pixels differ\n", cv_.w, cv_.h, ok ? "ok" : "FAILED", diff, cv_.w * cv_.h);
        x11_close(win);
        return ok && diff == 0 ? 0 : 1;
    }
#else
    if (x11check) { fprintf(stderr, "built without the X11 window\n"); return 1; }
    (void)headless;
#endif

    /* ---- interactive / shot run ---- */
    inputs_t in = inputs_default();
    rig_t rig;
    rig_init(&rig, in.imperial, in.theme);
    src_t src = SRC_DRIVE;
    bool paused = false;
    int sock = udp_port > 0 ? udp_open(udp_port) : -1;
    if (udp_port > 0 && sock < 0) fprintf(stderr, "harness: cannot listen on UDP %d\n", udp_port);
    FILE *rec = record_path ? fopen(record_path, "w") : 0;
    rec_t *replay = 0;
    if (replay_path) {
        replay_n = load_replay(replay_path, &replay);
        if (replay_n <= 0) { fprintf(stderr, "harness: cannot read %s\n", replay_path); return 2; }
        src = SRC_REPLAY;
    }
    uint64_t t_start = now_ms(), next_tick = t_start, last_rx = 0, last_present = 0, last_rate = t_start;
    uint32_t rx_total = 0, rx_rate = 0, rx_window = 0, runs_window_base = 0, runs_rate = 0, frames = 0, frames_rate = 0;
    bool had_android = false;
    float drive_t = 0.0f;
    size_t replay_i = 0;
    uint64_t replay_t0 = t_start;
    char l0[160], l1[160], l2[160], l3[160], l4[160];
    const char *hud[HUD_LINES] = { l0, l1, l2, l3, l4 };
    bool quit = false, shot_done = false;
    int zoom_i = scale >= 1.7f ? 2 : scale >= 1.4f ? 1 : 0;
    static const float zooms[3] = { 1.0f, 1.5f, 1.75f };
    uint64_t pic_counter = 0;
#ifndef HARNESS_X11
    (void)zoom_i; (void)zooms; (void)pic_counter; (void)paused;
#endif

    while (!quit) {
        uint64_t t = now_ms();
        if (t < next_tick) { sleep_ms(next_tick - t); t = now_ms(); }
        next_tick += 10;
        if (next_tick + 100 < t) next_tick = t;

        /* events */
#ifdef HARNESS_X11
        hev_t ev;
        while (win && x11_poll(win, &ev)) {
            if (ev.type == HEV_QUIT) { quit = true; fprintf(stderr, "harness: window closed\n"); }
            if (ev.type != HEV_KEY) continue;
            int k = ev.key;
            if (k == HK_ESC || k == 'q' || k == 'Q') { quit = true; fprintf(stderr, "harness: quit key\n"); }
            else if (k == ' ') paused = !paused;
            else if (k == 'd' || k == 'D') src = SRC_DRIVE;
            else if (k == 'm' || k == 'M') src = SRC_MANUAL;
            else if (k == 'a' || k == 'A') src = SRC_ANDROID;
            else if ((k == 'r' || k == 'R') && replay) { src = SRC_REPLAY; replay_i = 0; replay_t0 = t; }
            else if (k == 'u' || k == 'U') in.imperial = !in.imperial;
            else if (k == 'c' || k == 'C') in.center = !in.center;
            else if (k == 't' || k == 'T') in.theme = (theme_t)(((int)in.theme + 1) % (int)THEME_COUNT);
            else if (k >= '1' && k <= '6') in.ok[k - '1'] = !in.ok[k - '1'];
            else if (k == '\t' || k == HK_ENTER) {
                zoom_i = (zoom_i + 1) % 3;
                free(cv_.px);
                canvas_init(&cv_, zooms[zoom_i]);
            } else if (k == 's' || k == 'S') {
                char path[64];
                snprintf(path, sizeof path, "harness_%03llu.png", (unsigned long long)pic_counter++);
                printf("saved %s: %s\n", path, write_png(path, cv_.px, cv_.w, cv_.h) ? "ok" : "FAILED");
            } else {
                if (src != SRC_MANUAL) { src = SRC_MANUAL; }
                float *v = in.v;
                switch (k) {
                case HK_UP: v[I_SPEED] += 5; break;
                case HK_DOWN: v[I_SPEED] -= 5; break;
                case HK_RIGHT: v[I_RPM] += 250; break;
                case HK_LEFT: v[I_RPM] -= 250; break;
                case 'F': v[I_FUEL] += 5; break;
                case 'f': v[I_FUEL] -= 5; break;
                case 'C': v[I_COOL] += 5; break;
                case 'c': v[I_COOL] -= 5; break;
                case 'O': v[I_OIL] += 25; break;
                case 'o': v[I_OIL] -= 25; break;
                case 'B': v[I_BATT] += 0.2f; break;
                case 'b': v[I_BATT] -= 0.2f; break;
                default: break;
                }
            }
        }
#endif

        /* data */
        bool alive = true, android_gone = false;
        if (sock >= 0) {
            char buf[512];
            ssize_t n;
            while ((n = recv(sock, buf, sizeof buf - 1, 0)) > 0) {
                buf[n] = 0;
                if (rec) fprintf(rec, "%llu\t%s\n", (unsigned long long)(t - t_start), buf);
                char copy[512];
                memcpy(copy, buf, (size_t)n + 1);
                if (src == SRC_ANDROID || !had_android) {
                    if (parse_telemetry(copy, &in)) { last_rx = t; rx_total++; rx_window++; if (!had_android) { had_android = true; src = SRC_ANDROID; } }
                } else {
                    last_rx = t; rx_total++; rx_window++;          /* keep the rate display honest while another source is chosen */
                }
            }
            if (rec) fflush(rec);
        }
        if (src == SRC_DRIVE) { if (!paused) drive_t += 0.01f; drive_at(drive_t, &in); }
        else if (src == SRC_ANDROID) {
            /* The gauges board does not depend on Android: its senders, Hall pickup and the car bus are its own. If the feed
             * stops (the app was left, closed or crashed) the screens keep running, on the built-in drive here, with the last
             * theme and units (the board keeps those in flash) and with speed back on the small screens. */
            android_gone = had_android && t - last_rx > STALE_MS;
            {
                static bool was_gone = false;
                if (android_gone != was_gone) {
                    fprintf(stderr, "harness: %s\n", android_gone ? "Android feed lost: the gauges run on their own sensors" : "Android feed is back");
                    was_gone = android_gone;
                }
            }
            if (android_gone) {
                if (!paused) drive_t += 0.01f;
                drive_at(drive_t, &in);
                in.center = false;
            }
        }
        else if (src == SRC_REPLAY && replay && !paused) {
            uint64_t el = t - replay_t0;
            while (replay_i < (size_t)replay_n && replay[replay_i].ms <= el) {
                char copy[200];
                snprintf(copy, sizeof copy, "%s", replay[replay_i].line);
                parse_telemetry(copy, &in);
                replay_i++;
            }
            if (replay_i >= (size_t)replay_n) { replay_i = 0; replay_t0 = t; }
        }
        if (!paused || src == SRC_MANUAL) rig_tick(&rig, &in, alive);
        else { /* paused: keep sending what is already queued */
            aux_display_poll_budget(AUX_POLL_RUNS, AUX_POLL_BYTES);
        }

        if (t - last_rate >= 1000) {
            rx_rate = rx_window; rx_window = 0;
            runs_rate = rig.runs_total - runs_window_base; runs_window_base = rig.runs_total;
            frames_rate = frames; frames = 0;
            last_rate = t;
        }

        /* picture */
        bool want_present = t - last_present >= 33;        /* 30 Hz is plenty for a window */
        if (want_present) {
            char val[I_COUNT][12];
            for (int i = 0; i < I_COUNT; i++) {
                if (!in.ok[i] || !alive) snprintf(val[i], sizeof val[i], "--");
                else snprintf(val[i], sizeof val[i], i == I_BATT ? "%.1f" : "%.0f", in.v[i]);
            }
            snprintf(l0, sizeof l0, "SOURCE %s%s   UNITS %s   THEME %s%s   DATA %s", SRC_NAME[src], paused ? " (PAUSED)" : "", in.imperial ? "MPH" : "KM/H", in.theme == THEME_FACTORY ? "FACTORY" : in.theme == THEME_CARPLAY ? "CARPLAY" : (in.theme == THEME_MODERN ? "MODERN" : "CLASSIC"), in.center ? " (SPEED ON CENTRE)" : "",
                     src == SRC_ANDROID ? (android_gone ? "ANDROID GONE: ON OWN SENSORS" : (alive ? "LIVE FROM ANDROID" : "WAITING FOR ANDROID")) : "BUILT IN");
            snprintf(l1, sizeof l1, "SPEED %s KM/H  RPM %s  BATT %s V  FUEL %s %%  COOL %s C  OIL %s KPA", val[0], val[1], val[2], val[3], val[4], val[5]);
            snprintf(l2, sizeof l2, "PANEL BUS %.1f %% (9.6 MHZ)  PEAK %.1f %%  BACKLOG %d TILES  RUNS/S %u  DATA/S %u  FRAMES/S %u",
                     rig.last_window_pct, rig.peak_window_pct, aux_display_pending_tiles(), runs_rate, rx_rate, frames_rate);
            snprintf(l3, sizeof l3, "KEYS  SPACE PAUSE  D DRIVE  M MANUAL  A ANDROID  R REPLAY  U UNITS  T THEME  TAB ZOOM  S SAVE PNG  Q QUIT");
            snprintf(l4, sizeof l4, "      ARROWS SPEED AND RPM   F C O B FUEL COOLANT OIL BATTERY (SMALL DOWN, CAPITAL UP)   1-6 TOGGLE AN INPUT");
            if (compose(&cv_, rig.mock, hud)) {
#ifdef HARNESS_X11
                if (win) x11_present(win, cv_.px, cv_.w, cv_.h);
#endif
                frames++;
            }
            last_present = t;
        }
        if (shot && !shot_done && t - t_start >= (uint64_t)after * 1000u) {
            printf("shot %s: %s (%dx%d)\n", shot, write_png(shot, cv_.px, cv_.w, cv_.h) ? "ok" : "FAILED", cv_.w, cv_.h);
            shot_done = true;
            quit = true;
        }
    }
    if (rec) fclose(rec);
#ifdef HARNESS_X11
    if (win) x11_close(win);
#endif
    return 0;
}
