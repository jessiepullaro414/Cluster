#ifndef PFLASH_H
#define PFLASH_H
/* Program flash access for the bootloader, behind a struct of functions so bootcore.c runs on the host against a model
 * (test/pflash_mock.c) and on the part against pflash_s32k.c. Offsets are absolute addresses in the 512 KB program flash.
 *
 * Layout: the bootloader owns 0x0000 - 0x7FFF (vector table, the flash configuration field at 0x400, FPROT write-protected by the
 * configuration field so that even a bug cannot erase it); the application owns 0x8000 - 0x7FFFF. Sectors are 4 KB (the 512 KB
 * part is interleaved, RM 36.2.1.1), programming is by 8-byte phrases that must be erased first. */
#include <stdbool.h>
#include <stdint.h>

#define PFLASH_SECTOR_BYTES  4096u
#define PFLASH_PHRASE_BYTES  8u
#define PFLASH_BYTES         0x80000u
#define BOOT_REGION_BYTES    0x8000u
#define APP_BASE             0x8000u
#define APP_SIZE             (PFLASH_BYTES - APP_BASE)

typedef struct {
    const uint8_t *(*mem)(void);                                  /* the memory-mapped flash, address 0 */
    bool (*erase)(uint32_t addr);                                 /* blocks until done; addr sector aligned; false on error */
    bool (*program)(uint32_t addr, const uint8_t phrase[8]);      /* blocks until done; addr 8-byte aligned; false on error */
} pflash_ops_t;

extern const pflash_ops_t pflash_s32k;

#endif
