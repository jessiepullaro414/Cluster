#ifndef PANEL_HAL_H
#define PANEL_HAL_H
/*
 * The only thing the GC9A01 driver needs from the hardware. On the target it is
 * LPSPI2 plus GPIO (panel_hal_s32k.c); on the host it is a mock panel that
 * checks the protocol (test/panel_mock.c). Four screens share SCK, SDA and
 * RESET; each has its own CS and D/C line (gauges_pins.h).
 */
#include <stdbool.h>
#include <stdint.h>

typedef struct panel_hal {
    void *ctx;
    /* chip select for one screen: asserted = low on the wire */
    void (*select)(void *ctx, uint8_t screen, bool asserted);
    /* D/C line of one screen: data = high (RS pin on the Raystar module), command = low */
    void (*dc)(void *ctx, uint8_t screen, bool data);
    /* shared hardware reset: asserted = low */
    void (*reset)(void *ctx, bool asserted);
    /* clock len bytes out MSB first and return when the last bit has left the shift register */
    void (*write)(void *ctx, const uint8_t *buf, uint32_t len);
    void (*delay_ms)(void *ctx, uint32_t ms);
    /* backlight switch (BL_EN on gauges/): one switch for all four screens, no dimming */
    void (*backlight)(void *ctx, bool on);
} panel_hal_t;

/* Implemented by the board file; NULL on a host build without a mock. */
const panel_hal_t *panel_hal_board(void);

/* Count of SPI waits that hit their time limit (target only); nonzero means the bus hung once. */
uint32_t panel_hal_timeouts(void);
#endif
