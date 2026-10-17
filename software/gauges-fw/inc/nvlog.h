#ifndef NVLOG_H
#define NVLOG_H
/*
 * A power-loss-safe log of fixed-size records in a few sectors of the data flash. REAL, host-tested (through the odometer's
 * tests, which cut the power at every command event, and the settings store's).
 *
 * An entry is  [payload, a multiple of 8 bytes][sequence number, 4 bytes][CRC-32 of the payload and the sequence, 4 bytes].
 * The payload phrases are programmed first and the phrase holding the sequence and the CRC last, so an entry exists only when
 * its last phrase lands; a torn entry fails its CRC and is skipped. At boot the entry with the highest sequence number wins.
 * The sectors form a ring: the sector after the one being written is erased ahead of time (it holds the oldest data), so a
 * write never waits for an erase. A slot that fails or is torn is abandoned: a flash bit can only be programmed once per
 * erase. With 8-byte payload this is the odometer's original format, byte for byte.
 */
#include <stdbool.h>
#include <stdint.h>
#include "nvflash.h"

#define NVLOG_MAX_SECTORS 32u
#define NVLOG_MAX_PAYLOAD 32u
#define NVLOG_GIVE_UP     8u        /* consecutive failed commands before the log is left alone */

typedef enum { NVLOG_IDLE = 0, NVLOG_PROGRAM, NVLOG_ERASE } nvlog_state_t;     /* the command in flight, if any */
typedef enum { NVLOG_EV_NONE = 0, NVLOG_EV_COMMITTED, NVLOG_EV_FAILED } nvlog_event_t;

typedef struct {
    const nv_ops_t *nv;
    uint32_t base_off;
    uint16_t entry_bytes, slots;
    uint8_t  sectors, payload_bytes, phrases;     /* phrases: payload phrases + the sequence/CRC phrase */
    uint8_t  sector;
    uint16_t slot;                                /* where the next entry goes */
    uint32_t seq;                                 /* sequence number of the newest committed entry */
    bool     blank[NVLOG_MAX_SECTORS];            /* sector known to be fully erased */
    nvlog_state_t state;
    bool     pending_write;                       /* an entry has been asked for and is not committed yet */
    uint8_t  phrase;                              /* the phrase being programmed */
    uint8_t  erase_sector;
    uint8_t  failures;
    uint8_t  pending[NVLOG_MAX_PAYLOAD];
    uint32_t pending_seq;
    uint32_t valid_at_boot;
} nvlog_t;

/* Scan the log; copy the newest entry's payload to `latest` (payload_bytes long, may be NULL) and return true, or return false if
 * there is none. nv == NULL makes a log that accepts nothing. payload_bytes: 8, 16, 24 or 32. */
bool nvlog_init(nvlog_t *l, const nv_ops_t *nv, uint32_t base_off, unsigned sectors, unsigned payload_bytes, void *latest);

/* Start writing a new entry. False if one is already being written or the log has given up. */
bool nvlog_write(nvlog_t *l, const void *payload);

/* One step of the state machine (a flash command is started or finished); cheap when idle. The event says what finished. */
nvlog_event_t nvlog_service(nvlog_t *l);

bool nvlog_busy(const nvlog_t *l);      /* an entry is being written, or an erase is running */
bool nvlog_dead(const nvlog_t *l);      /* gave up after repeated failures */

#endif
