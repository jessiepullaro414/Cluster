#include "bootcore.h"
#include "status.h"

/* The 32-byte header the bootloader looks for at APP_BASE + 0x400 (linker script s32k144_app.ld). The length and the two CRCs are
 * placeholders: tools/mkimage.py computes them from the finished binary and patches them in. An image that has not been through
 * mkimage.py has a length of 0xFFFFFFFF, which the bootloader rejects. */
__attribute__((section(".app_header"), used))
const app_header_t g_app_header = {
    .magic = APP_MAGIC, .header_version = 1u, .board_id = BOARD_ID_GAUGES,
    .fw_major = FW_MAJOR, .fw_minor = FW_MINOR,
    .image_len = 0xFFFFFFFFu, .image_crc = 0xFFFFFFFFu,
    .min_boot_version = 1u, .reserved = 0u, .header_crc = 0xFFFFFFFFu,
};
