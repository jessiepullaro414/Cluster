#include "crc.h"

/* Nibble-at-a-time CRC-32: a 16-entry table (64 bytes of flash) and two lookups per byte, about four times faster than the bitwise loop.
 * It matters at one place: the bootloader checks the whole application image (100 KB and more) before every start, from the 48 MHz
 * internal clock. crc32_update takes and returns the finished CRC (already inverted), so calls chain:
 * crc32_update(crc32_update(0, a, n), b, m) equals the CRC of a followed by b. */
static const uint32_t NIBBLE[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
    0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu, 0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

uint32_t crc32_update(uint32_t crc, const void *data, size_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    crc = ~crc;
    while (len--) {
        crc ^= *p++;
        crc = (crc >> 4) ^ NIBBLE[crc & 0xFu];
        crc = (crc >> 4) ^ NIBBLE[crc & 0xFu];
    }
    return ~crc;
}

uint32_t crc32(const void *data, size_t len) { return crc32_update(CRC32_INIT, data, len); }
