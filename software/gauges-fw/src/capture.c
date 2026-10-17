#include "capture.h"

void capture_reset(capture_t *c)
{
    c->last_us = 0u; c->period_us = 0u; c->edges = 0u; c->glitches = 0u;
}

void capture_edge(capture_t *c, uint32_t t_us)
{
    if (c->edges > 0u) {
        uint32_t dt = t_us - c->last_us;
        if (dt < CAP_MIN_EDGE_US) {                  /* contact bounce, ignition noise */
            if (c->glitches < 65535u) c->glitches++;
            return;
        }
        c->period_us = dt;
    }
    c->last_us = t_us;
    if (c->edges < 255u) c->edges++;
}

cap_state_t capture_state(const capture_t *c, uint32_t now_us, uint32_t *period_us)
{
    *period_us = 0u;
    if (c->edges < 2u) return CAP_ABSENT;
    uint32_t age = now_us - c->last_us;
    uint32_t p = c->period_us;
    if (age > p) p = age;                            /* the next pulse is late: the speed is at most 1 / age */
    if (p < CAP_FAST_US) return CAP_FAULT;
    if (p > CAP_SLOW_US) return CAP_STOPPED;
    *period_us = p;
    return CAP_RUNNING;
}

void capture_keepalive(capture_t *c, uint32_t now_us)
{
    if (c->edges >= 2u && (uint32_t)(now_us - c->last_us) > 4u * CAP_SLOW_US)
        c->last_us = now_us - 4u * CAP_SLOW_US;      /* still "long ago", never wraps into "just now" */
}

uint32_t capture_extend(uint16_t overflows, bool tof_pending, uint16_t cnv)
{
    uint32_t hi = overflows;
    if (tof_pending && cnv < 0x8000u) hi++;
    return (hi << 16) | cnv;
}
