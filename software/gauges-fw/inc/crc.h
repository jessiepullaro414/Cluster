#ifndef CRC_H
#define CRC_H
/* CRC-32 (IEEE 802.3, reflected, poly 0xEDB88320, init 0xFFFFFFFF, final XOR 0xFFFFFFFF), the common "zlib"
 * CRC. Bitwise: no table, so no flash cost and nothing to get wrong; the retained fault record, the odometer
 * log and the firmware-update image check are all a few dozen bytes to a few hundred KB, read rarely.
 * Check value: crc32("123456789") == 0xCBF43926. REAL, host-tested. */
#include <stddef.h>
#include <stdint.h>

uint32_t crc32_update(uint32_t crc, const void *data, size_t len);   /* crc: the previous return value, or CRC32_INIT */
#define CRC32_INIT 0u
uint32_t crc32(const void *data, size_t len);

#endif
