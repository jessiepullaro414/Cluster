#ifndef INPUTS_HW_H
#define INPUTS_HW_H
/* The few hardware facts the pulse, lamp and ignition inputs need, behind a struct of functions so the logic in inputs.c
 * runs on the host against a fake (test/test_inputs.c) and on the part against the register driver (inputs_hw_s32k.c). */
#include <stdbool.h>
#include <stdint.h>

#define LAMP_COUNT 6u       /* bit order everywhere: turn L, turn R, high beam, brake, alternator, oil */

typedef struct {
    uint32_t (*now_us)(void);           /* free-running microsecond time, extended from the 16-bit timer */
    uint8_t  (*lamps_raw)(void);        /* bit n = the pin of lamp n is HIGH (a 12 V-active lamp that is on, behind its divider) */
    bool     (*ign_raw)(void);          /* the ignition sense pin is HIGH */
    void     (*irq_lock)(void);         /* the capture interrupt is held off while the main loop copies a capture_t */
    void     (*irq_unlock)(void);
} inputs_hw_t;

extern const inputs_hw_t inputs_hw_s32k;
void inputs_hw_init(void);   /* pins, FTM1 and its interrupts */

/* Called by the timer interrupt for each accepted capture: channel 0 = speed (FTM1 CH4), 1 = tach (FTM1 CH5), with the
 * capture time already extended to 32 bits. Defined in inputs.c. */
void inputs_on_capture(unsigned channel, uint32_t t_us);

#endif
