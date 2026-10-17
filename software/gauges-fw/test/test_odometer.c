/* Odometer tests against a flash model that loses power at any event. Built twice: with a 4-sector log (so the ring
 * wraps often and every power-cut point can be swept) and with the real 16-sector log. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nv_mock.h"
#include "odometer.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

/* every (odo, trip) pair the firmware ever started to write, so a recovered value can be checked against them */
typedef struct { uint32_t odo, trip; } snap_t;
static snap_t *hist;
static size_t nhist, cap_hist;
static odo_state_t prev_state;

static void hist_add(uint32_t odo, uint32_t trip)
{
    if (nhist == cap_hist) { cap_hist = cap_hist ? cap_hist * 2 : 4096; hist = realloc(hist, cap_hist * sizeof *hist); }
    hist[nhist].odo = odo; hist[nhist].trip = trip; nhist++;
}

static bool hist_has(uint32_t odo, uint32_t trip)
{
    for (size_t i = nhist; i-- > 0; )
        if (hist[i].odo == odo && hist[i].trip == trip) return true;
    return false;
}

static void track(const odo_t *o)
{
    if (o->state == ODO_PROG0 && prev_state == ODO_IDLE) hist_add(o->snap_odo_m, o->snap_trip_m);
    prev_state = o->state;
}

static void step(odo_t *o, uint32_t dt_ms, uint32_t speed_c)
{
    odo_tick(o, dt_ms, speed_c);
    nv_mock_tick();
    odo_service(o);
    track(o);
}

static void boot(odo_t *o, uint32_t step_m)
{
    odo_init(o, &nv_mock, 0);
    o->save_step_m = step_m;
    prev_state = o->state;
    hist_add(o->odo_m, o->trip_m);
}

static uint32_t rng_state = 1;
static uint32_t rnd(void) { rng_state = rng_state * 1664525u + 1013904223u; return rng_state >> 8; }

/* ---- distance integration is exact ---------------------------------------------------------------------------- */
static void test_integration(void)
{
    nv_mock_reset(1);
    odo_t o; boot(&o, 1000000u);
    for (int i = 0; i < 72000; i++) odo_tick(&o, 10, 5000);          /* 50 km/h for 720 s */
    CHECK(o.odo_m == 10000u && o.trip_m == 10000u);                  /* exactly 10 km, no drift */
    odo_t p; boot(&p, 1000000u);
    for (int i = 0; i < 360000; i++) odo_tick(&p, 10, 12345);        /* 123.45 km/h for 3600 s */
    CHECK(p.odo_m == 123450u);
    odo_t q; boot(&q, 1000000u);
    for (int i = 0; i < 1000; i++) odo_tick(&q, 10, 0);
    CHECK(q.odo_m == 0u);
    odo_tick(&q, 5000000u, 36000u);                                  /* a stalled loop is capped at 1 s: 360 km/h = 100 m */
    CHECK(q.odo_m == 100u);
    odo_tick(&q, 1000u, 99999999u);                                  /* an absurd speed is capped at 400 km/h */
    CHECK(q.odo_m == 100u + 111u);
}

/* ---- a fresh part, a normal drive and a clean reboot ---------------------------------------------------------- */
static void test_basic(void)
{
    nv_mock_reset(2); nhist = 0;
    odo_t o; boot(&o, 5u);
    CHECK(o.odo_m == 0u && o.trip_m == 0u && o.sector == 0u && o.slot == 0u);
    for (int i = 0; i < 20000; i++) step(&o, 10, 25000);             /* 250 km/h, 0.69 m per tick: ~13.9 km */
    CHECK(o.odo_m > 13000u);
    odo_ignition(&o, false);
    for (int i = 0; i < 100 && !odo_idle(&o); i++) step(&o, 10, 0);
    CHECK(odo_idle(&o));
    uint32_t live = o.odo_m, trip = o.trip_m;
    odo_t r; boot(&r, 5u);
    CHECK(r.odo_m == live && r.trip_m == trip);                      /* ignition off saved everything */
    CHECK(nv_mock_violations == 0);
}

static void test_trip_reset(void)
{
    nv_mock_reset(3); nhist = 0;
    odo_t o; boot(&o, 1000000u);                                     /* no distance-driven saves at all */
    for (int i = 0; i < 6000; i++) odo_tick(&o, 10, 10000);          /* 100 km/h for 60 s = 1666 m */
    odo_trip_reset(&o);
    for (int i = 0; i < 100; i++) step(&o, 10, 0);
    CHECK(o.trip_m == 0u && o.odo_m > 1600u);
    odo_t r; boot(&r, 1000000u);
    CHECK(r.trip_m == 0u && r.odo_m == o.odo_m);                     /* the reset and the odometer reached the flash */
}

