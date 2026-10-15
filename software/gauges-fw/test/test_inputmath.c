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

    /* dimmer */
    uint16_t off = 0, full = (uint16_t)(12.0f * IM_DIM_DIVIDER / 3.3f * 4095.0f);
    uint16_t mid = (uint16_t)(8.0f * IM_DIM_DIVIDER / 3.3f * 4095.0f);
    CHECK(!im_dim_lights_on(off, 3300u) && im_dim_percent(off, 3300u) == 0);
    CHECK(im_dim_lights_on(full, 3300u) && im_dim_percent(full, 3300u) >= 99);
    CHECK(im_dim_percent(mid, 3300u) >= 48 && im_dim_percent(mid, 3300u) <= 52);
    CHECK(NEAR(im_adc_to_mv(4095u, 3300u), 3300.0f, 0.01f));

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
