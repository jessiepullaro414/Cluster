#include "inputs.h"
#include "power.h"

/* See power.h for the sequence. Times are compared with signed differences so the 32-bit millisecond clock can wrap. */
static const power_hw_t *g_hw;
static power_state_t g_state;
static bool g_off_seen;            /* the debounced ignition reads off, the confirm timer is running */
static uint32_t g_off_since_ms;
static uint32_t g_countdown_end_ms;
static uint32_t g_now_ms;

void power_init(const power_hw_t *hw)
{
    g_hw = hw;
    g_state = POWER_RUN;
    g_off_seen = false;
}

void power_poll(uint32_t now_ms)
{
    g_now_ms = now_ms;
    if (inputs_ignition_on()) {
        g_off_seen = false;
        g_state = POWER_RUN;                                   /* the key came back: cancel any countdown */
        return;
    }
    if (!g_off_seen) {
        g_off_seen = true;
        g_off_since_ms = now_ms;
    }
    if (g_state == POWER_RUN && (int32_t)(now_ms - g_off_since_ms) >= (int32_t)POWER_OFF_CONFIRM_MS) {
        g_state = POWER_COUNTDOWN;
        g_countdown_end_ms = now_ms + POWER_SUSPEND_COUNTDOWN_S * 1000u;
    }
    if (g_state == POWER_COUNTDOWN && (int32_t)(now_ms - g_countdown_end_ms) >= 0)
        g_state = POWER_SLEEP_READY;
}

bool power_ignition_on(void) { return g_state == POWER_RUN; }

bool power_suspend_request(void) { return g_state != POWER_RUN; }

uint8_t power_suspend_in_s(void)
{
    if (g_state != POWER_COUNTDOWN)
        return 0u;
    int32_t left_ms = (int32_t)(g_countdown_end_ms - g_now_ms);
    if (left_ms <= 0)
        return 0u;
    return (uint8_t)((left_ms + 999) / 1000);                 /* whole seconds, rounded up: 5, 4, ... 1 */
}

power_state_t power_state(void) { return g_state; }

void power_enter_stop_if_idle(uint32_t now_ms)
{
    (void)now_ms;
    if (g_state == POWER_SLEEP_READY && g_hw && g_hw->enter_sleep)
        g_hw->enter_sleep();
}
