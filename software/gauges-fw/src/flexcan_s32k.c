/* FlexCAN0 (car bus) and FlexCAN1 (private link) register driver, RM chapter 55. Written from the RM; compiled and linked for the
 * S32K144, NEVER RUN on a part.
 *
 * Both controllers use the 8 MHz crystal as the protocol engine clock (CTRL1[CLKSRC] = 0, SOSCDIV2 = divide by 1; the RM requires
 * that clock to be slower than the bus clock, 8 < 40 MHz), so the bit rate does not depend on the PLL. Mailboxes: one per accepted
 * identifier with an individual mask that compares all 11 identifier bits, so each holds the NEWEST frame of its message; transmit
 * mailboxes follow the receive ones. Reception is polled from the 10 ms loop.
 *
 * The car bus cannot transmit, in three independent ways: CTRL1[LOM] (listen-only) is set, no transmit mailbox is configured and
 * tx() refuses the bus, and the CAN0_TX pin (PTE5) is never given to the FlexCAN: it is a GPIO output held high (recessive). */
#include "can_bittiming.h"
#include "can_hw.h"
#include "canmb.h"
#include "gauges_pins.h"
#include "s32k144_regs.h"

#define PE_CLOCK_HZ   8000000u
#define MB_COUNT      16u
#define POLL_LIMIT    200000u

typedef struct { uint8_t port, pin; } pin_t;

static const pin_t CAN0_RX = { PORTE, 4 };      /* PIN_CAN0_RX, CAN0_RX alt 5 (IO signal table) */
static const pin_t CAN0_TX = { PORTE, 5 };      /* PIN_CAN0_TX, held high as a GPIO, never the FlexCAN function */
static const pin_t CAN0_EN = { PORTB, 5 };      /* PIN_CAN0_EN, TJA1043T */
static const pin_t CAN0_STB_N = { PORTB, 4 };   /* PIN_CAN0_STB_N, TJA1043T */
static const pin_t CAN1_RX = { PORTC, 6 };      /* PIN_CAN1_RX, CAN1_RX alt 3 */
static const pin_t CAN1_TX = { PORTC, 7 };      /* PIN_CAN1_TX, CAN1_TX alt 3 */
static const pin_t CAN1_STB = { PORTE, 0 };     /* PIN_CAN1_STB, TCAN1044V standby (high = standby) */

typedef struct {
    bool    up, listen_only;
    uint8_t n_rx, n_tx;
    uint16_t tx_id[CAN_MAX_IDS];
    uint8_t next_rx;                            /* round robin start, so a busy mailbox cannot starve the others */
} bus_t;
static bus_t g_bus[CAN_BUS_COUNT];

static void pin_mux(pin_t p, unsigned mux)
{
    PCC_PORT(p.port) = PCC_CGC;
    PORT_PCR(p.port, p.pin) = PORT_MUX(mux);
}

static void pin_out(pin_t p, bool high)
{
    pin_mux(p, 1);
    if (high) GPIO_PSOR(p.port) = 1u << p.pin; else GPIO_PCOR(p.port) = 1u << p.pin;
    GPIO_PDDR(p.port) |= 1u << p.pin;
}

static bool wait_for(volatile uint32_t *reg, uint32_t mask, bool set)
{
    for (uint32_t k = 0; k < POLL_LIMIT; k++)
        if (((*reg & mask) != 0u) == set) return true;
    return false;
}

