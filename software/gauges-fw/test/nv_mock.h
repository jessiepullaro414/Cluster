#ifndef NV_MOCK_H
#define NV_MOCK_H
/* A model of the S32K144 data flash that can lose power at any point of any command.
 *
 * Each erase or program command passes through three events: it starts, it is half done, it is complete. The power can
 * fail at any one of them (nv_mock_cut_at(n) picks the n-th event counted from the call). A cut at the start changes
 * nothing, a cut half way leaves what an interrupted operation leaves (an erase: bytes that are erased, still old or
 * garbage; a program: bits that did and did not clear), a cut after the end keeps the whole result but the software never
 * learns of it. After a cut every command is refused and busy() stays true until nv_mock_power_cycle().
 * It also records every rule violation the hardware forbids: programming a phrase that is not erased, misaligned or
 * out-of-range commands, a command started while another runs. */
#include <stdbool.h>
#include <stdint.h>
#include "nvflash.h"

#define NV_MOCK_BYTES 65536u

extern uint8_t nv_mem[NV_MOCK_BYTES];
extern const nv_ops_t nv_mock;

void nv_mock_reset(uint32_t seed);              /* erased flash, no cut armed, counters cleared */
void nv_mock_cut_at(long event);                /* arm: the power fails at the event-th event from now (1 = the first); 0 = never */
bool nv_mock_dead(void);
void nv_mock_power_cycle(void);                 /* power back: the contents stay, commands work again */
void nv_mock_tick(void);                        /* time passes: a running command advances */
void nv_mock_set_latency(unsigned erase_ticks, unsigned program_ticks);
void nv_mock_fail_next(unsigned n);             /* the next n commands finish with an error flag (MGSTAT0) and no change */

extern long nv_mock_events;                     /* events seen since the last reset/arm */
extern unsigned nv_mock_violations;
extern unsigned nv_mock_erases, nv_mock_programs;
extern unsigned nv_mock_sector_erases[NV_MOCK_BYTES / NV_SECTOR_BYTES];

#endif
