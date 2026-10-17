#ifndef SENDERS_H
#define SENDERS_H
/* Resistive senders (fuel, oil pressure, coolant temperature) and battery voltage, from the ADC to engineering units.
 * REAL logic, host-tested against a fake ADC (test/test_senders.c); the ADC register driver is adc_s32k.c.
 *
 * Front end (gauges/ rev C schematic): sender node -- 1k pull-up to the 3V3 analog rail, and 1k series -- ADC pin with a
 * BAV99-Q clamp and 100 nF; the ADC reference is the same rail, so the reading is ratiometric:
 *     R_sender = 1000 * code / (4095 - code)         (an open wire reads full scale, a shorted one zero)
 * Battery: 49.9k / 10k divider from the protected battery rail, VREFH = the 3V3 rail:  V = code / 4095 * 3.3 * 5.99.
 *
 * The sender CURVES (ohms to level / kPa / degC) are NOT KNOWN: they have to be measured on the real senders (plan A9). Until
 * senders_set_curve() is given at least two points for a sender, that sender reports its resistance (senders_ohms) but its
 * value is invalid, so its screen shows dashes rather than an invented number. Battery voltage needs no curve. */
#include "adc.h"
#include "aggregate.h"

typedef enum { SENDER_FUEL = 0, SENDER_OIL = 1, SENDER_COOLANT = 2, SENDER_COUNT = 3 } sender_kind_t;

typedef struct { float ohm; float value; } sender_pt_t;     /* a curve: ascending ohms, linear between points, clamped at the ends */

#define SENDER_PULLUP_OHM   1000.0f
#define BATT_DIVIDER        ((49900.0f + 10000.0f) / 10000.0f)
#define SENDER_VREF_V       3.3f
#define SENDER_OPEN_CODE    4000u      /* above this the sender (or its wire) is open: more than about 42 kOhm */
#define SENDER_SHORT_CODE   8u         /* below this it is shorted to ground: under about 2 Ohm */
#define SENDER_FLAG_SAMPLES 25u        /* an open or a short must persist this many samples (1 s) before it is reported */

void     senders_init(const adc_ops_t *adc);        /* null: a dead set (everything invalid) */
void     senders_set_curve(sender_kind_t k, const sender_pt_t *pts, uint8_t n);   /* the points must outlive the call */
void     senders_poll(uint32_t now_ms);             /* call every 10 ms; reads one channel per call */
sample_t senders_fuel_pct(void);                    /* 0..100 % */
sample_t senders_coolant_c(void);                   /* degC */
sample_t senders_oil_kpa(void);                     /* kPa gauge */
sample_t senders_battery_v(void);                   /* volts */
uint8_t  senders_open_mask(void);                   /* bit 0 fuel, 1 oil, 2 coolant: reads open circuit (wire off or sender failed) */
uint8_t  senders_short_mask(void);                  /* the same bits for a short to ground */
void     sender_curves_load(void);                  /* installs the measured curves (src/sender_curves.c); none yet */
float    senders_ohms(sender_kind_t k);             /* filtered sender resistance, or -1 before the first reading / when open or shorted */
#endif
