/* Fault manager tests: reset-cause decode, the retained record, the task/watchdog policy, quarantine and limp
 * levels, driven by a small model of the chip's watchdog (a counter that resets the "chip" when the loop does not
 * kick it in time, keeping the retained record as the real SRAM would). */
#include <stdio.h>
#include <string.h>
#include "crc.h"
#include "fault.h"
#include "status.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

#define SRS_POR 0x82u
#define SRS_WDOG (1u << 5)

/* ---- the simulated chip ------------------------------------------------------------------------------------ */
static fault_retained_t ram;           /* survives "resets" */
static fault_t f;
static uint32_t now;
static uint32_t since_kick;
static int resets;

static void chip_reset(uint32_t srs)
{
    fault_boot(&f, &ram, srs, now);
    since_kick = 0;
}

/* One 10 ms pass. `hang` names the task that never returns (TASK_NONE = none, TASK_COUNT = hang outside any task).
 * Returns true if the watchdog expired and the chip reset. */
static bool pass(uint8_t hang)
{
    bool hung = false;
    for (int t = 0; t < TASK_COUNT && !hung; t++) {
        if (!fault_task_enabled(&f, (fault_task_t)t)) continue;
        fault_task_begin(&f, (fault_task_t)t);
        if (hang == t) { hung = true; break; }      /* never ends: running stays set */
        fault_task_end(&f, (fault_task_t)t);
    }
    if (hang == TASK_COUNT) hung = true;            /* stuck between tasks (running = none) */
    now += 10;
    if (!hung && fault_service(&f, now)) since_kick = 0;
    else since_kick += 10;
    if (since_kick >= WDOG_TIMEOUT_MS) {
        resets++;
        chip_reset(SRS_WDOG);
        return true;
    }
    return false;
}

static void run_until_reset(uint8_t hang)
{
    for (int i = 0; i < 50; i++)
        if (pass(hang)) return;
    CHECK(!"watchdog never expired");
}

static void power_on(void)
{
    memset(&ram, 0xA5, sizeof ram);      /* SRAM after power-up holds junk (startup.c zeroes it; fault_boot must not trust it anyway) */
    now = 0; resets = 0;
    chip_reset(SRS_POR);
}

static const fault_facts_t ALIVE = { true, 0u };

static void test_crc(void)
{
    CHECK(crc32("123456789", 9) == 0xCBF43926u);
    CHECK(crc32("", 0) == 0u);
    uint32_t a = crc32("1234", 4);
    CHECK(crc32_update(a, "56789", 5) == 0xCBF43926u);          /* chaining */
}

static void test_decode(void)
{
    CHECK(fault_decode_reset(0x82u) == RESET_POWER_ON);          /* POR + LVD, the reset value */
    CHECK(fault_decode_reset(1u << 5) == RESET_WATCHDOG);
    CHECK(fault_decode_reset(1u << 9) == RESET_LOCKUP);
    CHECK(fault_decode_reset(1u << 10) == RESET_SOFTWARE);
    CHECK(fault_decode_reset(1u << 6) == RESET_PIN);
    CHECK(fault_decode_reset(1u << 2) == RESET_CLOCK);
    CHECK(fault_decode_reset(1u << 3) == RESET_CLOCK);
    CHECK(fault_decode_reset(1u << 4) == RESET_CLOCK);
    CHECK(fault_decode_reset(1u << 8) == RESET_DEBUGGER);
    CHECK(fault_decode_reset(1u << 11) == RESET_DEBUGGER);
    CHECK(fault_decode_reset(0u) == RESET_UNKNOWN);
    CHECK(fault_decode_reset(1u << 1) == RESET_UNKNOWN);         /* bare LVD */
    CHECK(fault_decode_reset((1u << 5) | (1u << 6)) == RESET_WATCHDOG);   /* priority: watchdog beats pin */
    CHECK(fault_decode_reset((1u << 7) | (1u << 5)) == RESET_POWER_ON);   /* power-on beats everything */
}