static bool can_start(can_bus_t bus, const can_config_t *cfg)
{
    if ((unsigned)bus >= CAN_BUS_COUNT || cfg->n_rx + cfg->n_tx > MB_COUNT || cfg->n_rx > CAN_MAX_IDS || cfg->n_tx > CAN_MAX_IDS) return false;
    can_timing_t t;
    if (!can_bit_timing(PE_CLOCK_HZ, cfg->bitrate, &t)) return false;
    if (bus == CAN_BUS_CAR && !cfg->listen_only) return false;                      /* the car bus is receive-only, always */
    const unsigned i = (unsigned)bus;
    bus_t *b = &g_bus[bus];
    b->up = false;

    SCG_SOSCDIV = (SCG_SOSCDIV & ~(7u << 8)) | SCG_SOSCDIV2(1);                      /* 8 MHz to the protocol engines */
    if (bus == CAN_BUS_CAR) {
        PCC_FLEXCAN0 = PCC_CGC;
        pin_out(CAN0_TX, true);                                                       /* recessive, and not the FlexCAN function */
        pin_mux(CAN0_RX, 5);
        pin_out(CAN0_EN, true);                                                       /* TJA1043T normal mode: EN and STB_N high */
        pin_out(CAN0_STB_N, true);
    } else {
        PCC_FLEXCAN1 = PCC_CGC;
        pin_mux(CAN1_TX, 3);
        pin_mux(CAN1_RX, 3);
        pin_out(CAN1_STB, false);                                                     /* TCAN1044V normal mode: STB low */
    }

    /* Leave Disable mode into Freeze mode, soft reset, then configure (CTRL1 timing, MB RAM and RXIMR only accept writes in Freeze) */
    CAN_MCR(i) &= ~CAN_MCR_MDIS;
    CAN_MCR(i) |= CAN_MCR_FRZ | CAN_MCR_HALT;                                          /* also when restarting a running controller */
    if (!wait_for(&CAN_MCR(i), CAN_MCR_FRZACK, true)) return false;
    CAN_MCR(i) |= CAN_MCR_SOFTRST;
    if (!wait_for(&CAN_MCR(i), CAN_MCR_SOFTRST, false)) return false;
    CAN_MCR(i) |= CAN_MCR_FRZ | CAN_MCR_HALT;
    if (!wait_for(&CAN_MCR(i), CAN_MCR_FRZACK, true)) return false;

    for (unsigned mb = 0; mb < MB_COUNT; mb++) {                                       /* the mailbox RAM and masks power up undefined */
        for (unsigned w = 0; w < 4; w++) CAN_MB_WORD(i, mb, w) = 0u;
        CAN_RXIMR(i, mb) = 0u;
    }
    CAN_MCR(i) = (CAN_MCR(i) & ~0x7Fu) | CAN_MCR_MAXMB(MB_COUNT - 1u) | CAN_MCR_IRMQ | CAN_MCR_SRXDIS | CAN_MCR_AEN;
    CAN_CTRL1(i) = can_ctrl1(&t, cfg->listen_only);

    for (unsigned k = 0; k < cfg->n_rx; k++) {
        CAN_MB_WORD(i, k, 1) = MB_ID_STD(cfg->rx_ids[k]);
        CAN_RXIMR(i, k) = MB_ID_STD_MASK;                                               /* all 11 bits must match; IDE is always compared */
        CAN_MB_WORD(i, k, 0) = MB_RX_EMPTY << MB_CODE_SHIFT;                            /* armed last */
    }
    b->n_rx = cfg->n_rx; b->n_tx = cfg->listen_only ? 0u : cfg->n_tx; b->listen_only = cfg->listen_only; b->next_rx = 0u;
    for (unsigned k = 0; k < b->n_tx; k++) {
        b->tx_id[k] = cfg->tx_ids[k];
        CAN_MB_WORD(i, cfg->n_rx + k, 0) = MB_TX_INACTIVE << MB_CODE_SHIFT;
    }
    CAN_IFLAG1(i) = 0xFFFFFFFFu;                                                        /* write 1 to clear */

    CAN_MCR(i) &= ~(CAN_MCR_HALT | CAN_MCR_FRZ);                                        /* leave Freeze mode */
    if (!wait_for(&CAN_MCR(i), CAN_MCR_FRZACK | CAN_MCR_NOTRDY, false)) return false;
    b->up = true;
    return true;
}

static bool can_rx(can_bus_t bus, can_frame_t *f)
{
    bus_t *b = &g_bus[bus];
    if (!b->up || b->n_rx == 0u) return false;
    const unsigned i = (unsigned)bus;
    for (unsigned n = 0; n < b->n_rx; n++) {
        unsigned mb = (b->next_rx + n) % b->n_rx;
        if ((CAN_IFLAG1(i) & (1u << mb)) == 0u) continue;
        uint32_t cs;
        unsigned guard = 0;
        do { cs = CAN_MB_WORD(i, mb, 0); } while ((cs & (1u << MB_CODE_SHIFT)) != 0u && ++guard < 100u);   /* BUSY bit: a frame is being moved in */
        uint32_t id = CAN_MB_WORD(i, mb, 1), d0 = CAN_MB_WORD(i, mb, 2), d1 = CAN_MB_WORD(i, mb, 3);
        (void)CAN_TIMER(i);                                                              /* reading the timer unlocks the mailbox */
        CAN_IFLAG1(i) = 1u << mb;
        CAN_MB_WORD(i, mb, 0) = MB_RX_EMPTY << MB_CODE_SHIFT;                            /* arm it again */
        b->next_rx = (uint8_t)((mb + 1u) % b->n_rx);
        if (canmb_rx_decode(cs, id, d0, d1, f)) return true;
    }
    return false;
}

static bool can_tx(can_bus_t bus, const can_frame_t *f)
{
    bus_t *b = &g_bus[bus];
    if (bus == CAN_BUS_CAR || b->listen_only || !b->up) return false;
    const unsigned i = (unsigned)bus;
    for (unsigned k = 0; k < b->n_tx; k++) {
        if (b->tx_id[k] != f->id) continue;
        unsigned mb = b->n_rx + k;
        if (mb_code(CAN_MB_WORD(i, mb, 0)) != MB_TX_INACTIVE) return false;             /* the previous frame has not left yet */
        uint32_t cs, id, d0, d1;
        canmb_tx_encode(f, &cs, &id, &d0, &d1);
        CAN_IFLAG1(i) = 1u << mb;
        CAN_MB_WORD(i, mb, 1) = id;
        CAN_MB_WORD(i, mb, 2) = d0;
        CAN_MB_WORD(i, mb, 3) = d1;
        CAN_MB_WORD(i, mb, 0) = cs;                                                      /* last: arms the transmission */
        return true;
    }
    return false;
}

static bool can_bus_off(can_bus_t bus)
{
    return g_bus[bus].up && CAN_ESR1_FLTCONF(CAN_ESR1((unsigned)bus)) >= 2u;
}

const can_hw_t can_hw_s32k = { can_start, can_rx, can_tx, can_bus_off };
