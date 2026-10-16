/*
 * Panel bus for the four GC9A01 screens on the S32K144: LPSPI2 as the SPI master
 * (SCK PTC15, SDA = SOUT PTC1) plus GPIO for the per-screen chip selects and D/C lines,
 * the shared reset and the backlight switch. Pin assignments are gauges_pins.h
 * (checked against it by tools/check_pins.py).
 *
 * WRITTEN FROM THE REFERENCE MANUAL; NEVER RUN ON A PART. Facts used, with sources:
 *  - LPSPI2 base 0x4002_E000, CR/SR/CFGR1/CCR/FSR/TCR/TDR layouts: RM ch. 51.
 *  - Functional clock: PCC_LPSPI2[PCS] = 3 selects FIRCDIV2_CLK (RM ch. 27/29); SCG_FIRCDIV2
 *    must be enabled (it is off at reset): 48 MHz with divide-by-1.
 *  - SCK = functional clock / (PRESCALE x (SCKDIV + 2)) = 48 MHz / 5 = 9.6 MHz. The S32K144
 *    datasheet limits LPSPI to 10 MHz in Run mode (as quoted from Rev 13 on NXP's forum;
 *    CHECK THE CURRENT DATASHEET TABLE: the part number and supply decide it). The GC9A01
 *    itself accepts a 10 ns write cycle (GC9A01 datasheet 7.3.4), so the MCU is the limit.
 *  - SPI mode 0 (CPOL = 0, CPHA = 0): the GC9A01 samples SDA on the rising SCL edge (4.1.9).
 *  - Pin mux: GPIO = ALT1, LPSPI2 = ALT3 on PTC15/PTC1 (NXP IO signal table).
 *  - Blocking, polled transfers. A DMA path (eDMA with the LPSPI TX request) would free the CPU
 *    during the 6 ms a typical update spends on the bus; not done.
 */
#include "panel_hal.h"
#include "s32k144_regs.h"
#include "tick.h"

typedef struct { uint8_t port, pin; } pin_t;

/* From gauges_pins.h: CS0..3 = PTE3, PTD16, PTD15, PTE9; DC0..3 = PTE8, PTD7, PTD6, PTD5;
 * AUX_RST = PTB13; BL_EN = PTE7; SCK = PTC15; SOUT = PTC1. */
static const pin_t CS[4] = {
    { PORTE, 3 },      /* PIN_AUX_CS0 */
    { PORTD, 16 },     /* PIN_AUX_CS1 */
    { PORTD, 15 },     /* PIN_AUX_CS2 */
    { PORTE, 9 },      /* PIN_AUX_CS3 */
};
static const pin_t DC[4] = {
    { PORTE, 8 },      /* PIN_AUX_DC0 */
    { PORTD, 7 },      /* PIN_AUX_DC1 */
    { PORTD, 6 },      /* PIN_AUX_DC2 */
    { PORTD, 5 },      /* PIN_AUX_DC3 */
};
static const pin_t RST = { PORTB, 13 };     /* PIN_AUX_RST */
static const pin_t BL = { PORTE, 7 };       /* PIN_BL_EN */
static const pin_t SCK = { PORTC, 15 };     /* PIN_LPSPI2_SCK */
static const pin_t SOUT = { PORTC, 1 };     /* PIN_LPSPI2_SOUT */

#define SCKDIV            3u        /* 48 MHz / (3 + 2) = 9.6 MHz */
#define POLL_LIMIT        200000u   /* about 10 ms of polling: a hung bus must not hang the loop */
#define TCR_BASE          (LPSPI_TCR_RXMSK)            /* mode 0, PRESCALE 0, no PCS, 1-bit width */
#define MAX_FRAME_BYTES   512u                          /* FRAMESZ is 12 bits: 4096 bits */

static volatile uint32_t g_spi_timeouts;                /* nonzero: a transfer never completed */
static bool g_ready;

static void out(const pin_t *p, bool high)
{
    if (high) GPIO_PSOR(p->port) = 1u << p->pin;
    else GPIO_PCOR(p->port) = 1u << p->pin;
}

static void make_output(const pin_t *p, bool level)
{
    out(p, level);                                      /* set the level before the pin drives it */
    PORT_PCR(p->port, p->pin) = PORT_MUX(1);
    GPIO_PDDR(p->port) |= 1u << p->pin;
}

static bool wait_clear(volatile uint32_t *reg, uint32_t mask)
{
    for (uint32_t i = 0; i < POLL_LIMIT; i++)
        if ((*reg & mask) == 0u) return true;
    g_spi_timeouts++;
    return false;
}

static bool wait_set(volatile uint32_t *reg, uint32_t mask)
{
    for (uint32_t i = 0; i < POLL_LIMIT; i++)
        if (*reg & mask) return true;
    g_spi_timeouts++;
    return false;
}

