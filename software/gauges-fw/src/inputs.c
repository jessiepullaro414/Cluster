#include "inputs.h"

/* TODO: FTM1 input capture with overflow handling (speed 5 Hz..1 kHz, tach up
 * to a few hundred Hz), lamp GPIOs with debounce (~20 ms, turn signals flash at
 * about 1.5 Hz), dimmer ADC with a 1.5 V lights-off threshold (a first guess
 * to measure on the car), ignition pin interrupt. */
static sample_t none(void) { sample_t s = { 0.0f, false, 0 }; return s; }

void inputs_init(void) {}
void inputs_poll(uint32_t now_ms) { (void)now_ms; }
sample_t inputs_speed_kph(void) { return none(); }
sample_t inputs_rpm_from_tach(void) { return none(); }
lamps_t inputs_lamps(uint8_t invert_mask) { lamps_t l = {0}; (void)invert_mask; return l; }
bool inputs_dash_lights_on(void) { return false; }
uint8_t inputs_dimmer_pct(void) { return 100; }
bool inputs_ignition_on(void) { return false; }
