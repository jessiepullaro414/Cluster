#include <string.h>
#include "crc.h"
#include "odometer.h"

#define SEQ_NONE 0xFFFFFFFFu

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }

static bool entry_blank(const uint8_t *e)
{
    for (unsigned i = 0; i < ODO_ENTRY_BYTES; i++)
        if (e[i] != 0xFFu) return false;
    return true;
}

static bool entry_valid(const uint8_t *e)
{
    return rd32(e + 8) != SEQ_NONE && crc32(e, 12) == rd32(e + 12);
}

static const uint8_t *entry_at(const odo_t *o, unsigned sector, unsigned slot)
{
    return o->nv->base() + o->base_off + sector * NV_SECTOR_BYTES + slot * ODO_ENTRY_BYTES;
}

static uint32_t slot_off(const odo_t *o, unsigned sector, unsigned slot)
{
    return o->base_off + sector * NV_SECTOR_BYTES + slot * ODO_ENTRY_BYTES;
}

static void advance_cursor(odo_t *o)
{
    if (++o->slot >= ODO_SLOTS_PER_SECTOR) {
        o->slot = 0;
        o->sector = (uint8_t)((o->sector + 1u) % ODO_SECTORS);
    }
}

void odo_init(odo_t *o, const nv_ops_t *nv, uint32_t base_off)
{
    memset(o, 0, sizeof *o);
    o->nv = nv;
    o->base_off = base_off;
    o->save_step_m = ODO_SAVE_EVERY_M;

    if (!nv) { o->ign_prev = true; return; }                  /* no storage: RAM only */
    bool found = false;
    uint32_t best_seq = 0;
    unsigned best_sector = 0, best_slot = 0;
    for (unsigned s = 0; s < ODO_SECTORS; s++) {
        bool all_blank = true;
        for (unsigned j = 0; j < ODO_SLOTS_PER_SECTOR; j++) {
            const uint8_t *e = entry_at(o, s, j);
            if (!entry_blank(e)) all_blank = false;
            if (entry_valid(e)) {
                o->entries_valid_at_boot++;
                uint32_t seq = rd32(e + 8);
                if (!found || seq > best_seq) {
                    found = true; best_seq = seq; best_sector = s; best_slot = j;
                    o->odo_m = rd32(e); o->trip_m = rd32(e + 4);
                }
            }
        }
        o->blank[s] = all_blank;
    }
    (void)nv->last_ok();                         /* clear any ECC flag a torn word raised during the scan */

    o->saved_odo_m = o->odo_m;
    o->saved_trip_m = o->trip_m;
    o->seq = found ? best_seq : 0u;
    o->sector = (uint8_t)best_sector;
    o->slot = (uint8_t)best_slot;
    if (found) advance_cursor(o);               /* the slot after the newest */
    /* Skip slots that are not blank (a torn entry, or garbage): they cannot be programmed again. */
    for (unsigned guard = 0; guard < ODO_SECTORS * ODO_SLOTS_PER_SECTOR; guard++) {
        if (o->slot == 0 && !o->blank[o->sector]) break;     /* a whole sector to erase before use */
        if (entry_blank(entry_at(o, o->sector, o->slot))) break;
        advance_cursor(o);
    }
    o->state = ODO_IDLE;
    o->ign_prev = true;                          /* the first call to odo_ignition(false) is an edge to save */
}

void odo_tick(odo_t *o, uint32_t dt_ms, uint32_t speed_centi_kmh)
{
    if (dt_ms > 1000u) dt_ms = 1000u;            /* a stalled loop must not turn into a jump in distance */
    if (speed_centi_kmh > 40000u) speed_centi_kmh = 40000u;
    o->frac += speed_centi_kmh * dt_ms;          /* 0.01 km/h * ms; 360 of these are one millimetre (1 km/h = 0.27778 mm/ms) */
    uint32_t mm = o->frac / 360u;
    o->frac -= mm * 360u;
    o->mm_acc += mm;
    uint32_t m = o->mm_acc / 1000u;
    if (m != 0u) {
        o->mm_acc -= m * 1000u;
        o->odo_m += m;
        o->trip_m += m;
    }
}

