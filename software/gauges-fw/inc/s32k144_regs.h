#ifndef S32K144_REGS_H
#define S32K144_REGS_H
/* Register layer for the S32K144, written from the S32K1xx Series Reference
 * Manual, Rev. 14 (09/2021) - no NXP SDK. Only registers the firmware uses are
 * here; each block names the RM section it was read from. Base addresses come
 * from NXP's S32K1xx_Memory_Map.xlsx (S32K144 column).
 *
 * All SCG and WDOG registers need 32-bit accesses (RM 28.3, 23.3). */
#include <stdint.h>

#define REG32(addr) (*(volatile uint32_t *)(uintptr_t)(addr))

/* ---- SCG, base 0x4006_4000 (RM chapter 28) ------------------------------ */
#define SCG_BASE        0x40064000u
#define SCG_CSR         REG32(SCG_BASE + 0x010u)    /* 28.3.3 clock status */
#define SCG_RCCR        REG32(SCG_BASE + 0x014u)    /* 28.3.4 RUN clock control */
#define SCG_SOSCCSR     REG32(SCG_BASE + 0x100u)    /* 28.3.8 */
#define SCG_SOSCDIV     REG32(SCG_BASE + 0x104u)    /* 28.3.9 */
#define SCG_SOSCCFG     REG32(SCG_BASE + 0x108u)    /* 28.3.10 */
#define SCG_SPLLCSR     REG32(SCG_BASE + 0x600u)    /* 28.3.17 */
#define SCG_SPLLDIV     REG32(SCG_BASE + 0x604u)    /* 28.3.18 */
#define SCG_SPLLCFG     REG32(SCG_BASE + 0x608u)    /* 28.3.19 */

/* SCS: system clock source (RCCR and CSR bits 27:24) */
#define SCG_SCS_SOSC    1u
#define SCG_SCS_FIRC    3u
#define SCG_SCS_SPLL    6u
#define SCG_SCS_SHIFT   24
#define SCG_SCS_MASK    (0xFu << SCG_SCS_SHIFT)
/* RCCR dividers: value n divides by n + 1 */
#define SCG_DIVCORE(n)  ((uint32_t)(n) << 16)
#define SCG_DIVBUS(n)   ((uint32_t)(n) << 4)
#define SCG_DIVSLOW(n)  ((uint32_t)(n) << 0)

#define SCG_CSR_EN      (1u << 0)       /* SOSCEN / SPLLEN (bit 0 of both) */
#define SCG_CSR_VLD     (1u << 24)      /* SOSCVLD / SPLLVLD */
#define SCG_CSR_CM      (1u << 16)      /* clock monitor enable */
#define SCG_CSR_CMRE    (1u << 17)      /* clock monitor generates reset */
#define SCG_CSR_ERR     (1u << 26)      /* SOSCERR / SPLLERR */

/* SOSCCFG: RANGE[5:4] = 3 high (8-40 MHz, required when the PLL is used),
 * HGO[3] = 0 low gain, EREFS[2] = 1 crystal oscillator */
#define SCG_SOSCCFG_8MHZ_XTAL   ((3u << 4) | (0u << 3) | (1u << 2))
/* SPLLCFG: MULT[20:16] (factor = MULT + 16), PREDIV[10:8] (factor = PREDIV + 1),
 * SOURCE[0] = 0 SOSC. VCO = ref / (PREDIV+1) * (MULT+16); SPLL_CLK = VCO / 2. */
#define SCG_SPLLCFG_VAL(mult, prediv)  (((uint32_t)(mult) << 16) | ((uint32_t)(prediv) << 8))

/* ---- WDOG, base 0x4005_2000 (RM chapter 23) ----------------------------- */
#define WDOG_BASE       0x40052000u
#define WDOG_CS         REG32(WDOG_BASE + 0x0u)     /* reset 0x0000_2980 */
#define WDOG_CNT        REG32(WDOG_BASE + 0x4u)
#define WDOG_TOVAL      REG32(WDOG_BASE + 0x8u)
#define WDOG_WIN        REG32(WDOG_BASE + 0xCu)
#define WDOG_CS_EN      (1u << 7)
#define WDOG_CS_UPDATE  (1u << 5)
#define WDOG_CS_RCS     (1u << 10)      /* reconfiguration successful */
#define WDOG_CS_ULK     (1u << 11)      /* unlocked */
#define WDOG_UNLOCK     0xD928C520u     /* 32-bit write to CNT (CMD32EN = 1 at reset) */
#define WDOG_REFRESH    0xB480A602u     /* 32-bit write to CNT while CMD32EN = 1 (RM 23.4.2.2) */
#define WDOG_CS_CMD32EN (1u << 13)
#define WDOG_CS_CLK_LPO (1u << 8)       /* CLK 01 = LPO_CLK, the 128 kHz low-power oscillator (RM 23.3.1.2, chip-specific 23.1.1) */
#define WDOG_LPO_HZ     128000u

/* ---- RCM, base 0x4007_F000 (S32K1xx_Memory_Map.xlsx; RM chapter 26) ---- */
#define RCM_BASE        0x4007F000u
#define RCM_SRS         REG32(RCM_BASE + 0x8u)      /* 26.4.3 system reset status, reset value 0x82 */
#define RCM_SRS_POR     (1u << 7)
#define RCM_SRS_LVD     (1u << 1)

