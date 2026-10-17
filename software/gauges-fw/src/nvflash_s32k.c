#include "nvflash.h"
#include "s32k144_regs.h"

/* Written from RM chapter 36 (rev 14.2): FSTAT/FCCOB registers, the command write sequence (36.5.9.1), Program Phrase
 * (36.5.11.4) and Erase Flash Sector (36.5.11.6). Compiled and linked for the part, NEVER RUN on one.
 * Commands are refused in HSRUN and VLP modes (the part runs in RUN, 80 MHz). */

static const uint8_t *nv_base(void) { return (const uint8_t *)(uintptr_t)FLEXNVM_BASE; }
static bool nv_busy(void) { return (FTFC_FSTAT & FTFC_FSTAT_CCIF) == 0u; }

static bool launch(void)
{
    FTFC_FSTAT = FTFC_FSTAT_CCIF;               /* writing 1 clears CCIF and starts the command */
    return true;
}

static bool prepare(void)
{
    if (nv_busy()) return false;
    /* A previous error blocks the launch; clear the flags first, then load FCCOB, then launch (RM 36.5.9.1.2). */
    FTFC_FSTAT = FTFC_FSTAT_RDCOLERR | FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL;
    return true;
}

static void put_addr(uint32_t off)
{
    uint32_t a = FTFC_DFLASH_ADDR_BIT | off;
    FTFC_FCCOB(1) = (uint8_t)(a >> 16);
    FTFC_FCCOB(2) = (uint8_t)(a >> 8);
    FTFC_FCCOB(3) = (uint8_t)a;
}

static bool nv_erase(uint32_t off)
{
    if ((off % NV_SECTOR_BYTES) != 0u || off >= FLEXNVM_BYTES || !prepare()) return false;
    FTFC_FCCOB(0) = FTFC_CMD_ERSSCR;
    put_addr(off);
    return launch();
}

static bool nv_program(uint32_t off, const uint8_t phrase[NV_PHRASE_BYTES])
{
    if ((off % NV_PHRASE_BYTES) != 0u || off >= FLEXNVM_BYTES || !prepare()) return false;
    FTFC_FCCOB(0) = FTFC_CMD_PGM8;
    put_addr(off);
    for (unsigned i = 0; i < NV_PHRASE_BYTES; i++)
        FTFC_FCCOB(4 + i) = phrase[i];          /* FCCOB4..B = bytes 0..7 */
    return launch();
}

static bool nv_last_ok(void)
{
    uint8_t st = FTFC_FSTAT;
    FTFC_FSTAT = FTFC_FSTAT_RDCOLERR | FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL;
    FTFC_FERSTAT = FTFC_FERSTAT_DFDIF;          /* a torn write can leave an uncorrectable word behind; the odometer's CRC rejects it */
    return (st & (FTFC_FSTAT_RDCOLERR | FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL | FTFC_FSTAT_MGSTAT0)) == 0u;
}

nv_partition_t nv_s32k_partition(void)
{
    uint32_t f = SIM_FCFG1;
    unsigned depart = SIM_FCFG1_DEPART(f), eee = SIM_FCFG1_EEERAMSIZE(f);
    if (eee == 0xFu && (depart == 0x0u || depart == 0xCu)) return NV_PARTITION_DATA_FLASH;    /* RM table 10: 0000 and 1100 are 64 KB data flash */
    if (eee == 0xFu && depart == 0xFu) return NV_PARTITION_BLANK;
    return NV_PARTITION_OTHER;
}

/* Runs from SRAM (the linker script puts .ramfunc into .data, which the startup code copies): flash is not readable while
 * Program Partition runs, so nothing here may call into flash. Everything is volatile register access, inlined. */
__attribute__((section(".ramfunc"), noinline, used))
static bool format_in_ram(void)
{
    uint32_t primask;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(primask) :: "memory");
    while ((FTFC_FSTAT & FTFC_FSTAT_CCIF) == 0u) { }
    FTFC_FSTAT = FTFC_FSTAT_RDCOLERR | FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL;
    FTFC_FCCOB(0) = FTFC_CMD_PGMPART;
    FTFC_FCCOB(1) = 0u;         /* CSEc: no key size / MAC length provision */
    FTFC_FCCOB(2) = 0u;         /* SFE */
    FTFC_FCCOB(3) = 0u;         /* FlexRAM loaded with EEPROM data at reset: irrelevant with no EEPROM */
    FTFC_FCCOB(4) = 0x0Fu;      /* EEPROM data set size code: 0 bytes (RM table 7/8, "0xF") */
    FTFC_FCCOB(5) = 0x00u;      /* FlexNVM partition code 0000: 64 KB data flash, 0 KB EEPROM backup (table 10) */
    FTFC_FCCOB(6) = 0u;
    FTFC_FCCOB(7) = 0u;
    FTFC_FSTAT = FTFC_FSTAT_CCIF;
    while ((FTFC_FSTAT & FTFC_FSTAT_CCIF) == 0u) { }
    bool ok = (FTFC_FSTAT & (FTFC_FSTAT_ACCERR | FTFC_FSTAT_FPVIOL | FTFC_FSTAT_MGSTAT0)) == 0u;
    __asm volatile("msr primask, %0" :: "r"(primask) : "memory");
    return ok;
}

bool nv_s32k_format(void) { return format_in_ram(); }

const nv_ops_t nv_s32k = { nv_base, nv_busy, nv_erase, nv_program, nv_last_ok };
