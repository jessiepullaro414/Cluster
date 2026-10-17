/* Register layer for the pulse, lamp and ignition inputs: FTM1 input capture (RM chapter 47), GPIO (chapter 12), PORT, PCC.
 * Written from the RM; compiled and linked for the S32K144, NEVER RUN on a part. */
#include "capture.h"
#include "gauges_pins.h"
#include "inputs_hw.h"
#include "s32k144_irq.h"
#include "s32k144_regs.h"

typedef struct { uint8_t port, pin; } pin_t;

/* port and pin of each input (the comment tag is what tools/check_pins.py compares with gauges_pins.h) */
static const pin_t LAMP_PINS[LAMP_COUNT] = {
    { PORTC, 9 },    /* PIN_LAMP_TURN_L */
    { PORTC, 8 },    /* PIN_LAMP_TURN_R */
    { PORTA, 7 },    /* PIN_LAMP_HIGH_BEAM */
    { PORTA, 6 },    /* PIN_LAMP_BRAKE */
    { PORTB, 12 },   /* PIN_LAMP_ALT */
    { PORTD, 4 },    /* PIN_LAMP_OIL */
};
static const pin_t IGN_PIN = { PORTE, 1 };      /* PIN_IGN_SENSE */
static const pin_t SPEED_PIN = { PORTA, 10 };   /* PIN_SPEED_IN */
static const pin_t TACH_PIN = { PORTA, 11 };    /* PIN_TACH_IN */

#define FTM1_SPEED_CH 4u        /* FTM1_CH4 on PTA10, PORT mux alt 2 (IO signal table) */
#define FTM1_TACH_CH  5u        /* FTM1_CH5 on PTA11, PORT mux alt 2 */

static volatile uint16_t g_overflows;           /* counts TOF in the overflow interrupt */
static uint32_t g_saved_primask;

static void gpio_input(pin_t p)
{
    PCC_PORT(p.port) = PCC_CGC;
    PORT_PCR(p.port, p.pin) = PORT_MUX(1);      /* GPIO, no internal pull: the board has its own divider (and DNP pull-up) */
    GPIO_PDDR(p.port) &= ~(1u << p.pin);
}

static void ftm_pin(pin_t p)
{
    PCC_PORT(p.port) = PCC_CGC;
    PORT_PCR(p.port, p.pin) = PORT_MUX(2);
}

void inputs_hw_init(void)
{
    for (unsigned i = 0; i < LAMP_COUNT; i++) gpio_input(LAMP_PINS[i]);
    gpio_input(IGN_PIN);
    ftm_pin(SPEED_PIN);
    ftm_pin(TACH_PIN);

    /* 8 MHz crystal -> SOSCDIV1 (divide by 1) -> FTM1 input clock, prescaled by 8 -> 1 MHz: one count is one microsecond. */
    SCG_SOSCDIV = (SCG_SOSCDIV & ~0x7u) | SCG_SOSCDIV1(1);
    PCC_FTM1 = 0u;                                          /* PCS is writable only while the clock gate is off */
    PCC_FTM1 = PCC_PCS(PCC_PCS_SOSCDIV1) | PCC_CGC;
    FTM1_SC = 0u;                                           /* counter stopped while it is set up */
    FTM1_MODE = 0x4u;                                       /* WPDIS (reset value), FTMEN off */
    FTM1_CNTIN = 0u;
    FTM1_MOD = 0xFFFFu;
    FTM1_CNT = 0u;
    FTM1_CNSC(FTM1_SPEED_CH) = FTM_CNSC_CHIE | FTM_CNSC_ELSA;
    FTM1_CNSC(FTM1_TACH_CH) = FTM_CNSC_CHIE | FTM_CNSC_ELSA;
    NVIC_ENABLE(FTM1_OVF_RELOAD_IRQn);
    NVIC_ENABLE(FTM1_CH4_5_IRQn);
    FTM1_SC = FTM_SC_TOIE | FTM_SC_CLKS_SYS | FTM_SC_PS(3);   /* starts the counter */
}

/* ---- interrupts ---------------------------------------------------------------------------------------------- */

void FTM1_OVF_RELOAD_IRQHandler(void)
{
    uint32_t sc = FTM1_SC;
    if (sc & FTM_SC_TOF) {
        FTM1_SC = sc & ~FTM_SC_TOF;             /* read with TOF set, then write 0 (RM 47.3.3) */
        g_overflows++;
    }
}

/* A capture's 32-bit time: read the captured value first, then the overflow flag; a flag still set with a value in the low
 * half of the range means the capture came after the wrap whose interrupt has not run yet (capture_extend). */
static uint32_t extended(uint16_t cnv)
{
    bool tof = (FTM1_SC & FTM_SC_TOF) != 0u;
    return capture_extend(g_overflows, tof, cnv);
}

void FTM1_CH4_5_IRQHandler(void)
{
    for (unsigned ch = FTM1_SPEED_CH; ch <= FTM1_TACH_CH; ch++) {
        uint32_t sc = FTM1_CNSC(ch);
        if (sc & FTM_CNSC_CHF) {
            uint16_t v = (uint16_t)FTM1_CNV(ch);
            uint32_t t = extended(v);
            FTM1_CNSC(ch) = sc & ~FTM_CNSC_CHF;
            inputs_on_capture(ch - FTM1_SPEED_CH, t);
        }
    }
}

/* ---- the ops the logic uses ---------------------------------------------------------------------------------- */

static void lock(void) { __asm volatile("mrs %0, primask\n cpsid i" : "=r"(g_saved_primask) :: "memory"); }
static void unlock(void) { __asm volatile("msr primask, %0" :: "r"(g_saved_primask) : "memory"); }

static uint32_t now_us(void)
{
    lock();
    uint16_t cnt = (uint16_t)FTM1_CNT;
    uint32_t t = extended(cnt);
    unlock();
    return t;
}

static uint8_t lamps_raw(void)
{
    uint8_t m = 0;
    for (unsigned i = 0; i < LAMP_COUNT; i++)
        if (GPIO_PDIR(LAMP_PINS[i].port) & (1u << LAMP_PINS[i].pin)) m |= (uint8_t)(1u << i);
    return m;
}

static bool ign_raw(void) { return (GPIO_PDIR(IGN_PIN.port) & (1u << IGN_PIN.pin)) != 0u; }

const inputs_hw_t inputs_hw_s32k = { now_us, lamps_raw, ign_raw, lock, unlock };
