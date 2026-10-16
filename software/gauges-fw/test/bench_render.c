/* Counts the rendering work of typical updates (compile with -DGFX_STATS). Not a timing
 * measurement: cycles on the S32K144 are not measured, only operations are counted, and
 * the cycle figure printed is an ESTIMATE from an assumed cost per operation. */
#include <stdio.h>
#include <string.h>
#include "dial.h"

static chosen_t cv(float v) { chosen_t c = { v, true, SRC_LOCAL }; return c; }

static void run(const char *what, dial_t *d, const screen_view_t *view, bool imp)
{
    gfx_stat_pixels = gfx_stat_op_evals = gfx_stat_sqrt = 0;
    dial_set_view(d, view, imp);
    static uint16_t stage[GFX_SIZE * GFX_TILE];
    int row, col, n, tiles = 0, runs = 0;
    while (dial_next_run(d, &row, &col, &n)) { dial_render_run(d, row, col, n, stage); tiles += n; runs++; }
    const double CYC_PER_OP = 40.0, CYC_PER_PIXEL = 12.0, CYC_PER_SQRT = 60.0;   /* assumptions */
    double cyc = gfx_stat_op_evals * CYC_PER_OP + gfx_stat_pixels * CYC_PER_PIXEL + gfx_stat_sqrt * CYC_PER_SQRT;
    printf("%-28s %4d tiles %3d runs %6u px %6u op-evals %5u sqrt  ~%.2f ms CPU at 80 MHz (estimate)   %5.1f KB\n",
           what, tiles, runs, gfx_stat_pixels, gfx_stat_op_evals, gfx_stat_sqrt, cyc / 80000.0,
           (double)(tiles * GFX_TILE * GFX_TILE * 2 + runs * 11) / 1024.0);
}

int main(void)
{
    static dial_t d;
    for (int s = 0; s < SCREEN_COUNT; s++) {
        dial_init(&d);
        screen_values_t v = { cv(96.5f), cv(3500.0f), cv(13.8f), cv(68.0f), cv(90.0f), cv(350.0f) };
        screen_view_t a = screens_build(&SCREENS_DEFAULT[s], &v, false);
        char name[48];
        snprintf(name, sizeof name, "screen %d full draw", s);
        run(name, &d, &a, false);
        v.speed_kph.value += 1.0f; v.rpm.value += 60.0f; v.fuel_pct.value += 0.5f; v.coolant_c.value += 1.0f;
        v.oil_kpa.value += 3.0f; v.battery_v.value += 0.05f;
        screen_view_t b = screens_build(&SCREENS_DEFAULT[s], &v, false);
        snprintf(name, sizeof name, "screen %d small move", s);
        run(name, &d, &b, false);
        v.speed_kph.value += 8.0f; v.rpm.value += 400.0f; v.fuel_pct.value -= 5.0f; v.coolant_c.value += 8.0f;
        v.oil_kpa.value += 50.0f; v.battery_v.value -= 0.5f;
        screen_view_t c = screens_build(&SCREENS_DEFAULT[s], &v, false);
        snprintf(name, sizeof name, "screen %d large move", s);
        run(name, &d, &c, false);
    }
    return 0;
}
