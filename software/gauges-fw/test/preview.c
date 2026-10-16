/* Renders the four screens through the real driver into the mock panel and writes
 * build/screen_<n>.ppm (circle-masked). Usage: preview <preset> [metric] [classic|modern|carplay|factory]
 * presets: 0 cruise, 1 warnings, 2 inputs invalid, 3 idle, 4 redline */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "aux_display.h"
#include "panel_mock.h"

static mock_t g_mock;

static chosen_t ok(float v) { chosen_t c = { v, true, SRC_LOCAL }; return c; }
static chosen_t bad(void) { chosen_t c = { 0.0f, false, SRC_NONE }; return c; }

int main(int argc, char **argv)
{
    int preset = argc > 1 ? atoi(argv[1]) : 0;
    bool imperial = !(argc > 2 && strcmp(argv[2], "metric") == 0);
    theme_t theme = THEME_CLASSIC;
    if (argc > 3 && strcmp(argv[3], "modern") == 0) theme = THEME_MODERN;
    if (argc > 3 && strcmp(argv[3], "carplay") == 0) theme = THEME_CARPLAY;
    if (argc > 3 && strcmp(argv[3], "factory") == 0) theme = THEME_FACTORY;
    mock_init(&g_mock);
    aux_display_init(mock_hal(&g_mock), theme, imperial);
    const screen_cfg_t *layout = screens_layout(theme);

    screen_values_t v;
    switch (preset) {
    case 1:  v = (screen_values_t){ ok(143.0f), ok(5200.0f), ok(11.2f), ok(8.0f), ok(116.0f), ok(60.0f) }; break;
    case 2:  v = (screen_values_t){ bad(), bad(), bad(), bad(), bad(), bad() }; break;
    case 3:  v = (screen_values_t){ ok(0.0f), ok(820.0f), ok(13.9f), ok(68.0f), ok(72.0f), ok(190.0f) }; break;
    case 4:  v = (screen_values_t){ ok(190.0f), ok(6800.0f), ok(14.2f), ok(40.0f), ok(98.0f), ok(420.0f) }; break;
    default: v = (screen_values_t){ ok(96.56f), ok(3500.0f), ok(13.8f), ok(68.0f), ok(90.0f), ok(350.0f) }; break;
    }
    for (uint8_t s = 0; s < SCREEN_COUNT; s++) {
        screen_view_t view = screens_build(&layout[s], &v, imperial);
        aux_display_screen(s, &view);
    }
    while (aux_display_poll(64) > 0) { }

    for (int s = 0; s < SCREEN_COUNT; s++) {
        char name[64];
        snprintf(name, sizeof name, "build/screen_%d.ppm", s);
        FILE *f = fopen(name, "wb");
        if (!f) { perror(name); return 1; }
        fprintf(f, "P6\n240 240\n255\n");
        for (int y = 0; y < 240; y++)
            for (int x = 0; x < 240; x++) {
                uint16_t p = g_mock.fb[s][y * 240 + x];
                int dx = x - 120, dy = y - 120;
                unsigned char rgb[3] = { 0, 0, 0 };
                if (dx * dx + dy * dy <= 120 * 120) {
                    rgb[0] = (unsigned char)(((p >> 11) & 31) * 255 / 31);
                    rgb[1] = (unsigned char)(((p >> 5) & 63) * 255 / 63);
                    rgb[2] = (unsigned char)((p & 31) * 255 / 31);
                }
                fwrite(rgb, 1, 3, f);
            }
        fclose(f);
    }
    printf("mock errors: %d, bytes sent: %llu, spans: %u\n", mock_errors(&g_mock),
           (unsigned long long)g_mock.bytes_written, g_mock.spans);
    return 0;
}
