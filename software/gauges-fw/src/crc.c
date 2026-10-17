#include "crc.h"

/* crc32_update takes and returns the finished CRC (already inverted), so calls chain: crc32_update(crc32_update(0, a, n), b, m)
 * equals the CRC of a followed by b. */
uint32_t crc32_update(uint32_t crc, const void *data, size_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    crc = ~crc;
    while (len--) {
        crc ^= *p++;
        for (int i = 0; i < 8; i++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

uint32_t crc32(const void *data, size_t len) { return crc32_update(CRC32_INIT, data, len); }
