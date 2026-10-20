/* Key-off sleep logic (src/power.c): confirm delay, the SuspendRequest countdown, cancel on key-on, cranking dips,
 * clock wrap, an aborted sleep entry, power-up with the key off, and no hardware layer at all. */
#include <stdio.h>
#include "power.h"

static bool g_ign;
bool inputs_ignition_on(void) { return g_ign; }      /* the debounced input power.c reads */

static int g_sleeps;
static void fake_sleep(void) { g_sleeps++; }          /* returns: like an aborted entry on the target */
static const power_hw_t HW = { fake_sleep };

static int g_fail, g_checks;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

/* run the 10 ms loop from t0 to t1 (exclusive) the way main.c does */
static void run(uint32_t *t, uint32_t ms)
{
    for (uint32_t end = *t + ms; (int32_t)(*t - end) < 0; *t += 10u) {
        power_poll(*t);
        power_enter_stop_if_idle(*t);
    }
}

static void key_off_sequence(uint32_t t0)
{
    uint32_t t = t0;
    power_init(&HW); g_sleeps = 0;
    g_ign = true; run(&t, 100);
    CHECK(power_ignition_on() && !power_suspend_request() && power_suspend_in_s() == 0u);

    g_ign = false; run(&t, 290);                        /* not yet confirmed */
    CHECK(power_ignition_on() && power_state() == POWER_RUN);
    run(&t, 20);                                        /* 300 ms reached */
    CHECK(!power_ignition_on() && power_state() == POWER_COUNTDOWN);
    CHECK(power_suspend_request() && power_suspend_in_s() == POWER_SUSPEND_COUNTDOWN_S);
    run(&t, 1000);
    CHECK(power_suspend_in_s() == POWER_SUSPEND_COUNTDOWN_S - 1u);
    run(&t, 3000);
    CHECK(power_suspend_in_s() == 1u && g_sleeps == 0);
    run(&t, 1000);
    CHECK(power_state() == POWER_SLEEP_READY && power_suspend_request() && power_suspend_in_s() == 0u);
    CHECK(g_sleeps >= 1);
    int before = g_sleeps;
    run(&t, 50);                                        /* an aborted entry is retried every tick */
    CHECK(g_sleeps > before);

    g_ign = true; run(&t, 10);                          /* key back while asleep-pending: run at once */
    CHECK(power_ignition_on() && power_state() == POWER_RUN && !power_suspend_request());
}

int main(void)
{
    key_off_sequence(1000u);
    key_off_sequence(0xFFFFFE00u);                      /* the millisecond clock wraps during the countdown */

    /* key back during the countdown cancels it */
    uint32_t t = 0;
    power_init(&HW); g_sleeps = 0; g_ign = false;
    run(&t, 2000);
    CHECK(power_state() == POWER_COUNTDOWN);
    g_ign = true; run(&t, 10);
    CHECK(power_state() == POWER_RUN && !power_suspend_request() && power_suspend_in_s() == 0u);
    g_ign = false; run(&t, 1000);                       /* a new key-off starts a fresh countdown */
    CHECK(power_state() == POWER_COUNTDOWN && power_suspend_in_s() == POWER_SUSPEND_COUNTDOWN_S);

    /* cranking dips shorter than the confirm time never start a shutdown */
    t = 50000u; power_init(&HW); g_sleeps = 0;
    for (int i = 0; i < 20; i++) {
        g_ign = false; run(&t, 200);
        g_ign = true; run(&t, 100);
        CHECK(power_state() == POWER_RUN && !power_suspend_request());
    }

    /* powered up with the key off (battery reconnected): sleeps after the confirm time and the countdown */
    t = 0; power_init(&HW); g_sleeps = 0; g_ign = false;
    run(&t, POWER_OFF_CONFIRM_MS + POWER_SUSPEND_COUNTDOWN_S * 1000u - 20u);
    CHECK(g_sleeps == 0);
    run(&t, 40);
    CHECK(g_sleeps >= 1);

    /* no hardware layer (host build of main.c): the state still advances, nothing is called */
    t = 0; power_init(0); g_ign = false;
    run(&t, 10000);
    CHECK(power_state() == POWER_SLEEP_READY);

    printf("%s: %d checks, %d failures\n", g_fail ? "FAIL" : "ok", g_checks, g_fail);
    return g_fail ? 1 : 0;
}
