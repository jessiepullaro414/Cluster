#include "clock.h"
#include "s32k144_regs.h"
#include "tick.h"

#define TICK_MS 10u

static volatile uint32_t g_ticks;
static uint32_t g_seen;
static uint32_t g_overruns;

void tick_init(void)
{
    SYST_RVR = clock_core_hz() / (1000u / TICK_MS) - 1u;       /* 24-bit: 800000-1 at 80 MHz */
    SYST_CVR = 0u;
    SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

void SysTick_Handler(void) { g_ticks++; }

uint32_t now_ms(void) { return g_ticks * TICK_MS; }

void wait_for_tick_10ms(void)
{
    while (g_ticks == g_seen)
        __asm volatile("wfi");
    if (g_ticks - g_seen > 1u)
        g_overruns++;
    g_seen = g_ticks;
}

uint32_t tick_overruns(void) { return g_overruns; }
