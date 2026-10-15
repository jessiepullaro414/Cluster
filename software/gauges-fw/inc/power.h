#ifndef POWER_H
#define POWER_H
/* STUB. Ignition tracking and low-power STOP mode. display/ suspends to RAM and
 * wakes on its own WAKE1 pin; gauges/ must be live within milliseconds of
 * ignition and tells display/ about key state with PowerState (0x310). */
#include <stdbool.h>
#include <stdint.h>

void power_init(void);
void power_poll(uint32_t now_ms);
bool power_ignition_on(void);
void power_enter_stop_if_idle(uint32_t now_ms);    /* wakes on the IGN_SENSE pin interrupt */
#endif
