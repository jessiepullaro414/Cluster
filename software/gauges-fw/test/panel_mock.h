#ifndef PANEL_MOCK_H
#define PANEL_MOCK_H
/* A mock of four GC9A01 panels behind the panel_hal interface. It decodes the SPI byte
 * stream per screen (D/C and CS as the driver sets them), models the GRAM window of the
 * datasheet (CASET/RASET/RAMWR with wrap), keeps a framebuffer per screen, logs every
 * command, and counts protocol violations. Host tests only. */
#include <stdbool.h>
#include <stdint.h>
#include "panel_hal.h"

#define MOCK_SCREENS 4
#define MOCK_LOG_MAX 4096

typedef struct { uint8_t screen, cmd, n; uint8_t p[16]; } mock_cmd_t;

typedef struct {
    uint16_t fb[MOCK_SCREENS][240 * 240];      /* RGB565, host order */
    bool     written[MOCK_SCREENS][240 * 240]; /* pixel was ever written */

    mock_cmd_t log[MOCK_LOG_MAX];
    int        n_log;

    /* per screen state */
    bool     cs[MOCK_SCREENS], dc_data[MOCK_SCREENS];
    int      cur_cmd[MOCK_SCREENS], n_params[MOCK_SCREENS];
    uint8_t  params[MOCK_SCREENS][16];
    int      sc[MOCK_SCREENS], ec[MOCK_SCREENS], sp[MOCK_SCREENS], ep[MOCK_SCREENS];
    int      col[MOCK_SCREENS], row[MOCK_SCREENS];
    bool     ramwr[MOCK_SCREENS], have_hi[MOCK_SCREENS], wrapped[MOCK_SCREENS];
    uint8_t  hi[MOCK_SCREENS];
    bool     inter_enabled[MOCK_SCREENS], display_on[MOCK_SCREENS], sleeping[MOCK_SCREENS];
    bool     inverted[MOCK_SCREENS];
    int      colmod[MOCK_SCREENS], madctl[MOCK_SCREENS];
    uint32_t ms_since_slpout[MOCK_SCREENS];
    bool     last_was_fe[MOCK_SCREENS], slpout_seen[MOCK_SCREENS];

    /* global */
    bool     reset_asserted;
    int      reset_count;
    uint32_t total_delay_ms;
    uint64_t bytes_written, pixel_bytes;
    uint32_t spans;                             /* chip-select assertions */
    int      selected;                          /* screen currently selected, -1 none */
    bool     backlight;

    /* violations */
    int err_no_cs, err_two_cs, err_in_reset, err_pixel_no_ramwr, err_window, err_wrap,
        err_inter_before_unlock, err_colmod, err_dispon_early, err_bad_params, err_odd_pixel_bytes, err_cmd_too_soon;
} mock_t;

void mock_init(mock_t *m);
const panel_hal_t *mock_hal(mock_t *m);
int  mock_errors(const mock_t *m);
/* Count log entries of a command for a screen (or all screens if screen < 0). */
int  mock_count(const mock_t *m, int screen, int cmd);
#endif
