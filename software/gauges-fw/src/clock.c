#include "clock.h"
#include "s32k144_regs.h"

#define FIRC_HZ        48000000u
#define WAIT_LIMIT     400000u      /* polls; a valid crystal takes ~0.5 ms, a poll ~3 cycles */

static uint32_t g_core_hz = FIRC_HZ;

static bool wait_valid(volatile uint32_t *csr)
{
    for (uint32_t i = 0; i < WAIT_LIMIT; i++)
        if (*csr & SCG_CSR_VLD)
            return true;
    return false;
}

static bool wait_scs(uint32_t scs)
{
    for (uint32_t i = 0; i < WAIT_LIMIT; i++)
        if ((SCG_CSR & SCG_SCS_MASK) == (scs << SCG_SCS_SHIFT))
            return true;
    return false;
}

uint32_t clock_core_hz(void) { return g_core_hz; }

bool clock_init_80mhz(void)
{
    const uint32_t div = SCG_DIVCORE(1) | SCG_DIVBUS(1) | SCG_DIVSLOW(2);

    /* Dividers first, still on FIRC, as RM 28.3.17 requires before SPLLEN. */
    SCG_RCCR = (SCG_SCS_FIRC << SCG_SCS_SHIFT) | div;
    if (!wait_scs(SCG_SCS_FIRC))
        return false;
    g_core_hz = FIRC_HZ / 2u;

    /* 8 MHz crystal. SOSCCFG can only change while SOSC is disabled. */
    SCG_SOSCCSR = 0u;
    SCG_SOSCDIV = 0u;
    SCG_SOSCCFG = SCG_SOSCCFG_8MHZ_XTAL;
    SCG_SOSCCSR = SCG_CSR_EN;
    if (!wait_valid(&SCG_SOSCCSR)) {
        SCG_SOSCCSR = 0u;
        return false;
    }

    /* PLL: 8 MHz / 1 x 40 = 320 MHz VCO, SPLL_CLK = VCO / 2 = 160 MHz. */
    SCG_SPLLCSR = 0u;
    SCG_SPLLDIV = 0u;
    SCG_SPLLCFG = SCG_SPLLCFG_VAL(40u - 16u, 0u);
    SCG_SPLLCSR = SCG_CSR_EN;
    if (!wait_valid(&SCG_SPLLCSR)) {
        SCG_SPLLCSR = 0u;
        SCG_SOSCCSR = 0u;
        return false;
    }

    /* RM 28.1.5: monitors (with reset on error) on before SOSC/SPLL become the
     * system clock. */
    SCG_SOSCCSR = SCG_CSR_EN | SCG_CSR_CM | SCG_CSR_CMRE;
    SCG_SPLLCSR = SCG_CSR_EN | SCG_CSR_CM | SCG_CSR_CMRE;

    SCG_RCCR = (SCG_SCS_SPLL << SCG_SCS_SHIFT) | div;
    if (!wait_scs(SCG_SCS_SPLL))
        return false;                   /* still running on FIRC / 2 */
    g_core_hz = CLK_CORE_HZ;
    return true;
}
