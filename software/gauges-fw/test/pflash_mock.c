#include <string.h>
#include "pflash_mock.h"

uint8_t pf_mem[PFLASH_BYTES];
unsigned pf_violations, pf_boot_touched, pf_erases, pf_programs;
static long fail_n, cut_n, count;
static bool dead;
static uint32_t rng = 12345;

static uint32_t rnd(void) { rng = rng * 1664525u + 1013904223u; return rng >> 8; }

void pf_reset(void)
{
    memset(pf_mem, 0xFF, sizeof pf_mem);
    memset(pf_mem, 0xA5, BOOT_REGION_BYTES);                    /* the bootloader: anything that changes it is a bug */
    pf_violations = pf_boot_touched = pf_erases = pf_programs = 0;
    fail_n = cut_n = count = 0; dead = false;
}

void pf_fail_at(long n) { fail_n = n ? count + n : 0; }
void pf_cut_at(long n) { cut_n = n ? count + n : 0; }
bool pf_dead(void) { return dead; }
void pf_power_cycle(void) { dead = false; fail_n = cut_n = 0; }

static const uint8_t *m_mem(void) { return pf_mem; }

static bool m_erase(uint32_t addr)
{
    count++;
    if (dead) return false;
    if (addr % PFLASH_SECTOR_BYTES != 0 || addr + PFLASH_SECTOR_BYTES > PFLASH_BYTES) { pf_violations++; return false; }
    if (addr < BOOT_REGION_BYTES) { pf_boot_touched++; pf_violations++; return false; }
    if (fail_n && count == fail_n) return false;
    pf_erases++;
    if (cut_n && count == cut_n) {                              /* power lost half way through the erase */
        for (unsigned i = 0; i < PFLASH_SECTOR_BYTES; i++) { uint32_t r = rnd() % 3; if (r == 0) continue; pf_mem[addr + i] = r == 1 ? 0xFF : (uint8_t)rnd(); }
        dead = true;
        return false;
    }
    memset(pf_mem + addr, 0xFF, PFLASH_SECTOR_BYTES);
    return true;
}

static bool m_program(uint32_t addr, const uint8_t phrase[8])
{
    count++;
    if (dead) return false;
    if (addr % PFLASH_PHRASE_BYTES != 0 || addr + PFLASH_PHRASE_BYTES > PFLASH_BYTES) { pf_violations++; return false; }
    if (addr < BOOT_REGION_BYTES) { pf_boot_touched++; pf_violations++; return false; }
    for (unsigned i = 0; i < 8; i++) if (pf_mem[addr + i] != 0xFF) { pf_violations++; break; }
    if (fail_n && count == fail_n) return false;
    pf_programs++;
    if (cut_n && count == cut_n) {
        for (unsigned i = 0; i < 8; i++) { uint32_t r = rnd() & 3u; if (r == 0) continue; pf_mem[addr + i] &= r == 1 ? phrase[i] : (uint8_t)(phrase[i] | rnd()); }
        dead = true;
        return false;
    }
    for (unsigned i = 0; i < 8; i++) pf_mem[addr + i] &= phrase[i];
    return true;
}

const pflash_ops_t pflash_mock = { m_mem, m_erase, m_program };
