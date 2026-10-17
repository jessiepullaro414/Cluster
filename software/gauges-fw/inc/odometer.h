#ifndef ODOMETER_H
#define ODOMETER_H
/*
 * Odometer and trip meter that survive power loss. REAL, host-tested against a flash model that cuts the power at
 * every step (test/test_odometer.c).
 *
 * Distance is integrated from the chosen speed (exact integer arithmetic, no drift), counted in metres. It is kept in
 * RAM and written to data flash through nvlog.h as 16-byte entries (odometer m, trip m, sequence, CRC-32); see there
 * for how a torn write, a failed command and the ring of sectors are handled.
 *
 * What is guaranteed: after ANY power loss the recovered odometer is at least the last value whose save finished,
 * and never more than was driven; at most ODO_SAVE_EVERY_M metres are lost to an unannounced loss, none when the
 * ignition is switched off first (a save is forced then). What is not: the flash cycling endurance has not been
 * checked against the S32K144 data sheet (it is not in the reference set); the numbers are in the README.
 *
 * All flash work is non-blocking: odo_service() advances one step per call (10 ms is plenty).
 */
#include <stdbool.h>
#include <stdint.h>
#include "nvflash.h"
#include "nvlog.h"

#ifndef ODO_SECTORS
#define ODO_SECTORS            16u       /* 32 KB of the 64 KB data flash (tests build a 4-sector log too) */
#endif
#define ODO_SAVE_EVERY_M       161u      /* 0.1 mile: the last digit of a mechanical odometer */

typedef struct {
    nvlog_t  log;
    uint32_t save_step_m;                /* distance between automatic saves (a field so tests can shrink it) */
    /* live values */
    uint32_t odo_m, trip_m;
    uint32_t mm_acc;                     /* sub-metre remainder, millimetres */
    uint32_t frac;                       /* integration remainder, units of (0.01 km/h * ms); 360 units = 1 mm */
    /* what the log holds */
    uint32_t saved_odo_m, saved_trip_m;
    bool     flush;                      /* save now regardless of distance (ignition off, trip reset, a failed write) */
    bool     ign_prev;
    uint32_t snap_odo_m, snap_trip_m;    /* the values of the write in flight */
    uint32_t writes_started;             /* diagnostics */
} odo_t;

/* Scan the log and recover the newest valid entry. Call once, with the flash idle, before anything else.
 * nv == NULL (no usable storage) gives a counter that starts at zero and is never saved. */
void odo_init(odo_t *o, const nv_ops_t *nv, uint32_t base_off);

/* Advance the distance by dt_ms at speed_centi_kmh (0.01 km/h units; pass 0 when the speed is not valid). */
void odo_tick(odo_t *o, uint32_t dt_ms, uint32_t speed_centi_kmh);

void odo_ignition(odo_t *o, bool on);       /* a falling edge forces a save */
void odo_trip_reset(odo_t *o);              /* zero the trip meter and save */

/* One step of the flash state machine; cheap when nothing is pending. */
void odo_service(odo_t *o);

/* True when no flash command is running and nothing is waiting to be saved: safe to stop the clock. */
bool odo_idle(const odo_t *o);

static inline uint32_t odo_get_m(const odo_t *o) { return o->odo_m; }
static inline uint32_t odo_get_trip_m(const odo_t *o) { return o->trip_m; }

#endif
