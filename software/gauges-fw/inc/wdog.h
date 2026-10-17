#ifndef WDOG_H
#define WDOG_H
/* Hardware side of the watchdog and the reset status. REAL register code (RM chapters 23 and 26), compiled for the
 * target, never run on the host: the policy lives in fault.c. */
#include <stdint.h>

/* Raw RCM_SRS: the reason for the most recent reset. Read it once, early. */
uint32_t rcm_reset_status(void);

/* Start the watchdog on the 128 kHz LPO with this timeout. Final configuration: UPDATE = 0, so nothing that runs
 * afterwards can disable or retime it (RM 23.4.3.1); only a reset opens it again. Not running in debug mode (a
 * halted core would reset every time). Waits for the new configuration to take effect. */
void wdog_start(uint32_t timeout_ms);

/* Restart the count. One 32-bit write of the refresh word (CMD32EN is set by the startup code). */
void wdog_kick(void);

#endif
