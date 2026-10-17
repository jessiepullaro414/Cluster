#ifndef PFLASH_MOCK_H
#define PFLASH_MOCK_H
/* A model of the 512 KB program flash with the rules the hardware has: erase by 4 KB sector, program by erased 8-byte phrase, and
 * the bootloader's own 32 KB never touched. Faults can be injected: the n-th command fails (nothing changes), or the power is lost
 * during the n-th command (a sector is left half erased, a phrase half programmed) and every later command fails. */
#include <stdbool.h>
#include <stdint.h>
#include "pflash.h"

extern uint8_t pf_mem[PFLASH_BYTES];
extern const pflash_ops_t pflash_mock;
extern unsigned pf_violations;           /* rule breaks: programming a non-erased phrase, a misaligned address, any access below APP_BASE */
extern unsigned pf_boot_touched;         /* commands that addressed the bootloader's region */
extern unsigned pf_erases, pf_programs;

void pf_reset(void);                     /* the bootloader region holds a sentinel pattern, the application region is erased */
void pf_fail_at(long n);                 /* the n-th command from now fails with no effect (0 = never) */
void pf_cut_at(long n);                  /* power is lost during the n-th command from now (0 = never) */
bool pf_dead(void);
void pf_power_cycle(void);

#endif
