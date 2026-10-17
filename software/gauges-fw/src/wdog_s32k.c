#include "s32k144_regs.h"
#include "wdog.h"

uint32_t rcm_reset_status(void) { return RCM_SRS; }

void wdog_start(uint32_t timeout_ms)
{
    uint32_t primask;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(primask) :: "memory");
    uint32_t ticks = timeout_ms * (WDOG_LPO_HZ / 1000u);
    if (ticks > 0xFFFFu) ticks = 0xFFFFu;       /* TOVAL is 16 bits; 0 would reset at once (RM 23.3.1.4) */
    if (ticks == 0u) ticks = 1u;
    /* The startup code left the watchdog unlocked-capable (UPDATE = 1, CMD32EN = 1, disabled). Unlock, then within 128 bus
     * clocks write the timeout and the control word; the new configuration takes effect once these are written (RM 23.4.3). */
    WDOG_CNT = WDOG_UNLOCK;
    WDOG_TOVAL = ticks;
    WDOG_CS = WDOG_CS_CMD32EN | WDOG_CS_CLK_LPO | WDOG_CS_EN;     /* UPDATE 0, INT 0, DBG 0, STOP 0 */
    while ((WDOG_CS & WDOG_CS_RCS) == 0u) { }
    __asm volatile("msr primask, %0" :: "r"(primask) : "memory");
}

void wdog_kick(void)
{
    uint32_t primask;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(primask) :: "memory");   /* an interrupt must not split the write (RM 23.4.2.2) */
    WDOG_CNT = WDOG_REFRESH;
    __asm volatile("msr primask, %0" :: "r"(primask) : "memory");
}
