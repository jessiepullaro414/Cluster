#include "inputs.h"
#include "power.h"

/* TODO: IGN_SENSE pin interrupt, debounce, shutdown delay (display/ gets
 * SuspendRequest and a SuspendInSeconds countdown first), STOP/VLPS entry
 * (the RM's AWIC table: any enabled pin interrupt wakes from STOP and VLPS). */
void power_init(void) {}
void power_poll(uint32_t now_ms) { (void)now_ms; }
bool power_ignition_on(void) { return inputs_ignition_on(); }
void power_enter_stop_if_idle(uint32_t now_ms) { (void)now_ms; }
