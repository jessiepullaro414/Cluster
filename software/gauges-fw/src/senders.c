#include "senders.h"

/* TODO: ADC0/ADC1 setup on the pins in gauges_pins.h, averaging, open-circuit
 * detection (the sender front end pulls up to 3.3 V through 1 k), table lookup
 * from measured curves. All values invalid until implemented. */
static sample_t none(void) { sample_t s = { 0.0f, false, 0 }; return s; }

void senders_init(void) {}
void senders_poll(uint32_t now_ms) { (void)now_ms; }
sample_t senders_fuel_pct(void) { return none(); }
sample_t senders_coolant_c(void) { return none(); }
sample_t senders_oil_kpa(void) { return none(); }
sample_t senders_battery_v(void) { return none(); }
