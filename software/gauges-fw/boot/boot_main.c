/* The bootloader (S32K144, first 32 KB of program flash). Written for the part; compiled and linked, NEVER RUN on one.
 *
 * At every reset it decides, before touching the clocks or any peripheral, whether to run the application:
 *   - the application is valid (header, board, vector table, CRC-32 of the whole image) and nobody asked for an update -> jump to it.
 *     It then starts as if from reset: SRAM was zeroed and the watchdog parked by the startup code, nothing else was touched.
 *   - the application asked to be reflashed (a note in the retained RAM), or there is no valid application -> update mode.
 *   - the application has been failing (six watchdog resets in a row in the fault manager's retained record) -> update mode for
 *     15 s; if nobody turns up, reset once with a note that says run the application anyway, so a flaky application is never locked
 *     out for good.
 * Update mode brings up the clock and the PRIVATE LINK only (CAN1, 500 kbit/s); the car bus is never started here. The protocol is
 * in bootcore.c. Nothing outside 0x8000-0x7FFFF can be erased or programmed (bootcore, pflash_s32k.c, and the flash configuration
 * field write-protects the bootloader's own 32 KB). */
#include <stddef.h>
#include <stdint.h>
#include "boot_request.h"
#include "bootcore.h"
#include "can_hw.h"
#include "clock.h"
#include "crc.h"
#include "fault.h"
#include "pflash.h"
#include "s32k144_regs.h"
#include "tick.h"

extern char __faultrec_start[];          /* linker script: the fault manager's retained record (src/fault.c), 16 bytes into the retained RAM */

#define FAILING_WINDOW_MS 15000u

static void reset_now(void)
{
    __asm volatile("dsb");
    SCB_AIRCR = SCB_AIRCR_RESET;
    for (;;) { }
}

static void jump_to_app(void)
{
    const uint32_t *vt = (const uint32_t *)APP_BASE;
    uint32_t sp = vt[0], pc = vt[1];
    __asm volatile("cpsid i" ::: "memory");
    SCB_VTOR = APP_BASE;
    __asm volatile("msr msp, %0\n bx %1" :: "r"(sp), "r"(pc));
    for (;;) { }
}

static bool send_response(const can_frame_t *r)
{
    for (uint32_t t0 = now_ms(); (uint32_t)(now_ms() - t0) < 50u; )
        if (can_hw_s32k.tx(CAN_BUS_LINK, r)) return true;           /* the mailbox frees when the previous answer has left */
    return false;
}

static void update_mode(boot_decision_t why)
{
    (void)clock_init_80mhz();
    tick_init();
    can_config_t c = { .bitrate = 500000u, .listen_only = false, .n_rx = 2u, .n_tx = 1u };
    c.rx_ids[0] = BOOT_ID_CMD; c.rx_ids[1] = BOOT_ID_DATA; c.tx_ids[0] = BOOT_ID_RESP;
    (void)can_hw_s32k.start(CAN_BUS_LINK, &c);
    bootcore_t bc;
    bootcore_init(&bc, &pflash_s32k, BOARD_ID_GAUGES);
    uint32_t started = now_ms();
    for (;;) {
        uint32_t now = now_ms();
        can_frame_t in, out;
        for (unsigned n = 0; n < 8u && can_hw_s32k.rx(CAN_BUS_LINK, &in); n++)
            if (bootcore_on_frame(&bc, &in, &out, now)) (void)send_response(&out);
        bootcore_tick(&bc, now);
        if (bc.boot_requested) {                                     /* the answer to BOOT has been sent: restart into the new application */
            for (uint32_t t0 = now_ms(); (uint32_t)(now_ms() - t0) < 20u; ) { }
            reset_now();
        }
        if (why == BOOT_UPDATE_APP_FAILING && bc.state == BC_IDLE && (uint32_t)(now - started) > FAILING_WINDOW_MS) {
            bootreq_write(&g_bootreq, BOOTREQ_RUN);                  /* nobody came: try the application again, this time unconditionally */
            reset_now();
        }
        __asm volatile("wfi");                                       /* the SysTick wakes this every 10 ms; received frames are polled */
    }
}

void boot_main(void)
{
    const uint8_t *flash = (const uint8_t *)0;
    bool valid = app_image_valid(flash + APP_BASE, APP_SIZE, BOARD_ID_GAUGES);
    uint32_t req = bootreq_take(&g_bootreq);
    if (req == BOOTREQ_RUN && valid) jump_to_app();

    const fault_retained_t *fr = (const fault_retained_t *)(const void *)__faultrec_start;
    bool fr_valid = fr->magic == FAULT_RETAINED_MAGIC && fr->crc == crc32(fr, offsetof(fault_retained_t, crc));
    boot_decision_t d = boot_decide(valid, req == BOOTREQ_ENTER, fr_valid, fr->consec_wdog);
    if (d == BOOT_RUN_APP) jump_to_app();
    update_mode(d);
}