/* ---- power loss, randomly placed ------------------------------------------------------------------------------ */
static void check_recovery(uint32_t live, uint32_t saved_before, uint32_t step_m, const odo_t *r, bool after_flush_ok)
{
    CHECK(r->odo_m >= saved_before);                                 /* never behind a finished save */
    CHECK(r->odo_m <= live);                                         /* never ahead of what was driven */
    CHECK(hist_has(r->odo_m, r->trip_m));                            /* a value that was really written, not garbage */
    if (!after_flush_ok) CHECK(live - r->odo_m <= step_m + 40u);     /* the loss is about one save step */
}

static void test_random_cuts(uint32_t seed, int cuts)
{
    nv_mock_reset(seed); nhist = 0; rng_state = seed;
    odo_t o; boot(&o, 5u);
    uint32_t speed = 25000u;
    long total_ticks = 0;
    for (int c = 0; c < cuts; c++) {
        nv_mock_cut_at(1 + (long)(rnd() % 700));
        long guard = 0;
        while (!nv_mock_dead() && guard++ < 200000) {
            if ((rnd() & 0x3FF) == 0) speed = (rnd() % 4) * 8000u + (rnd() % 2) * 1500u;      /* 0 .. 25500 */
            step(&o, 10, speed);
            total_ticks++;
            if ((rnd() & 0x7FF) == 0) {                                                          /* key off, a pause, key on */
                odo_ignition(&o, false);
                for (int i = 0; i < 30 && !nv_mock_dead(); i++) step(&o, 10, 0);
                odo_ignition(&o, true);
            }
        }
        CHECK(nv_mock_dead());
        uint32_t live = o.odo_m, saved = o.saved_odo_m;
        nv_mock_power_cycle();
        odo_t r; boot(&r, 5u);
        check_recovery(live, saved, 5u, &r, true);
        o = r;                                                                                   /* the car goes on from there */
    }
    CHECK(nv_mock_violations == 0);
    if (seed == 1) printf("odometer: %d random power cuts over %ld ticks, every recovery between the last finished save and the distance driven\n", cuts, total_ticks);
}

/* ---- power loss at EVERY event of a drive that wraps the ring twice ------------------------------------------- */
#if ODO_SECTORS == 4
static long scenario(long cut, uint32_t *live_out, uint32_t *saved_out)
{
    nv_mock_reset(77); nhist = 0;
    odo_t o; boot(&o, 5u);
    if (cut) nv_mock_cut_at(cut);
    long ticks = (long)ODO_SECTORS * ODO_SLOTS_PER_SECTOR * 2 * 7 + 3000;       /* about two laps of the ring */
    for (long i = 0; i < ticks && !nv_mock_dead(); i++) step(&o, 10, 25000);
    *live_out = o.odo_m; *saved_out = o.saved_odo_m;
    if (!cut) return nv_mock_events;
    if (!nv_mock_dead()) return -1;
    nv_mock_power_cycle();
    odo_t r; boot(&r, 5u);
    check_recovery(*live_out, *saved_out, 5u, &r, true);
    /* and it keeps working after the recovery: drive on, key off, reboot, exact */
    for (int i = 0; i < 3000; i++) step(&r, 10, 25000);
    odo_ignition(&r, false);
    for (int i = 0; i < 200 && !odo_idle(&r); i++) step(&r, 10, 0);
    CHECK(odo_idle(&r));
    uint32_t end = r.odo_m;
    odo_t z; boot(&z, 5u);
    CHECK(z.odo_m == end);
    return 0;
}

static void test_every_cut(void)
{
    uint32_t live, saved;
    long events = scenario(0, &live, &saved);
    CHECK(events > 1000);
    CHECK(nv_mock_sector_erases[0] >= 2u);                           /* the scenario really wrapped the ring */
    long swept = 0;
    int before = failures;
    for (long cut = 1; cut <= events; cut++) {
        if (scenario(cut, &live, &saved) == 0) swept++;
        if (failures != before) { printf("  first failure with the power cut at event %ld of %ld\n", cut, events); break; }
    }
    CHECK(swept >= events - 2);
    printf("odometer: power cut at each of the %ld command events of a drive that wraps the %u-sector log twice: %ld recoveries checked\n",
           events, (unsigned)ODO_SECTORS, swept);
}

#endif

/* ---- commands that fail, and a part that has gone bad --------------------------------------------------------- */
static void test_command_failures(void)
{
    nv_mock_reset(5); nhist = 0;
    odo_t o; boot(&o, 5u);
    nv_mock_fail_next(3);                                            /* three commands finish with an error and no change */
    for (int i = 0; i < 5000; i++) step(&o, 10, 25000);
    odo_ignition(&o, false);
    for (int i = 0; i < 200 && !odo_idle(&o); i++) step(&o, 10, 0);
    odo_t r; boot(&r, 5u);
    CHECK(r.odo_m == o.odo_m);                                       /* failed slots were abandoned and the save retried */
    CHECK(nv_mock_violations == 0);

    nv_mock_reset(6);
    odo_t g; boot(&g, 5u);
    nv_mock_fail_next(100000);                                       /* nothing works any more */
    for (int i = 0; i < 20000; i++) step(&g, 10, 25000);
    CHECK(g.failures >= ODO_GIVE_UP);
    CHECK(g.odo_m > 10000u);                                         /* the count in RAM carries on */
    odo_ignition(&g, false);
    CHECK(odo_idle(&g));                                             /* and the clock is allowed to stop */
}

