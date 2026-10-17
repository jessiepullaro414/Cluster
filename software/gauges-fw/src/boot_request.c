#include "boot_request.h"

#ifdef HOST_BUILD
boot_request_t g_bootreq;
#else
boot_request_t g_bootreq __attribute__((section(".noinit.bootreq")));
#endif

void bootreq_write(boot_request_t *r, uint32_t value)
{
    r->value = value;
    r->value_inv = ~value;
    r->pad = 0u;
    r->magic = BOOTREQ_MAGIC;                    /* last: a half-written note is not valid */
}

uint32_t bootreq_take(boot_request_t *r)
{
    uint32_t v = BOOTREQ_NONE;
    if (r->magic == BOOTREQ_MAGIC && r->value_inv == ~r->value && (r->value == BOOTREQ_ENTER || r->value == BOOTREQ_RUN))
        v = r->value;
    r->magic = 0u; r->value = 0u; r->value_inv = 0u; r->pad = 0u;
    return v;
}