void odo_ignition(odo_t *o, bool on)
{
    if (o->ign_prev && !on) o->flush = true;
    o->ign_prev = on;
}

void odo_trip_reset(odo_t *o)
{
    o->trip_m = 0u;
    o->flush = true;
}

static bool dirty(const odo_t *o)
{
    return o->odo_m != o->saved_odo_m || o->trip_m != o->saved_trip_m;
}

static bool save_due(const odo_t *o)
{
    if (!dirty(o)) return false;
    return o->flush || (o->odo_m - o->saved_odo_m) >= o->save_step_m;
}

/* Which sector wants erasing, or -1: the cursor's own (when about to start it) or the one after it, ahead of time. */
static int erase_wanted(const odo_t *o)
{
    if (o->slot == 0 && !o->blank[o->sector]) return o->sector;
    unsigned next = (o->sector + 1u) % ODO_SECTORS;
    if (!o->blank[next] && o->slot > 0) return (int)next;
    return -1;
}

bool odo_idle(const odo_t *o)
{
    if (!o->nv) return true;
    if (o->failures >= ODO_GIVE_UP) return true;     /* the flash is not answering: waiting would never end */
    return o->state == ODO_IDLE && !o->nv->busy() && !dirty(o);
}

static void command_failed(odo_t *o)
{
    if (o->failures < 255u) o->failures++;
}

static void burn_slot(odo_t *o)
{
    o->blank[o->sector] = false;
    advance_cursor(o);
    o->flush = true;                             /* what that entry should have held is still unsaved: try again at once */
}

void odo_service(odo_t *o)
{
    const nv_ops_t *nv = o->nv;
    if (!nv || nv->busy()) return;

    switch (o->state) {
    case ODO_PROG0: {
        if (!nv->last_ok()) { command_failed(o); burn_slot(o); o->state = ODO_IDLE; return; }
        uint8_t ph[NV_PHRASE_BYTES];
        uint8_t e[12];
        wr32(e, o->snap_odo_m); wr32(e + 4, o->snap_trip_m); wr32(e + 8, o->snap_seq);
        wr32(ph, o->snap_seq);
        wr32(ph + 4, crc32(e, 12));
        if (nv->program(slot_off(o, o->sector, o->slot) + 8u, ph)) o->state = ODO_PROG1;
        else { command_failed(o); burn_slot(o); o->state = ODO_IDLE; }
        return;
    }
    case ODO_PROG1:
        o->state = ODO_IDLE;
        if (!nv->last_ok()) { command_failed(o); burn_slot(o); return; }
        o->failures = 0;
        o->saved_odo_m = o->snap_odo_m;
        o->saved_trip_m = o->snap_trip_m;
        o->seq = o->snap_seq;
        advance_cursor(o);
        return;
    case ODO_ERASE:
        o->state = ODO_IDLE;
        if (nv->last_ok()) { o->blank[o->erase_sector] = true; o->failures = 0; }
        else command_failed(o);
        return;
    case ODO_IDLE:
        break;
    }

    if (o->failures >= ODO_GIVE_UP) return;      /* the flash is not answering: keep counting in RAM, stop poking it */

    int e = erase_wanted(o);
    if (e >= 0) {
        o->erase_sector = (uint8_t)e;
        if (nv->erase(o->base_off + (uint32_t)e * NV_SECTOR_BYTES)) o->state = ODO_ERASE;
        else command_failed(o);
        return;
    }
    if (save_due(o)) {
        o->snap_odo_m = o->odo_m;
        o->snap_trip_m = o->trip_m;
        o->snap_seq = o->seq + 1u;
        o->flush = false;
        uint8_t ph[NV_PHRASE_BYTES];
        wr32(ph, o->snap_odo_m);
        wr32(ph + 4, o->snap_trip_m);
        o->blank[o->sector] = false;             /* no longer a fully erased sector, whatever happens next */
        if (nv->program(slot_off(o, o->sector, o->slot), ph)) o->state = ODO_PROG0;
        else { command_failed(o); burn_slot(o); }
    }
}
