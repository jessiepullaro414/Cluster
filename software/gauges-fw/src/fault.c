#include <stddef.h>
#include <string.h>
#include "crc.h"
#include "fault.h"

/* RCM_SRS bits, RM 26.4.3 (rev 14.2 page 549-551) */
#define SRS_LOL      (1u << 3)
#define SRS_LOC      (1u << 2)
#define SRS_CMU_LOC  (1u << 4)
#define SRS_WDOG     (1u << 5)
#define SRS_PIN      (1u << 6)
#define SRS_POR      (1u << 7)
#define SRS_JTAG     (1u << 8)
#define SRS_LOCKUP   (1u << 9)
#define SRS_SW       (1u << 10)
#define SRS_MDM_AP   (1u << 11)

reset_cause_t fault_decode_reset(uint32_t srs)
{
    if (srs & SRS_POR)                         return RESET_POWER_ON;      /* LVD is set together with POR */
    if (srs & SRS_WDOG)                        return RESET_WATCHDOG;
    if (srs & SRS_LOCKUP)                      return RESET_LOCKUP;
    if (srs & SRS_SW)                          return RESET_SOFTWARE;
    if (srs & (SRS_LOC | SRS_LOL | SRS_CMU_LOC)) return RESET_CLOCK;
    if (srs & (SRS_MDM_AP | SRS_JTAG))         return RESET_DEBUGGER;
    if (srs & SRS_PIN)                         return RESET_PIN;
    return RESET_UNKNOWN;                      /* includes a bare LVD or SACKERR: reported, not interpreted */
}

static uint32_t record_crc(const fault_retained_t *r)
{
    return crc32(r, offsetof(fault_retained_t, crc));
}

static void seal(fault_retained_t *r) { r->crc = record_crc(r); }

static void set_running(fault_retained_t *r, uint8_t t)
{
    r->running = t;
    r->running_inv = (uint8_t)~t;
}

static uint8_t running_of(const fault_retained_t *r)
{
    return (uint8_t)(r->running ^ r->running_inv) == 0xFFu ? r->running : TASK_NONE;
}

static void sat_inc(uint8_t *v) { if (*v < 255u) (*v)++; }

void fault_boot(fault_t *f, fault_retained_t *r, uint32_t srs, uint32_t now_ms)
{
    f->r = r;
    f->progress = 0u;
    f->healthy_since_ms = now_ms;
    f->cause = fault_decode_reset(srs);

    bool valid = f->cause != RESET_POWER_ON && r->magic == FAULT_RETAINED_MAGIC && r->crc == record_crc(r);
    uint8_t blamed = valid ? running_of(r) : TASK_NONE;
    if (!valid) {
        memset(r, 0, sizeof *r);
        r->magic = FAULT_RETAINED_MAGIC;
        r->suspect = TASK_NONE;
    }

    if (f->cause == RESET_WATCHDOG || f->cause == RESET_LOCKUP) {
        sat_inc(&r->consec_wdog);
        if (f->cause == RESET_WATCHDOG) sat_inc(&r->wdog_total);
        if (blamed < TASK_COUNT) {
            if (blamed == r->suspect)
                r->quarantine |= (uint8_t)(1u << blamed);       /* second time in the same task: switch it off */
            else
                r->suspect = blamed;
        }
        /* A hang outside every task (init, the idle wfi) blames nobody: it can only escalate through the count. */
    } else if (f->cause != RESET_POWER_ON) {
        r->consec_wdog = 0u;                                   /* a clean pin/software reset breaks the streak */
        r->suspect = TASK_NONE;
    }
    r->last_cause = (uint8_t)f->cause;
    set_running(r, TASK_NONE);
    seal(r);
}

bool fault_task_enabled(const fault_t *f, fault_task_t t)
{
    return (f->r->quarantine & (1u << t)) == 0u;
}

void fault_task_begin(fault_t *f, fault_task_t t) { set_running(f->r, (uint8_t)t); }

void fault_task_end(fault_t *f, fault_task_t t)
{
    f->progress |= 1u << t;
    set_running(f->r, TASK_NONE);
}

bool fault_service(fault_t *f, uint32_t now_ms)
{
    uint32_t need = TASK_MASK_ALL & ~(uint32_t)f->r->quarantine;
    if ((f->progress & need) != need)
        return false;
    f->progress = 0u;
    if (f->r->consec_wdog != 0u && now_ms - f->healthy_since_ms >= FAULT_HEALTHY_MS) {
        f->r->consec_wdog = 0u;
        f->r->suspect = TASK_NONE;
        seal(f->r);
    }
    return true;
}

void fault_ignition_on(fault_t *f)
{
    if (f->r->quarantine != 0u || f->r->consec_wdog != 0u || f->r->suspect != TASK_NONE) {
        f->r->quarantine = 0u;
        f->r->consec_wdog = 0u;
        f->r->suspect = TASK_NONE;
        seal(f->r);
    }
}

limp_t fault_level(const fault_t *f, const fault_facts_t *facts)
{
    if (f->r->quarantine != 0u || f->r->consec_wdog >= FAULT_LIMP_RESETS)
        return LIMP_LIMP;
    if (!facts->display_alive || facts->sender_open_mask != 0u || f->r->consec_wdog != 0u)
        return LIMP_DEGRADED;
    return LIMP_NORMAL;
}

uint8_t fault_quarantine_mask(const fault_t *f) { return f->r->quarantine; }
uint8_t fault_wdog_resets(const fault_t *f) { return f->r->wdog_total; }
