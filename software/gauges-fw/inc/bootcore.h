#ifndef BOOTCORE_H
#define BOOTCORE_H
/*
 * The CAN firmware-update protocol and the image check. REAL, host-tested against a flash model (test/test_boot.c) and against
 * the Python tool's own frames (tools/test_can_flash.py + test/boot_replay.c). The register code is in pflash_s32k.c and boot/.
 *
 * IMAGE: the application, linked at APP_BASE, begins with its vector table (0x400 bytes reserved) followed at +0x400 by a 32-byte
 * header; tools/mkimage.py fills in the length and the CRC-32 after the link. The bootloader runs the application only if the header
 * and the CRC of the whole image are right.
 *
 * PROTOCOL (private link, CAN1, 500 kbit/s, standard identifiers, stop-and-wait, one command in flight):
 *   0x7C0 tool -> boot   command   [cmd, args...]
 *   0x7C1 tool -> boot   data      [seq, 7 bytes]
 *   0x7C8 boot -> tool   response  [cmd | 0x80, status, ...]
 *   cmd 0x01 ENTER   [01 'B' 'L' board lo, board hi, 0, 0, 0]   -> [81 st bootver board lo, board hi, app_base>>12, 0, 0]
 *   cmd 0x02 BEGIN   [02 len(4, little endian) 0 0 0]           -> [82 st ...]  erases the application region first (the old image is
 *                                                                  invalid from this moment), then waits for data
 *   data frames      [seq(8 bit, from 0) 7 bytes]               -> [90 st next_seq ...]   a repeated seq is acknowledged and ignored
 *   cmd 0x03 FINISH  [03 crc(4, little endian) 0 0 0]           -> [83 st ...]  checks the header, the length and the CRC in flash
 *   cmd 0x04 ABORT   [04 ...]                                   -> [84 st ...]
 *   cmd 0x05 BOOT    [05 ...]                                   -> [85 st ...]  only after a successful FINISH; the caller then resets
 * Status 0 is OK; see BC_ST_*. A bad frame never changes state except where stated.
 */
#include <stdbool.h>
#include <stdint.h>
#include "can_hw.h"
#include "pflash.h"

#define BOOT_ID_CMD    0x7C0u
#define BOOT_ID_DATA   0x7C1u
#define BOOT_ID_RESP   0x7C8u
#define BOOT_VERSION   1u
#define BOARD_ID_GAUGES 1u

#define APP_HEADER_OFFSET 0x400u
#define APP_MAGIC         0x50414C43u        /* "CLAP" little endian */
#define APP_HEADER_BYTES  32u
#define APP_MIN_BYTES     (APP_HEADER_OFFSET + APP_HEADER_BYTES + 8u)
#define RAM_LOW           0x1FFF8000u
#define RAM_HIGH          0x20007000u

typedef struct {
    uint32_t magic;
    uint16_t header_version, board_id;
    uint16_t fw_major, fw_minor;
    uint32_t image_len;              /* from APP_BASE to the end of the image */
    uint32_t image_crc;              /* CRC-32 of the image with this field and header_crc read as zero */
    uint32_t min_boot_version;
    uint32_t reserved;
    uint32_t header_crc;             /* CRC-32 of the 28 bytes before it */
} app_header_t;

typedef enum {
    BC_ST_OK = 0, BC_ST_BAD_STATE = 1, BC_ST_BAD_ARG = 2, BC_ST_FLASH = 3, BC_ST_CRC = 4, BC_ST_BAD_IMAGE = 5, BC_ST_SEQ = 6
} bc_status_t;

typedef enum { BC_IDLE = 0, BC_ENTERED, BC_RECEIVING, BC_RECEIVED, BC_VERIFIED } bc_state_t;

typedef struct {
    const pflash_ops_t *fl;
    uint16_t board_id;
    bc_state_t state;
    uint32_t len, written, received;     /* image length; bytes programmed; bytes taken from the stream */
    uint8_t  expect_seq;
    uint8_t  buf[8];
    uint8_t  nbuf;
    uint32_t last_ms;
    bool     boot_requested;
} bootcore_t;

void bootcore_init(bootcore_t *b, const pflash_ops_t *fl, uint16_t board_id);

/* Handle one frame; returns true if `resp` holds the answer to send. `now_ms` feeds the inactivity timeout. */
bool bootcore_on_frame(bootcore_t *b, const can_frame_t *in, can_frame_t *resp, uint32_t now_ms);

/* Give up a transfer that has gone quiet for 10 s (the application stays invalid). */
void bootcore_tick(bootcore_t *b, uint32_t now_ms);

/* Image checks on a memory-mapped application (mem points at APP_BASE, size bytes are readable). */
uint32_t app_image_crc(const uint8_t *mem, uint32_t len);
bool     app_image_valid(const uint8_t *mem, uint32_t size, uint16_t board_id);

/* What the bootloader does at reset: run the application, or stay and wait for an update. */
typedef enum { BOOT_RUN_APP = 0, BOOT_UPDATE_NO_APP, BOOT_UPDATE_REQUESTED, BOOT_UPDATE_APP_FAILING } boot_decision_t;
#define BOOT_FAILING_RESETS 6u              /* this many watchdog resets in a row and the application is considered broken */
boot_decision_t boot_decide(bool app_valid, bool update_requested, bool fault_record_valid, uint8_t consecutive_wdog_resets);

#endif