static void test_healthy_run(void)
{
    power_on();
    CHECK(f.cause == RESET_POWER_ON);
    CHECK(ram.magic == FAULT_RETAINED_MAGIC && ram.quarantine == 0 && ram.consec_wdog == 0);
    for (int i = 0; i < 1000; i++) CHECK(!pass(TASK_NONE));
    CHECK(resets == 0);
    CHECK(fault_level(&f, &ALIVE) == LIMP_NORMAL);
    fault_facts_t no_display = { false, 0u };
    CHECK(fault_level(&f, &no_display) == LIMP_DEGRADED);        /* a dead display is a degraded state, not a failure of ours */
    fault_facts_t open = { true, 2u };
    CHECK(fault_level(&f, &open) == LIMP_DEGRADED);
}

static void test_kick_needs_every_task(void)
{
    power_on();
    fault_task_begin(&f, TASK_POWER);   fault_task_end(&f, TASK_POWER);
    fault_task_begin(&f, TASK_SENSORS); fault_task_end(&f, TASK_SENSORS);
    CHECK(!fault_service(&f, 10));                               /* three tasks have not run */
    for (int t = TASK_INPUTS; t < TASK_COUNT; t++) { fault_task_begin(&f, (fault_task_t)t); fault_task_end(&f, (fault_task_t)t); }
    CHECK(fault_service(&f, 20));
    CHECK(!fault_service(&f, 30));                               /* progress was consumed by the kick */
}

static void test_hang_is_quarantined_after_two(void)
{
    power_on();
    for (int i = 0; i < 10; i++) pass(TASK_NONE);
    /* the screens hang (a stuck SPI transfer) */
    run_until_reset(TASK_SCREENS);
    CHECK(f.cause == RESET_WATCHDOG);
    CHECK(ram.consec_wdog == 1 && ram.suspect == TASK_SCREENS && ram.quarantine == 0);
    CHECK(fault_level(&f, &ALIVE) == LIMP_DEGRADED);
    run_until_reset(TASK_SCREENS);                               /* it hangs again after the restart */
    CHECK(ram.consec_wdog == 2);
    CHECK(ram.quarantine == (1u << TASK_SCREENS));
    CHECK(!fault_task_enabled(&f, TASK_SCREENS));
    CHECK(fault_level(&f, &ALIVE) == LIMP_LIMP);
    CHECK(fault_quarantine_mask(&f) == 0x10);
    /* now the loop runs without the screens, and the watchdog is happy again */
    int before = resets;
    for (int i = 0; i < 1000; i++) pass(TASK_SCREENS);           /* the "hang" no longer happens: the task is skipped */
    CHECK(resets == before);
    CHECK(fault_wdog_resets(&f) == 2);
    /* ignition off and on again: a fresh attempt */
    fault_ignition_on(&f);
    CHECK(fault_task_enabled(&f, TASK_SCREENS));
    CHECK(ram.consec_wdog == 0 && ram.quarantine == 0);
    CHECK(fault_level(&f, &ALIVE) == LIMP_NORMAL);
    CHECK(fault_wdog_resets(&f) == 2);                           /* the history count is not erased */
}

static void test_different_tasks_do_not_quarantine(void)
{
    power_on();
    run_until_reset(TASK_CAN);
    run_until_reset(TASK_SCREENS);
    CHECK(ram.quarantine == 0 && ram.suspect == TASK_SCREENS);   /* two different tasks: nobody is blamed twice */
    run_until_reset(TASK_CAN);
    CHECK(ram.quarantine == 0);
    CHECK(ram.consec_wdog == 3);
    CHECK(fault_level(&f, &ALIVE) == LIMP_LIMP);                 /* but three resets in a row is limp regardless */
}

static void test_hang_outside_tasks(void)
{
    power_on();
    run_until_reset(TASK_COUNT);
    CHECK(ram.suspect == TASK_NONE && ram.quarantine == 0);
    run_until_reset(TASK_COUNT);
    CHECK(ram.quarantine == 0 && ram.consec_wdog == 2);          /* nobody to blame, nothing to switch off */
    CHECK(fault_level(&f, &ALIVE) == LIMP_DEGRADED);
}

static void test_healthy_period_clears_the_streak(void)
{
    power_on();
    run_until_reset(TASK_CAN);
    CHECK(ram.consec_wdog == 1);
    for (int i = 0; i < (int)(FAULT_HEALTHY_MS / 10) - 5; i++) pass(TASK_NONE);
    CHECK(ram.consec_wdog == 1);
    for (int i = 0; i < 10; i++) pass(TASK_NONE);
    CHECK(ram.consec_wdog == 0 && ram.suspect == TASK_NONE);
    run_until_reset(TASK_CAN);                                   /* the next hang starts a new streak, no quarantine */
    CHECK(ram.quarantine == 0);
}

