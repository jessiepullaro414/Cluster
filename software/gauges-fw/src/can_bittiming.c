#include "can_bittiming.h"

bool can_bit_timing(uint32_t clock_hz, uint32_t bitrate, can_timing_t *out)
{
    if (bitrate == 0u) return false;
    bool found = false;
    float best_err = 1.0e9f;
    for (uint32_t div = 1; div <= 256u; div++) {
        uint32_t per_tq = div * bitrate;
        if (per_tq == 0u || clock_hz % per_tq != 0u) continue;
        uint32_t tq = clock_hz / per_tq;
        if (tq < 8u || tq > 25u) continue;
        /* phase segment 2 gets about 12.5 % of the bit, at least 2 and at most 8 quanta */
        uint32_t ps2 = (tq + 4u) / 8u;
        if (ps2 < 2u) ps2 = 2u;
        if (ps2 > 8u) ps2 = 8u;
        uint32_t rest = tq - 1u - ps2;                  /* propagation segment + phase segment 1 */
        uint32_t ps1 = rest / 2u;
        if (ps1 < 1u) ps1 = 1u;
        if (ps1 > 8u) ps1 = 8u;
        uint32_t prop = rest - ps1;
        if (prop < 1u) { prop = 1u; if (ps1 > 1u) ps1 = rest - 1u; }
        if (prop > 8u || ps1 > 8u || rest < 2u) continue;
        float sp = (float)(tq - ps2) / (float)tq;
        float err = sp > 0.875f ? sp - 0.875f : 0.875f - sp;
        /* the closest sample point wins; at equal distance the finer quantum (larger tq) does */
        if (!found || err < best_err - 1.0e-6f || (err < best_err + 1.0e-6f && tq > out->tq)) {
            uint32_t sjw = ps2 < ps1 ? ps2 : ps1;
            if (sjw > 4u) sjw = 4u;
            out->presdiv = (uint16_t)(div - 1u);
            out->rjw = (uint8_t)(sjw - 1u);
            out->pseg1 = (uint8_t)(ps1 - 1u);
            out->pseg2 = (uint8_t)(ps2 - 1u);
            out->propseg = (uint8_t)(prop - 1u);
            out->tq = (uint8_t)tq;
            out->sample_point = sp;
            best_err = err;
            found = true;
        }
    }
    return found;
}

uint32_t can_ctrl1(const can_timing_t *t, bool listen_only)
{
    return ((uint32_t)t->presdiv << 24) | ((uint32_t)t->rjw << 22) | ((uint32_t)t->pseg1 << 19) |
           ((uint32_t)t->pseg2 << 16) | (listen_only ? (1u << 3) : 0u) | t->propseg;
}
