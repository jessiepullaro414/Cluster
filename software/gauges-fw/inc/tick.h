#ifndef TICK_H
#define TICK_H
#include <stdint.h>

/* 10 ms SysTick. Cooperative scheduler support for main(): now_ms() is the
 * millisecond clock (wraps at 2^32 ms, about 49 days: all users must compare
 * with unsigned subtraction), wait_for_tick_10ms() sleeps in WFI until the
 * next tick. tick_overruns() counts iterations that took longer than 10 ms. */
void     tick_init(void);
uint32_t now_ms(void);
void     wait_for_tick_10ms(void);
uint32_t tick_overruns(void);
#endif