static void hw_init(void)
{
    SCG_FIRCDIV |= SCG_FIRCDIV2(1);                     /* FIRCDIV2_CLK = 48 MHz for the LPSPI */

    for (unsigned i = PORTA; i <= PORTE; i++) PCC_PORT(i) = PCC_CGC;
    PCC_LPSPI2 = PCC_PCS(PCC_PCS_FIRCDIV2);             /* PCS can only change with the gate closed */
    PCC_LPSPI2 = PCC_PCS(PCC_PCS_FIRCDIV2) | PCC_CGC;

    for (unsigned s = 0; s < 4; s++) {
        make_output(&CS[s], true);                      /* deselected */
        make_output(&DC[s], true);
    }
    make_output(&RST, true);                            /* reset released */
    make_output(&BL, false);                            /* backlight off until the first frame is up */

    PORT_PCR(SCK.port, SCK.pin) = PORT_MUX(3);
    PORT_PCR(SOUT.port, SOUT.pin) = PORT_MUX(3);

    LPSPI2_CR = LPSPI_CR_RST;                           /* software reset, then configure disabled */
    LPSPI2_CR = 0u;
    LPSPI2_CFGR1 = LPSPI_CFGR1_MASTER;
    LPSPI2_CCR = SCKDIV;
    LPSPI2_CR = LPSPI_CR_MEN | LPSPI_CR_RTF | LPSPI_CR_RRF;
    g_ready = true;
}

static void idle_wait(void)
{
    wait_set(&LPSPI2_SR, LPSPI_SR_TCF);
    LPSPI2_SR = LPSPI_SR_TCF;                           /* write 1 to clear */
    wait_clear(&LPSPI2_SR, LPSPI_SR_MBF);
}

/* Whole 32-bit words in one frame. BYSW makes the first byte in memory the first on the wire. */
static void write_words(const uint8_t *buf, uint32_t bytes)
{
    wait_clear(&LPSPI2_SR, LPSPI_SR_MBF);
    LPSPI2_TCR = TCR_BASE | LPSPI_TCR_BYSW | LPSPI_TCR_FRAMESZ(bytes * 8u);
    for (uint32_t i = 0; i < bytes; i += 4) {
        for (uint32_t k = 0; k < POLL_LIMIT && LPSPI_FSR_TXCOUNT(LPSPI2_FSR) >= LPSPI_TXFIFO_WORDS; k++) { }
        uint32_t w = (uint32_t)buf[i] | ((uint32_t)buf[i + 1] << 8) | ((uint32_t)buf[i + 2] << 16) |
                     ((uint32_t)buf[i + 3] << 24);
        LPSPI2_TDR = w;
    }
    idle_wait();
}

static void write_byte(uint8_t b)
{
    wait_clear(&LPSPI2_SR, LPSPI_SR_MBF);
    LPSPI2_TCR = TCR_BASE | LPSPI_TCR_FRAMESZ(8u);
    LPSPI2_TDR = b;
    idle_wait();
}

/* ---- panel_hal_t ---- */

static void h_select(void *ctx, uint8_t s, bool asserted) { (void)ctx; out(&CS[s], !asserted); }
static void h_dc(void *ctx, uint8_t s, bool data) { (void)ctx; out(&DC[s], data); }
static void h_reset(void *ctx, bool asserted) { (void)ctx; out(&RST, !asserted); }
static void h_backlight(void *ctx, bool on) { (void)ctx; out(&BL, on); }

static void h_write(void *ctx, const uint8_t *buf, uint32_t len)
{
    (void)ctx;
    while (len >= 4u) {
        uint32_t chunk = len & ~3u;
        if (chunk > MAX_FRAME_BYTES) chunk = MAX_FRAME_BYTES;
        write_words(buf, chunk);
        buf += chunk;
        len -= chunk;
    }
    while (len--) write_byte(*buf++);
}

/* Granularity is the 10 ms tick, so a wait is up to 10 ms longer than asked: fine for the
 * 10 to 150 ms panel waits. Needs tick_init() to have run (startup.c does it before main). */
static void h_delay_ms(void *ctx, uint32_t ms)
{
    (void)ctx;
    uint32_t t0 = now_ms();
    while ((uint32_t)(now_ms() - t0) < ms + 10u)
        __asm volatile("wfi");
}

static const panel_hal_t g_hal = { 0, h_select, h_dc, h_reset, h_write, h_delay_ms, h_backlight };

const panel_hal_t *panel_hal_board(void)
{
    if (!g_ready) hw_init();
    return &g_hal;
}

uint32_t panel_hal_timeouts(void) { return g_spi_timeouts; }
