# gauges-fw (S32K144: boots to main in the image; inputs, senders, fault handling and odometer real, CAN and power still stubs)

Target: NXP S32K144, 64-LQFP, on `../../gauges`. Pin numbers below come from the gauges schematic comments (which were read from NXP's S32K1xx IO table); `inc/gauges_pins.h` is the single place they live.

## Layout (follows `../../../ecu-firmware`: inc/, src/, test/)

| File | Job | State |
|---|---|---|
| `src/main.c` | init order and a 10 ms scheduler loop | stub |
| `src/aggregate.c` | source priority: Hall vs car-bus speed, tach vs car-bus RPM, car vs local fluids | **real, tested** |
| `src/senders.c`, `inc/senders.h`, `inc/adc.h` | resistive fuel / oil / coolant senders and battery voltage: ratiometric resistance, damping, open/short detection, curve lookup | **real, tested** against a fake ADC; the sender **curves are not known** (dashes until measured, `src/sender_curves.c`) |
| `src/inputs.c`, `inc/inputs.h`, `inc/inputs_hw.h` | speed and tach from the capture periods, six lamp inputs with debounce and per-lamp inversion, dimmer, ignition debounce | **real, tested** against a fake hardware layer |
| `src/capture.c`, `inc/capture.h` | period tracking for a pulse input: glitch rejection, 16-bit timer overflow extension, absent / running / stopped / fault, time wrap | **real, tested** |
| `src/inputs_hw_s32k.c`, `src/adc_s32k.c` | FTM1 input capture (CH4 speed, CH5 tach) with its interrupts, lamp and ignition GPIO, ADC0/ADC1 calibration and conversions | written from the RM, **compiled and linked, never run on a part** |
| `src/can_link.c` | CAN0 (car bus, listen-only) and CAN1 (private link) with counter + CRC-8 from `cluster_can.h` | stub |
| `src/gfx.c`, `inc/gfx.h` | tile renderer for the 240x240 round screens: anti-aliased arcs, capsules, discs and 5x7 glyphs from a short op list, integer inner loops, no framebuffer (one frame is 115 KB, the part has 60 KB of RAM) | **real, tested** |
| `src/dial_modern.c` | the **modern theme**: dark navy face, thick progress arcs filling blue (to red), big proportional digits, small icons, two horizontal bars for volts and oil, modelled on the owner's reference picture | **real, tested**; styling a first pass |
| `src/dial_carplay.c` | the **carplay theme**: Apple-inspired (black face, thin rings, white knob, system colours, two concentric rings for volts and oil); shares the arc themes' change tracking with dial_modern.c | **real, tested**; styling a first pass; whether the product may call it CarPlay-styled is a licensing question (B5) |
| `src/dial_factory.c`, `src/face.c`, `src/face_data.c` | the **factory theme**: printed 1966 Mustang gauge faces (generated pictures) with needles drawn over them | **real, tested**; faces drawn by eye from photos, a first pass to tune |
| `src/font_data.c`, `inc/font.h`, `tools/gen_font.py` | anti-aliased bitmap fonts (60 px digits, 28 px and 15 px text) generated from Inter (SIL Open Font License, `../../docs/fonts/OFL-Inter.txt`); the generated C is committed, Pillow is only needed to regenerate | generated |
| `src/dial.c`, `inc/dial.h` | one screen's picture (scale, ticks, labels, red zones, needle, seven-segment digits, unit, small readout) built from a `screen_view_t`, and the change tracking: which 8x8 tiles differ from what is on the panel | **real, tested**; the styling is a first pass to tune with the owner |
| `src/gc9a01.c`, `inc/gc9a01.h` | GC9A01 driver: init sequence, window, RGB565 blit | **real, tested against a mock panel**; init values partly from an open-source driver, see below |
| `src/aux_display.c` | four screens: reset, init, first frame, then send only the changed tiles, a bounded number per tick | **real, tested** |
| `src/panel_hal_s32k.c` | LPSPI2 + GPIO bus layer for the four screens (blocking, polled, 9.6 MHz) | written from the RM, **compiled and linked, never run on a part** |
| `test/panel_mock.c` | mock of four GC9A01 panels: decodes the SPI stream, models the GRAM window, flags protocol mistakes | test tool |
| `src/power.c` | STOP mode, ignition wake, `PowerState` message | stub |
| `src/fault.c`, `inc/fault.h` | fault manager: reset-cause decode, the task/watchdog policy, quarantine of a task that hangs twice, limp level (see "Fault handling") | **real, tested** |
| `src/wdog_s32k.c`, `inc/wdog.h` | starts the watchdog (128 kHz LPO, 100 ms, final configuration), kicks it, reads `RCM_SRS` | written from the RM, **compiled and linked, never run on a part** |
| `src/status.c`, `inc/status.h` | builds the `GaugesStatus` message (sources, open senders, reset cause, limp level, quarantine) | **real, tested** |
| `src/odometer.c`, `inc/odometer.h` | odometer and trip meter: exact distance integration, saved every 0.1 mile, at ignition-off and on trip reset (see "Odometer storage") | **real, tested with power cut at every event** |
| `src/nvlog.c`, `inc/nvlog.h`, `inc/nvflash.h` | the power-loss-safe record log in the data flash that the odometer and the settings share: CRC and sequence per entry, ring of sectors, erase ahead, torn and failed commands | **real, tested** |
| `src/settings_store.c`, `inc/settings_store.h` | the display settings kept in flash so a dead display never changes units, theme or calibration; saved once a change has been stable for 3 s | **real, tested** |
| `src/nvflash_s32k.c` | FTFC driver for the data flash (erase sector, program phrase), FlexNVM partition check and the one-time Program Partition (runs from SRAM) | written from the RM, **compiled and linked, never run on a part** |
| `src/crc.c`, `inc/crc.h` | CRC-32 (zlib) for the retained record, the odometer log and the update image | **real, tested** |
| `src/startup.c`, `src/vectors.c`, `src/fcf.c`, `link/s32k144.ld` | reset path (SRAM ECC zero-fill, watchdog off, .data, FPU), generated 139-entry vector table, flash configuration field at 0x400, linker script | **real, built and linked; not run on a part** |
| `src/clock.c`, `src/tick.c` | 8 MHz crystal to SPLL to 80 MHz core, 10 ms SysTick, `now_ms()` | **real, not run on a part** |
| `inc/s32k144_regs.h`, `inc/s32k144_irq.h` | register layer written from the RM (each block cites its section); IRQ numbers generated by `tools/gen_vectors.py` | real |
| `src/screens.c` | what each small screen shows: speed, rpm, fuel, volts, coolant, oil as needle fraction, number, unit, warning (imperial or metric); default layout fuel+volts / speed / rpm / coolant+oil | **real, tested** |
| `test/test_*.c` | host unit tests (aggregate, inputmath, codec, screens, gfx, dial, gc9a01, fault) | real |

## Rules this firmware must keep
- CAN0 stays in **listen-only**: gauges/ never transmits on the car bus.
- Every private message carries a rolling counter and CRC-8 (SAE J1850, 0x1D, init 0xFF, xorout 0xFF) exactly as `cluster_can.h` defines.
- Each value carries a valid flag and a source; stale car-bus data (older than `CLUSTER_CAR_BUS_TIMEOUT_MS`) falls back to the local sender.
- Display liveness: no `DisplayHeartbeat` for `CLUSTER_DISPLAY_TIMEOUT_MS` sets `DisplayOffline`, but gauges/ keeps running.

## Toolchain
`arm-none-eabi-gcc` 12.3 (installed in WSL for the AAOS build, see `../PLAN.md`), no NXP SDK. In WSL:

```
make test       # host tests (gcc)
make arm-check  # compile every file for the Cortex-M4F, -Werror
make arm        # link build/gauges-fw.elf with link/s32k144.ld
sh tools/inspect_elf.sh   # vector table, flash config, reset code
```

Verified by inspection of the linked image only (SP 0x20006FE0: the top 32 bytes of RAM are the retained fault record, reset vector 0x411, SysTick at vector 15, flash configuration 0xFE/0xFB at 0x40C/0x40D). **Nothing has executed on a part.** `FSEC` is left unsecured for debugging; production must secure it.

## Inputs and senders

Everything between a pin and the numbers the screens show is split into logic that runs on the host and a thin register layer that does not:

- **Speed and tach.** FTM1 counts microseconds (8 MHz crystal, divide by 8) and captures rising edges on CH4 (PTA10, Hall speed) and CH5 (PTA11, tach). The interrupt extends the 16-bit capture to 32 bits with an overflow counter (`capture_extend`: a capture in the lower half of the range seen with the overflow flag still set belongs after the wrap) and hands it to `capture.c`, which rejects edges closer than 100 us, reports a period, and says whether the sender is absent (fewer than two edges since boot), running, stopped (slower than 2 Hz), or a fault (faster than 2 kHz). The speed is `im_speed_kph(period, pulses_per_mile)`; a reading falls as soon as the next pulse is late, not when a timeout expires. A sender that is present and not pulsing reports a valid 0 km/h; one that never pulsed is invalid, so the car bus can take over. **A Hall 0 is overruled by a fresh car-bus speed of 8 km/h or more** (a dead sensor looks like a stopped one). Tested with 60 mph at 16000 pulses/mile (96.56 km/h), 5 Hz, standing still, recalibration, 4 kHz noise, 200,000 captures across timer wraps.
- **Lamps and ignition.** Six GPIOs, each debounced 20 ms; the invert mask makes a ground-switched lamp (DNP pull-up fitted) read correctly. The ignition needs 50 ms to change (a crank dip does not switch the cluster off).
- **Senders.** One channel per 10 ms poll, so each is read every 40 ms; the ADC averages 8 conversions in hardware. The reading is ratiometric: `R = 1000 * code / (4095 - code)` for the 1 k pull-up to the 3V3 rail (the series resistor, clamp and 100 nF do not matter at DC), and an open wire reads full scale. An open or a short must persist 1 s before it is reported; a channel whose conversions stop succeeding goes invalid after 2 s. The values are damped (fuel about 5 s against slosh, oil and battery 0.6 s, coolant 1.3 s) in integer arithmetic with 12 fractional bits so the damping has no dead band. Battery voltage is the 49.9 k / 10 k divider times the code; its accuracy is the 3V3 rail's (VREFH is that rail), not a reference's.
- **Curves.** `senders_set_curve()` takes ascending (ohm, value) points. **None are known**: until a sender has a curve its gauge shows dashes and `senders_ohms()` gives the live resistance for the measurement (plan A9). Nothing here invents a curve.
- **ADC bring-up.** `adc_hw_init()` follows the RM's calibration recipe (clear the CLP registers, SC3 = CAL | AVGE | 32 samples, wait for COCO, one ADC at a time) at ADCK 6 MHz, then runs conversions at 12 MHz. The ADCK limits come from the data sheet, which is not among the references; both clocks are well below any plausible limit.
- **What is checked about the hardware layer:** `tools/check_pins.py` compares every pin in the register code with `gauges_pins.h`; the port mux alternatives (CAN0 alt 5 on PTE4/5, CAN1 alt 3 on PTC6/7, FTM1_CH4/5 alt 2 on PTA10/11) were read from NXP's IO signal table. **Not checked:** that a single edge is delivered by the real FTM, the interrupt timing, ADC accuracy, anything electrical.
- **Mutation check:** 22 deliberate breakages of `capture.c`, `inputs.c` and `senders.c` (a wrong threshold, a missing lock, an inverted mask, no stale check ...), 21 caught and one equivalent (a clamp that triggers at 200 s instead of 2 s).

## Fault handling

The rule: a dead display, a dead car bus, a broken sender or a hung task must never take the gauges down. `step()` in `main.c` runs the firmware as six **tasks** (power, senders, inputs, CAN, screens, storage), each bracketed by `fault_task_begin/end`.

- **Watchdog.** `wdog_start(100 ms)` after init, on the 128 kHz LPO, `UPDATE = 0` so nothing running later can switch it off. The loop kicks it only when every enabled task finished since the last kick (`fault_service`). The SRAM zero-fill at reset takes less than the default 8 ms timeout, so `startup.c` still disables the dog until `main` has finished init.
- **Quarantine.** The last 32 bytes of SRAM (`.noinit`) are not cleared at a watchdog reset; they hold which task was running, protected by a CRC-32 (and by a complement for the single byte that changes every task). If the **same** task is running at two watchdog resets in a row it is switched off (the others keep running) until the next ignition-on, or until a power-on reset. Two different tasks hanging, or a hang outside every task, blame nobody; three resets in a row is limp mode regardless. After 30 s of good passes the streak count restarts.
- **After power-on** the retained area holds junk and is ECC-unsafe to read, so `startup.c` writes it with 32-bit stores when `RCM_SRS` shows power-on or low voltage, and `fault_boot` also refuses a record whose magic or CRC is wrong.
- **What a quarantined task means for the output:** senders switched off → local sender values invalid, the car bus still feeds the gauges; inputs off → no Hall speed, no tach, all lamps off; CAN off → no car data and nothing transmitted; screens off → the four small screens freeze on their last picture; storage off → the odometer keeps counting in RAM but is not saved (and does not hold the chip awake); power off → treated as ignition on. `GaugesStatus` (1 Hz) carries `ResetCause`, `LimpLevel` (0 normal, 1 degraded, 2 limp), `QuarantineMask` and `WatchdogResets`, so Android can say so.
- **Tested** with a model of the chip's watchdog (`test/test_fault.c`: hangs in each place, alternation, torn and corrupted records, power-on junk, the healthy-period restart, saturation) and by deliberately breaking nine lines of `fault.c`, each caught. **Not tested:** the real LPO rate and timeout, an actual reset on a part, and whether a hang in the blocking SPI loop is really interrupted by the reset (it should be: the watchdog is a hardware counter).

## Odometer storage

The odometer and the trip meter are `uint32` metres, counted from the chosen speed in exact integer arithmetic (1 km/h for 10 ms is 2.7778 mm; the remainder is carried, so 50 km/h for 720 s is exactly 10,000 m in the test). They live in RAM and are written to the **data flash** (FlexNVM, all 64 KB set up as data flash; the first 32 KB are the log) as a ring of 16 sectors of 2 KB, 128 entries each:

| bytes | 0-3 | 4-7 | 8-11 | 12-15 |
|---|---|---|---|---|
| entry | odometer m | trip m | sequence | CRC-32 of bytes 0-11 |

- **Power-loss safety.** (The log itself is `nvlog.c`; the settings use it with a 16-byte payload.) The first 8-byte phrase (distance) is programmed first, the second (sequence + CRC) last, so an entry only exists when its last phrase lands. A torn entry fails the CRC and the previous one is used; a slot that is torn or that the chip reports an error for is abandoned (flash bits can only be programmed once). The next sector is erased ahead of time, always the oldest data, so a save never waits for an erase, and an interrupted erase can only damage old entries. The test (`test/test_odometer.c`, `test/nv_mock.c`) models the flash with the real rules (erase before program, one command at a time, 8-byte phrases, 2 KB sectors) and **cuts the power at every one of the 8,488 command events of a drive that wraps a 4-sector log twice** (before the command, half way through it with a random half-erased or half-programmed result, and just after it), plus 960 random cuts with random speeds and key cycles. After every cut the recovered odometer is never behind the last finished save, never ahead of the distance driven, and is a value that really was written. All twelve deliberate breakages of `nvlog.c` (no CRC check, no skipping of torn slots, no erase before use, no erase ahead, the wrong CRC span, a wrong ring wrap ...) are caught by these tests. A first version of `nvlog.c` silently dropped a write request when an erase started; the mutation run found it.
- **Display settings.** The same log, 4 sectors after the odometer's 16 (data flash offset 32768), 16-byte records of brightness, night, units, theme, car profile and bit rate, lamp inversion, tach, tank size and pulses per mile (not `center_shows_speed` or the heartbeat, which describe the display's state, not a preference). `test/test_settings.c`: the format, no write for unchanged defaults, a slider dragged for 5 s is one write (three programs), and a power cut at each of the nine events of a save leaves the old or the new settings, nothing else.
- **When it saves.** Every 161 m (0.1 mile) driven, immediately when the ignition goes off, and when the trip meter is reset. So an unannounced battery disconnect loses at most 0.1 mile; a normal key-off loses nothing.
- **Wear.** 100,000 miles in the test is 7,460 sector erases over 16 sectors, at most **467 on any one sector**. The S32K144 data sheet (not among the reference documents here) must be checked for the data flash program/erase endurance at the temperatures in the engine bay; the design only needs a few thousand cycles.
- **Production step.** On a fresh part the FlexNVM is unpartitioned. At first boot `main()` sees that (`SIM_FCFG1`, `NV_PARTITION_BLANK`), runs **Program Partition** once from SRAM (EEPROM size code 0xF, partition code 0000: 64 KB data flash), and resets so it takes effect. A part partitioned any other way is left alone and the odometer runs in RAM only (`GaugesStatus.NvStorageOk = 0`). This changes the part for life (only a mass erase undoes it) and has never run on a part.
- **Not done:** the factory-theme odometer window is still empty (the numbers go to Android in `Odometer` 0x304; drawing them on the small screen is a separate change to the face and the golden pictures), no service interface sets the odometer, and rollover display (a mechanical 1966 odometer rolls at 99,999.9 miles) is the display's job. **If a cluster replaces a car's old one, US federal law (49 U.S.C. 32705) and many state laws require the replacement to be disclosed and the mileage handled correctly; any future "set odometer" feature needs a deliberate, owner-visible policy rather than an open CAN message.**

