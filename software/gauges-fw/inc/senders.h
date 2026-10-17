#ifndef SENDERS_H
#define SENDERS_H
/* STUB. Resistive senders and battery to engineering units. Needs the real
 * sender curves (measure the actual fuel / oil / coolant senders) before the
 * tables mean anything. */
#include "aggregate.h"

void     senders_init(void);
void     senders_poll(uint32_t now_ms);          /* call every 10 ms */
sample_t senders_fuel_pct(void);                 /* 0..100 % */
sample_t senders_coolant_c(void);                /* degC */
sample_t senders_oil_kpa(void);                  /* kPa gauge */
sample_t senders_battery_v(void);                /* volts */
uint8_t  senders_open_mask(void);                /* bit 0 fuel, 1 oil, 2 coolant: reads open circuit (wire off or sender failed) */
#endif
