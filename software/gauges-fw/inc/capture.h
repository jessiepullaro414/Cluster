#ifndef CAPTURE_H
#define CAPTURE_H
/* Period tracking for a pulse input (Hall speed sender, tach). REAL, host-tested; the FTM interrupt that feeds it is in
 * inputs_hw_s32k.c. Time is a 32-bit count of microseconds from a free-running timer (wraps after 71 minutes; every
 * difference below is taken in unsigned arithmetic, so a wrap is harmless).
 *
 * What it reports:
 *   CAP_ABSENT  fewer than two edges since boot: no sender wired, or the car has not moved yet
 *   CAP_RUNNING pulses arriving; the period is that of the last two edges, or the time since the last edge if that is longer
 *               (so the reading falls as soon as the next pulse is late, instead of sticking until a timeout)
 *   CAP_STOPPED a sender that has been seen but whose pulses are slower than 2 Hz: standing still
 *   CAP_FAULT   pulses faster than 2 kHz: noise, not a sender
 * Edges closer than CAP_MIN_EDGE_US are ignored as glitches. */
#include <stdbool.h>
#include <stdint.h>

#define CAP_MIN_EDGE_US   100u          /* 10 kHz: nothing real is this fast */
#define CAP_FAST_US       500u          /* faster than this (2 kHz) is a fault, matching im_pulse_rate_ok() */
#define CAP_SLOW_US       500000u       /* slower than this (2 Hz) counts as stopped */

typedef struct {
    uint32_t last_us;                   /* time of the last accepted edge */
    uint32_t period_us;                 /* between the last two accepted edges */
    uint8_t  edges;                     /* accepted edges, saturating at 255 */
    uint16_t glitches;                  /* rejected edges, saturating (diagnostics) */
} capture_t;

typedef enum { CAP_ABSENT = 0, CAP_RUNNING, CAP_STOPPED, CAP_FAULT } cap_state_t;

void        capture_reset(capture_t *c);
void        capture_edge(capture_t *c, uint32_t t_us);                       /* called from the interrupt */
cap_state_t capture_state(const capture_t *c, uint32_t now_us, uint32_t *period_us);
/* Keep the age of the last edge from wrapping into "recent" while standing still for over an hour. Call from the main loop. */
void        capture_keepalive(capture_t *c, uint32_t now_us);

/* A 32-bit microsecond time from the timer's overflow count and a 16-bit captured value. `tof_pending` is true if the
 * overflow flag was set when the capture was read but the overflow interrupt has not yet counted it; a capture in the lower
 * half of the range then belongs after the wrap. The timer counts 0..65535 at 1 MHz. */
uint32_t    capture_extend(uint16_t overflows, bool tof_pending, uint16_t cnv);

#endif
