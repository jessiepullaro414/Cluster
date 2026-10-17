#ifndef CAN_BITTIMING_H
#define CAN_BITTIMING_H
/* FlexCAN CTRL1 bit timing for a given protocol-engine clock and bit rate. REAL, host-tested.
 * One bit is  1 + (PROPSEG+1) + (PSEG1+1) + (PSEG2+1)  time quanta, a quantum is  (PRESDIV+1) / clock  (RM 55.5.2.3). The search
 * wants the bit rate EXACT and the sample point as close to 87.5 % as the quanta allow (80 to 90 % is the usual automotive band). */
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t presdiv;       /* register value: divide by presdiv + 1, 0..255 */
    uint8_t  rjw;           /* register value: resync jump width = rjw + 1, 0..3 */
    uint8_t  pseg1;         /* register value: phase segment 1 = pseg1 + 1, 0..7 */
    uint8_t  pseg2;         /* register value: phase segment 2 = pseg2 + 1, 1..7 */
    uint8_t  propseg;       /* register value: propagation segment = propseg + 1, 0..7 */
    uint8_t  tq;            /* time quanta per bit (8..25) */
    float    sample_point;  /* fraction of the bit at which the bit is sampled */
} can_timing_t;

/* False when no exact setting exists. */
bool can_bit_timing(uint32_t clock_hz, uint32_t bitrate, can_timing_t *out);

/* The CTRL1 word for a timing (CLKSRC = 0 oscillator clock; listen_only sets LOM). */
uint32_t can_ctrl1(const can_timing_t *t, bool listen_only);

#endif
