#include <string.h>
#include "nv_mock.h"

uint8_t nv_mem[NV_MOCK_BYTES];
long nv_mock_events;
unsigned nv_mock_violations;
unsigned nv_mock_erases, nv_mock_programs;
unsigned nv_mock_sector_erases[NV_MOCK_BYTES / NV_SECTOR_BYTES];

static long cut_event;                  /* absolute event number at which the power fails, 0 = never */
static bool dead;
static uint64_t rng = 1;
static unsigned erase_ticks = 4, program_ticks = 1;
static unsigned fail_count;

typedef enum { NONE, ERASING, PROGRAMMING } kind_t;
static kind_t pending = NONE;
static unsigned remaining;
static uint32_t pend_off;
static uint8_t pend_data[NV_PHRASE_BYTES];
static bool last_ok_flag = true;

static uint32_t rnd(void)
{
    rng = rng * 6364136223846793005ull + 1442695040888963407ull;
    return (uint32_t)(rng >> 33);
}

void nv_mock_reset(uint32_t seed)
{
    memset(nv_mem, 0xFF, sizeof nv_mem);
    memset(nv_mock_sector_erases, 0, sizeof nv_mock_sector_erases);
    rng = seed * 2654435761u + 12345u;
    cut_event = 0; dead = false; pending = NONE; nv_mock_events = 0;
    nv_mock_violations = nv_mock_erases = nv_mock_programs = 0;
    erase_ticks = 4; program_ticks = 1; fail_count = 0; last_ok_flag = true;
}

void nv_mock_cut_at(long event) { cut_event = event ? nv_mock_events + event : 0; }
bool nv_mock_dead(void) { return dead; }
void nv_mock_power_cycle(void) { dead = false; pending = NONE; cut_event = 0; last_ok_flag = true; }
void nv_mock_set_latency(unsigned e, unsigned p) { erase_ticks = e; program_ticks = p; }
void nv_mock_fail_next(unsigned n) { fail_count = n; }

static bool event(void)
{
    nv_mock_events++;
    if (cut_event != 0 && nv_mock_events == cut_event) { dead = true; pending = NONE; return true; }
    return false;
}

static void apply_erase(bool partial)
{
    for (unsigned i = 0; i < NV_SECTOR_BYTES; i++) {
        uint8_t *b = &nv_mem[pend_off + i];
        if (!partial) { *b = 0xFF; continue; }
        switch (rnd() % 3) {
        case 0: break;                          /* still old */
        case 1: *b = 0xFF; break;               /* erased */
        default: *b = (uint8_t)rnd(); break;    /* anything */
        }
    }
}

static void apply_program(bool partial)
{
    for (unsigned i = 0; i < NV_PHRASE_BYTES; i++) {
        uint8_t *b = &nv_mem[pend_off + i];
        if (!partial) { *b &= pend_data[i]; continue; }
        switch (rnd() % 4) {
        case 0: break;                                  /* untouched */
        case 1: *b &= pend_data[i]; break;              /* done */
        default: *b &= (uint8_t)(pend_data[i] | rnd()); break;      /* some of the bits */
        }
    }
}

static void finish(void)
{
    if (fail_count) { fail_count--; pending = NONE; last_ok_flag = false; return; }   /* verify failed: nothing changed */
    if (event()) {                                      /* power fails half way */
        if (pending == ERASING) apply_erase(true); else apply_program(true);
        return;
    }
    if (pending == ERASING) { apply_erase(false); nv_mock_sector_erases[pend_off / NV_SECTOR_BYTES]++; }
    else apply_program(false);
    pending = NONE;
    last_ok_flag = true;
    (void)event();                                      /* power may fail right after, before the software notices */
}

void nv_mock_tick(void)
{
    if (dead || pending == NONE) return;
    if (remaining > 1) { remaining--; return; }
    finish();
}

static const uint8_t *m_base(void) { return nv_mem; }
static bool m_busy(void) { return dead || pending != NONE; }

static bool start(kind_t k, uint32_t off, const uint8_t *data)
{
    if (dead) return false;
    if (pending != NONE) { nv_mock_violations++; return false; }
    if (event()) return false;
    pending = k; pend_off = off;
    if (data) memcpy(pend_data, data, NV_PHRASE_BYTES);
    remaining = k == ERASING ? erase_ticks : program_ticks;
    if (remaining == 0) remaining = 1;
    return true;
}

static bool m_erase(uint32_t off)
{
    if (off % NV_SECTOR_BYTES != 0 || off + NV_SECTOR_BYTES > NV_MOCK_BYTES) { nv_mock_violations++; return false; }
    nv_mock_erases++;
    return start(ERASING, off, 0);
}

static bool m_program(uint32_t off, const uint8_t phrase[NV_PHRASE_BYTES])
{
    if (off % NV_PHRASE_BYTES != 0 || off + NV_PHRASE_BYTES > NV_MOCK_BYTES) { nv_mock_violations++; return false; }
    for (unsigned i = 0; i < NV_PHRASE_BYTES; i++)
        if (nv_mem[off + i] != 0xFF) { nv_mock_violations++; break; }      /* the phrase must be erased */
    nv_mock_programs++;
    return start(PROGRAMMING, off, phrase);
}

static bool m_last_ok(void) { bool r = last_ok_flag; last_ok_flag = true; return r; }

const nv_ops_t nv_mock = { m_base, m_busy, m_erase, m_program, m_last_ok };
