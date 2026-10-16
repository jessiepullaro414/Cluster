#include "aux_display.h"

#include "dial.h"
#include "gc9a01.h"
#include "gfx.h"

/* RAM: four dials (about 4.5 KB each) and one shared staging buffer for a full row of
 * tiles (240 x 16 x 2 = 7.5 KB), 26 KB of the part's 60 KB. */
static dial_t g_dial[SCREEN_COUNT];
static uint16_t g_stage[GFX_SIZE * GFX_TILE];
static const panel_hal_t *g_hal;
static bool g_imperial;
static uint8_t g_next;                       /* round-robin start */

void aux_display_set_backlight(bool on, uint8_t pct)
{
    /* One switch for all four (BL_EN, gauges/ Q2); brightness steps would need a PWM on that
     * pin, which is not wired, so pct only decides on/off. */
    if (g_hal && g_hal->backlight) g_hal->backlight(g_hal->ctx, on && pct > 0u);
}

void aux_display_set_imperial(bool imperial) { g_imperial = imperial; }

void aux_display_init(const panel_hal_t *hal, const screen_cfg_t layout[SCREEN_COUNT], bool imperial)
{
    g_hal = hal;
    g_imperial = imperial;
    g_next = 0;
    gc9a01_reset(hal);
    for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
        gc9a01_init(hal, s);
        dial_init(&g_dial[s]);
        screen_values_t none;                       /* every input invalid: draws dashes */
        none.speed_kph = none.rpm = none.battery_v = none.fuel_pct = none.coolant_c = none.oil_kpa
            = (chosen_t){ 0.0f, false, SRC_NONE };
        screen_view_t v = screens_build(&layout[s], &none, imperial);
        dial_set_view(&g_dial[s], &v, imperial);
    }
    hal->delay_ms(hal->ctx, GC9A01_SLEEP_OUT_WAIT_MS);          /* one wait for all four */
    /* draw everything before any display is switched on, so no frame of garbage shows */
    while (aux_display_poll(64) > 0) { }
    for (uint8_t s = 0; s < SCREEN_COUNT; s++)
        gc9a01_display(hal, s, true);
    aux_display_set_backlight(true, 100);                       /* only now: no unlit-then-lit flash */
}

void aux_display_screen(uint8_t index, const screen_view_t *view)
{
    if (index < SCREEN_COUNT) dial_set_view(&g_dial[index], view, g_imperial);
}

int aux_display_poll(int max_runs)
{
    if (!g_hal) return 0;
    int sent = 0;
    for (uint8_t i = 0; i < SCREEN_COUNT && sent < max_runs; i++) {
        uint8_t s = (uint8_t)((g_next + i) % SCREEN_COUNT);
        int row, col, n;
        if (dial_next_run(&g_dial[s], &row, &col, &n)) {
            dial_render_run(&g_dial[s], row, col, n, g_stage);
            gc9a01_blit(g_hal, s, col * GFX_TILE, row * GFX_TILE, n * GFX_TILE, GFX_TILE, g_stage);
            sent++;
        }
    }
    g_next = (uint8_t)((g_next + 1) % SCREEN_COUNT);
    return sent;
}

int aux_display_pending_tiles(void)
{
    int n = 0;
    for (uint8_t s = 0; s < SCREEN_COUNT; s++) n += dial_dirty_tiles(&g_dial[s]);
    return n;
}
