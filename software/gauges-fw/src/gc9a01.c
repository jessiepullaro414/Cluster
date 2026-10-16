#include "gc9a01.h"

/* ---- commands (datasheet 6.1 unless noted) ---- */
#define CMD_SLPOUT  0x11u
#define CMD_INVON   0x21u
#define CMD_DISPOFF 0x28u
#define CMD_DISPON  0x29u
#define CMD_CASET   0x2Au
#define CMD_RASET   0x2Bu
#define CMD_RAMWR   0x2Cu
#define CMD_MADCTL  0x36u
#define CMD_COLMOD  0x3Au       /* DBI[2:0] = 101: 16 bits per pixel (6.2.22) */
#define CMD_FRAMERATE 0xE8u     /* 6.4.1 */
#define CMD_PWR2    0xC3u       /* 6.4.4 */
#define CMD_PWR3    0xC4u       /* 6.4.5 */
#define CMD_PWR4    0xC9u       /* 6.4.6 */
#define CMD_GAMMA1  0xF0u       /* 6.4.10 - 6.4.13 */
#define CMD_GAMMA2  0xF1u
#define CMD_GAMMA3  0xF2u
#define CMD_GAMMA4  0xF3u
#define CMD_INREG1  0xFEu       /* 6.4.8 */
#define CMD_INREG2  0xEFu       /* 6.4.9 */

/* Reset timing is the open-source driver's (Zephyr display_gc9x01x.c). */
#define RESET_LOW_MS   10u
#define RESET_WAIT_MS  120u

/* VENDOR BLOCK: not in the datasheet (see gc9a01.h). cmd, count, bytes. */
typedef struct { uint8_t cmd, n; uint8_t d[12]; } reg_t;
static const reg_t vendor_block[] = {
    { 0xEB, 1, { 0x14 } },
    { 0x84, 1, { 0x40 } }, { 0x85, 1, { 0xFF } }, { 0x86, 1, { 0xFF } }, { 0x87, 1, { 0xFF } },
    { 0x88, 1, { 0x0A } }, { 0x89, 1, { 0x21 } }, { 0x8A, 1, { 0x00 } }, { 0x8B, 1, { 0x80 } },
    { 0x8C, 1, { 0x01 } }, { 0x8D, 1, { 0x01 } }, { 0x8E, 1, { 0xFF } }, { 0x8F, 1, { 0xFF } },
    { 0xB6, 2, { 0x00, 0x20 } },                                  /* Display Function Control, 6.3.3 */
    { 0x90, 4, { 0x08, 0x08, 0x08, 0x08 } },
    { 0xBD, 1, { 0x06 } }, { 0xBC, 1, { 0x00 } },
    { 0xFF, 3, { 0x60, 0x01, 0x04 } },
    { 0xBE, 1, { 0x11 } },
    { 0xE1, 2, { 0x10, 0x0E } },
    { 0xDF, 3, { 0x21, 0x0C, 0x02 } },
    { 0xED, 2, { 0x1B, 0x0B } },
    { 0xAE, 1, { 0x77 } }, { 0xCD, 1, { 0x63 } },
    { 0x70, 9, { 0x07, 0x07, 0x04, 0x0E, 0x0F, 0x09, 0x07, 0x08, 0x03 } },
    { 0x62, 12, { 0x18, 0x0D, 0x71, 0xED, 0x70, 0x70, 0x18, 0x0F, 0x71, 0xEF, 0x70, 0x70 } },
    { 0x63, 12, { 0x18, 0x11, 0x71, 0xF1, 0x70, 0x70, 0x18, 0x13, 0x71, 0xF3, 0x70, 0x70 } },
    { 0x64, 7, { 0x28, 0x29, 0xF1, 0x01, 0xF1, 0x00, 0x07 } },
    { 0x66, 10, { 0x3C, 0x00, 0xCD, 0x67, 0x45, 0x45, 0x10, 0x00, 0x00, 0x00 } },
    { 0x67, 10, { 0x00, 0x3C, 0x00, 0x00, 0x00, 0x01, 0x54, 0x10, 0x32, 0x98 } },
    { 0x74, 7, { 0x10, 0x85, 0x80, 0x00, 0x00, 0x4E, 0x00 } },
    { 0x98, 2, { 0x3E, 0x07 } },
};

/* Documented registers, with the values the open-source driver ships as defaults. */
static const uint8_t PWR2 = 0x13, PWR3 = 0x13, PWR4 = 0x22, FRAMERATE = 0x34;
static const uint8_t GAMMA_NEG[6] = { 0x45, 0x09, 0x08, 0x08, 0x26, 0x2A };     /* F0h, F2h */
static const uint8_t GAMMA_POS[6] = { 0x43, 0x70, 0x72, 0x36, 0x37, 0x6F };     /* F1h, F3h */

