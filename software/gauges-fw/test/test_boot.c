/* The bootloader core: image validation, the update protocol over a flash model (duplicates, wrong order, corruption, failures,
 * power loss at any point), the boot decision. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "boot_request.h"
#include "bootcore.h"
#include "crc.h"
#include "pflash_mock.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static uint32_t rng_state = 99;
static uint32_t rnd(void) { rng_state = rng_state * 1664525u + 1013904223u; return rng_state >> 8; }

/* A well-formed application image of `len` bytes: a vector table, the 32-byte header at +0x400 with the right CRCs, then noise. */
static uint8_t *make_image(uint32_t len, uint16_t board, uint16_t major)
{
    uint8_t *img = malloc(len);
    for (uint32_t i = 0; i < len; i++) img[i] = (uint8_t)rnd();
    uint32_t sp = 0x20006FE0u, pc = (APP_BASE + 0x420u) | 1u;
    memcpy(img, &sp, 4); memcpy(img + 4, &pc, 4);
    app_header_t h = { APP_MAGIC, 1, board, major, 7, len, 0, 1, 0, 0 };
    memcpy(img + APP_HEADER_OFFSET, &h, sizeof h);
    h.image_crc = app_image_crc(img, len);
    h.header_crc = crc32(&h, APP_HEADER_BYTES - 4u);
    memcpy(img + APP_HEADER_OFFSET, &h, sizeof h);
    return img;
}

static void put_image(const uint8_t *img, uint32_t len)
{
    memcpy(pf_mem + APP_BASE, img, len);
}

static void test_validation(void)
{
    const uint32_t len = 6000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    pf_reset(); put_image(img, len);
    const uint8_t *app = pf_mem + APP_BASE;
    CHECK(app_image_valid(app, APP_SIZE, BOARD_ID_GAUGES));
    CHECK(!app_image_valid(app, APP_SIZE, BOARD_ID_GAUGES + 1));                           /* another board's image */
    /* any single flipped bit in the image is caught (every byte of the vector table, the header and a sample of the rest) */
    unsigned undetected = 0;
    for (uint32_t i = 0; i < len; i += (i < 0x440u ? 1u : 37u)) {
        for (int bit = 0; bit < 8; bit += 3) {
            pf_mem[APP_BASE + i] ^= (uint8_t)(1u << bit);
            if (app_image_valid(app, APP_SIZE, BOARD_ID_GAUGES)) undetected++;
            pf_mem[APP_BASE + i] ^= (uint8_t)(1u << bit);
        }
    }
    CHECK(undetected == 0u);
    CHECK(app_image_valid(app, APP_SIZE, BOARD_ID_GAUGES));
    /* bytes after the image are not part of it */
    pf_mem[APP_BASE + len + 10] = 0x12;
    CHECK(app_image_valid(app, APP_SIZE, BOARD_ID_GAUGES));
    /* a blank flash is not an image */
    pf_reset();
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    /* a header that is itself consistent but whose vector table is nonsense */
    uint8_t *bad = make_image(len, BOARD_ID_GAUGES, 1);
    uint32_t sp = 0x30000000u; memcpy(bad, &sp, 4);
    app_header_t h; memcpy(&h, bad + APP_HEADER_OFFSET, sizeof h); h.image_crc = app_image_crc(bad, len); h.header_crc = crc32(&h, 28);
    memcpy(bad + APP_HEADER_OFFSET, &h, sizeof h);
    put_image(bad, len);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    sp = 0x20006FE0u; uint32_t pc = 0x00000501u; memcpy(bad, &sp, 4); memcpy(bad + 4, &pc, 4);          /* reset vector inside the bootloader */
    memcpy(&h, bad + APP_HEADER_OFFSET, sizeof h); h.image_crc = app_image_crc(bad, len); h.header_crc = crc32(&h, 28);
    memcpy(bad + APP_HEADER_OFFSET, &h, sizeof h);
    put_image(bad, len);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    /* a reset vector past the end of the image, a header describing a length too short to hold itself: both with correct CRCs */
    sp = 0x20006FE0u; pc = ((APP_BASE + len + 8u) | 1u); memcpy(bad, &sp, 4); memcpy(bad + 4, &pc, 4);
    memcpy(&h, bad + APP_HEADER_OFFSET, sizeof h); h.image_crc = app_image_crc(bad, len); h.header_crc = crc32(&h, 28);
    memcpy(bad + APP_HEADER_OFFSET, &h, sizeof h);
    put_image(bad, len);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    pc = (APP_BASE + 0x40u) | 1u; memcpy(bad + 4, &pc, 4);
    memcpy(&h, bad + APP_HEADER_OFFSET, sizeof h); h.image_len = 100u; h.image_crc = 0u; h.header_crc = crc32(&h, 28);
    memcpy(bad + APP_HEADER_OFFSET, &h, sizeof h);
    put_image(bad, len);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    free(bad); free(img);
}

