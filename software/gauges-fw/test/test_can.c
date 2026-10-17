/* CAN bit timing and mailbox word packing: pure functions behind the FlexCAN driver. */
#include <stdio.h>
#include <string.h>
#include "can_bittiming.h"
#include "canmb.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void check_timing(uint32_t clock, uint32_t rate, bool expect)
{
    can_timing_t t;
    bool ok = can_bit_timing(clock, rate, &t);
    CHECK(ok == expect);
    if (!ok) return;
    uint32_t tq = 4u + t.propseg + t.pseg1 + t.pseg2;                      /* 1 + (PROPSEG+1) + (PSEG1+1) + (PSEG2+1) */
    CHECK(tq == t.tq && tq >= 8u && tq <= 25u);
    CHECK((uint64_t)clock == (uint64_t)rate * (t.presdiv + 1u) * tq);       /* the bit rate is EXACT */
    CHECK(t.presdiv <= 255u);
    CHECK(t.propseg <= 7u && t.pseg1 <= 7u && t.pseg2 >= 1u && t.pseg2 <= 7u);
    CHECK(t.rjw <= 3u && t.rjw <= t.pseg2 && t.rjw <= t.pseg1);              /* the jump width fits inside both phase segments */
    CHECK(t.sample_point >= 0.75f && t.sample_point <= 0.90f);
    float sp = (float)(1u + t.propseg + 1u + t.pseg1 + 1u) / (float)tq;
    CHECK(sp > t.sample_point - 0.001f && sp < t.sample_point + 0.001f);
    uint32_t w = can_ctrl1(&t, true), n = can_ctrl1(&t, false);
    CHECK((w & 8u) != 0u && (n & 8u) == 0u);                                 /* LOM */
    CHECK((w & (1u << 13)) == 0u);                                           /* CLKSRC = oscillator */
    CHECK(((w >> 24) & 0xFFu) == t.presdiv && ((w >> 22) & 3u) == t.rjw && ((w >> 19) & 7u) == t.pseg1 &&
          ((w >> 16) & 7u) == t.pseg2 && (w & 7u) == t.propseg);
}

static void test_timing(void)
{
    static const uint32_t clocks[] = { 8000000u, 40000000u, 48000000u, 80000000u };
    static const uint32_t rates[] = { 125000u, 250000u, 500000u, 1000000u };
    for (unsigned c = 0; c < 4; c++)
        for (unsigned r = 0; r < 4; r++)
            check_timing(clocks[c], rates[r], true);
    can_timing_t t;
    CHECK(can_bit_timing(8000000u, 500000u, &t) && t.tq == 16u && t.sample_point == 0.875f);      /* the real case: 16 quanta, 87.5 % */
    CHECK(can_bit_timing(8000000u, 1000000u, &t) && t.tq == 8u && t.presdiv == 0u);
    CHECK(can_bit_timing(8000000u, 250000u, &t) && t.tq == 16u && t.presdiv == 1u);               /* 25 quanta max: the divider takes the rest */
    check_timing(8000000u, 300000u, false);                                  /* 26.67 quanta at a divider of 1: no exact setting */
    check_timing(7000000u, 1000000u, false);
    check_timing(8000000u, 0u, false);
    check_timing(8000000u, 5000000u, false);                                 /* below 8 quanta per bit */
}

static void test_mailbox_words(void)
{
    can_frame_t f = { 0x301u, 8, { 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF } };
    uint32_t cs, id, d0, d1;
    canmb_tx_encode(&f, &cs, &id, &d0, &d1);
    CHECK(mb_code(cs) == MB_TX_DATA);
    CHECK(((cs >> 16) & 0xFu) == 8u);
    CHECK((cs & MB_CS_IDE) == 0u && (cs & MB_CS_RTR) == 0u);
    CHECK(id == (0x301u << 18));
    CHECK(d0 == 0x01234567u && d1 == 0x89ABCDEFu);                           /* byte 0 in the top byte of word 2 */
    can_frame_t g;
    CHECK(canmb_rx_decode((MB_RX_FULL << MB_CODE_SHIFT) | (8u << 16), id, d0, d1, &g));
    CHECK(g.id == 0x301u && g.dlc == 8u && memcmp(g.data, f.data, 8) == 0);
    /* a short frame: the unused bytes read as zero, whatever the mailbox held */
    can_frame_t h = { 0x7FFu, 3, { 1, 2, 3, 99, 99, 99, 99, 99 } };
    canmb_tx_encode(&h, &cs, &id, &d0, &d1);
    CHECK(d0 == 0x01020300u && d1 == 0u);
    CHECK(canmb_rx_decode((MB_RX_FULL << MB_CODE_SHIFT) | (3u << 16), id, 0x010203FFu, 0xFFFFFFFFu, &g));
    CHECK(g.id == 0x7FFu && g.dlc == 3u && g.data[3] == 0u && g.data[7] == 0u);
    /* a DLC above 8 means 8; an extended or a remote frame is not wanted */
    CHECK(canmb_rx_decode(MB_RX_FULL << MB_CODE_SHIFT | (15u << 16), 0, 0, 0, &g) && g.dlc == 8u);
    CHECK(!canmb_rx_decode(MB_CS_IDE | (MB_RX_FULL << MB_CODE_SHIFT) | (8u << 16), 0, 0, 0, &g));
    CHECK(!canmb_rx_decode(MB_CS_RTR | (MB_RX_FULL << MB_CODE_SHIFT) | (8u << 16), 0, 0, 0, &g));
    can_frame_t big = { 0x1FFFu, 12, { 0 } };                                 /* out-of-range inputs are clamped, not wrapped into other bits */
    canmb_tx_encode(&big, &cs, &id, &d0, &d1);
    CHECK(id == (0x7FFu << 18) && ((cs >> 16) & 0xFu) == 8u);
    CHECK(mb_code(MB_TX_INACTIVE << MB_CODE_SHIFT) == 8u && mb_code(MB_RX_EMPTY << MB_CODE_SHIFT) == 4u);
    CHECK(MB_ID_STD_MASK == 0x1FFC0000u);
}

int main(void)
{
    test_timing();
    test_mailbox_words();
    if (failures) { printf("test_can: %d FAILED\n", failures); return 1; }
    printf("test_can: ok\n");
    return 0;
}
