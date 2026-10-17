#ifndef FAULT_H
#define FAULT_H
/*
 * Fault manager: watchdog policy, reset-cause decode and limp mode. REAL, host-tested (the register access
 * is in wdog.h / wdog_s32k.c, so everything here runs on the host).
 *
 * The rule this implements: a dead display, a dead car bus, a broken sender or a hung firmware task must never
 * take the gauges down with them.
 *
 *  - Every pass of the 10 ms loop runs the firmware as a few TASKS. A task is bracketed by fault_task_begin()
 *    and fault_task_end(). The hardware watchdog is only kicked when every task that is switched on finished
 *    since the last kick (fault_service() says so). A hang in any task therefore resets the chip within the
 *    watchdog timeout (WDOG_TIMEOUT_MS), and the loop's own wfi is covered too.
 *  - Before it resets, the chip remembers (in RAM that the startup code does not clear, see fault_retained_t)
 *    which task was running. If the SAME task is running at two watchdog resets in a row, that task is
 *    QUARANTINED: switched off until the next ignition-on, while everything else keeps running. A hung SPI
 *    transfer to a screen then costs the screens, not the speedometer on the centre display, the CAN link or
 *    the lamps. Quarantine is reported to the display (GaugesStatus.QuarantineMask / LimpLevel) so Android can say so.
 *  - LimpLevel is derived from what is known, not stored: NORMAL, DEGRADED (display or a sender missing, or a recent
 *    watchdog reset), LIMP (a task is quarantined, or three watchdog resets in a row).
 *
 * Not claimed: the watchdog LPO clock rate and the real timeout have never been measured on a part, and the
 * failure paths run only in the host simulation.
 */
#include <stdbool.h>
#include <stdint.h>

/* The firmware tasks, one bit each in the progress and quarantine masks. The values go on the CAN link
 * (GaugesStatus.QuarantineMask), so do not renumber them. */
typedef enum {
    TASK_POWER = 0,       /* ignition, battery, STOP entry */
    TASK_SENSORS = 1,     /* resistive senders, battery voltage */
    TASK_INPUTS = 2,      /* Hall speed, tach, lamps, dimmer */
    TASK_CAN = 3,         /* both CAN controllers and the private-link transmit */
    TASK_SCREENS = 4,     /* rendering and the SPI transfers to the four GC9A01 */
    TASK_COUNT = 5
} fault_task_t;
#define TASK_NONE 0xFFu
#define TASK_MASK_ALL ((1u << TASK_COUNT) - 1u)

/* Reset causes as sent on the CAN link (GaugesStatus.ResetCause). */
typedef enum {
    RESET_UNKNOWN = 0, RESET_POWER_ON = 1, RESET_WATCHDOG = 2, RESET_SOFTWARE = 3,
    RESET_LOCKUP = 4, RESET_PIN = 5, RESET_CLOCK = 6, RESET_DEBUGGER = 7
} reset_cause_t;

typedef enum { LIMP_NORMAL = 0, LIMP_DEGRADED = 1, LIMP_LIMP = 2 } limp_t;

/* Decode RCM_SRS (RM 26.4.3) into one cause. Several bits can be set at once (power-on also sets LVD); the order
 * of the checks is the priority. Pure function. */
reset_cause_t fault_decode_reset(uint32_t srs);

/* The record that survives a watchdog reset. It lives in the last bytes of SRAM, which the startup code does not
 * clear (link/s32k144.ld .noinit). After a power-on reset SRAM holds nothing valid (ECC!), so fault_boot() only
 * trusts it when the reset cause is not power-on AND the magic and the CRC match. */
typedef struct {
    uint32_t magic;
    uint8_t  consec_wdog;       /* watchdog or lockup resets in a row (saturates at 255) */
    uint8_t  suspect;           /* task that was running at the previous such reset, TASK_NONE if none */
    uint8_t  quarantine;        /* bit per fault_task_t */
    uint8_t  wdog_total;        /* watchdog resets since power-on (saturates at 255) */
    uint8_t  last_cause;        /* reset_cause_t of the most recent reset */
    uint8_t  pad[3];
    uint32_t crc;               /* crc32 of the bytes above */
    uint8_t  running;           /* task being run right now; changes every task, so it is NOT covered by the crc ... */
    uint8_t  running_inv;       /* ... but is stored with its complement, so a half-written value reads as TASK_NONE */
    uint8_t  pad2[2];
} fault_retained_t;
#define FAULT_RETAINED_MAGIC 0x464C5431u   /* "FLT1" */

#define WDOG_TIMEOUT_MS     100u        /* ten loop periods; the loop kicks once per 10 ms pass */
#define FAULT_HEALTHY_MS    30000u      /* this long without a reset and the consecutive-reset count restarts */
#define FAULT_LIMP_RESETS   3u          /* this many watchdog resets in a row is LIMP even without a blamed task */

typedef struct {
    fault_retained_t *r;
    uint32_t progress;                  /* tasks finished since the last kick */
    uint32_t healthy_since_ms;
    reset_cause_t cause;                /* why this run started */
} fault_t;

/* Call once after the clock is up. `r` points at the retained record, `srs` is the raw RCM_SRS. */
void fault_boot(fault_t *f, fault_retained_t *r, uint32_t srs, uint32_t now_ms);

bool fault_task_enabled(const fault_t *f, fault_task_t t);   /* false while the task is quarantined */
void fault_task_begin(fault_t *f, fault_task_t t);
void fault_task_end(fault_t *f, fault_task_t t);

/* Call once at the end of every loop pass. Returns true when the watchdog may be kicked: every enabled task ended
 * since the last true. Also restarts the consecutive-reset count after FAULT_HEALTHY_MS of good passes. */
bool fault_service(fault_t *f, uint32_t now_ms);

/* The ignition just came on: give quarantined tasks and the reset history a fresh start. */
void fault_ignition_on(fault_t *f);

typedef struct {
    bool display_alive;                 /* DisplayHeartbeat arriving */
    uint8_t sender_open_mask;           /* any resistive sender reading open circuit */
} fault_facts_t;

limp_t  fault_level(const fault_t *f, const fault_facts_t *facts);
uint8_t fault_quarantine_mask(const fault_t *f);
uint8_t fault_wdog_resets(const fault_t *f);

#endif
