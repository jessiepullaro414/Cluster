#ifndef SENDERS_H
#define SENDERS_H
/* Resistive senders (fuel, oil pressure, coolant temperature) and battery voltage, from the ADC to engineering units.
 * REAL logic, host-tested against a fake circuit (test/test_inputs.c); the ADC register driver is adc_s32k.c.
 *
 * Front end (gauges/ schematic, review 2026-11-03): each sender node has a 1 k pull-up to SENDER_EXC (the excitation rail,
 * switched by U11 from the 3V3 analog supply) and a 1 k series resistor to its ADC pin, where 100 nF, a BAV99-Q clamp and a
 * 6.8 k bias resistor to SENDER_BIAS (an MCU output, high while awake) meet. The ADC reference is the same 3V3 rail.
 *
 * Why two readings: the senders return through the engine block or the tank and body, this board through its own ground
 * wire, and the two grounds sit tens to hundreds of millivolts apart (the body-to-engine strap carries the body loads'
 * return current). A 10 ohm sender with 3.3 mA in it is 33 mV, so a single reading cannot tell a full tank or a hot engine
 * from a few tens of millivolts of ground offset. Every poll reads all three channels and then flips the excitation; a
 * reading with it on and one with it off share the same ground offset, which cancels in their difference:
 *     node voltage   vS = vA (1 + k) - k vB                           k = R_SER / R_BIAS, vB = the bias (1.0 in VREF units)
 *     sender current I  = (vE - vS) / R_PU + (vB - vA) / R_BIAS       vE = 1 (on), or the floating rail (off): the mean of the
 *                                                                     three node voltages, which the three pull-ups join
 *     R_sender = (vS_on - vS_off) / (I_on - I_off),  offset = vS_on - I_on R_sender
 * The bias voltage cancels too (to 0.2 % through the floating-rail term), so a GPIO can drive it. The bias lifts the ADC pin
 * by 0.42 V, so an offset down to about -0.48 V stays readable; beyond that the channel reports a ground fault.
 * Battery: 49.9k / 10k divider from the protected battery rail, VREFH = the 3V3 rail:  V = code / 4095 * 3.3 * 5.99.
 *
 * The sender CURVES (ohms to level / kPa / degC) are NOT KNOWN: they have to be measured on the real senders (plan A9). Until
 * senders_set_curve() is given at least two points for a sender, that sender reports its resistance (senders_ohms) but its
 * value is invalid, so its screen shows dashes rather than an invented number. Battery voltage needs no curve. */
#include <stdbool.h>
#include "adc.h"
#include "aggregate.h"

typedef enum { SENDER_FUEL = 0, SENDER_OIL = 1, SENDER_COOLANT = 2, SENDER_COUNT = 3 } sender_kind_t;

typedef struct { float ohm; float value; } sender_pt_t;     /* a curve: ascending ohms, linear between points, clamped at the ends */

#define SENDER_PULLUP_OHM   1000.0f
#define SENDER_SERIES_OHM   1000.0f
#define SENDER_BIAS_OHM     6800.0f
#define BATT_DIVIDER        ((49900.0f + 10000.0f) / 10000.0f)
#define SENDER_VREF_V       3.3f
#define SENDER_OPEN_CODE    4000u      /* excitation on and the pin this close to the rail: the sender (or its wire) is open */
#define SENDER_SHORT_OHM    2.0f       /* below this the sender is shorted to ground */
#define SENDER_GROUND_CODE  8u         /* excitation off and the pin this low: the offset is beyond -0.48 V (a ground fault) */
#define SENDER_FLAG_SAMPLES 25u        /* an open, a short or a ground fault must persist this many samples (about 1 s) */

/* The excitation switch (U11). excite(true) connects the pull-ups to the 3V3 rail, excite(false) leaves them floating. */
typedef struct { void (*excite)(bool on); } sender_hw_t;
extern const sender_hw_t sender_hw_s32k;

void     senders_init(const adc_ops_t *adc, const sender_hw_t *hw);   /* either null: a dead set (everything invalid) */
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
float    senders_ground_mv(sender_kind_t k);        /* the sender's ground relative to this board's, mV (diagnostics); 0 if unknown */
uint8_t  senders_ground_fault_mask(void);           /* the bits of senders_open_mask(): offset beyond what the bias can read */
#endif
