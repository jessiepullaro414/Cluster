/* Program flash erase and program for the bootloader (RM chapter 36). Written from the RM; compiled and linked for the S32K144,
 * NEVER RUN on a part.
 *
 * The S32K144 has ONE program flash block, so the CPU cannot fetch code from it while a command on it runs: the command is
 * launched and waited for from a function that lives in SRAM (the linker script puts .ramfunc into .data, which the startup code
 * copies), with interrupts off and nothing in it that calls back into flash. Erase takes tens of milliseconds, a phrase about a
 * hundred microseconds; the update protocol is stop-and-wait, so nothing is lost while the CPU waits.
 * Sectors are 4 KB (the 512 KB part is interleaved), phrases are 8 bytes and 8-byte aligned. Address bit 23 = 0 selects program flash. */
#include <stdbool.h>
#include "pflash.h"
#include "s32k144_regs.h"

__attribute__((section(".ramfunc"), noinline, used))
static bool run_command(uint8_t cmd, uint32_t addr, const uint8_t *phrase)
{
    uint32_t primask;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(primask) :: "memory");
    while ((FTFC_FSTAT & FTFC_FSTAT_CCIF) == 0u) { }
    FTFC_FSTAT = FTFC_FSTAT_RDCOLERR | FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL;          /* clear old errors (RM 36.5.9.1.2) */
    FTFC_FCCOB(0) = cmd;
    FTFC_FCCOB(1) = (uint8_t)(addr >> 16);
    FTFC_FCCOB(2) = (uint8_t)(addr >> 8);
    FTFC_FCCOB(3) = (uint8_t)addr;
    if (phrase != 0) {
        FTFC_FCCOB(4) = phrase[0]; FTFC_FCCOB(5) = phrase[1]; FTFC_FCCOB(6) = phrase[2]; FTFC_FCCOB(7) = phrase[3];
        FTFC_FCCOB(8) = phrase[4]; FTFC_FCCOB(9) = phrase[5]; FTFC_FCCOB(10) = phrase[6]; FTFC_FCCOB(11) = phrase[7];
    }
    FTFC_FSTAT = FTFC_FSTAT_CCIF;                                                       /* launch */
    while ((FTFC_FSTAT & FTFC_FSTAT_CCIF) == 0u) { }
    bool ok = (FTFC_FSTAT & (FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL | FTFC_FSTAT_MGSTAT0)) == 0u;
    FTFC_FERSTAT = FTFC_FERSTAT_DFDIF;
    __asm volatile("msr primask, %0" :: "r"(primask) : "memory");
    return ok;
}

static const uint8_t *p_mem(void) { return (const uint8_t *)0; }

static bool p_erase(uint32_t addr)
{
    if ((addr % PFLASH_SECTOR_BYTES) != 0u || addr < BOOT_REGION_BYTES || addr >= PFLASH_BYTES) return false;      /* the bootloader's own region is never touched */
    return run_command(FTFC_CMD_ERSSCR, addr, 0);
}

static bool p_program(uint32_t addr, const uint8_t phrase[8])
{
    if ((addr % PFLASH_PHRASE_BYTES) != 0u || addr < BOOT_REGION_BYTES || addr + PFLASH_PHRASE_BYTES > PFLASH_BYTES) return false;
    return run_command(FTFC_CMD_PGM8, addr, phrase);
}

const pflash_ops_t pflash_s32k = { p_mem, p_erase, p_program };
