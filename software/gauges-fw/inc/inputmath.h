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

/* Dash dimmer: the instrument-lamp feed passes a 22k / 4.7k divider (0.176)
 * into a 12-bit ADC with a 3.3 V reference: 18.75 V full scale, 4.6 mV a count.
 * Below IM_DIM_LIGHTS_ON_MV on the pin the headlight switch is treated as off.
 * 2026-11-04: it was 22k / 6.8k, 14 V full scale. At the alternator's 14.4 V the
 * ADC sat at full scale, so the test load's sag (below) read as nothing.
 * Review 2026-11-03: the threshold was 1500 mV on the pin, a 6.4 V feed, above
 * the 4 V bottom of the dimming range: turning the knob down past about half
 * read as "lights off" and put the screens back to daytime brightness at night.
 * The threshold is now a 2.0 V feed, 352 mV on the pin: below any lit setting and
 * well above the ~0 V of a feed that is switched off.
 *
 * The knob's position (2026-11-04, G-38). The knob is a rheostat in series with the feed, and a rheostat drops voltage only
 * while current flows, so with the stock cluster's bulbs gone the feed reads the battery at every position. inputs.c therefore
 * reads the feed, switches a known load across it for 10 ms (R105, through D37 and Q4), reads it again, and asks what source
 * resistance explains the sag. The readings are 10 ms apart, so a change of battery voltage does not enter into it.
 *
 *   load current     I = (loaded feed - IM_DIM_LOAD_DROP_V) / IM_DIM_LOAD_OHM
 *   source resistance  R = (open feed - loaded feed) / I        this is the rheostat in parallel with any bulbs left on the feed
 *   rheostat         R / (open feed / battery)                  the bulbs cancel: with rheostat Rx and bulbs Rb, R = Rx Rb / (Rx + Rb)
 *                                                               and open feed / battery = Rb / (Rx + Rb)
 *
 * IM_DIM_RHEO_FULL_OHM is ASSUMED. No published figure for the 1965-66 headlight switch was found, only 2.5 and 5 ohm for other cars
 * (forum posts), and about 11-16 ohm reckoned from the stock lamp current. A car with less reaches its lowest setting above
 * 0 %; a car with more reaches 0 % before the end of the knob's travel. Measure one switch and set it here.
 *
 * With bulbs left on the feed and the knob well down, the feed itself is low and the load current small, so the sag is too small
 * to measure well. The open feed against the battery says the same thing there, so the lower of the two wins. Above
 * IM_DIM_RATIO_FULL the ratio does not count, so that the voltage drop in old wiring cannot dim the screens. */
#define IM_DIM_DIVIDER       (4.7f / (22.0f + 4.7f))
#define IM_DIM_LIGHTS_ON_MV  352u
#define IM_DIM_LOAD_OHM      330.0f     /* R105 */
#define IM_DIM_LOAD_DROP_V   1.8f       /* D37's two diodes and Q4 at about 40 mA */
#define IM_DIM_RHEO_TOP_OHM  0.5f       /* contacts and wiring: at or below this the knob is at the top */
#define IM_DIM_RHEO_FULL_OHM 12.0f      /* ASSUMED, see above: at or above this the knob is at the bottom */
#define IM_DIM_RHEO_MAX_OHM  60.0f      /* what a dead or nearly dead feed reads as, so one bad reading cannot swamp the filter */
#define IM_DIM_RATIO_FULL    0.85f
#define IM_DIM_RATIO_ZERO    0.33f      /* the old 4 V bottom of the range on a 12 V feed */
float   im_adc_to_mv(uint16_t adc12, uint16_t vref_mv);
bool    im_dim_lights_on(uint16_t adc12, uint16_t vref_mv);
/* Volts on the feed: without the load, with it, and the battery (0 if unknown, which leaves the bulbs out of the sum). */
float   im_dim_rheostat_ohm(float open_v, float loaded_v, float batt_v);
uint8_t im_dim_percent(float rheostat_ohm, float open_v, float batt_v);   /* 0..100 */

/* Piecewise-linear table lookup (senders): x ascending, clamps at the ends. */
float im_table(const float *x, const float *y, uint8_t n, float v);

#endif
