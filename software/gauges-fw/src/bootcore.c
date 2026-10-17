#include <string.h>
#include "bootcore.h"
#include "crc.h"

#define CMD_ENTER  0x01u
#define CMD_BEGIN  0x02u
#define CMD_FINISH 0x03u
#define CMD_ABORT  0x04u
#define CMD_BOOT   0x05u
#define RESP_DATA  0x90u
#define TIMEOUT_MS 10000u

static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

void bootcore_init(bootcore_t *b, const pflash_ops_t *fl, uint16_t board_id)
{
    memset(b, 0, sizeof *b);
    b->fl = fl;
    b->board_id = board_id;
}

/* ---- the image ------------------------------------------------------------------------------------------------ */

uint32_t app_image_crc(const uint8_t *mem, uint32_t len)
{
    /* the CRC fields themselves (image_crc at +16 and header_crc at +28 of the header) are read as zero */
    static const uint8_t zero4[4] = { 0, 0, 0, 0 };
    const uint32_t h = APP_HEADER_OFFSET;
    if (len < h + APP_HEADER_BYTES) return 0u;
    uint32_t c = crc32(mem, h + 16u);
    c = crc32_update(c, zero4, 4u);
    c = crc32_update(c, mem + h + 20u, 8u);
    c = crc32_update(c, zero4, 4u);
    return crc32_update(c, mem + h + APP_HEADER_BYTES, len - h - APP_HEADER_BYTES);
}

bool app_image_valid(const uint8_t *mem, uint32_t size, uint16_t board_id)
{
    if (size < APP_MIN_BYTES) return false;
    const uint8_t *h = mem + APP_HEADER_OFFSET;
    app_header_t hd;
    memcpy(&hd, h, sizeof hd);
    if (hd.magic != APP_MAGIC || hd.header_version != 1u || hd.board_id != board_id) return false;
    if (hd.header_crc != crc32(h, APP_HEADER_BYTES - 4u)) return false;
    if (hd.min_boot_version > BOOT_VERSION) return false;
    if (hd.image_len < APP_MIN_BYTES || hd.image_len > size) return false;
    uint32_t sp = rd32(mem), pc = rd32(mem + 4);                      /* the vector table: a stack in RAM and a Thumb reset vector in the image */
    if (sp < RAM_LOW || sp > RAM_HIGH || (sp & 3u) != 0u) return false;
    if ((pc & 1u) == 0u || (pc & ~1u) < APP_BASE || (pc & ~1u) >= APP_BASE + hd.image_len) return false;
    return app_image_crc(mem, hd.image_len) == hd.image_crc;
}

boot_decision_t boot_decide(bool app_valid, bool update_requested, bool fault_record_valid, uint8_t consecutive_wdog_resets)
{
    if (!app_valid) return BOOT_UPDATE_NO_APP;
    if (update_requested) return BOOT_UPDATE_REQUESTED;
    if (fault_record_valid && consecutive_wdog_resets >= BOOT_FAILING_RESETS) return BOOT_UPDATE_APP_FAILING;
    return BOOT_RUN_APP;
}

/* ---- the protocol --------------------------------------------------------------------------------------------- */

static void respond(can_frame_t *r, uint8_t cmd, uint8_t status)
{
    memset(r, 0, sizeof *r);
    r->id = BOOT_ID_RESP; r->dlc = 8u;
    r->data[0] = cmd; r->data[1] = status;
}

static bool in_app(uint32_t addr, uint32_t bytes)
{
    return addr >= APP_BASE && bytes <= PFLASH_BYTES - addr;
}

/* Take one 8-byte phrase of the stream to the flash. */
static bool program_phrase(bootcore_t *b)
{
    uint32_t addr = APP_BASE + b->written;
    if (!in_app(addr, PFLASH_PHRASE_BYTES) || !b->fl->program(addr, b->buf)) return false;
    b->written += PFLASH_PHRASE_BYTES;
    b->nbuf = 0;
    return true;
}

static bc_status_t do_begin(bootcore_t *b, uint32_t len)
{
    if (b->state != BC_ENTERED && b->state != BC_RECEIVED && b->state != BC_VERIFIED) return BC_ST_BAD_STATE;
    if (len < APP_MIN_BYTES || len > APP_SIZE) return BC_ST_BAD_ARG;
    /* Erase from the first sector: the header goes first, so a transfer that dies half way can never leave a valid-looking image. */
    uint32_t end = APP_BASE + ((len + PFLASH_SECTOR_BYTES - 1u) / PFLASH_SECTOR_BYTES) * PFLASH_SECTOR_BYTES;
    b->state = BC_ENTERED;
    for (uint32_t a = APP_BASE; a < end; a += PFLASH_SECTOR_BYTES)
        if (!b->fl->erase(a)) return BC_ST_FLASH;
    b->len = len; b->written = 0; b->received = 0; b->expect_seq = 0; b->nbuf = 0;
    b->state = BC_RECEIVING;
    return BC_ST_OK;
}

