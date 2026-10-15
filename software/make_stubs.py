"""
Writes the software stub tree under cluster-pcb/software/ (run once; edit the
generated files by hand afterwards, this script is only the starting point).
Everything here is a STUB unless a file says otherwise.
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def w(rel, text):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.lstrip("\n"))


w("README.md", r'''
# Cluster software (stubs, 2026-10-14)

Nothing here runs on a car yet. Every file is a stub unless it says otherwise.

| Dir | What | State |
|---|---|---|
| `gauges-fw/` | NXP S32K144 firmware for `gauges/`: inputs, sender conversion, source-priority aggregation, CAN gateway, four GC9A01 gauges, STOP-mode wake | skeleton; `aggregate.c` is real and unit-tested on the host, everything else is a stub |
| `android/` | Android Automotive side for `display/`: VHAL bridge (SocketCAN to vehicle properties), cluster app, rotary dial service | README-level plan and file layout, no code |

The wire protocol is not duplicated here: `../protocol/can_protocol.py` generates `cluster_can.h`, the DBC files and the spec, and both sides use those.

Host build and test of the firmware core (needs gcc, available in WSL here):

```
wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
```
''')

w("gauges-fw/README.md", r'''
# gauges-fw (S32K144, stubs)

Target: NXP S32K144, 64-LQFP, on `../../gauges`. Pin numbers below come from the gauges schematic comments (which were read from NXP's S32K1xx IO table); `inc/gauges_pins.h` is the single place they live.

## Layout (follows `../../../ecu-firmware`: inc/, src/, test/)

| File | Job | State |
|---|---|---|
| `src/main.c` | init order and a 10 ms scheduler loop | stub |
| `src/aggregate.c` | source priority: Hall vs car-bus speed, tach vs car-bus RPM, car vs local fluids | **real, tested** |
| `src/senders.c` | resistive fuel / oil / coolant / battery ADC to engineering units | stub, needs measured sender curves |
| `src/inputs.c` | FTM1 capture for speed (CH4) and tach (CH5), six lamp GPIOs, dimmer ADC, ignition wake | stub |
| `src/can_link.c` | CAN0 (car bus, listen-only) and CAN1 (private link) with counter + CRC-8 from `cluster_can.h` | stub |
| `src/aux_display.c` | four GC9A01 gauges on LPSPI2 | stub |
| `src/power.c` | STOP mode, ignition wake, `PowerState` message | stub |
| `test/test_aggregate.c` | host unit tests for `aggregate.c` | real |

## Rules this firmware must keep
- CAN0 stays in **listen-only**: gauges/ never transmits on the car bus.
- Every private message carries a rolling counter and CRC-8 (SAE J1850, 0x1D, init 0xFF, xorout 0xFF) exactly as `cluster_can.h` defines.
- Each value carries a valid flag and a source; stale car-bus data (older than `CLUSTER_CAR_BUS_TIMEOUT_MS`) falls back to the local sender.
- Display liveness: no `DisplayHeartbeat` for `CLUSTER_DISPLAY_TIMEOUT_MS` sets `DisplayOffline`, but gauges/ keeps running.

## Toolchain
A real ARM build is not set up: the S32K144 needs NXP's S32 Design Studio / S32 SDK or `arm-none-eabi-gcc` plus the S32K1xx headers, and none is installed here. Until that decision is made, only the hardware-independent core builds, on the host with gcc.

## Not decided yet
- Toolchain and SDK (S32DS + S32 SDK vs bare CMSIS + `arm-none-eabi-gcc`).
- Clock tree (80 MHz run vs 112 MHz HSRUN).
- Sender curves (measure the real fuel / oil / coolant senders).
- Debounce and polarity policy per lamp channel (`InputConfig.LampInvertMask`).
''')

w("gauges-fw/Makefile", r'''
# Host build of the hardware-independent core. Run in WSL (gcc 11 available):
#   wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2 -Iinc -I../../protocol

CORE := src/aggregate.c
STUBS := src/senders.c src/inputs.c src/can_link.c src/aux_display.c src/power.c

.PHONY: test stubs clean
test: build/test_aggregate
	./build/test_aggregate

build/test_aggregate: test/test_aggregate.c $(CORE) inc/aggregate.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_aggregate.c $(CORE)

# Compile-check the stubs and main on the host (no hardware access): catches
# header and signature mistakes before an ARM toolchain exists.
stubs:
	mkdir -p build
	$(CC) $(CFLAGS) -DHOST_BUILD -c src/main.c $(CORE) $(STUBS) -o /dev/null 2>/dev/null || \
	for f in src/main.c $(CORE) $(STUBS); do $(CC) $(CFLAGS) -DHOST_BUILD -c $$f -o build/$$(basename $$f .c).o || exit 1; done

clean:
	rm -rf build
''')

w("gauges-fw/inc/gauges_pins.h", r'''
#ifndef GAUGES_PINS_H
#define GAUGES_PINS_H
/*
 * Pin claims for gauges/ rev C. Numbers are the 64-LQFP package pins; port
 * names are from NXP's S32K1xx IO table as recorded in
 * ../../gauges/build_schematic.py (single source of truth, regenerate this
 * file from it if the schematic changes).
 */

/* car bus, FlexCAN0 */
#define PIN_CAN0_RX        6   /* PTE4 */
#define PIN_CAN0_TX        5   /* PTE5 */
#define PIN_CAN0_EN        18  /* PTB5, TJA1043T EN */
#define PIN_CAN0_STB_N     19  /* PTB4, TJA1043T STB_N */
/* private link to display/, FlexCAN1 */
#define PIN_CAN1_RX        52  /* PTC6 */
#define PIN_CAN1_TX        51  /* PTC7 */
#define PIN_CAN1_STB       60  /* PTE0, TCAN1044V standby */

/* timer capture (FTM1) */
#define PIN_SPEED_IN       58  /* PTA10, FTM1_CH4, Hall speed pulses */
#define PIN_TACH_IN        57  /* PTA11, FTM1_CH5, tach pulses */

/* ignition: pin interrupt, wakes the part from STOP/VLPS */
#define PIN_IGN_SENSE      59  /* PTE1 */

/* resistive senders and battery (ADC) */
#define PIN_ADC_FUEL       50  /* PTA0, ADC0_SE0 */
#define PIN_ADC_OIL        49  /* PTA1, ADC0_SE1 */
#define PIN_ADC_TEMP       48  /* PTA2, ADC1_SE0 */
#define PIN_ADC_BATT       47  /* PTA3, ADC1_SE1 */
#define PIN_DIM_ADC        31  /* PTB3, ADC0_SE7, dash dimmer feed */

/* six 12 V-active indicator lamps (active-low if the DNP pull-up is fitted) */
#define PIN_LAMP_TURN_L    35  /* PTC9 */
#define PIN_LAMP_TURN_R    36  /* PTC8 */
#define PIN_LAMP_HIGH_BEAM 37  /* PTA7 */
#define PIN_LAMP_BRAKE     38  /* PTA6 */
#define PIN_LAMP_ALT       43  /* PTB12 */
#define PIN_LAMP_OIL       44  /* PTD4 */

/* four GC9A01 aux gauges on LPSPI2 */
#define PIN_LPSPI2_SCK     29  /* PTC15 */
#define PIN_LPSPI2_SIN     26  /* PTC0 */
#define PIN_LPSPI2_SOUT    25  /* PTC1 */
#define PIN_LPSPI2_PCS0    30  /* PTC14 (claimed, unused: chip selects are GPIO) */
#define PIN_AUX_CS0        13  /* PTE3 */
#define PIN_AUX_CS1        14  /* PTD16 */
#define PIN_AUX_CS2        15  /* PTD15 */
#define PIN_AUX_CS3        16  /* PTE9 */
#define PIN_AUX_DC0        17  /* PTE8 */
#define PIN_AUX_DC1        22  /* PTD7 */
#define PIN_AUX_DC2        23  /* PTD6 */
#define PIN_AUX_DC3        24  /* PTD5 */
#define PIN_AUX_RST        42  /* PTB13 */
#define PIN_BL_EN          39  /* PTE7, aux backlight switch */

/* debug */
#define PIN_SWDIO          64  /* PTA4 */
#define PIN_SWCLK          62  /* PTC4 */

#endif
''')

w("gauges-fw/inc/aggregate.h", r'''
#ifndef AGGREGATE_H
#define AGGREGATE_H
/*
 * Source-priority aggregation (the gateway's brain). REAL, host-tested.
 * Rules from the plan: speed = Hall sender if present and plausible, else the
 * car bus; RPM = tach if enabled and fresh, else the car bus; fluids and
 * battery = a fresh car-bus value, else the local sender. Every result carries
 * a valid flag and its source so the UI can grey out a stale reading.
 */
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float    value;
    bool     valid;       /* the producer says the value is usable */
    uint32_t stamp_ms;    /* time the value was last updated */
} sample_t;

typedef enum { SRC_NONE = 0, SRC_LOCAL = 1, SRC_CAR = 2 } source_t;

typedef struct {
    float    value;
    bool     valid;
    source_t src;
} chosen_t;

#define AGG_SPEED_MAX_KPH   400.0f   /* above this a Hall reading is implausible */
#define AGG_RPM_MAX         12000.0f

/* true when `now_ms - s.stamp_ms <= timeout_ms` (wrap-safe) and s.valid */
bool agg_fresh(sample_t s, uint32_t now_ms, uint32_t timeout_ms);

/* Fluids / battery: car value if fresh, else local if valid, else none. */
chosen_t agg_pick_car_first(sample_t car, sample_t local, uint32_t now_ms,
                            uint32_t car_timeout_ms);

/* Speed: local (Hall) if valid and plausible, else car, else none. */
chosen_t agg_pick_speed(sample_t hall, sample_t car, uint32_t now_ms,
                        uint32_t car_timeout_ms);

/* RPM: tach if enabled, fresh and plausible, else car, else none. */
chosen_t agg_pick_rpm(sample_t tach, bool tach_enabled, sample_t car,
                      uint32_t now_ms, uint32_t car_timeout_ms,
                      uint32_t tach_timeout_ms);

#endif
''')

w("gauges-fw/src/aggregate.c", r'''
#include "aggregate.h"

bool agg_fresh(sample_t s, uint32_t now_ms, uint32_t timeout_ms)
{
    /* unsigned subtraction is correct across a 32-bit millisecond wrap */
    return s.valid && (uint32_t)(now_ms - s.stamp_ms) <= timeout_ms;
}

static chosen_t none(void)
{
    chosen_t c = { 0.0f, false, SRC_NONE };
    return c;
}

static chosen_t from(sample_t s, source_t src)
{
    chosen_t c = { s.value, true, src };
    return c;
}

chosen_t agg_pick_car_first(sample_t car, sample_t local, uint32_t now_ms,
                            uint32_t car_timeout_ms)
{
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    if (local.valid)
        return from(local, SRC_LOCAL);
    return none();
}

chosen_t agg_pick_speed(sample_t hall, sample_t car, uint32_t now_ms,
                        uint32_t car_timeout_ms)
{
    if (hall.valid && hall.value >= 0.0f && hall.value <= AGG_SPEED_MAX_KPH)
        return from(hall, SRC_LOCAL);
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    return none();
}

chosen_t agg_pick_rpm(sample_t tach, bool tach_enabled, sample_t car,
                      uint32_t now_ms, uint32_t car_timeout_ms,
                      uint32_t tach_timeout_ms)
{
    if (tach_enabled && agg_fresh(tach, now_ms, tach_timeout_ms) &&
        tach.value >= 0.0f && tach.value <= AGG_RPM_MAX)
        return from(tach, SRC_LOCAL);
    if (agg_fresh(car, now_ms, car_timeout_ms))
        return from(car, SRC_CAR);
    return none();
}
''')

w("gauges-fw/test/test_aggregate.c", r'''
#include <stdio.h>
#include "aggregate.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static sample_t S(float v, bool ok, uint32_t t) { sample_t s = { v, ok, t }; return s; }

int main(void)
{
    /* freshness, including a 32-bit millisecond wrap */
    CHECK(agg_fresh(S(1, true, 1000), 1400, 500));
    CHECK(!agg_fresh(S(1, true, 1000), 1600, 500));
    CHECK(!agg_fresh(S(1, false, 1000), 1100, 500));
    CHECK(agg_fresh(S(1, true, 0xFFFFFF00u), 0x00000100u, 600));

    /* fluids: fresh car value wins, stale car falls back to local */
    chosen_t c = agg_pick_car_first(S(50, true, 900), S(40, true, 900), 1000, 500);
    CHECK(c.valid && c.src == SRC_CAR && c.value == 50);
    c = agg_pick_car_first(S(50, true, 100), S(40, true, 900), 1000, 500);
    CHECK(c.valid && c.src == SRC_LOCAL && c.value == 40);
    c = agg_pick_car_first(S(50, true, 100), S(40, false, 900), 1000, 500);
    CHECK(!c.valid && c.src == SRC_NONE);

    /* speed: plausible Hall wins; implausible Hall falls to the car bus */
    c = agg_pick_speed(S(88, true, 0), S(90, true, 990), 1000, 500);
    CHECK(c.src == SRC_LOCAL && c.value == 88);
    c = agg_pick_speed(S(900, true, 0), S(90, true, 990), 1000, 500);
    CHECK(c.src == SRC_CAR && c.value == 90);
    c = agg_pick_speed(S(0, false, 0), S(90, true, 100), 1000, 500);
    CHECK(!c.valid);

    /* rpm: tach only when enabled and fresh */
    c = agg_pick_rpm(S(3000, true, 990), true, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_LOCAL && c.value == 3000);
    c = agg_pick_rpm(S(3000, true, 990), false, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_CAR && c.value == 3100);
    c = agg_pick_rpm(S(3000, true, 100), true, S(3100, true, 990), 1000, 500, 200);
    CHECK(c.src == SRC_CAR);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("aggregate: all tests passed\n");
    return 0;
}
''')

# ---- stubs ----------------------------------------------------------------
w("gauges-fw/inc/senders.h", r'''
#ifndef SENDERS_H
#define SENDERS_H
/* STUB. Resistive senders and battery to engineering units. Needs the real
 * sender curves (measure the actual fuel / oil / coolant senders) before the
 * tables mean anything. */
#include "aggregate.h"

void     senders_init(void);
void     senders_poll(uint32_t now_ms);          /* call every 10 ms */
sample_t senders_fuel_pct(void);                 /* 0..100 % */
sample_t senders_coolant_c(void);                /* degC */
sample_t senders_oil_kpa(void);                  /* kPa gauge */
sample_t senders_battery_v(void);                /* volts */
#endif
''')
w("gauges-fw/src/senders.c", r'''
#include "senders.h"

/* TODO: ADC0/ADC1 setup on the pins in gauges_pins.h, averaging, open-circuit
 * detection (the sender front end pulls up to 3.3 V through 1 k), table lookup
 * from measured curves. All values invalid until implemented. */
static sample_t none(void) { sample_t s = { 0.0f, false, 0 }; return s; }

void senders_init(void) {}
void senders_poll(uint32_t now_ms) { (void)now_ms; }
sample_t senders_fuel_pct(void) { return none(); }
sample_t senders_coolant_c(void) { return none(); }
sample_t senders_oil_kpa(void) { return none(); }
sample_t senders_battery_v(void) { return none(); }
''')

w("gauges-fw/inc/inputs.h", r'''
#ifndef INPUTS_H
#define INPUTS_H
/* STUB. Pulse inputs, lamps, dimmer. */
#include <stdbool.h>
#include "aggregate.h"

typedef struct {
    bool turn_left, turn_right, high_beam, brake, alternator, oil;
} lamps_t;

void     inputs_init(void);
void     inputs_poll(uint32_t now_ms);           /* call every 10 ms */
sample_t inputs_speed_kph(void);                 /* from FTM1_CH4 capture and PulsesPerMile */
sample_t inputs_rpm_from_tach(void);             /* from FTM1_CH5 capture and TachPulsesPerRev */
lamps_t  inputs_lamps(uint8_t invert_mask);      /* bit n set = lamp n is active-low */
bool     inputs_dash_lights_on(void);
uint8_t  inputs_dimmer_pct(void);                /* 0..100 */
bool     inputs_ignition_on(void);
#endif
''')
w("gauges-fw/src/inputs.c", r'''
#include "inputs.h"

/* TODO: FTM1 input capture with overflow handling (speed 5 Hz..1 kHz, tach up
 * to a few hundred Hz), lamp GPIOs with debounce (~20 ms, turn signals flash at
 * about 1.5 Hz), dimmer ADC with a 1.5 V lights-off threshold (a first guess
 * to measure on the car), ignition pin interrupt. */
static sample_t none(void) { sample_t s = { 0.0f, false, 0 }; return s; }

void inputs_init(void) {}
void inputs_poll(uint32_t now_ms) { (void)now_ms; }
sample_t inputs_speed_kph(void) { return none(); }
sample_t inputs_rpm_from_tach(void) { return none(); }
lamps_t inputs_lamps(uint8_t invert_mask) { lamps_t l = {0}; (void)invert_mask; return l; }
bool inputs_dash_lights_on(void) { return false; }
uint8_t inputs_dimmer_pct(void) { return 100; }
bool inputs_ignition_on(void) { return false; }
''')

w("gauges-fw/inc/can_link.h", r'''
#ifndef CAN_LINK_H
#define CAN_LINK_H
/* STUB. CAN0 (car bus, LISTEN-ONLY, profile selectable: ecu-pcb native or
 * Haltech V2) and CAN1 (private link to display/). Message layouts, counters
 * and CRC come from ../../protocol/cluster_can.h (generated, do not copy). */
#include <stdbool.h>
#include "aggregate.h"

typedef struct {
    sample_t speed_kph, rpm, battery_v, fuel_pct, coolant_c, oil_kpa;
    bool     active;                 /* any car-bus frame seen within the timeout */
} car_bus_t;

typedef struct {
    uint8_t brightness_pct;
    bool    night_mode, units_mph;
    uint8_t car_profile;             /* 0 none, 1 Haltech V2 */
    uint8_t car_bitrate;             /* 0 500k, 1 1M, 2 250k */
    float   tank_capacity_l;
    uint8_t lamp_invert_mask;
    bool    tach_enabled;
    uint8_t tach_pulses_per_rev;
    uint32_t pulses_per_mile;
    bool    display_heartbeat_seen;
} display_settings_t;

void       can_link_init(void);
void       can_link_poll(uint32_t now_ms);            /* drain RX, update tables */
car_bus_t  can_link_car(void);
display_settings_t can_link_settings(void);
/* private-link transmit (counter + CRC added inside): */
void can_link_send_motion(float kph, float rpm, float battery_v,
                          bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall);
void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa,
                          bool fuel_ok, bool coolant_ok, bool oil_ok);
void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil,
                              bool lights_on, uint8_t dimmer_pct);
void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s);
#endif
''')
w("gauges-fw/src/can_link.c", r'''
#include "can_link.h"
#include "cluster_can.h"      /* generated; also checks the header compiles as C */

/* TODO: FlexCAN0 in listen-only mode (never transmit on the car bus), FlexCAN1
 * at 500 kbit/s; RX filters for the Haltech V2 ids (0x360, 0x361, 0x370,
 * 0x372, 0x3E0, 0x3E2) and the ecu-pcb ids; byte-order handling per profile;
 * private-link TX with the rolling counter and cluster_crc8(). */
static display_settings_t g_settings = { 100, false, false, 0, 0, 0.0f, 0, false, 4, 16000u, false };

void can_link_init(void) {}
void can_link_poll(uint32_t now_ms) { (void)now_ms; }
car_bus_t can_link_car(void) { car_bus_t c = {0}; return c; }
display_settings_t can_link_settings(void) { return g_settings; }
void can_link_send_motion(float kph, float rpm, float battery_v,
                          bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall)
{ (void)kph; (void)rpm; (void)battery_v; (void)kph_ok; (void)rpm_ok; (void)batt_ok; (void)from_hall; }
void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa,
                          bool fuel_ok, bool coolant_ok, bool oil_ok)
{ (void)fuel_pct; (void)coolant_c; (void)oil_kpa; (void)fuel_ok; (void)coolant_ok; (void)oil_ok; }
void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil,
                              bool lights_on, uint8_t dimmer_pct)
{ (void)l; (void)r; (void)hb; (void)brake; (void)alt; (void)oil; (void)lights_on; (void)dimmer_pct; }
void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s)
{ (void)ignition_on; (void)suspend_request; (void)suspend_in_s; }
''')

w("gauges-fw/inc/aux_display.h", r'''
#ifndef AUX_DISPLAY_H
#define AUX_DISPLAY_H
/* STUB. Four GC9A01 round gauges (240x240) on LPSPI2 with GPIO chip selects
 * and D/C pins. Order on the board: fuel, oil, coolant temp, battery. */
#include "aggregate.h"

void aux_display_init(void);
void aux_display_set_backlight(bool on, uint8_t pct);
/* draw a needle gauge from a value in [lo, hi]; invalid values draw a dash */
void aux_display_gauge(uint8_t index, chosen_t v, float lo, float hi);
#endif
''')
w("gauges-fw/src/aux_display.c", r'''
#include "aux_display.h"

/* TODO: LPSPI2 setup, GC9A01 init sequence (from Raystar's RFA401280B-AYW-DNF1
 * datasheet, not yet requested), framebuffer-less needle drawing or a DMA line
 * buffer, backlight via the BL_EN switch (gauges/ Q2). */
void aux_display_init(void) {}
void aux_display_set_backlight(bool on, uint8_t pct) { (void)on; (void)pct; }
void aux_display_gauge(uint8_t index, chosen_t v, float lo, float hi)
{ (void)index; (void)v; (void)lo; (void)hi; }
''')

w("gauges-fw/inc/power.h", r'''
#ifndef POWER_H
#define POWER_H
/* STUB. Ignition tracking and low-power STOP mode. display/ suspends to RAM and
 * wakes on its own WAKE1 pin; gauges/ must be live within milliseconds of
 * ignition and tells display/ about key state with PowerState (0x310). */
#include <stdbool.h>
#include <stdint.h>

void power_init(void);
void power_poll(uint32_t now_ms);
bool power_ignition_on(void);
void power_enter_stop_if_idle(uint32_t now_ms);    /* wakes on the IGN_SENSE pin interrupt */
#endif
''')
w("gauges-fw/src/power.c", r'''
#include "power.h"

/* TODO: IGN_SENSE pin interrupt, debounce, shutdown delay (display/ gets
 * SuspendRequest and a SuspendInSeconds countdown first), STOP/VLPS entry
 * (the RM's AWIC table: any enabled pin interrupt wakes from STOP and VLPS). */
void power_init(void) {}
void power_poll(uint32_t now_ms) { (void)now_ms; }
bool power_ignition_on(void) { return false; }
void power_enter_stop_if_idle(uint32_t now_ms) { (void)now_ms; }
''')

w("gauges-fw/src/main.c", r'''
#include <stdint.h>
#include "aggregate.h"
#include "aux_display.h"
#include "can_link.h"
#include "inputs.h"
#include "power.h"
#include "senders.h"
#include "cluster_can.h"

/* STUB main: the init order and the 10 ms task are the point; every module is
 * a stub. now_ms() and the scheduler tick come from a SysTick/LPIT driver that
 * does not exist yet. */
extern uint32_t now_ms(void);
extern void     wait_for_tick_10ms(void);

static void step(uint32_t now)
{
    power_poll(now);
    senders_poll(now);
    inputs_poll(now);
    can_link_poll(now);

    car_bus_t car = can_link_car();
    display_settings_t cfg = can_link_settings();

    chosen_t speed = agg_pick_speed(inputs_speed_kph(), car.speed_kph, now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t rpm = agg_pick_rpm(inputs_rpm_from_tach(), cfg.tach_enabled, car.rpm, now,
                                CLUSTER_CAR_BUS_TIMEOUT_MS, 200u);
    chosen_t battery = agg_pick_car_first(car.battery_v, senders_battery_v(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t fuel = agg_pick_car_first(car.fuel_pct, senders_fuel_pct(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t coolant = agg_pick_car_first(car.coolant_c, senders_coolant_c(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);
    chosen_t oil = agg_pick_car_first(car.oil_kpa, senders_oil_kpa(), now, CLUSTER_CAR_BUS_TIMEOUT_MS);

    aux_display_gauge(0, fuel, 0.0f, 100.0f);
    aux_display_gauge(1, oil, 0.0f, 700.0f);
    aux_display_gauge(2, coolant, 40.0f, 130.0f);
    aux_display_gauge(3, battery, 10.0f, 16.0f);

    can_link_send_motion(speed.value, rpm.value, battery.value, speed.valid, rpm.valid,
                         battery.valid, speed.src == SRC_LOCAL);
    can_link_send_fluids(fuel.value, coolant.value, oil.value, fuel.valid, coolant.valid, oil.valid);
    lamps_t l = inputs_lamps(cfg.lamp_invert_mask);
    can_link_send_indicators(l.turn_left, l.turn_right, l.high_beam, l.brake, l.alternator, l.oil,
                             inputs_dash_lights_on(), inputs_dimmer_pct());
    can_link_send_power(power_ignition_on(), false, 0);
    power_enter_stop_if_idle(now);
}

#ifndef HOST_BUILD
int main(void)
{
    power_init();
    senders_init();
    inputs_init();
    can_link_init();
    aux_display_init();
    for (;;) {
        step(now_ms());
        wait_for_tick_10ms();
    }
}
#else
/* host build only: lets `make stubs` compile-check step() without a main */
void host_step(uint32_t now) { step(now); }
#endif
''')

# ---- android --------------------------------------------------------------
w("android/README.md", r'''
# Android Automotive side (plan and layout, no code yet)

Target: Verdin iMX95 on `../../display` running Android Automotive (AOSP, AAOS). On the production module this is a PORT (NXP's AAOS release supports the 19x19 EVK, see the plan); app-level work can start on the EVK or any AAOS emulator.

| Dir | What | State |
|---|---|---|
| `vhal-bridge/` | Vehicle HAL service: Linux SocketCAN to Android vehicle properties, decoding the private link | plan only |
| `cluster-app/` | full-screen round UI sized for the panel; reads the Car Property API | plan only |
| `rotary-service/` | turns the dial (ADC + click) into Android key/rotary events for the UI and for CarPlay / Android Auto | plan only |

Display shape: the panel is round (4.0 in 720 x 720 today; 1080 x 1080 for 5 in, 720 x 720 for the Anders 4.2 in). CarPlay / Android Auto need a rectangular viewport inside the circle (about 88 x 50 mm at 4.0 in); the cluster app must clip and lay out for that.

The wire protocol is generated: `../../protocol/cluster_private.dbc` and `cluster_can.h`.
''')
w("android/vhal-bridge/README.md", r'''
# vhal-bridge (plan)

Reads CAN1 frames from SocketCAN (`can0` on the Verdin), verifies the rolling counter and CRC-8 (`cluster_crc8` in `../../../protocol/cluster_can.h`: SAE J1850, poly 0x1D, init 0xFF, xorout 0xFF), and publishes vehicle properties. It never transmits anything except `DisplaySettings`, `SpeedCalibration`, `InputConfig` and `DisplayHeartbeat` to gauges/, and nothing on the car bus (gauges/ is the only node on it).

Property mapping, TO VERIFY against AOSP's `VehicleProperty.aidl` for the release in use (names are from memory):

| Message / signal | Vehicle property (candidate) | Notes |
|---|---|---|
| `VehicleMotion.SpeedKph` | `PERF_VEHICLE_SPEED` (m/s) | convert km/h to m/s; honour `SpeedValid` |
| `VehicleMotion.Rpm` | `ENGINE_RPM` | honour `RpmValid` |
| `VehicleMotion.BatteryV` | vendor property | no standard 12 V battery voltage property |
| `VehicleFluids.FuelPct` | `FUEL_LEVEL` (needs capacity) or a percentage property | `DisplaySettings.TankCapacityL` |
| `VehicleFluids.CoolantC` | `ENGINE_COOLANT_TEMP` | |
| `VehicleFluids.OilKpa` | vendor property | standard oil property is level, not pressure |
| `Indicators.TurnLeft/TurnRight` | `TURN_SIGNAL_STATE` | |
| `Indicators.HighBeam` | `HIGH_BEAM_LIGHTS_STATE` | |
| `Indicators.BrakeWarning` | `PARKING_BRAKE_ON` (or a vendor warning) | |
| `Indicators.AlternatorWarning`, `OilWarning` | vendor warning properties | |
| `Indicators.DashLightsOn`, `DashDimmerPct` | `NIGHT_MODE` and the display brightness | |
| `PowerState.IgnitionOn`, `SuspendRequest` | `IGNITION_STATE`, power policy | suspend-to-RAM request |

Stale data: if a message is older than its `CAN_PERIOD_MS_*` times a few, mark the property unavailable (`STATUS_UNAVAILABLE`) rather than holding the last value.
''')
w("android/cluster-app/README.md", r'''
# cluster-app (plan)

Full-screen round instrument UI. Safe drawing area: the active circle (101.5 mm / 720 px on the TSD panel; 105.84 mm / 720 px on the Anders 4.2 in). Reads speed, RPM, fluids, warnings and lighting through the Car Property API; greys out any property reported unavailable. Brightness follows `DashDimmerPct` and `NightMode`. Hosts a CarPlay / Android Auto viewport as a rectangle inscribed in the circle (16:9 gives 88.5 x 49.8 mm at 4.0 in); navigation by the rotary dial.

First milestone: the app on an AAOS emulator fed by a fake property source, round layout only.
''')
w("android/rotary-service/README.md", r'''
# rotary-service (plan)

The dial is a Piher PSC-360 (contactless, 5 V ratiometric analog output, endless) read on Verdin ADC_1, plus a separate push switch on GPIO_1 (see `../../../display` J11). The service unwraps the angle into detents, debounces the click, and injects rotary / key events for the cluster UI and for CarPlay / Android Auto. The dial's 5 V is switched off in sleep by `CTRL_SLEEP_MOCI#`, so the service must treat the first reading after wake as a re-zero.
''')
print("stubs written under", ROOT)
