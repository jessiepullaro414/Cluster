#ifndef FACE_H
#define FACE_H
/* Printed faces of the factory theme: 240 x 240 pictures of 4-bit palette indices, run-length coded
 * (tools/gen_faces.py). A byte is value << 4 | (run - 1); row_off[y] is where row y starts in rle. */
#include <stdint.h>

typedef struct {
    const uint8_t  *rle;
    const uint16_t *row_off;            /* 240 entries */
    const uint32_t *pal;                /* 16 colours, 0x00RRGGBB */
} face_t;

#define FACE_COUNT 6
extern const face_t FACE_SPEED_MPH, FACE_SPEED_KPH, FACE_FUEL, FACE_OIL, FACE_TEMP, FACE_VOLTS;
extern const face_t *const FACE_LIST[FACE_COUNT];
extern const char *const FACE_NAMES[FACE_COUNT];
extern const uint32_t FACE_CHECKS[FACE_COUNT];     /* CRC-32 of the decoded pixels, one byte each, row-major */

/* Decode pixels [0, x_to) of one row into out (palette indices). */
void face_decode_row(const face_t *f, int row, int x_to, uint8_t *out);
#endif
