#ifndef POWER_H
#define POWER_H
/* Ignition tracking and key-off sleep. REAL logic, host-tested (test/test_power.c); the register layer is
 * power_hw_s32k.c (compiled and linked, never run on a part).
 *
 * Key off: the ignition input (already debounced 50 ms by inputs.c) must read off for POWER_OFF_CONFIRM_MS, so a
 * cranking dip or a bounce never starts a shutdown. Then PowerState (0x310) carries SuspendRequest with a
 * POWER_SUSPEND_COUNTDOWN_S countdown, which display/ (clusterd) shows and then suspends on. When the countdown
 * has run out and nothing is being saved, the board turns its backlights off, puts both CAN transceivers in
 * standby, arms the ignition pin interrupt and enters VLPS; the key coming back wakes it, and it restarts with a
 * clean software reset (the fault manager does not count that as a fault). Key on again during the countdown:
 * back to RUN at once. A board powered up with the key off (battery reconnected) sleeps after the same sequence. */
#include <stdbool.h>
#include <stdint.h>

#define POWER_OFF_CONFIRM_MS      300u
#define POWER_SUSPEND_COUNTDOWN_S 5u

typedef enum { POWER_RUN, POWER_COUNTDOWN, POWER_SLEEP_READY } power_state_t;

typedef struct {
    /* Backlights off, transceivers to standby, ignition pin interrupt armed, VLPS; on the target it never returns
     * (a wake resets the chip). Returning means the entry was aborted: the logic tries again on a later tick. */
    void (*enter_sleep)(void);
} power_hw_t;

void power_init(const power_hw_t *hw);              /* hw may be NULL: then the board never sleeps */
void power_poll(uint32_t now_ms);                   /* reads inputs_ignition_on() */
bool power_ignition_on(void);                       /* false only once the key-off is confirmed */
bool power_suspend_request(void);                   /* PowerState.SuspendRequest */
uint8_t power_suspend_in_s(void);                   /* PowerState.SuspendInSeconds, 0 when no request */
power_state_t power_state(void);
void power_enter_stop_if_idle(uint32_t now_ms);     /* the caller has already checked that nothing is being saved */

extern const power_hw_t power_hw_s32k;
void power_hw_s32k_init(void);                      /* target: allow VLPS (SMC_PMPROT is write-once after reset) */
#endif
