#include <string.h>
#include "crc.h"
#include "nvlog.h"

#define SEQ_NONE 0xFFFFFFFFu

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }

static uint32_t slot_off(const nvlog_t *l, unsigned sector, unsigned slot)
{
    return l->base_off + sector * NV_SECTOR_BYTES + slot * l->entry_bytes;
}

static const uint8_t *entry_at(const nvlog_t *l, unsigned sector, unsigned slot)
{
    return l->nv->base() + slot_off(l, sector, slot);
}

static bool entry_blank(const nvlog_t *l, const uint8_t *e)
{
    for (unsigned i = 0; i < l->entry_bytes; i++)
        if (e[i] != 0xFFu) return false;
    return true;
}

static bool entry_valid(const nvlog_t *l, const uint8_t *e)
{
    unsigned p = l->payload_bytes;
    return rd32(e + p) != SEQ_NONE && crc32(e, p + 4u) == rd32(e + p + 4u);
}

static void advance_cursor(nvlog_t *l)
{
    if (++l->slot >= l->slots) {
        l->slot = 0;
        l->sector = (uint8_t)((l->sector + 1u) % l->sectors);
    }
}

bool nvlog_init(nvlog_t *l, const nv_ops_t *nv, uint32_t base_off, unsigned sectors, unsigned payload_bytes, void *latest)
{
    memset(l, 0, sizeof *l);
    l->nv = nv;
    l->base_off = base_off;
    if (sectors == 0u || sectors > NVLOG_MAX_SECTORS) sectors = 1u;
    if (payload_bytes < 8u || payload_bytes > NVLOG_MAX_PAYLOAD || (payload_bytes % 8u) != 0u) payload_bytes = 8u;
    l->sectors = (uint8_t)sectors;
    l->payload_bytes = (uint8_t)payload_bytes;
    l->entry_bytes = (uint16_t)(payload_bytes + 8u);
    l->slots = (uint16_t)(NV_SECTOR_BYTES / l->entry_bytes);
    l->phrases = (uint8_t)(payload_bytes / NV_PHRASE_BYTES + 1u);
    if (!nv) { l->failures = NVLOG_GIVE_UP; return false; }

    bool found = false;
    uint32_t best_seq = 0;
    unsigned best_sector = 0, best_slot = 0;
    for (unsigned s = 0; s < l->sectors; s++) {
        bool all_blank = true;
        for (unsigned j = 0; j < NV_SECTOR_BYTES; j += 8) {                  /* whole sector, including the unused tail */
            const uint8_t *b = nv->base() + l->base_off + s * NV_SECTOR_BYTES + j;
            for (unsigned k = 0; k < 8; k++) if (b[k] != 0xFFu) { all_blank = false; break; }
            if (!all_blank) break;
        }
        for (unsigned j = 0; j < l->slots; j++) {
            const uint8_t *e = entry_at(l, s, j);
            if (entry_valid(l, e)) {
                l->valid_at_boot++;
                uint32_t seq = rd32(e + payload_bytes);
                if (!found || seq > best_seq) {
                    found = true; best_seq = seq; best_sector = s; best_slot = j;
                    if (latest) memcpy(latest, e, payload_bytes);
                }
            }
        }
        l->blank[s] = all_blank;
    }
    (void)nv->last_ok();                         /* clear any ECC flag a torn word raised during the scan */

    l->seq = found ? best_seq : 0u;
    l->sector = (uint8_t)best_sector;
    l->slot = (uint16_t)best_slot;
    if (found) advance_cursor(l);               /* the slot after the newest */
    /* Skip slots that are not blank (a torn entry, or garbage): they cannot be programmed again. */
    for (unsigned guard = 0; guard < l->sectors * l->slots; guard++) {
        if (l->slot == 0 && !l->blank[l->sector]) break;                     /* a whole sector to erase before use */
        if (entry_blank(l, entry_at(l, l->sector, l->slot))) break;
        advance_cursor(l);
    }
    return found;
}

bool nvlog_dead(const nvlog_t *l) { return l->failures >= NVLOG_GIVE_UP; }

