#include "face.h"

void face_decode_row(const face_t *f, int row, int x_to, uint8_t *out)
{
    const uint8_t *p = f->rle + f->row_off[row];
    int x = 0;
    while (x < x_to) {
        uint8_t b = *p++;
        int run = (b & 15) + 1;
        uint8_t v = (uint8_t)(b >> 4);
        for (int i = 0; i < run && x < x_to; i++) out[x++] = v;
    }
}
