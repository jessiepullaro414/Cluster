#include <string.h>
#include "settings_store.h"

#define VERSION 1u

/* record: [0] version  [1] brightness  [2] flags (bit0 night, bit1 mph, bit2 tach)  [3] theme  [4] profile  [5] bitrate
 *         [6] lamp invert mask  [7] tach pulses/rev  [8..9] tank capacity in 0.1 L  [10..11] zero  [12..15] pulses per mile */
void settings_pack(const display_settings_t *d, uint8_t out[16])
{
    memset(out, 0, 16);
    out[0] = VERSION;
    out[1] = d->brightness_pct;
    out[2] = (uint8_t)((d->night_mode ? 1u : 0u) | (d->units_mph ? 2u : 0u) | (d->tach_enabled ? 4u : 0u));
    out[3] = d->gauge_theme;
    out[4] = d->car_profile;
    out[5] = d->car_bitrate;
    out[6] = d->lamp_invert_mask;
    out[7] = d->tach_pulses_per_rev;
    float dl = d->tank_capacity_l * 10.0f + 0.5f;
    uint16_t tank = dl < 0.0f ? 0u : (dl > 65535.0f ? 65535u : (uint16_t)dl);
    out[8] = (uint8_t)tank; out[9] = (uint8_t)(tank >> 8);
    out[12] = (uint8_t)d->pulses_per_mile; out[13] = (uint8_t)(d->pulses_per_mile >> 8);
    out[14] = (uint8_t)(d->pulses_per_mile >> 16); out[15] = (uint8_t)(d->pulses_per_mile >> 24);
}

bool settings_unpack(const uint8_t in[16], display_settings_t *d)
{
    if (in[0] != VERSION) return false;
    if (in[1] > 100u || in[7] == 0u || in[7] > 16u) return false;       /* the ranges the protocol allows */
    d->brightness_pct = in[1];
    d->night_mode = (in[2] & 1u) != 0u;
    d->units_mph = (in[2] & 2u) != 0u;
    d->tach_enabled = (in[2] & 4u) != 0u;
    d->gauge_theme = in[3];
    d->car_profile = in[4];
    d->car_bitrate = in[5];
    d->lamp_invert_mask = in[6];
    d->tach_pulses_per_rev = in[7];
    d->tank_capacity_l = (float)((uint16_t)in[8] | ((uint16_t)in[9] << 8)) / 10.0f;
    d->pulses_per_mile = (uint32_t)in[12] | ((uint32_t)in[13] << 8) | ((uint32_t)in[14] << 16) | ((uint32_t)in[15] << 24);
    return true;
}

/* the fields that are kept: compared on the stored representation, so a float that rounds to the same value is not a change */
static bool same(const display_settings_t *a, const display_settings_t *b)
{
    uint8_t x[16], y[16];
    settings_pack(a, x); settings_pack(b, y);
    return memcmp(x, y, 16) == 0;
}

void settings_store_init(settings_store_t *s, const nv_ops_t *nv, uint32_t base_off, display_settings_t *settings)
{
    memset(s, 0, sizeof *s);
    uint8_t rec[16];
    if (nvlog_init(&s->log, nv, base_off, SETTINGS_SECTORS, 16u, rec) && settings_unpack(rec, settings))
        s->have_saved = true;
    s->saved = *settings;
    s->want = *settings;
}

void settings_store_offer(settings_store_t *s, const display_settings_t *cur, uint32_t now_ms)
{
    if (!same(cur, &s->want)) s->changed_ms = now_ms;       /* restart the quiet period */
    s->want = *cur;
    s->dirty = !same(&s->want, &s->saved);        /* defaults that nobody changed need no record */
}

void settings_store_service(settings_store_t *s, uint32_t now_ms)
{
    nvlog_event_t ev = nvlog_service(&s->log);
    if (ev == NVLOG_EV_COMMITTED) { s->saved = s->inflight; s->have_saved = true; }
    else if (ev == NVLOG_EV_FAILED) s->changed_ms = now_ms - SETTINGS_QUIET_MS;          /* retry at once */
    s->dirty = !same(&s->want, &s->saved);
    if (s->dirty && !nvlog_busy(&s->log) && (uint32_t)(now_ms - s->changed_ms) >= SETTINGS_QUIET_MS) {
        uint8_t rec[16];
        settings_pack(&s->want, rec);
        if (nvlog_write(&s->log, rec)) s->inflight = s->want;
    }
}

bool settings_store_idle(const settings_store_t *s)
{
    return nvlog_dead(&s->log) || (!nvlog_busy(&s->log) && !s->dirty);
}
