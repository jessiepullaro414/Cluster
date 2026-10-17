#ifndef ODOMETER_H
#define ODOMETER_H
/*
 * Odometer and trip meter that survive power loss. REAL, host-tested against a flash model that cuts the power at
 * every step (test/test_odometer.c).
 *
 * Distance is integrated from the chosen speed (exact integer arithmetic, no drift), counted in metres. It is kept in
 * RAM and written to data flash as a log of 16-byte entries:
 *     bytes 0-3 odometer (m), 4-7 trip (m), 8-11 sequence number, 12-15 CRC-32 of bytes 0-11
 * Phrase 0 (bytes 0-7) is programmed first and phrase 1 (the sequence and the CRC) last, so an entry only becomes valid
 * when its last phrase lands; a torn entry fails the CRC and is skipped. The newest valid entry (highest sequence
 * number) wins at boot. The log is a ring of ODO_SECTORS sectors; the sector after the one being written is erased
 * ahead of time, so a save never waits for an erase, and every erase is of the oldest data. Nothing is ever
 * programmed twice (bits only go 1 to 0 once), and a slot that fails or is torn is abandoned.
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

#ifndef ODO_SECTORS
#define ODO_SECTORS            16u       /* 32 KB of the 64 KB data flash (tests build a 4-sector log too) */
#endif
#define ODO_ENTRY_BYTES        16u
#define ODO_SLOTS_PER_SECTOR   (NV_SECTOR_BYTES / ODO_ENTRY_BYTES)
#define ODO_SAVE_EVERY_M       161u      /* 0.1 mile: the last digit of a mechanical odometer */

typedef enum { ODO_IDLE = 0, ODO_PROG0, ODO_PROG1, ODO_ERASE } odo_state_t;

typedef struct {
    const nv_ops_t *nv;
    uint32_t base_off;                   /* where the log starts in the data flash */
    uint32_t save_step_m;                /* distance between automatic saves (a field so tests can shrink it) */
    /* live values */
    uint32_t odo_m, trip_m;
    uint32_t mm_acc;                     /* sub-metre remainder, millimetres */
    uint32_t frac;                       /* integration remainder, units of (0.01 km/h * ms); 360 units = 1 mm */
    /* what the log holds */
    uint32_t saved_odo_m, saved_trip_m, seq;
    uint8_t  sector, slot;               /* where the next entry goes */
    bool     blank[ODO_SECTORS];         /* sector known to be fully erased */
    /* state machine */
    odo_state_t state;
    bool     flush;                      /* save now regardless of distance (ignition off, trip reset) */
    bool     ign_prev;
    uint32_t snap_odo_m, snap_trip_m, snap_seq;
    uint8_t  erase_sector;
    uint8_t  failures;                   /* consecutive failed commands; ODO_GIVE_UP and the log is left alone */
    uint32_t entries_valid_at_boot;      /* diagnostics */
} odo_t;

#define ODO_GIVE_UP 8u

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
