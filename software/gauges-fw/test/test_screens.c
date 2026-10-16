#include <math.h>
#include <stdio.h>
#include <string.h>
#include "screens.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)
#define NEAR(a, b, tol) (fabsf((float)(a) - (float)(b)) <= (tol))

static chosen_t ok(float v) { chosen_t c = { v, true, SRC_LOCAL }; return c; }
static chosen_t bad(void) { chosen_t c = { 123.0f, false, SRC_NONE }; return c; }

static screen_values_t sample(void)
{
    screen_values_t v;
    v.speed_kph = ok(96.56064f);       /* 60 mph */
    v.rpm = ok(3500.0f);
    v.battery_v = ok(13.8f);
    v.fuel_pct = ok(68.0f);
    v.coolant_c = ok(90.0f);
    v.oil_kpa = ok(350.0f);
    return v;
}

int main(void)
{
    /* the shipped layout shows each of the six quantities exactly once, speed on a primary slot */
    int seen[GK_COUNT] = { 0 };
    for (int i = 0; i < SCREEN_COUNT; i++) {
        seen[SCREENS_DEFAULT[i].primary]++;
        seen[SCREENS_DEFAULT[i].secondary]++;
    }
    for (int k = GK_SPEED; k < GK_COUNT; k++) CHECK(seen[k] == 1);
    CHECK(SCREENS_DEFAULT[1].primary == GK_SPEED);       /* inner left */

    screen_values_t v = sample();

    /* speed, imperial: 60 mph on a 0..120 mph scale is half way */
    gauge_view_t g = screens_gauge(GK_SPEED, &v, true);
    CHECK(g.valid && NEAR(g.value, 60.0f, 0.01f) && NEAR(g.needle, 0.5f, 0.001f));
    CHECK(strcmp(g.unit, "MPH") == 0);
    /* speed, metric: 96.56 km/h on 0..200 */
    g = screens_gauge(GK_SPEED, &v, false);
    CHECK(NEAR(g.value, 96.56f, 0.01f) && NEAR(g.needle, 96.56064f / 200.0f, 0.001f));
    CHECK(strcmp(g.unit, "KM/H") == 0);
    /* beyond the scale the needle stops at the end; the number keeps going */
    v.speed_kph = ok(250.0f);
    g = screens_gauge(GK_SPEED, &v, false);
    CHECK(g.needle == 1.0f && NEAR(g.value, 250.0f, 0.001f));
    v.speed_kph = ok(-3.0f);
    g = screens_gauge(GK_SPEED, &v, true);
    CHECK(g.needle == 0.0f && g.value == 0.0f);

    v = sample();
    g = screens_gauge(GK_RPM, &v, true);
    CHECK(NEAR(g.needle, 0.5f, 0.001f) && NEAR(g.value, 3500.0f, 0.01f) && !g.warn);

    /* coolant: the needle uses degrees C whatever the display units */
    g = screens_gauge(GK_COOLANT, &v, true);
    CHECK(NEAR(g.value, 194.0f, 0.01f) && NEAR(g.needle, 50.0f / 90.0f, 0.001f) && !g.warn);
    CHECK(strcmp(g.unit, "F") == 0);
    g = screens_gauge(GK_COOLANT, &v, false);
    CHECK(NEAR(g.value, 90.0f, 0.001f) && strcmp(g.unit, "C") == 0);
    v.coolant_c = ok(112.0f);
    CHECK(screens_gauge(GK_COOLANT, &v, false).warn);
    v.coolant_c = ok(110.0f);                                    /* at the threshold counts */
    CHECK(screens_gauge(GK_COOLANT, &v, false).warn);
    v.coolant_c = ok(109.9f);
    CHECK(!screens_gauge(GK_COOLANT, &v, false).warn);

    /* oil pressure: 350 kPa is 50.8 psi */
    v = sample();
    g = screens_gauge(GK_OIL, &v, true);
    CHECK(NEAR(g.value, 50.76f, 0.01f) && strcmp(g.unit, "PSI") == 0);
    g = screens_gauge(GK_OIL, &v, false);
    CHECK(NEAR(g.value, 350.0f, 0.001f) && NEAR(g.needle, 0.5f, 0.001f));

    /* battery warns low and high, not in between */
    v.battery_v = ok(11.4f);  CHECK(screens_gauge(GK_BATTERY, &v, true).warn);
    v.battery_v = ok(11.5f);  CHECK(!screens_gauge(GK_BATTERY, &v, true).warn);
    v.battery_v = ok(15.1f);  CHECK(screens_gauge(GK_BATTERY, &v, true).warn);
    v.battery_v = ok(13.0f);  g = screens_gauge(GK_BATTERY, &v, true);
    CHECK(NEAR(g.needle, 0.5f, 0.001f));

    /* fuel warns at or below 10 % */
    v.fuel_pct = ok(10.0f);   CHECK(screens_gauge(GK_FUEL, &v, true).warn);
    v.fuel_pct = ok(10.5f);   CHECK(!screens_gauge(GK_FUEL, &v, true).warn);

    /* an invalid input is a dash: no number, no needle, no warning, whatever its stale value */
    v = sample();
    v.speed_kph = bad();
    v.coolant_c = bad();
    g = screens_gauge(GK_SPEED, &v, true);
    CHECK(!g.valid && g.needle == 0.0f && g.value == 0.0f && !g.warn);
    g = screens_gauge(GK_COOLANT, &v, true);
    CHECK(!g.valid && g.needle == 0.0f && g.value == 0.0f && !g.warn);

    /* whole-screen build: outer right is coolant + oil, and an empty secondary is inert */
    v = sample();
    screen_view_t s = screens_build(&SCREENS_DEFAULT[3], &v, false);
    CHECK(s.primary.kind == GK_COOLANT && s.secondary.kind == GK_OIL && s.secondary.valid);
    s = screens_build(&SCREENS_DEFAULT[1], &v, false);
    CHECK(s.primary.kind == GK_SPEED && s.secondary.kind == GK_NONE && !s.secondary.valid);
    CHECK(screens_gauge(GK_COUNT, &v, true).kind == GK_NONE);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("screens: all tests passed\n");
    return 0;
}
