#ifndef NVFLASH_H
#define NVFLASH_H
/* Non-blocking access to the S32K144's data flash (FlexNVM, 64 KB at 0x1000_0000, partitioned as all data flash:
 * Program Partition with EEPROM size code 0xF and partition code 0x0, a one-time step at production, see
 * README "Odometer and settings storage"). The odometer sits on this interface so that the same logic runs on the
 * target (nvflash_s32k.c) and against a model that cuts the power at any point (test/nv_mock.c).
 *
 * Rules the hardware imposes (RM 36.5.8, 36.5.11): erase works on 2 KB sectors, programming on 8-byte phrases that
 * are 8-byte aligned and must be erased (all 1) beforehand, a bit can only go 1 to 0 by programming, only one command
 * runs at a time, the CPU may keep fetching code from program flash while a data flash command runs but must not READ
 * the data flash meanwhile, and an interrupted command leaves undefined contents. Offsets are bytes from the start of
 * the data flash. */
#include <stdbool.h>
#include <stdint.h>

#define NV_SECTOR_BYTES 2048u
#define NV_PHRASE_BYTES 8u

typedef struct {
    const uint8_t *(*base)(void);               /* memory-mapped data flash for reads; only valid while !busy() */
    bool (*busy)(void);                         /* a command is still running */
    bool (*erase)(uint32_t off);                /* start erasing the sector at `off` (sector aligned); false if refused */
    bool (*program)(uint32_t off, const uint8_t phrase[NV_PHRASE_BYTES]);    /* start programming; false if refused */
    bool (*last_ok)(void);                      /* the last finished command completed without error (and clears the flags) */
} nv_ops_t;

/* The real driver for the part. */
extern const nv_ops_t nv_s32k;

/* How the FlexNVM is partitioned (SIM_FCFG1, read from the flash IFR at reset). The odometer needs all 64 KB as data flash. */
typedef enum {
    NV_PARTITION_DATA_FLASH = 0,        /* 64 KB data flash, no emulated EEPROM: usable */
    NV_PARTITION_BLANK = 1,             /* the IFR is erased (a fresh part): nv_s32k_format() may set it up */
    NV_PARTITION_OTHER = 2              /* partitioned some other way: leave it alone, the odometer runs from RAM only */
} nv_partition_t;
nv_partition_t nv_s32k_partition(void);

/* Program Partition: all of the FlexNVM becomes data flash (RM chapter 36 Program Partition command, table 36-61; FTFC addendum rev 2 chapter 6). Runs from RAM, because the
 * command takes the flash away from the CPU; returns true if the command finished clean. Takes effect after the next reset. Only
 * ever call it when nv_s32k_partition() says NV_PARTITION_BLANK: it erases the FlexNVM. */
bool nv_s32k_format(void);

#endif