void gc9a01_command(const panel_hal_t *hal, uint8_t screen, uint8_t cmd, const uint8_t *params, uint32_t n)
{
    hal->select(hal->ctx, screen, true);
    hal->dc(hal->ctx, screen, false);
    hal->write(hal->ctx, &cmd, 1);
    if (n) {
        hal->dc(hal->ctx, screen, true);
        hal->write(hal->ctx, params, n);
    }
    hal->select(hal->ctx, screen, false);
}

void gc9a01_reset(const panel_hal_t *hal)
{
    hal->reset(hal->ctx, true);
    hal->delay_ms(hal->ctx, RESET_LOW_MS);
    hal->reset(hal->ctx, false);
    hal->delay_ms(hal->ctx, RESET_WAIT_MS);
}

void gc9a01_init(const panel_hal_t *hal, uint8_t screen)
{
    gc9a01_command(hal, screen, CMD_DISPOFF, 0, 0);
    gc9a01_command(hal, screen, CMD_INREG1, 0, 0);
    gc9a01_command(hal, screen, CMD_INREG2, 0, 0);
    for (unsigned i = 0; i < sizeof vendor_block / sizeof vendor_block[0]; i++)
        gc9a01_command(hal, screen, vendor_block[i].cmd, vendor_block[i].d, vendor_block[i].n);
    gc9a01_command(hal, screen, CMD_PWR2, &PWR2, 1);
    gc9a01_command(hal, screen, CMD_PWR3, &PWR3, 1);
    gc9a01_command(hal, screen, CMD_PWR4, &PWR4, 1);
    gc9a01_command(hal, screen, CMD_GAMMA1, GAMMA_NEG, 6);
    gc9a01_command(hal, screen, CMD_GAMMA2, GAMMA_POS, 6);
    gc9a01_command(hal, screen, CMD_GAMMA3, GAMMA_NEG, 6);
    gc9a01_command(hal, screen, CMD_GAMMA4, GAMMA_POS, 6);
    gc9a01_command(hal, screen, CMD_FRAMERATE, &FRAMERATE, 1);

    const uint8_t colmod = 0x05u;                       /* 16 bits per pixel on the MCU interface */
    gc9a01_command(hal, screen, CMD_COLMOD, &colmod, 1);
    const uint8_t madctl = (uint8_t)GC9A01_MADCTL;
    gc9a01_command(hal, screen, CMD_MADCTL, &madctl, 1);
#if GC9A01_INVERT
    gc9a01_command(hal, screen, CMD_INVON, 0, 0);
#endif
    gc9a01_command(hal, screen, CMD_SLPOUT, 0, 0);
    /* The display stays OFF until the first frame has been drawn. The caller waits
     * GC9A01_SLEEP_OUT_WAIT_MS once for all screens before any further command to them. */
}

void gc9a01_display(const panel_hal_t *hal, uint8_t screen, bool on)
{
    gc9a01_command(hal, screen, on ? CMD_DISPON : CMD_DISPOFF, 0, 0);
}

void gc9a01_blit(const panel_hal_t *hal, uint8_t screen, int x, int y, int w, int h, const uint16_t *pix)
{
    const uint8_t ca[4] = { (uint8_t)(x >> 8), (uint8_t)x, (uint8_t)((x + w - 1) >> 8), (uint8_t)(x + w - 1) };
    const uint8_t ra[4] = { (uint8_t)(y >> 8), (uint8_t)y, (uint8_t)((y + h - 1) >> 8), (uint8_t)(y + h - 1) };

    hal->select(hal->ctx, screen, true);                /* one chip-select span for the whole block */
    uint8_t cmd = CMD_CASET;
    hal->dc(hal->ctx, screen, false);  hal->write(hal->ctx, &cmd, 1);
    hal->dc(hal->ctx, screen, true);   hal->write(hal->ctx, ca, 4);
    cmd = CMD_RASET;
    hal->dc(hal->ctx, screen, false);  hal->write(hal->ctx, &cmd, 1);
    hal->dc(hal->ctx, screen, true);   hal->write(hal->ctx, ra, 4);
    cmd = CMD_RAMWR;
    hal->dc(hal->ctx, screen, false);  hal->write(hal->ctx, &cmd, 1);
    hal->dc(hal->ctx, screen, true);

    /* RGB565 goes out high byte first (datasheet 4.1.9: MSB first) */
    uint8_t chunk[128];
    uint32_t total = (uint32_t)w * (uint32_t)h, i = 0;
    while (i < total) {
        uint32_t n = total - i;
        if (n > sizeof chunk / 2) n = sizeof chunk / 2;
        for (uint32_t k = 0; k < n; k++) {
            uint16_t p = pix[i + k];
            chunk[2 * k] = (uint8_t)(p >> 8);
            chunk[2 * k + 1] = (uint8_t)p;
        }
        hal->write(hal->ctx, chunk, n * 2);
        i += n;
    }
    hal->select(hal->ctx, screen, false);
}