## The four screens (A7)

Four themes, chosen by the user (`DisplaySettings.GaugeTheme` in the protocol; the Android settings list sets it, the harness key T switches it locally). A theme brings its own layout (`screens_layout()`): **classic** is needles on 270 degree scales with seven-segment digits (fuel + volts, speed, rpm, coolant + oil); **modern** follows the reference picture (speed with fuel, rpm with coolant, volts and oil as two bars, coolant); **carplay** (added 2026-10-16) is Apple-inspired: black face, thin rings with a white knob, system colours, volts and oil as two concentric activity-style rings. The Android app switches the small screens to it automatically while a phone shows CarPlay (setting "With CarPlay", on by default), and back afterwards; Android Auto and no phone keep the user theme. **factory** (added 2026-10-16) copies the 1966 Mustang's own gauges: fuel (with a small volts readout), speedometer (MILES or KM/H, radial numerals), oil and temperature, black printed faces with a red-orange needle; no tachometer (the stock cluster has none) and an empty odometer window. The printed faces are pictures made by `tools/gen_faces.py` (condensed Inter, run-length coded 4-bit, `src/face_data.c`), the needles are drawn by `src/dial_factory.c`. Previews rendered through the real driver into the mock panel are in `docs/screens/` (`make preview PRESET=1 UNITS=metric THEME=modern` style: `./build/preview <preset> <imperial|metric> <classic|modern|carplay|factory>`, then `python tools/montage.py out.png`). Unknown theme numbers show classic.

