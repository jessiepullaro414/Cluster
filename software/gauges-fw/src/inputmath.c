#include "inputmath.h"

float im_speed_kph(uint32_t period_us, uint32_t pulses_per_mile)
{
    if (period_us == 0u || pulses_per_mile == 0u)
        return 0.0f;
    /* pulses/s = 1e6/period; miles/s = that / pulses_per_mile; km/h = x 3600 x km/mile */
    return (1.0e6f / (float)period_us) / (float)pulses_per_mile * 3600.0f * IM_KM_PER_MILE;
}

bool im_pulse_rate_ok(uint32_t period_us)
{
    /* 2 Hz .. 2 kHz : 500000 us .. 500 us */
    return period_us >= 500u && period_us <= 500000u;
}

float im_rpm(uint32_t period_us, uint8_t pulses_per_rev)
{
    if (period_us == 0u || pulses_per_rev == 0u)
        return 0.0f;
    return 60.0e6f / ((float)period_us * (float)pulses_per_rev);
}

bool im_lamp_update(lamp_debounce_t *d, bool raw_active, uint8_t elapsed_ms)
{
    if (raw_active == d->state) {
        d->candidate = d->state;
        d->held_ms = 0;
    } else if (raw_active == d->candidate) {
        uint16_t t = (uint16_t)d->held_ms + elapsed_ms;
        d->held_ms = (uint8_t)(t > 255u ? 255u : t);
        if (d->held_ms >= IM_LAMP_DEBOUNCE_MS) {
            d->state = raw_active;
            d->held_ms = 0;
        }
    } else {
        d->candidate = raw_active;
        d->held_ms = elapsed_ms;
        if (d->held_ms >= IM_LAMP_DEBOUNCE_MS) {
            d->state = raw_active;
            d->held_ms = 0;
        }
    }
    return d->state;
}

float im_adc_to_mv(uint16_t adc12, uint16_t vref_mv)
{
    if (adc12 > 4095u) adc12 = 4095u;
    return (float)adc12 * (float)vref_mv / 4095.0f;
}

bool im_dim_lights_on(uint16_t adc12, uint16_t vref_mv)
{
    return im_adc_to_mv(adc12, vref_mv) >= (float)IM_DIM_LIGHTS_ON_MV;
}

uint8_t im_dim_percent(uint16_t adc12, uint16_t vref_mv)
{
    if (!im_dim_lights_on(adc12, vref_mv))
        return 0;
    float feed_v = im_adc_to_mv(adc12, vref_mv) / 1000.0f / IM_DIM_DIVIDER;
    float f = (feed_v - IM_DIM_FEED_MIN_V) / (IM_DIM_FEED_FULL_V - IM_DIM_FEED_MIN_V);
    if (f < 0.0f) f = 0.0f;
    if (f > 1.0f) f = 1.0f;
    return (uint8_t)(f * 100.0f + 0.5f);
}

float im_table(const float *x, const float *y, uint8_t n, float v)
{
    if (n == 0) return 0.0f;
    if (v <= x[0]) return y[0];
    if (v >= x[n - 1]) return y[n - 1];
    for (uint8_t i = 1; i < n; i++) {
        if (v <= x[i]) {
            float t = (v - x[i - 1]) / (x[i] - x[i - 1]);
            return y[i - 1] + t * (y[i] - y[i - 1]);
        }
    }
    return y[n - 1];
}
