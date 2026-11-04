#include <math.h>
#include <stdio.h>
#include "inputmath.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)
#define NEAR(a, b, tol) (fabsf((float)(a) - (float)(b)) <= (tol))

int main(void)
{
    /* 120 mph at 16000 pulses/mile = 533.33 Hz -> period 1875 us */
    CHECK(NEAR(im_speed_kph(1875u, 16000u), 120.0f * IM_KM_PER_MILE, 0.1f));
    /* 2 mph -> 8.889 Hz -> 112500 us */
    CHECK(NEAR(im_speed_kph(112500u, 16000u), 2.0f * IM_KM_PER_MILE, 0.01f));
    CHECK(im_speed_kph(0u, 16000u) == 0.0f && im_speed_kph(1000u, 0u) == 0.0f);
    CHECK(im_pulse_rate_ok(1875u) && im_pulse_rate_ok(112500u));
    CHECK(!im_pulse_rate_ok(100u) && !im_pulse_rate_ok(900000u));

    /* tach: 4 sparks per rev at 3000 rpm = 200 Hz -> 5000 us */
    CHECK(NEAR(im_rpm(5000u, 4u), 3000.0f, 0.5f));
    CHECK(im_rpm(0u, 4u) == 0.0f && im_rpm(5000u, 0u) == 0.0f);

    /* lamp debounce: needs 20 ms of a new state; a 10 ms glitch is ignored */
    lamp_debounce_t d = { false, false, 0 };
    CHECK(!im_lamp_update(&d, true, 10));
    CHECK(!im_lamp_update(&d, false, 10));
    CHECK(!im_lamp_update(&d, true, 10));
    CHECK(!im_lamp_update(&d, true, 5));
    CHECK(im_lamp_update(&d, true, 10));
    CHECK(im_lamp_update(&d, true, 10));
    CHECK(im_lamp_update(&d, false, 10));      /* still on: only 10 ms low */
    CHECK(!im_lamp_update(&d, false, 10));     /* 20 ms low: off */

    /* dimmer: lights on or off is a plain threshold on the feed, 2 V */
    uint16_t off = 0, low = (uint16_t)(3.0f * IM_DIM_DIVIDER / 3.3f * 4095.0f);
    CHECK(!im_dim_lights_on(off, 3300u) && im_dim_lights_on(low, 3300u));
    CHECK(NEAR(im_adc_to_mv(4095u, 3300u), 3300.0f, 0.01f));
    /* the rheostat from the sag. 14 V through 6 ohm into the load: I = (14 - 1.8) / (6 + 330) = 36.3 mA, so the feed sags 0.218 V */
    float i6 = (14.0f - IM_DIM_LOAD_DROP_V) / (6.0f + IM_DIM_LOAD_OHM);
    CHECK(NEAR(im_dim_rheostat_ohm(14.0f, 14.0f - i6 * 6.0f, 14.0f), 6.0f, 0.01f));
    CHECK(NEAR(im_dim_rheostat_ohm(14.0f, 14.0f, 14.0f), 0.0f, 0.001f));        /* no sag: the knob is at the top */
    CHECK(im_dim_rheostat_ohm(14.0f, 14.2f, 14.0f) == 0.0f);                    /* the battery rose between the readings: never negative */
    /* bulbs of 20 ohm on the feed: the feed is 20/26 of the battery and the sag shows 6 ohm in parallel with 20 ohm; the rheostat comes back */
    float open = 14.0f * 20.0f / 26.0f, rth = 6.0f * 20.0f / 26.0f;
    float ib = (open - IM_DIM_LOAD_DROP_V) / (rth + IM_DIM_LOAD_OHM);
    CHECK(NEAR(im_dim_rheostat_ohm(open, open - ib * rth, 14.0f), 6.0f, 0.01f));
    CHECK(NEAR(im_dim_rheostat_ohm(open, open - ib * rth, 0.0f), rth, 0.01f));  /* no battery reading: the bulbs stay in the sum */
    CHECK(im_dim_rheostat_ohm(2.2f, 2.0f, 14.0f) == IM_DIM_RHEO_MAX_OHM);        /* barely a load current: no division by next to nothing */
    CHECK(im_dim_rheostat_ohm(14.0f, 1.0f, 14.0f) == IM_DIM_RHEO_MAX_OHM);       /* a dead feed */
    CHECK(im_dim_rheostat_ohm(3.0f, 2.2f, 14.0f) == IM_DIM_RHEO_MAX_OHM);        /* a big sag on a small current: the ceiling, so it cannot swamp the filter */
    /* a feed reading above the battery (the battery is read after this board's own front end): the sag alone counts */
    float i15 = (15.0f - IM_DIM_LOAD_DROP_V) / (6.0f + IM_DIM_LOAD_OHM);
    CHECK(NEAR(im_dim_rheostat_ohm(15.0f, 15.0f - i15 * 6.0f, 14.0f), 6.0f, 0.01f));
    /* the scale */
    CHECK(im_dim_percent(0.0f, 14.0f, 14.0f) == 100u);
    CHECK(im_dim_percent(IM_DIM_RHEO_TOP_OHM, 14.0f, 14.0f) == 100u);
    CHECK(im_dim_percent(0.4f, 14.0f, 14.0f) == 100u);                           /* contacts and wiring do not read as a dimmed knob */
    CHECK(im_dim_percent((IM_DIM_RHEO_TOP_OHM + IM_DIM_RHEO_FULL_OHM) / 2.0f, 14.0f, 14.0f) == 50u);
    CHECK(im_dim_percent(IM_DIM_RHEO_FULL_OHM, 14.0f, 14.0f) == 0u);
    CHECK(im_dim_percent(60.0f, 14.0f, 14.0f) == 0u);
    /* a low open feed wins over the rheostat figure: bulbs, knob well down */
    CHECK(im_dim_percent(1.0f, 14.0f * 0.33f, 14.0f) == 0u);
    CHECK(im_dim_percent(1.0f, 14.0f * 0.59f, 14.0f) == 50u);
    /* a small wiring drop does not dim anything, and neither does a feed reading above the battery */
    CHECK(im_dim_percent(0.0f, 14.0f * 0.86f, 14.0f) == 100u);
    CHECK(im_dim_percent(0.0f, 15.0f, 14.0f) == 100u);
    CHECK(im_dim_percent(0.0f, 5.0f, 0.0f) == 100u);                             /* no battery reading: the ratio does not count */

    /* table */
    const float x[] = { 0.0f, 10.0f, 100.0f };
    const float y[] = { 0.0f, 50.0f, 100.0f };
    CHECK(NEAR(im_table(x, y, 3, 5.0f), 25.0f, 0.001f));
    CHECK(NEAR(im_table(x, y, 3, 55.0f), 75.0f, 0.001f));
    CHECK(im_table(x, y, 3, -1.0f) == 0.0f && im_table(x, y, 3, 500.0f) == 100.0f);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("inputmath: all tests passed\n");
    return 0;
}