/* ---- driving the protocol --------------------------------------------------------------------------------------- */
static bootcore_t bc;
static uint32_t t_ms;

static can_frame_t cmd(uint8_t c, uint32_t arg)
{
    can_frame_t f = { BOOT_ID_CMD, 8, { c, (uint8_t)arg, (uint8_t)(arg >> 8), (uint8_t)(arg >> 16), (uint8_t)(arg >> 24), 0, 0, 0 } };
    return f;
}

static can_frame_t enter_frame(uint16_t board)
{
    can_frame_t f = { BOOT_ID_CMD, 8, { 0x01, 'B', 'L', (uint8_t)board, (uint8_t)(board >> 8), 0, 0, 0 } };
    return f;
}

static int send(const can_frame_t *f, can_frame_t *r)
{
    t_ms += 3;
    return bootcore_on_frame(&bc, f, r, t_ms) ? r->data[1] : -1;
}

static int do_cmd(uint8_t c, uint32_t arg) { can_frame_t f = cmd(c, arg), r; return send(&f, &r); }

/* data frame number `n` of the image: seq n (8 bit), 7 bytes, the last one padded with 0xFF */
static can_frame_t data_frame(const uint8_t *img, uint32_t len, uint32_t n)
{
    can_frame_t f = { BOOT_ID_DATA, 8, { (uint8_t)n, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF } };
    for (unsigned i = 0; i < 7; i++) if (n * 7u + i < len) f.data[1 + i] = img[n * 7u + i];
    return f;
}

static uint32_t frames_for(uint32_t len) { return (len + 6u) / 7u; }

/* ENTER, BEGIN and the data frames of a well-behaved transfer, without FINISH; stops after `stop_after` data frames unless that is -1.
 * Returns 0 when all frames were accepted, 100 when it stopped on purpose, or the status that stopped it. */
static int transfer(const uint8_t *img, uint32_t len, long stop_after)
{
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    can_frame_t e = enter_frame(BOARD_ID_GAUGES), r;
    if (send(&e, &r) != BC_ST_OK) return -10;
    int st = do_cmd(0x02, len);
    if (st != BC_ST_OK) return st;
    for (uint32_t n = 0; n < frames_for(len); n++) {
        if (stop_after >= 0 && (long)n == stop_after) return 100;
        can_frame_t d = data_frame(img, len, n);
        st = send(&d, &r);
        if (st != BC_ST_OK) return st;
        if (r.data[2] != (uint8_t)(n + 1u)) return -11;
    }
    return 0;
}

static int transfer_full(const uint8_t *img, uint32_t len)
{
    int st = transfer(img, len, -1);
    if (st != 0) return st;
    return do_cmd(0x03, app_image_crc(img, len));
}