/* ---- FIRC divider for peripheral clocks (RM 28.3.15) ---- */
#define SCG_FIRCDIV     REG32(SCG_BASE + 0x304u)
#define SCG_FIRCDIV2(n) ((uint32_t)(n) << 8)    /* 001 = divide by 1 -> 48 MHz; 000 = off (the reset value) */

/* ---- PCC, base 0x4006_5000 (RM chapter 29) ---- */
#define PCC_BASE        0x40065000u
#define PCC_LPSPI2      REG32(PCC_BASE + 0xB8u)     /* 29.6.11 */
#define PCC_PORT(i)     REG32(PCC_BASE + 0x124u + 4u * (i))   /* PORTA..PORTE = 0x124..0x134 */
#define PCC_CGC         (1u << 30)                  /* clock gate */
#define PCC_PCS(n)      ((uint32_t)(n) << 24)       /* only writable while CGC = 0 */
#define PCC_PCS_FIRCDIV2 3u                         /* 001 SOSCDIV2, 010 SIRCDIV2, 011 FIRCDIV2, 110 SPLLDIV2 (RM ch. 27 figure) */

/* ---- PORT pin control, ports A..E at 0x4004_9000 + 0x1000 * i (memory map) ---- */
#define PORT_PCR(i, n)  REG32(0x40049000u + 0x1000u * (i) + 4u * (n))
#define PORT_MUX(n)     ((uint32_t)(n) << 8)        /* PCR bits 10:8: 1 = GPIO, 3 = LPSPI2 on PTC0/1/15 (IO signal table) */
#define PORTA 0
#define PORTB 1
#define PORTC 2
#define PORTD 3
#define PORTE 4

/* ---- GPIO, ports A..E at 0x400F_F000 + 0x40 * i (RM chapter 12) ---- */
#define GPIO_BASE(i)    (0x400FF000u + 0x40u * (i))
#define GPIO_PSOR(i)    REG32(GPIO_BASE(i) + 0x04u)
#define GPIO_PCOR(i)    REG32(GPIO_BASE(i) + 0x08u)
#define GPIO_PDDR(i)    REG32(GPIO_BASE(i) + 0x14u)

/* ---- LPSPI2, base 0x4002_E000 (RM chapter 51) ---- */
#define LPSPI2_BASE     0x4002E000u
#define LPSPI2_CR       REG32(LPSPI2_BASE + 0x10u)
#define LPSPI2_SR       REG32(LPSPI2_BASE + 0x14u)
#define LPSPI2_CFGR1    REG32(LPSPI2_BASE + 0x24u)
#define LPSPI2_CCR      REG32(LPSPI2_BASE + 0x40u)
#define LPSPI2_FCR      REG32(LPSPI2_BASE + 0x58u)
#define LPSPI2_FSR      REG32(LPSPI2_BASE + 0x5Cu)
#define LPSPI2_TCR      REG32(LPSPI2_BASE + 0x60u)
#define LPSPI2_TDR      REG32(LPSPI2_BASE + 0x64u)
#define LPSPI_CR_MEN    (1u << 0)
#define LPSPI_CR_RST    (1u << 1)
#define LPSPI_CR_RTF    (1u << 8)
#define LPSPI_CR_RRF    (1u << 9)
#define LPSPI_SR_TCF    (1u << 10)                  /* transfer complete (idle, TX FIFO empty); write 1 to clear */
#define LPSPI_SR_TEF    (1u << 11)
#define LPSPI_SR_MBF    (1u << 24)                  /* module busy */
#define LPSPI_CFGR1_MASTER (1u << 0)
#define LPSPI_TCR_BYSW  (1u << 22)
#define LPSPI_TCR_RXMSK (1u << 19)                  /* receive data discarded: nothing to read back */
#define LPSPI_TCR_PRESCALE(n) ((uint32_t)(n) << 27) /* divide by 2^n */
#define LPSPI_TCR_FRAMESZ(bits) ((uint32_t)((bits) - 1u) & 0xFFFu)
#define LPSPI_FSR_TXCOUNT(fsr) ((fsr) & 7u)
#define LPSPI_TXFIFO_WORDS 4u                       /* PARAM reset value 0x0000_0202: 2^2 words each way */

/* ---- Cortex-M4 system registers (ARMv7-M, PPB at 0xE000_0000) ----------- */
#define SYST_CSR        REG32(0xE000E010u)
#define SYST_RVR        REG32(0xE000E014u)
#define SYST_CVR        REG32(0xE000E018u)
#define SYST_CSR_ENABLE     (1u << 0)
#define SYST_CSR_TICKINT    (1u << 1)
#define SYST_CSR_CLKSOURCE  (1u << 2)   /* 1 = core clock */
#define SCB_VTOR        REG32(0xE000ED08u)
#define SCB_CPACR       REG32(0xE000ED88u)  /* CP10 and CP11 full access = 0xF << 20 */

/* ---- Clock plan (RM 27.4, Table 27-3 "Normal RUN, VCO 320 MHz") ---------- */
#define CLK_XTAL_HZ     8000000u
#define CLK_CORE_HZ     80000000u       /* 8 MHz x 40 = 320 MHz VCO, /2 = 160 MHz SPLL, DIVCORE /2 */
#define CLK_BUS_HZ      40000000u       /* DIVBUS /2 */
#define CLK_FLASH_HZ    26666666u       /* DIVSLOW /3: at the RUN-mode limit of 26.67 MHz */

#endif