/* A save that fails exactly when the key goes off must be retried until it lands. */
static void test_failed_key_off_save(void)
{
    nv_mock_reset(8); nhist = 0;
    odo_t o; boot(&o, 1000000u);
    for (int i = 0; i < 3000; i++) step(&o, 10, 10000);
    nv_mock_fail_next(2);
    odo_ignition(&o, false);
    for (int i = 0; i < 400 && !odo_idle(&o); i++) step(&o, 10, 0);
    CHECK(odo_idle(&o));
    odo_t r; boot(&r, 1000000u);
    CHECK(r.odo_m == o.odo_m && r.odo_m > 800u);
}

/* Erasing the next sector ahead of time means a save never waits for an erase, even a slow one. */
static void test_erase_ahead(void)
{
    nv_mock_reset(10); nhist = 0;
    odo_t o; boot(&o, 5u);
    nv_mock_set_latency(40, 1);                                      /* an erase takes 40 ticks: 28 m at 250 km/h, more than 5 m */
    unsigned waits = 0, laps_erases = 0;
    for (long i = 0; i < (long)ODO_SECTORS * ODO_SLOTS_PER_SECTOR * 2 * 7 + 3000; i++) {
        step(&o, 10, 25000);
        if (o.state == ODO_ERASE && o.erase_sector == o.sector && o.slot == 0 && o.odo_m != o.saved_odo_m) waits++;
    }
    for (unsigned s = 0; s < ODO_SECTORS; s++) laps_erases += nv_mock_sector_erases[s];
    CHECK(laps_erases >= ODO_SECTORS);                               /* the ring really went round */
    CHECK(waits == 0u);                                              /* and not one save stood waiting for an erase */
}

/* ---- garbage in the flash ------------------------------------------------------------------------------------- */
static void test_garbage_flash(void)
{
    nv_mock_reset(7); nhist = 0;
    for (unsigned i = 0; i < NV_MOCK_BYTES; i++) nv_mem[i] = (uint8_t)rnd();
    odo_t o; boot(&o, 5u);
    CHECK(o.odo_m == 0u && o.trip_m == 0u);                          /* nothing valid in noise */
    for (int i = 0; i < 5000; i++) step(&o, 10, 25000);              /* it erases what it needs and carries on */
    odo_ignition(&o, false);
    for (int i = 0; i < 200 && !odo_idle(&o); i++) step(&o, 10, 0);
    CHECK(odo_idle(&o));
    odo_t r; boot(&r, 5u);
    CHECK(r.odo_m == o.odo_m && r.odo_m > 3000u);
    CHECK(nv_mock_violations == 0);
}

/* ---- wear: 100000 miles at the real 16-sector log and 0.1 mile saves ------------------------------------------- */
#if ODO_SECTORS == 16
static void test_wear(void)
{
    nv_mock_reset(9); nhist = 0;
    odo_t o; boot(&o, ODO_SAVE_EVERY_M);
    nv_mock_set_latency(3, 1);
    /* 1 s steps at 100 km/h = 27.8 m each; 100000 miles = 160934 km */
    long calls = 160934L * 1000L / 28L;
    for (long i = 0; i < calls; i++) {
        odo_tick(&o, 1000, 10000);
        nv_mock_tick();
        odo_service(&o);
        if ((i % 20000) == 19999) { odo_ignition(&o, false); odo_ignition(&o, true); }          /* a trip every ~ 150 km */
    }
    unsigned mx = 0, total = 0;
    for (unsigned s = 0; s < ODO_SECTORS; s++) { total += nv_mock_sector_erases[s]; if (nv_mock_sector_erases[s] > mx) mx = nv_mock_sector_erases[s]; }
    printf("odometer: 100000 miles = %u sector erases in all, at most %u on any one of the %u sectors (0.1 mile saves)\n", total, mx, (unsigned)ODO_SECTORS);
    CHECK(mx < 1500u);
    CHECK(nv_mock_violations == 0);
}
#endif

int main(void)
{
    test_integration();
    test_basic();
    test_trip_reset();
    for (uint32_t seed = 1; seed <= 8; seed++) test_random_cuts(seed, 120);
#if ODO_SECTORS == 4
    test_every_cut();
#endif
    test_command_failures();
    test_failed_key_off_save();
    test_erase_ahead();
    test_garbage_flash();
#if ODO_SECTORS == 16
    test_wear();
#endif
    free(hist);
    if (failures) { printf("test_odometer: %d FAILED\n", failures); return 1; }
    printf("test_odometer (%u sectors): ok\n", (unsigned)ODO_SECTORS);
    return 0;
}