static void test_protocol(void)
{
    static const uint32_t lens[] = { 1064, 1065, 1071, 1072, 1073, 4096, 4097, 6000, 9999, 20000, 0x1E000 };
    for (unsigned k = 0; k < sizeof lens / sizeof lens[0]; k++) {
        uint32_t len = lens[k];
        uint8_t *img = make_image(len, BOARD_ID_GAUGES, 2);
        pf_reset();
        CHECK(transfer_full(img, len) == BC_ST_OK);
        CHECK(memcmp(pf_mem + APP_BASE, img, len) == 0);                      /* the flash holds the image */
        CHECK(app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
        CHECK(pf_mem[APP_BASE + len] == 0xFF || (len % 8u) != 0u || len == 0x1E000u);       /* nothing beyond the last phrase */
        CHECK(do_cmd(0x05, 0) == BC_ST_OK && bc.boot_requested);
        CHECK(pf_violations == 0 && pf_boot_touched == 0);
        for (uint32_t i = 0; i < BOOT_REGION_BYTES; i++) if (pf_mem[i] != 0xA5) { CHECK(!"bootloader region changed"); break; }
        free(img);
    }
}

static void test_state_rules(void)
{
    uint32_t len = 3000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    pf_reset();
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    can_frame_t r, e;
    CHECK(do_cmd(0x02, len) == BC_ST_BAD_STATE);                               /* BEGIN before ENTER */
    CHECK(do_cmd(0x05, 0) == BC_ST_BAD_STATE);                                 /* BOOT before anything */
    e = enter_frame(BOARD_ID_GAUGES + 1);
    CHECK(send(&e, &r) == BC_ST_BAD_ARG);                                      /* ENTER for another board */
    can_frame_t bad = enter_frame(BOARD_ID_GAUGES); bad.data[1] = 'X';
    CHECK(send(&bad, &r) == BC_ST_BAD_ARG);
    e = enter_frame(BOARD_ID_GAUGES);
    CHECK(send(&e, &r) == BC_ST_OK && r.id == BOOT_ID_RESP && r.data[0] == 0x81 && r.data[2] == BOOT_VERSION && r.data[5] == (APP_BASE >> 12));
    CHECK(do_cmd(0x02, 100) == BC_ST_BAD_ARG);                                 /* shorter than a header */
    CHECK(do_cmd(0x02, APP_SIZE + 1) == BC_ST_BAD_ARG);                        /* larger than the application region */
    CHECK(pf_erases == 0u);                                                     /* a refused BEGIN erases nothing */
    can_frame_t d = data_frame(img, len, 0);
    CHECK(send(&d, &r) == BC_ST_BAD_STATE);                                    /* data before BEGIN */
    CHECK(do_cmd(0x03, 0) == BC_ST_BAD_STATE);                                  /* FINISH before the data */
    CHECK(do_cmd(0x02, len) == BC_ST_OK);
    /* out of order: a gap is refused and says what it wants */
    d = data_frame(img, len, 1);
    CHECK(send(&d, &r) == BC_ST_SEQ && r.data[2] == 0u);
    d = data_frame(img, len, 0);
    CHECK(send(&d, &r) == BC_ST_OK && r.data[2] == 1u);
    CHECK(send(&d, &r) == BC_ST_OK && r.data[2] == 1u);                        /* the same frame again (lost ack): accepted, not applied twice */
    d = data_frame(img, len, 1);
    CHECK(send(&d, &r) == BC_ST_OK);
    d = data_frame(img, len, 5);
    CHECK(send(&d, &r) == BC_ST_SEQ && r.data[2] == 2u);
    can_frame_t shortf = { BOOT_ID_DATA, 5, { 2, 0 } };
    CHECK(send(&shortf, &r) == BC_ST_BAD_STATE);                               /* a short data frame is refused */
    CHECK(do_cmd(0x04, 0) == BC_ST_OK);                                         /* ABORT */
    d = data_frame(img, len, 2);
    CHECK(send(&d, &r) == BC_ST_BAD_STATE);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    /* commands that do not exist, and frames that are not for the bootloader */
    can_frame_t unk = cmd(0x77, 0), o = { 0x123, 8, { 0 } };
    CHECK(send(&unk, &r) == -1 && send(&o, &r) == -1);
    can_frame_t shortc = { BOOT_ID_CMD, 4, { 1, 'B', 'L', 1 } };
    CHECK(send(&shortc, &r) == -1);
    CHECK(pf_violations == 0 && pf_boot_touched == 0);
    free(img);
}

static void test_duplicates_everywhere(void)
{
    uint32_t len = 5000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    pf_reset();
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    can_frame_t e = enter_frame(BOARD_ID_GAUGES), r;
    CHECK(send(&e, &r) == BC_ST_OK);
    CHECK(do_cmd(0x02, len) == BC_ST_OK);
    for (uint32_t n = 0; n < frames_for(len); n++) {
        can_frame_t d = data_frame(img, len, n);
        CHECK(send(&d, &r) == BC_ST_OK);
        if (rnd() % 3 == 0) CHECK(send(&d, &r) == BC_ST_OK);                    /* a lost ack: the tool sends it again */
    }
    can_frame_t last = data_frame(img, len, frames_for(len) - 1);
    CHECK(send(&last, &r) == BC_ST_OK);                                          /* and again after the end */
    CHECK(do_cmd(0x03, app_image_crc(img, len)) == BC_ST_OK);
    CHECK(memcmp(pf_mem + APP_BASE, img, len) == 0 && pf_violations == 0);
    free(img);
}

static void test_corruption(void)
{
    uint32_t len = 8000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    /* one bit flipped in a data frame that the CAN CRC missed: FINISH refuses, BOOT refuses, the app stays invalid */
    pf_reset();
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    can_frame_t e = enter_frame(BOARD_ID_GAUGES), r;
    send(&e, &r); do_cmd(0x02, len);
    for (uint32_t n = 0; n < frames_for(len); n++) {
        can_frame_t d = data_frame(img, len, n);
        if (n == 500) d.data[3] ^= 0x10;
        send(&d, &r);
    }
    CHECK(do_cmd(0x03, app_image_crc(img, len)) == BC_ST_CRC);
    CHECK(do_cmd(0x05, 0) == BC_ST_BAD_STATE && !bc.boot_requested);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    /* the tool's CRC is wrong (or for another image) */
    pf_reset();
    CHECK(transfer(img, len, -1) == 0);
    CHECK(do_cmd(0x03, app_image_crc(img, len) ^ 1u) == BC_ST_CRC);
    CHECK(do_cmd(0x03, app_image_crc(img, len)) == BC_ST_OK);                   /* the right one afterwards still works */
    /* the header inside the image does not match the length announced */
    pf_reset();
    bootcore_init(&bc, &pflash_mock, BOARD_ID_GAUGES);
    send(&e, &r);
    CHECK(do_cmd(0x02, len - 8) == BC_ST_OK);
    for (uint32_t n = 0; n < frames_for(len - 8); n++) { can_frame_t d = data_frame(img, len - 8, n); send(&d, &r); }
    CHECK(do_cmd(0x03, app_image_crc(img, len - 8)) == BC_ST_BAD_IMAGE);
    /* an image for another board */
    uint8_t *other = make_image(len, BOARD_ID_GAUGES + 5, 1);
    pf_reset();
    CHECK(transfer_full(other, len) == BC_ST_BAD_IMAGE);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    free(other); free(img);
}

static void test_interruptions(void)
{
    uint32_t len = 7000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    uint8_t *old = make_image(5000, BOARD_ID_GAUGES, 0);
    /* a valid application is in place; an update that stops at any point leaves NO valid application (never a half-new one) */
    /* the old application is invalid from the moment BEGIN is accepted, even if it is only one sector long and every byte of it is still there */
    uint8_t *tiny = make_image(3000, BOARD_ID_GAUGES, 0);
    pf_reset(); put_image(tiny, 3000);
    CHECK(app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    CHECK(transfer(img, len, 0) == 100);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    free(tiny);
    unsigned nframes = frames_for(len);
    for (long stop = 0; stop < (long)nframes; stop += 23) {
        pf_reset(); put_image(old, 5000);
        CHECK(app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
        int st = transfer(img, len, stop);
        CHECK(st == 100);
        CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    }
    /* power lost during any one flash command of a full update: the result is invalid unless the whole image made it, never "valid but wrong" */
    pf_reset();
    transfer_full(img, len);
    long commands = (long)(pf_erases + pf_programs);
    unsigned good = 0, bad = 0;
    for (long cut = 1; cut <= commands + 1; cut += 1) {
        pf_reset(); put_image(old, 5000);
        pf_cut_at(cut);
        int st = transfer_full(img, len);
        bool valid = app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES);
        if (valid) {
            CHECK(memcmp(pf_mem + APP_BASE, img, len) == 0);                      /* valid means exactly the new image */
            good++;
        } else bad++;
        if (cut <= commands) CHECK(st != BC_ST_OK);
    }
    CHECK(bad >= (unsigned)commands && good <= 1u);
    printf("boot: power cut during each of the %ld flash commands of a full update: never a valid but wrong image\n", commands);
    /* a failing command stops the transfer with a flash status and nothing is left that looks valid */
    pf_reset(); put_image(old, 5000);
    pf_fail_at(40);
    CHECK(transfer_full(img, len) == BC_ST_FLASH);
    CHECK(!app_image_valid(pf_mem + APP_BASE, APP_SIZE, BOARD_ID_GAUGES));
    pf_reset(); put_image(old, 5000);
    pf_fail_at(2);                                                                /* an erase fails */
    CHECK(transfer_full(img, len) == BC_ST_FLASH);
    CHECK(pf_boot_touched == 0);
    free(old); free(img);
}

static void test_timeout_and_decision(void)
{
    uint32_t len = 3000;
    uint8_t *img = make_image(len, BOARD_ID_GAUGES, 1);
    pf_reset();
    CHECK(transfer(img, len, 20) == 100);
    can_frame_t r;
    bootcore_tick(&bc, t_ms + 5000);
    CHECK(bc.state == BC_RECEIVING);
    bootcore_tick(&bc, t_ms + 10001);
    CHECK(bc.state == BC_ENTERED);                                                  /* a quiet tool is dropped */
    can_frame_t d = data_frame(img, len, 20);
    CHECK(send(&d, &r) == BC_ST_BAD_STATE);
    CHECK(do_cmd(0x02, len) == BC_ST_OK);                                           /* and can start again */
    free(img);

    CHECK(boot_decide(true, false, true, 0) == BOOT_RUN_APP);
    CHECK(boot_decide(false, false, true, 0) == BOOT_UPDATE_NO_APP);
    CHECK(boot_decide(true, true, true, 0) == BOOT_UPDATE_REQUESTED);
    CHECK(boot_decide(false, true, true, 0) == BOOT_UPDATE_NO_APP);
    CHECK(boot_decide(true, false, true, BOOT_FAILING_RESETS) == BOOT_UPDATE_APP_FAILING);
    CHECK(boot_decide(true, false, true, BOOT_FAILING_RESETS - 1) == BOOT_RUN_APP);
    CHECK(boot_decide(true, false, false, 255) == BOOT_RUN_APP);                    /* a damaged fault record proves nothing */
}

static void test_boot_request(void)
{
    boot_request_t r;
    memset(&r, 0, sizeof r);
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);                                  /* zeroed RAM after a power-on reset */
    bootreq_write(&r, BOOTREQ_ENTER);
    CHECK(bootreq_take(&r) == BOOTREQ_ENTER);
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);                                  /* honoured once */
    bootreq_write(&r, BOOTREQ_RUN);
    CHECK(bootreq_take(&r) == BOOTREQ_RUN);
    bootreq_write(&r, BOOTREQ_ENTER); r.value_inv ^= 1u;
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);                                  /* the complement disagrees */
    bootreq_write(&r, BOOTREQ_ENTER); r.magic ^= 0x100u;
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);
    bootreq_write(&r, 0x12345678u);
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);                                  /* a value nobody defined */
    for (int i = 0; i < 4; i++) ((uint32_t *)&r)[i] = 0xDEADBEEFu;            /* RAM that was never written */
    CHECK(bootreq_take(&r) == BOOTREQ_NONE);
    CHECK(r.magic == 0u && r.value == 0u);                                    /* and it has been cleared */
}

int main(void)
{
    test_boot_request();
    test_validation();
    test_protocol();
    test_state_rules();
    test_duplicates_everywhere();
    test_corruption();
    test_interruptions();
    test_timeout_and_decision();
    if (failures) { printf("test_boot: %d FAILED\n", failures); return 1; }
    printf("test_boot: ok\n");
    return 0;
}
