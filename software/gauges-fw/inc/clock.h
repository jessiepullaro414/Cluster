#ifndef CLOCK_H
#define CLOCK_H
#include <stdbool.h>
#include <stdint.h>

/* 8 MHz crystal -> SPLL 160 MHz -> 80 MHz core, 40 MHz bus, 26.67 MHz flash
 * (RM 27.4 Table 27-3). Returns false and stays on the 48 MHz FIRC if the
 * crystal or the PLL does not validate; clock_core_hz() reports what is real.
 * UNTESTED ON HARDWARE: compiled against the RM only. */
bool     clock_init_80mhz(void);
uint32_t clock_core_hz(void);
#endif