bool nvlog_busy(const nvlog_t *l)
{
    if (!l->nv) return false;
    return l->state != NVLOG_IDLE || l->pending_write || l->nv->busy();
}

bool nvlog_write(nvlog_t *l, const void *payload)
{
    if (!l->nv || l->pending_write || l->state != NVLOG_IDLE || nvlog_dead(l)) return false;
    memcpy(l->pending, payload, l->payload_bytes);
    l->pending_seq = l->seq + 1u;
    l->pending_write = true;                     /* nvlog_service starts it as soon as the cursor sector is ready */
    return true;
}

static void command_failed(nvlog_t *l)
{
    if (l->failures < 255u) l->failures++;
}

static void burn_slot(nvlog_t *l)
{
    l->blank[l->sector] = false;
    advance_cursor(l);
}

/* Which sector wants erasing, or -1: the cursor's own when it is about to be started, or the next one ahead of time. */
static int erase_wanted(const nvlog_t *l)
{
    if (l->slot == 0 && !l->blank[l->sector]) return l->sector;
    unsigned next = (l->sector + 1u) % l->sectors;
    if (!l->blank[next] && l->slot > 0) return (int)next;
    return -1;
}

static bool program_phrase(nvlog_t *l, unsigned k)
{
    uint8_t ph[NV_PHRASE_BYTES];
    if (k < l->phrases - 1u) {
        memcpy(ph, l->pending + k * NV_PHRASE_BYTES, NV_PHRASE_BYTES);
    } else {
        uint8_t e[NVLOG_MAX_PAYLOAD + 4];
        memcpy(e, l->pending, l->payload_bytes);
        wr32(e + l->payload_bytes, l->pending_seq);
        wr32(ph, l->pending_seq);
        wr32(ph + 4, crc32(e, l->payload_bytes + 4u));
    }
    return l->nv->program(slot_off(l, l->sector, l->slot) + k * NV_PHRASE_BYTES, ph);
}

nvlog_event_t nvlog_service(nvlog_t *l)
{
    const nv_ops_t *nv = l->nv;
    if (!nv || nv->busy()) return NVLOG_EV_NONE;

    if (l->state == NVLOG_ERASE) {
        l->state = NVLOG_IDLE;
        if (nv->last_ok()) { l->blank[l->erase_sector] = true; l->failures = 0; }
        else command_failed(l);
        return NVLOG_EV_NONE;
    }

    if (l->state == NVLOG_PROGRAM) {                                 /* a phrase has just finished */
        if (!nv->last_ok()) {
            command_failed(l); burn_slot(l);
            l->state = NVLOG_IDLE; l->pending_write = false;
            return NVLOG_EV_FAILED;
        }
        if (l->phrase + 1u < l->phrases) {
            l->phrase++;
            if (!program_phrase(l, l->phrase)) {
                command_failed(l); burn_slot(l);
                l->state = NVLOG_IDLE; l->pending_write = false;
                return NVLOG_EV_FAILED;
            }
            return NVLOG_EV_NONE;
        }
        l->failures = 0;
        l->seq = l->pending_seq;
        advance_cursor(l);
        l->state = NVLOG_IDLE; l->pending_write = false;
        return NVLOG_EV_COMMITTED;
    }

    /* idle */
    if (nvlog_dead(l)) {                                              /* the flash is not answering: give the request back */
        if (l->pending_write) { l->pending_write = false; return NVLOG_EV_FAILED; }
        return NVLOG_EV_NONE;
    }
    int e = erase_wanted(l);
    if (e >= 0) {
        l->erase_sector = (uint8_t)e;
        if (nv->erase(l->base_off + (uint32_t)e * NV_SECTOR_BYTES)) l->state = NVLOG_ERASE;
        else command_failed(l);
        return NVLOG_EV_NONE;
    }
    if (l->pending_write) {                                           /* start the first phrase */
        l->blank[l->sector] = false;             /* no longer a fully erased sector, whatever happens next */
        l->phrase = 0;
        if (program_phrase(l, 0)) l->state = NVLOG_PROGRAM;
        else { command_failed(l); burn_slot(l); l->pending_write = false; return NVLOG_EV_FAILED; }
    }
    return NVLOG_EV_NONE;
}
