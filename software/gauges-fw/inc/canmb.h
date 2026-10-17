#ifndef CANMB_H
#define CANMB_H
/* FlexCAN message buffer words (RM 55.5.3): word 0 control/status, word 1 identifier, words 2 and 3 the eight data bytes with
 * byte 0 in the most significant byte of word 2. REAL, host-tested; flexcan_s32k.c does the register access. */
#include <stdbool.h>
#include <stdint.h>
#include "can_hw.h"

#define MB_CODE_SHIFT   24
#define MB_CODE_MASK    (0xFu << MB_CODE_SHIFT)
#define MB_RX_INACTIVE  0x0u
#define MB_RX_EMPTY     0x4u        /* armed, waiting for a frame */
#define MB_RX_FULL      0x2u
#define MB_RX_OVERRUN   0x6u
#define MB_TX_INACTIVE  0x8u
#define MB_TX_ABORT     0x9u
#define MB_TX_DATA      0xCu        /* a data frame waiting to go out; becomes TX_INACTIVE when sent */
#define MB_CS_IDE       (1u << 21)
#define MB_CS_RTR       (1u << 20)
#define MB_ID_STD(id)   ((uint32_t)(id) << 18)
#define MB_ID_STD_MASK  (0x7FFu << 18)

static inline uint32_t mb_code(uint32_t cs) { return (cs & MB_CODE_MASK) >> MB_CODE_SHIFT; }

/* Words of a transmit mailbox for a frame (standard identifier, data frame). Write cs LAST: that arms the transmission. */
void canmb_tx_encode(const can_frame_t *f, uint32_t *cs, uint32_t *id, uint32_t *d0, uint32_t *d1);

/* A received mailbox as a frame. False for an extended identifier or a remote frame (neither is wanted). */
bool canmb_rx_decode(uint32_t cs, uint32_t id, uint32_t d0, uint32_t d1, can_frame_t *f);

#endif
