/* Reset path for the S32K144. Written from the S32K1xx RM Rev. 14.
 *
 * Order matters:
 *  1. Reset_Handler (naked asm) zeroes ALL of SRAM with 32-bit stores before
 *     anything reads it. SRAM is ECC-protected and every 32-bit location must
 *     be written before it is read; a read of an uninitialised word is likely
 *     a multi-bit ECC error (RM 32.4.1.1). Only 32-bit writes may be used,
 *     16/8-bit writes are read-modify-write. No stack is used until it is done.
 *     The fill stops at _estack: the last 32 bytes (.noinit) are the retained fault record, see Reset_C.
 *     This file is compiled three ways: the standalone image (link/s32k144.ld), the application behind the bootloader
 *     (-DAPP_BUILD: VTOR at 0x8000) and the bootloader itself (-DBOOT_BUILD: calls boot_main() instead of bringing up the clocks).
 *  2. Reset_C disables the watchdog (it is enabled at reset: CS = 0x2980,
 *     TOVAL = 0x400 on the LPO clock), copies .data, enables the FPU, brings
 *     up the clocks and the tick, and calls main.
 * The zero-fill takes about 15360 stores, well under the watchdog's first
 * timeout (about 8 ms at a 128 kHz LPO - verify the LPO rate on hardware). */
#include <stdint.h>
#include "clock.h"
#include "s32k144_regs.h"
#include "tick.h"

extern uint32_t __data_load, __data_start, __data_end, __noinit_start, __noinit_end;
#ifdef BOOT_BUILD
extern void boot_main(void);                /* the bootloader (boot/boot_main.c) */
#else
extern int main(void);
#endif
void Reset_C(void);

__attribute__((naked, noreturn)) void Reset_Handler(void)
{
    __asm volatile(
        "ldr  r0, =__ram_start\n"
        "ldr  r1, =_estack\n"
        "movs r2, #0\n"
        "1:\n"
        "str  r2, [r0], #4\n"
        "cmp  r0, r1\n"
        "blo  1b\n"
        "b    Reset_C\n");
}

/* RM 23.5.2: after reset the watchdog is unlocked; rewrite CS and TOVAL so the
 * new configuration takes effect and wait for RCS. UPDATE = 1 keeps it
 * reconfigurable later (the final watchdog policy comes with the power work,
 * PLAN.md A8). CS = CMD32EN (bit 13) | CLK = 01 LPO (bits 9:8) | UPDATE | EN = 0. */
static void wdog_disable(void)
{
    WDOG_CNT = WDOG_UNLOCK;
    WDOG_TOVAL = 0xFFFFu;
    WDOG_CS = (1u << 13) | (1u << 8) | WDOG_CS_UPDATE;
    while ((WDOG_CS & WDOG_CS_RCS) == 0u) { }
}

void Reset_C(void)
{
#ifdef APP_BUILD
    SCB_VTOR = 0x8000u;                         /* behind the bootloader the vector table is not at address 0 (link/s32k144_app.ld) */
#endif
    wdog_disable();

    /* The top of SRAM holds the fault record across a watchdog reset, so the fill above stops short of it. After a
     * power-on or low-voltage reset it holds nothing valid and must be written (32-bit stores) before anything reads it. */
    if (RCM_SRS & (RCM_SRS_POR | RCM_SRS_LVD)) {
        for (uint32_t *p = &__noinit_start; p < &__noinit_end; )
            *p++ = 0u;
    }

    /* .data initialisers; .bss is already zero from the SRAM fill. */
    const uint32_t *src = &__data_load;
    for (uint32_t *dst = &__data_start; dst < &__data_end; )
        *dst++ = *src++;

    SCB_CPACR |= (0xFu << 20);                  /* CP10, CP11 full access: FPU on */
    __asm volatile("dsb\n isb");

#ifdef BOOT_BUILD
    boot_main();                                /* decides before any clock or peripheral is touched; never returns */
#else
    (void)clock_init_80mhz();                   /* falls back to FIRC on failure */
    tick_init();
    (void)main();
#endif
    for (;;) { }
}
