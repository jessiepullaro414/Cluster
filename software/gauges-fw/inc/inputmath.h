#ifndef INPUTMATH_H
#define INPUTMATH_H
/* Hardware-independent input conversions. REAL, host-tested. The capture,
 * ADC and GPIO drivers (stubs in inputs.c) feed these. */
#include <stdbool.h>
#include <stdint.h>

#define IM_KM_PER_MILE 1.609344f

/* Hall speed: period between pulses in microseconds and the calibration in
 * pulses per mile (AutoMeter 16-pulse sender at 1000 rev/mile = 16000).
 * Returns 0 for a zero period or zero calibration. */
float im_speed_kph(uint32_t period_us, uint32_t pulses_per_mile);

/* Pulse rates the capture logic must cover (plan: roughly 5 Hz to 1 kHz at
 * 16000 pulses/mile). Outside 2 Hz .. 2 kHz a reading is not trusted. */
bool  im_pulse_rate_ok(uint32_t period_us);

/* Tach: rpm = 60e6 / (period_us * pulses_per_rev). */
float im_rpm(uint32_t period_us, uint8_t pulses_per_rev);

/* Lamp debounce: the raw input must hold a new state for IM_LAMP_DEBOUNCE_MS. */
#define IM_LAMP_DEBOUNCE_MS 20u
typedef struct { bool state; bool candidate; uint8_t held_ms; } lamp_debounce_t;
bool im_lamp_update(lamp_debounce_t *d, bool raw_active, uint8_t elapsed_ms);

/* Dash dimmer: the instrument-lamp feed passes a 22k / 6.8k divider (0.236)
 * into a 12-bit ADC with a 3.3 V reference. Below IM_DIM_LIGHTS_ON_MV on the
 * pin the headlight switch is treated as off. The 4 V / 12 V feed range is a
 * first guess to measure on the real rheostat. */
#define IM_DIM_DIVIDER      (6.8f / (22.0f + 6.8f))
#define IM_DIM_LIGHTS_ON_MV 1500u
#define IM_DIM_FEED_MIN_V   4.0f
#define IM_DIM_FEED_FULL_V  12.0f
float   im_adc_to_mv(uint16_t adc12, uint16_t vref_mv);
bool    im_dim_lights_on(uint16_t adc12, uint16_t vref_mv);
uint8_t im_dim_percent(uint16_t adc12, uint16_t vref_mv);   /* 0..100 */

/* Piecewise-linear table lookup (senders): x ascending, clamps at the ends. */
float im_table(const float *x, const float *y, uint8_t n, float v);

#endif
