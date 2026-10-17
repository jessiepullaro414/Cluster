#include "canmb.h"

void canmb_tx_encode(const can_frame_t *f, uint32_t *cs, uint32_t *id, uint32_t *d0, uint32_t *d1)
{
    uint8_t dlc = f->dlc > 8u ? 8u : f->dlc;
    uint8_t b[8] = { 0 };
    for (unsigned i = 0; i < dlc; i++) b[i] = f->data[i];
    *id = MB_ID_STD(f->id & 0x7FFu);
    *d0 = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3];
    *d1 = ((uint32_t)b[4] << 24) | ((uint32_t)b[5] << 16) | ((uint32_t)b[6] << 8) | b[7];
    *cs = (MB_TX_DATA << MB_CODE_SHIFT) | ((uint32_t)dlc << 16);
}

bool canmb_rx_decode(uint32_t cs, uint32_t id, uint32_t d0, uint32_t d1, can_frame_t *f)
{
    if ((cs & MB_CS_IDE) != 0u || (cs & MB_CS_RTR) != 0u) return false;
    uint8_t dlc = (uint8_t)((cs >> 16) & 0xFu);
    f->id = (uint16_t)((id >> 18) & 0x7FFu);
    f->dlc = dlc > 8u ? 8u : dlc;
    f->data[0] = (uint8_t)(d0 >> 24); f->data[1] = (uint8_t)(d0 >> 16); f->data[2] = (uint8_t)(d0 >> 8); f->data[3] = (uint8_t)d0;
    f->data[4] = (uint8_t)(d1 >> 24); f->data[5] = (uint8_t)(d1 >> 16); f->data[6] = (uint8_t)(d1 >> 8); f->data[7] = (uint8_t)d1;
    for (unsigned i = f->dlc; i < 8u; i++) f->data[i] = 0u;
    return true;
}
