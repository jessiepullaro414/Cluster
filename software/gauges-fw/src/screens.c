#include "screens.h"

const screen_cfg_t SCREENS_DEFAULT[SCREEN_COUNT] = {
    { GK_FUEL,    GK_BATTERY },   /* 0 outer left  */
    { GK_SPEED,   GK_NONE    },   /* 1 inner left  */
    { GK_RPM,     GK_NONE    },   /* 2 inner right */
    { GK_COOLANT, GK_OIL     },   /* 3 outer right */
};

static float frac(float v, float lo, float hi)
{
    float f = (v - lo) / (hi - lo);
    return f < 0.0f ? 0.0f : (f > 1.0f ? 1.0f : f);
}

static gauge_view_t make(gauge_kind_t k, chosen_t c, float lo, float hi, float display_value,
                         const char *unit, bool warn)
{
    gauge_view_t g = { k, c.valid, 0.0f, 0.0f, unit, false };
    if (c.valid) {
        g.needle = frac(c.value, lo, hi);
        g.value = display_value;
        g.warn = warn;
    }
    return g;
}

gauge_view_t screens_gauge(gauge_kind_t kind, const screen_values_t *v, bool imperial)
{
    switch (kind) {
    case GK_SPEED: {
        chosen_t c = v->speed_kph;
        float hi = imperial ? SCALE_SPEED_KPH_MAX_IMPERIAL : SCALE_SPEED_KPH_MAX_METRIC;
        float shown = imperial ? c.value / 1.609344f : c.value;
        if (shown < 0.0f) shown = 0.0f;
        return make(kind, c, 0.0f, hi, shown, imperial ? "MPH" : "KM/H", false);
    }
    case GK_RPM: {
        chosen_t c = v->rpm;
        return make(kind, c, 0.0f, SCALE_RPM_MAX, c.value, "RPM", false);
    }
    case GK_FUEL: {
        chosen_t c = v->fuel_pct;
        return make(kind, c, 0.0f, 100.0f, c.value, "%", c.value <= WARN_FUEL_PCT);
    }
    case GK_COOLANT: {
        chosen_t c = v->coolant_c;
        float shown = imperial ? c.value * 9.0f / 5.0f + 32.0f : c.value;
        return make(kind, c, SCALE_COOLANT_MIN_C, SCALE_COOLANT_MAX_C, shown,
                    imperial ? "F" : "C", c.value >= WARN_COOLANT_C);
    }
    case GK_OIL: {
        chosen_t c = v->oil_kpa;
        float shown = imperial ? c.value * 0.14503774f : c.value;
        return make(kind, c, 0.0f, SCALE_OIL_MAX_KPA, shown, imperial ? "PSI" : "KPA", false);
    }
    case GK_BATTERY: {
        chosen_t c = v->battery_v;
        return make(kind, c, SCALE_BATT_MIN_V, SCALE_BATT_MAX_V, c.value, "V",
                    c.value < WARN_BATT_LOW_V || c.value > WARN_BATT_HIGH_V);
    }
    default: {
        gauge_view_t none = { GK_NONE, false, 0.0f, 0.0f, "", false };
        return none;
    }
    }
}

screen_view_t screens_build(const screen_cfg_t *cfg, const screen_values_t *v, bool imperial)
{
    screen_view_t s;
    s.primary = screens_gauge(cfg->primary, v, imperial);
    s.secondary = screens_gauge(cfg->secondary, v, imperial);
    return s;
}
