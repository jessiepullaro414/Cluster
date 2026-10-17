#ifndef SETTINGS_STORE_H
#define SETTINGS_STORE_H
/* The display settings gauges/ keeps in data flash, so that a dead or still-booting display never changes the units, the theme
 * or the speed calibration. REAL, host-tested against the flash model (test/test_settings.c). A 16-byte record in a 4-sector
 * log (nvlog.h) after the odometer's 16 sectors. center_shows_speed and display_heartbeat_seen are NOT kept: they describe
 * the display's state right now, not a preference. A change is saved once it has been stable for SETTINGS_QUIET_MS, so dragging
 * a slider is one write, not hundreds. */
#include <stdbool.h>
#include <stdint.h>
#include "can_link.h"
#include "nvflash.h"
#include "nvlog.h"

#define SETTINGS_SECTORS   4u
#define SETTINGS_QUIET_MS  3000u

typedef struct {
    nvlog_t  log;
    display_settings_t saved;           /* what the log holds (or the defaults when it holds nothing) */
    display_settings_t want;            /* the latest value offered */
    display_settings_t inflight;
    bool     have_saved;
    bool     dirty;                     /* want differs from saved */
    uint32_t changed_ms;
} settings_store_t;

/* Load the newest record into *settings (left untouched, i.e. at its defaults, if there is none or nv is NULL). */
void settings_store_init(settings_store_t *s, const nv_ops_t *nv, uint32_t base_off, display_settings_t *settings);
/* Offer the current settings; remembers when they last changed. */
void settings_store_offer(settings_store_t *s, const display_settings_t *cur, uint32_t now_ms);
void settings_store_service(settings_store_t *s, uint32_t now_ms);
bool settings_store_idle(const settings_store_t *s);

/* The record format, exposed for the tests. */
void settings_pack(const display_settings_t *d, uint8_t out[16]);
bool settings_unpack(const uint8_t in[16], display_settings_t *d);

#endif