static void test_other_reset_breaks_streak(void)
{
    power_on();
    run_until_reset(TASK_CAN);
    chip_reset(1u << 6);                                         /* reset pin (programmer or user) */
    CHECK(ram.consec_wdog == 0 && ram.suspect == TASK_NONE);
    run_until_reset(TASK_CAN);
    CHECK(ram.quarantine == 0);
}

static void test_retained_validation(void)
{
    power_on();
    run_until_reset(TASK_CAN);
    fault_retained_t good = ram;
    /* a flipped bit in the covered bytes: the record is rejected and restarted */
    ram = good; ram.quarantine ^= 0x04u;
    chip_reset(SRS_WDOG);
    CHECK(ram.magic == FAULT_RETAINED_MAGIC && ram.quarantine == 0 && ram.wdog_total == 1);   /* fresh record + this reset */
    /* wrong magic */
    ram = good; ram.magic ^= 1u;
    chip_reset(SRS_WDOG);
    CHECK(ram.quarantine == 0 && ram.consec_wdog == 1);
    /* power-on never trusts the record, even a perfect one */
    ram = good;
    chip_reset(SRS_POR);
    CHECK(ram.consec_wdog == 0 && ram.wdog_total == 0 && ram.last_cause == RESET_POWER_ON);
    /* a torn write of the "running" byte reads as no task */
    power_on();
    fault_task_begin(&f, TASK_INPUTS);
    ram.running_inv ^= 0x10u;
    chip_reset(SRS_WDOG);
    CHECK(ram.suspect == TASK_NONE && ram.consec_wdog == 1);
}

static void test_total_saturates(void)
{
    power_on();
    for (int i = 0; i < 300; i++) run_until_reset(TASK_COUNT);
    CHECK(fault_wdog_resets(&f) == 255 && ram.consec_wdog == 255);
}

static void test_status_message(void)
{
    chosen_t car_v = { 50.0f, true, SRC_CAR }, loc_v = { 50.0f, true, SRC_LOCAL }, none_v = { 0.0f, false, SRC_NONE };
    status_in_t in = { car_v, none_v, loc_v, car_v, true, true, 1u, false, 0x05u, RESET_WATCHDOG, LIMP_LIMP, 0x10u, 7u };
    cluster_gauges_status_t m = status_build(&in), back;
    CHECK(m.fuel_from_car && !m.coolant_from_car && !m.oil_from_car && m.battery_from_car);
    CHECK(m.fuel_sender_open && !m.oil_sender_open && m.temp_sender_open);
    CHECK(m.display_offline && m.rpm_from_tach && m.car_bus_active && m.active_profile == 1u);
    CHECK(m.reset_cause == RESET_WATCHDOG && m.limp_level == LIMP_LIMP && m.quarantine_mask == 0x10u && m.watchdog_resets == 7u);
    uint8_t raw[8];
    cluster_gauges_status_pack(&m, raw);
    CHECK(cluster_gauges_status_unpack(raw, &back) == 0);
    CHECK(back.reset_cause == 2u && back.limp_level == 2u && back.quarantine_mask == 0x10u && back.watchdog_resets == 7u);
    CHECK(back.fw_major == FW_MAJOR && back.fw_minor == FW_MINOR && back.display_offline == 1 && back.fuel_sender_open == 1);
    in.car_bus_active = false;
    CHECK(status_build(&in).active_profile == 0u);               /* "none" when no car frames are arriving */
}

int main(void)
{
    test_crc();
    test_decode();
    test_healthy_run();
    test_kick_needs_every_task();
    test_hang_is_quarantined_after_two();
    test_different_tasks_do_not_quarantine();
    test_hang_outside_tasks();
    test_healthy_period_clears_the_streak();
    test_other_reset_breaks_streak();
    test_retained_validation();
    test_total_saturates();
    test_status_message();
    if (failures) { printf("test_fault: %d FAILED\n", failures); return 1; }
    printf("test_fault: ok\n");
    return 0;
}
