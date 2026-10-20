/* Register layer for the key-off sleep (power.h). Written from the S32K1xx RM rev 14 and the transceiver data sheets;
 * compiled and linked, NOT run on a part.
 *
 * Sources:
 *  - SMC at 0x4007E000 (S32K1xx memory map): PMPROT +0x08 (AVLP bit 5, write-once after reset), PMCTRL +0x0C
 *    (STOPM bits 2:0, 010 = VLPS), RM 40.3.3 / 40.3.4.
 *  - VLPS entry, RM 27.4 "VLPR/VLPS mode entry": the system clock must be SIRC, and FIRC, SOSC and SPLL must be
 *    disabled by software in RUN mode first. SCG_SIRCCSR +0x200 (reset 0x0100_0005: SIRC on, valid, kept on in
 *    VLP modes), SCG_FIRCCSR +0x300; RCCR SCS = 2 selects SIRC.
 *  - Wake, RM table 7-8 (AWIC stop and VLPS wake-up sources): "any enabled pin interrupt is capable of waking the
 *    system". The ignition sense is PTE1 (PIN_IGN_SENSE); PORT PCR IRQC bits 19:16 = 1001 interrupts on a rising
 *    edge, ISF bit 24 is write-one-to-clear; PORTE is IRQ 63.
 *  - The watchdog is configured with CS[STOP] = 0 (wdog_s32k.c), so it does not run in stop modes.
 *  - TJA1043T (NXP TJA1043 Rev 6, operating-mode table): STB_N LOW and EN LOW = Standby. TCAN1044V-Q1 (TI SLLSF17D):
 *    STB HIGH = low-power standby.
 * After the wake the chip is reset by software: every peripheral (clocks, FlexCAN, LPSPI, ADC, FTM, the screens)
 * starts exactly as from power-up, which is simpler and safer than restoring each one by hand. */
#include "panel_hal.h"
#include "power.h"
#include "s32k144_irq.h"
#include "s32k144_regs.h"

#define SMC_BASE          0x4007E000u
#define SMC_PMPROT        REG32(SMC_BASE + 0x08u)
#define SMC_PMCTRL        REG32(SMC_BASE + 0x0Cu)
#define SMC_PMPROT_AVLP   (1u << 5)
#define SMC_STOPM_MASK    7u
#define SMC_STOPM_VLPS    2u
#define SCG_SIRCCSR       REG32(SCG_BASE + 0x200u)
#define SCG_FIRCCSR       REG32(SCG_BASE + 0x300u)
#define SCG_SCS_SIRC      2u
#define SCB_SCR           REG32(0xE000ED10u)
#define SCB_SCR_SLEEPDEEP (1u << 2)
#define PCR_IRQC_MASK     (0xFu << 16)
#define PCR_IRQC_RISING   (0x9u << 16)
#define PCR_ISF           (1u << 24)
#define IGN_PORT          PORTE
#define IGN_PIN           1u              /* PTE1 */

/* PMPROT is write-once after a reset: allow the very-low-power modes at start-up, before anything could need it. */
void power_hw_s32k_init(void) { SMC_PMPROT = SMC_PMPROT_AVLP; }

void PORTE_IRQHandler(void)
{
    PORT_PCR(IGN_PORT, IGN_PIN) |= PCR_ISF;              /* the wake itself is all this interrupt is for */
}

static void enter_sleep(void)
{
    const panel_hal_t *hal = panel_hal_board();
    if (hal && hal->backlight)
        hal->backlight(hal->ctx, false);                  /* the screens keep their last picture, dark */
    GPIO_PCOR(PORTB) = (1u << 5) | (1u << 4);             /* TJA1043T EN (PTB5) and STB_N (PTB4) low: Standby */
    GPIO_PSOR(PORTE) = 1u << 0;                           /* TCAN1044V STB (PTE0) high: standby */

    __asm volatile ("cpsid i" ::: "memory");
    SYST_CSR = 0u;                                        /* no tick pending to abort the entry */
    uint32_t pcr = PORT_PCR(IGN_PORT, IGN_PIN) & ~PCR_IRQC_MASK;
    PORT_PCR(IGN_PORT, IGN_PIN) = pcr | PCR_IRQC_RISING | PCR_ISF;
    NVIC_ENABLE(PORTE_IRQn);

    /* Clocks: SIRC becomes the system clock (8 MHz, dividers 1/1/2), then SPLL, SOSC and FIRC are switched off. */
    SCG_RCCR = (SCG_SCS_SIRC << SCG_SCS_SHIFT) | SCG_DIVCORE(0) | SCG_DIVBUS(0) | SCG_DIVSLOW(1);
    for (uint32_t i = 0; i < 100000u && (SCG_CSR & SCG_SCS_MASK) != (SCG_SCS_SIRC << SCG_SCS_SHIFT); i++) { }
    SCG_SPLLCSR = 0u;
    SCG_SOSCCSR = 0u;
    SCG_FIRCCSR = 0u;

    SMC_PMCTRL = (SMC_PMCTRL & ~SMC_STOPM_MASK) | SMC_STOPM_VLPS;
    (void)SMC_PMCTRL;                                     /* the write must land before WFI */
    SCB_SCR |= SCB_SCR_SLEEPDEEP;
    if (PORT_PCR(IGN_PORT, IGN_PIN) & PCR_ISF) {          /* the key is already back: do not sleep at all */
        SCB_AIRCR = SCB_AIRCR_RESET;
        for (;;) { }
    }
    __asm volatile ("dsb\n\twfi\n\tisb" ::: "memory");
    /* Woken (or the entry was aborted by a pending interrupt): start again from reset either way. */
    SCB_AIRCR = SCB_AIRCR_RESET;
    for (;;) { }
}

const power_hw_t power_hw_s32k = { enter_sleep };
