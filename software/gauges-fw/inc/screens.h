#ifndef SCREENS_H
#define SCREENS_H
/*
 * What each of the four small round screens shows. REAL, host-tested.
 *
 * Decision 2026-10-15: the centre display is CarPlay / Android Auto maps, so
 * speed and rpm live HERE, on the small screens, together with the fluids. This
 * also keeps speed visible when Android is off, asleep or crashed: the gauges
 * board runs independently of display/.
 *
 * A screen has a primary gauge (needle plus large number) and an optional
 * secondary readout (small number). The assignment is data, so it can become a
 * user setting later; SCREENS_DEFAULT is the shipped layout. This module turns
 * aggregated values into a drawable model; the GC9A01 driver (aux_display.c,
 * PLAN.md A7) only draws what screen_view_t says.
 */
#include <stdbool.h>
#include <stdint.h>
#include "aggregate.h"

#define SCREEN_COUNT 4

/* The look of the four screens, chosen by the user (DisplaySettings.GaugeTheme, 4 bits). A theme brings its
 * own layout: which gauge is on which screen. Unknown values fall back to the classic theme. */
typedef enum { THEME_CLASSIC = 0, THEME_MODERN = 1, THEME_CARPLAY = 2, THEME_COUNT } theme_t;

typedef enum {
    GK_NONE = 0, GK_SPEED, GK_RPM, GK_FUEL, GK_COOLANT, GK_OIL, GK_BATTERY, GK_COUNT
} gauge_kind_t;

typedef struct { gauge_kind_t primary, secondary; } screen_cfg_t;

/* Left to right on the board (slots U6, U7, U8, U9 in ../../gauges): outer left,
 * inner left, inner right, outer right. Speed is on the inner-left screen, the
 * one nearest a left-hand-drive driver's line of sight. */
extern const screen_cfg_t SCREENS_DEFAULT[SCREEN_COUNT];            /* the classic theme's layout */

/* Layout of a theme. THEME_MODERN follows the reference picture: speed (+ fuel), rpm (+ coolant),
 * volts and oil as two bars, coolant. THEME_CARPLAY (Apple-inspired, for use next to a CarPlay screen): speed (+ fuel),
 * rpm, volts and oil as two concentric rings, coolant. */
const screen_cfg_t *screens_layout(theme_t theme);
theme_t             screens_theme_from_setting(uint32_t value);      /* clamps unknown values to classic */

typedef struct {
    /* aggregate.c results: already source-selected and freshness-checked */
    chosen_t speed_kph, rpm, battery_v, fuel_pct, coolant_c, oil_kpa;
} screen_values_t;

typedef struct {
    gauge_kind_t kind;
    bool         valid;      /* false: draw a dash, never a stale number */
    float        needle;     /* 0..1 along the scale, 0 when invalid */
    float        value;      /* in display units (see unit) */
    const char  *unit;       /* "MPH", "KM/H", "RPM", "%", "F", "C", "PSI", "KPA", "V" */
    bool         warn;       /* outside the normal range: draw in the warning colour */
} gauge_view_t;

typedef struct { gauge_view_t primary, secondary; } screen_view_t;

/* imperial = true: mph, degrees F, psi (the DisplaySettings.UnitsMph flag). */
screen_view_t screens_build(const screen_cfg_t *cfg, const screen_values_t *v, bool imperial);
gauge_view_t  screens_gauge(gauge_kind_t kind, const screen_values_t *v, bool imperial);

/* Scale limits in native units (kph, rpm, %, degC, kPa, V), for the drawing code. */
#define SCALE_SPEED_KPH_MAX_IMPERIAL 193.12f   /* 120 mph */
#define SCALE_SPEED_KPH_MAX_METRIC   200.0f
#define SCALE_RPM_MAX                7000.0f
#define SCALE_COOLANT_MIN_C          40.0f
#define SCALE_COOLANT_MAX_C          130.0f
#define SCALE_OIL_MAX_KPA            700.0f
#define SCALE_BATT_MIN_V             10.0f
#define SCALE_BATT_MAX_V             16.0f

/* First-guess warning thresholds, to be set against the real car. */
#define WARN_COOLANT_C               110.0f
#define WARN_BATT_LOW_V              11.5f
#define WARN_BATT_HIGH_V             15.0f
#define WARN_FUEL_PCT                10.0f
#endif