static bc_status_t do_finish(bootcore_t *b, uint32_t crc)
{
    if (b->state != BC_RECEIVED) return BC_ST_BAD_STATE;
    const uint8_t *app = b->fl->mem() + APP_BASE;
    if (b->len < APP_MIN_BYTES) return BC_ST_BAD_IMAGE;
    app_header_t hd;
    memcpy(&hd, app + APP_HEADER_OFFSET, sizeof hd);
    if (hd.image_len != b->len) return BC_ST_BAD_IMAGE;                    /* the header must describe what was sent */
    if (app_image_crc(app, b->len) != crc) return BC_ST_CRC;               /* what is in the flash is not what the tool sent */
    if (!app_image_valid(app, APP_SIZE, b->board_id)) return BC_ST_BAD_IMAGE;
    b->state = BC_VERIFIED;
    return BC_ST_OK;
}

static bool on_data(bootcore_t *b, const can_frame_t *in, can_frame_t *resp)
{
    respond(resp, RESP_DATA, BC_ST_OK);
    bool open = b->state == BC_RECEIVING || b->state == BC_RECEIVED;
    if (in->dlc != 8u || !open) { resp->data[1] = BC_ST_BAD_STATE; return true; }
    uint8_t seq = in->data[0];
    if (seq == (uint8_t)(b->expect_seq - 1u) && b->received > 0u) {          /* the previous frame again: the ack got lost */
        resp->data[2] = b->expect_seq;
        return true;
    }
    if (b->state == BC_RECEIVED) { resp->data[1] = BC_ST_BAD_STATE; return true; }      /* everything has arrived: no more data */
    if (seq != b->expect_seq) { resp->data[1] = BC_ST_SEQ; resp->data[2] = b->expect_seq; return true; }
    for (unsigned i = 1; i < 8u && b->received < b->len; i++) {
        b->buf[b->nbuf++] = in->data[i];
        b->received++;
        if (b->nbuf == 8u && !program_phrase(b)) { resp->data[1] = BC_ST_FLASH; return true; }
    }
    if (b->received >= b->len) {
        if (b->nbuf != 0u) {                                                  /* the last, partial phrase: pad with erased bytes */
            memset(b->buf + b->nbuf, 0xFF, 8u - b->nbuf);
            if (!program_phrase(b)) { resp->data[1] = BC_ST_FLASH; return true; }
        }
        b->state = BC_RECEIVED;
    }
    b->expect_seq = (uint8_t)(seq + 1u);
    resp->data[2] = b->expect_seq;
    return true;
}

bool bootcore_on_frame(bootcore_t *b, const can_frame_t *in, can_frame_t *resp, uint32_t now_ms)
{
    b->last_ms = now_ms;
    if (in->id == BOOT_ID_DATA) return on_data(b, in, resp);
    if (in->id != BOOT_ID_CMD || in->dlc != 8u) return false;
    uint8_t cmd = in->data[0];
    bc_status_t st = BC_ST_BAD_ARG;
    respond(resp, (uint8_t)(cmd | 0x80u), BC_ST_BAD_ARG);
    switch (cmd) {
    case CMD_ENTER:
        if (in->data[1] != 'B' || in->data[2] != 'L') break;
        if ((uint16_t)(in->data[3] | (in->data[4] << 8)) != b->board_id) break;       /* meant for another board */
        if (b->state == BC_IDLE) b->state = BC_ENTERED;
        st = BC_ST_OK;
        resp->data[2] = BOOT_VERSION; resp->data[3] = (uint8_t)b->board_id; resp->data[4] = (uint8_t)(b->board_id >> 8);
        resp->data[5] = (uint8_t)(APP_BASE >> 12);
        break;
    case CMD_BEGIN:
        st = do_begin(b, rd32(in->data + 1));
        break;
    case CMD_FINISH:
        st = do_finish(b, rd32(in->data + 1));
        break;
    case CMD_ABORT:
        if (b->state != BC_IDLE) b->state = BC_ENTERED;
        st = BC_ST_OK;
        break;
    case CMD_BOOT:
        if (b->state == BC_VERIFIED) { b->boot_requested = true; st = BC_ST_OK; } else st = BC_ST_BAD_STATE;
        break;
    default:
        return false;                                                          /* an unknown command is not answered */
    }
    resp->data[1] = (uint8_t)st;
    return true;
}

void bootcore_tick(bootcore_t *b, uint32_t now_ms)
{
    if ((b->state == BC_RECEIVING || b->state == BC_RECEIVED) && (uint32_t)(now_ms - b->last_ms) > TIMEOUT_MS)
        b->state = BC_ENTERED;
}