**Speed on the centre screen.** Each theme has its own speedometer on the round centre display too (Android `ClusterView`: needle, arc, ring or the 1966 face). While the centre shows it (`DisplaySettings.CenterShowsSpeed`, dev feed `center=1`), the small screens do not repeat speed: `screens_layout_for(theme, true)` gives the screen that had it another gauge (classic: volts; modern and carplay: fuel; factory: volts on an ammeter-style face). Previews: `docs/screens/center_<theme>.png` (small screens) and `android_center_themes.png` (centre).

![modern theme](docs/screens/modern_cruise_mph.png)

**The bus is the limit.** The S32K144 datasheet limits LPSPI to 10 MHz in Run mode (quoted for Rev 13 on NXP's forum; check the current table), so the HAL runs 9.6 MHz (48 MHz FIRC / 5). At that rate a full 240x240 frame is 96 KB, 80 ms: too slow to redraw, so nothing is redrawn whole. Numbers from `make test` and `make bench` (operations counted, not timed):

| | per screen | on the bus at 9.6 MHz |
|---|---|---|
| first full draw | 764 tiles, 96 KB | about 80 ms (all four: about 0.3 s, once at boot) |
| a small move (needle 1 degree, a digit changes) | 50 to 70 tiles, 6 to 9 KB | 5 to 7 ms |
| a large move | 70 to 100 tiles, 9 to 12 KB | 8 to 10 ms |
| nothing visible changed | 0 | 0 |

Four screens updating 15 times a second is about 3.5 Mbit/s, roughly a third of the bus. Tricks used: tiles are 8x8; only the tiles under the old and new needle are resent; only the digits that changed are resent; the needle moves in whole degrees; rpm is shown to the nearest 10. CPU cost per small update is about 2 to 3 ms (operation counts times an **assumed** cost per operation: not measured on hardware). The SPI transfers block the CPU; DMA would free it and is the next optimisation.

**Test harness (`test/harness.c`, `make harness` / `make harness_cli`).** One native program that runs the real screen code (screens, dial, gfx, driver, scheduler) in the firmware's loop shape against the mock panel, so a styling or timing change is seen or measured in seconds. `tools/run_harness.ps1` builds it, opens the window (an X11 window shown on the Windows desktop by WSLg; the X11 headers are unpacked once into `~/x11sdk` by `tools/get_x11_headers.sh`, no root needed) and points the Android app at it. Without a window (`build/harness_cli`, no display needed) the same program does the automated work:

| Command | What it does |
|---|---|
| `harness` | window with the four round screens (T switches theme) and a status area drawn with the firmware's own font. Keys: SPACE pause, D built-in drive, M manual (arrows = speed and rpm, F C O B = fuel, coolant, oil, battery, 1-6 toggle an input valid/invalid), A Android, R replay, U units, TAB zoom, S save a PNG, Q quit |
| `harness --udp 5005` | listen for the Android app's telemetry line (UDP); no data for 1 s shows dashes, like the firmware. `--record f` saves what arrives, `--replay f` plays it back |
| `make golden` | 11 fixed states x 4 screens against stored checksums (`test/golden_screens.txt`). A one-bit colour change or a moved label shows up as CHANGED; look with `make golden-dump` (PNGs in `build/golden`), accept with `make golden-update` |
| `make sim` | 60 virtual seconds of driving with unit switches: bus load, worst tick, backlog, time to redraw after a switch, and whether the panel equals the model at the end. Fails if any tick needs more than 10 ms of bus time |
| `harness --selftest` | panel equals model through a drive (with a unit switch), lost data gives dashes, CRC and PNG helpers |
| `harness --shot f.png --after 5` | run, then save the window picture (works without a display) |

What the harness found that the unit tests had not (it is the loop shape and the load that matter): with the old "12 tile runs per tick" limit the screens always had tiles waiting and a unit switch could need 12.8 ms of bus time in a 10 ms tick. The scheduler now has a byte budget (`aux_display_poll_budget`, 8000 bytes per tick): steady driving keeps up (on average 1 tile waiting, 95th percentile 8), no tick exceeds 9.9 ms of bus time at 9.6 MHz, and a unit switch (about 3000 tiles) settles in 380 ms.

The Android side of the feed: the app sends its vehicle state as one UDP line every 50 ms (`../android/cluster-app`, `Telemetry`), by default to `10.0.2.2:5005` (the PC); `run_harness.ps1` redirects it to WSL's address with the `telemetry` broadcast extra. In the car the data flows the other way (the gauges board is the source).

**Modern theme cost.** Redrawing big digits and arc ends on every wobble of the data took 35 % of the bus, so the modern dial follows the arc in whole degrees and refreshes the numbers at most every 80 ms (`AUX_TEXT_HOLD_TICKS`; a big jump, a warning or a change of validity goes through at once): 14 % on average, 50 % peak over a simulated drive.

**Verification.** The property test replays 720 random updates (all four layouts, both unit systems, valid and invalid inputs) and requires the patched panel to equal a full redraw and equal a render straight from the model; twelve deliberate breakages of the tile marking and the rasteriser are each caught. The mock panel enforces the GC9A01 protocol: chip select framing, the FEh/EFh unlock before level-3 registers, COLMOD before pixel writes, 5 ms after Sleep Out, no display-on too early, no pixels outside the window. `tools/check_vendor_block.py` re-derives the register tables from the open-source reference and compares them byte for byte; `tools/check_pins.py` checks the HAL's pins against `gauges_pins.h`.

**Not verified, and why (needs hardware or Raystar):**
- The init sequence. Documented commands come from the GC9A01 datasheet; the block of undocumented registers (84h-8Fh, 90h, ..., 98h) and the default power, gamma and frame-rate values are from Zephyr's driver (`display_gc9x01x.c`, Apache-2.0), which says they come from manufacturer sample code. **Raystar's RFA401280B-AYW-DNF1 may need other values: ask Raystar for their init code** (`../../docs/rfq-drafts.md`, section 5).
- Orientation (`GC9A01_MADCTL`), RGB/BGR order and display inversion (`GC9A01_INVERT`) for this module.
- The LPSPI limit and the HAL (clock source, FIFO use, byte swap, frame sizes) on a real part.
- Boot: about 0.3 s of waits plus the first draw before the screens turn on; the 150 ms after Sleep Out is the open-source driver's margin (the datasheet requires only 5 ms).

## Not decided yet
- 80 MHz RUN is configured; 112 MHz HSRUN is not needed yet.
- Final watchdog policy (it is disabled at boot with UPDATE=1 so it can be reconfigured; decide with the STOP-mode work).
- Sender curves (measure the real fuel / oil / coolant senders).
- Debounce and polarity policy per lamp channel (`InputConfig.LampInvertMask`).
