# Host build of the hardware-independent core. Run in WSL (gcc 11 available):
#   wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2 -Iinc -I../../protocol

# Real, host-testable code (no hardware access).
CORE := src/aggregate.c src/inputmath.c src/screens.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gc9a01.c src/aux_display.c src/crc.c src/fault.c src/status.c src/odometer.c src/nvlog.c src/settings_store.c src/capture.c src/inputs.c src/senders.c src/sender_curves.c src/can_bittiming.c src/canmb.c src/can_link.c src/bootcore.c src/boot_request.c src/power.c
# Still stubs (need the board): none since the key-off sleep was written (2026-10-18).
STUBS :=
# Real code that touches registers: compiled and linked for the target, never run on the host.
HW := src/power_hw_s32k.c src/panel_hal_s32k.c src/wdog_s32k.c src/nvflash_s32k.c src/inputs_hw_s32k.c src/adc_s32k.c src/flexcan_s32k.c

# Sources of the screen chain for tests that use the mock panel.
SCREEN := test/panel_mock.c src/aux_display.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/gc9a01.c src/screens.c

.PHONY: test stubs arm-check arm preview bench harness golden golden-update golden-dump sim clean
test: build/test_aggregate build/test_codec build/test_inputmath build/test_screens build/test_gfx build/test_dial build/test_gc9a01 build/test_fault build/test_odometer build/test_odometer16 build/test_inputs build/test_settings build/test_can build/test_can_link build/test_boot build/test_power build/boot_replay build/harness_cli
	./build/test_aggregate
	./build/test_codec
	./build/test_inputmath
	./build/test_screens
	./build/test_gfx
	./build/test_dial
	./build/test_gc9a01
	./build/test_fault
	./build/test_odometer
	./build/test_odometer16
	./build/test_inputs
	./build/test_settings
	./build/test_can
	./build/test_can_link
	./build/test_boot
	./build/test_power
	python3 tools/test_can_flash.py
	python3 tools/make_sender_curves.py --selftest
	./build/harness_cli --selftest
	./build/harness_cli --golden check test/golden_screens.txt

build/test_inputmath: test/test_inputmath.c src/inputmath.c inc/inputmath.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_inputmath.c src/inputmath.c -lm

build/test_screens: test/test_screens.c src/screens.c inc/screens.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_screens.c src/screens.c -lm

build/test_gfx: test/test_gfx.c src/gfx.c src/font_data.c src/face.c src/face_data.c inc/gfx.h inc/font.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_gfx.c src/gfx.c src/font_data.c src/face.c src/face_data.c -lm

build/test_dial: test/test_dial.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/screens.c inc/dial.h inc/gfx.h src/dial_internal.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_dial.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/screens.c -lm

build/test_gc9a01: test/test_gc9a01.c $(SCREEN) test/panel_mock.h inc/gc9a01.h inc/panel_hal.h inc/aux_display.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ test/test_gc9a01.c $(SCREEN) -lm

build/test_fault: test/test_fault.c src/crc.c src/fault.c src/status.c inc/fault.h inc/status.h inc/crc.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_fault.c src/crc.c src/fault.c src/status.c

INPSRC := test/test_inputs.c src/capture.c src/inputs.c src/senders.c src/sender_curves.c src/inputmath.c
build/test_inputs: $(INPSRC) inc/capture.h inc/inputs.h inc/inputs_hw.h inc/senders.h inc/adc.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ $(INPSRC) -lm

build/test_settings: test/test_settings.c test/nv_mock.c src/settings_store.c src/nvlog.c src/crc.c inc/settings_store.h inc/nvlog.h test/nv_mock.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ test/test_settings.c test/nv_mock.c src/settings_store.c src/nvlog.c src/crc.c -lm

build/test_can: test/test_can.c src/can_bittiming.c src/canmb.c inc/can_bittiming.h inc/canmb.h inc/can_hw.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_can.c src/can_bittiming.c src/canmb.c

build/test_can_link: test/test_can_link.c src/can_link.c src/aggregate.c inc/can_link.h inc/can_hw.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_can_link.c src/can_link.c src/aggregate.c -lm

build/test_boot: test/test_boot.c test/pflash_mock.c src/bootcore.c src/boot_request.c src/crc.c inc/bootcore.h inc/pflash.h inc/boot_request.h test/pflash_mock.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ test/test_boot.c test/pflash_mock.c src/bootcore.c src/boot_request.c src/crc.c

build/boot_replay: test/boot_replay.c test/pflash_mock.c src/bootcore.c src/crc.c inc/bootcore.h test/pflash_mock.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ test/boot_replay.c test/pflash_mock.c src/bootcore.c src/crc.c

ODOSRC := test/test_odometer.c test/nv_mock.c src/odometer.c src/nvlog.c src/crc.c
# The odometer is tested with a 4-sector log (the ring wraps often, so power can be cut at every event of a drive that wraps it
# twice) and with the real 16-sector log (long drive, wear count).
build/test_odometer: $(ODOSRC) test/nv_mock.h inc/odometer.h inc/nvlog.h inc/nvflash.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -DODO_SECTORS=4u -o $@ $(ODOSRC)

build/test_odometer16: $(ODOSRC) test/nv_mock.h inc/odometer.h inc/nvlog.h inc/nvflash.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ $(ODOSRC)

build/test_codec: test/test_codec.c ../../protocol/cluster_codec.h ../../protocol/cluster_can.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_codec.c -lm

build/test_power: test/test_power.c src/power.c inc/power.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_power.c src/power.c

build/test_aggregate: test/test_aggregate.c src/aggregate.c inc/aggregate.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_aggregate.c src/aggregate.c

# Render the four screens through the real driver into the mock panel and write
# build/screen_<n>.ppm; tools/montage.py joins them into a PNG.
#   make preview PRESET=1 UNITS=metric
PRESET ?= 0
UNITS ?= imperial
preview: build/preview
	./build/preview $(PRESET) $(UNITS)

build/preview: test/preview.c $(SCREEN) inc/aux_display.h
	mkdir -p build
	$(CC) $(CFLAGS) -Itest -o $@ test/preview.c $(SCREEN) -lm

# ---- test harness: the real screen code on a mock panel, with a window ----
# build/harness_cli has no window and needs no display (golden images, simulation, self test).
# build/harness adds an X11 window; on Windows 11 the WSLg X server shows it on the desktop. The X11
# development headers are not installed in WSL (no root), so they are unpacked privately by
# tools/get_x11_headers.sh into ~/x11sdk; the library itself is the system's libX11.so.6.
HARNESS_SRC := test/harness.c test/panel_mock.c src/aux_display.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/gc9a01.c src/screens.c
X11INC ?= $(HOME)/x11sdk/root/usr/include
HARNESS_DEPS := $(HARNESS_SRC) test/harness_x11.h inc/aux_display.h inc/dial.h inc/gfx.h

build/harness_cli: $(HARNESS_DEPS)
	mkdir -p build
	$(CC) $(CFLAGS) -D_POSIX_C_SOURCE=200809L -Itest -o $@ $(HARNESS_SRC) -lm

build/harness: $(HARNESS_DEPS) test/harness_x11.c
	mkdir -p build
	$(CC) -std=c11 -Wall -Wextra -Werror -O2 -Iinc -I../../protocol -DHARNESS_X11 -I$(X11INC) -Itest -o $@ $(HARNESS_SRC) test/harness_x11.c -lm -l:libX11.so.6

# Fixed states against stored checksums (test/golden_screens.txt). A styling change shows up as
# CHANGED lines; look at the pictures (make golden-dump), then accept with make golden-update.
golden: build/harness_cli
	./build/harness_cli --golden check test/golden_screens.txt

golden-update: build/harness_cli
	./build/harness_cli --golden update test/golden_screens.txt

golden-dump: build/harness_cli
	mkdir -p build/golden
	./build/harness_cli --golden check test/golden_screens.txt --dump build/golden || true

# 60 virtual seconds of driving: bus load, backlog, tick overruns, panel == model.
sim: build/harness_cli
	./build/harness_cli --sim 60 --units-switch
	./build/harness_cli --sim 60 --units-switch --theme modern
	./build/harness_cli --sim 60 --units-switch --theme carplay
	./build/harness_cli --sim 60 --units-switch --theme factory
	./build/harness_cli --sim 60 --units-switch --theme modern --center
	./build/harness_cli --sim 60 --units-switch --theme factory --center

# Counts the rendering work of typical updates (operations, not time).
bench: build/bench_render
	./build/bench_render

build/bench_render: test/bench_render.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/screens.c inc/dial.h inc/gfx.h
	mkdir -p build
	$(CC) $(CFLAGS) -DGFX_STATS -o $@ test/bench_render.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/screens.c -lm

# Compile-check the stubs and main on the host (no hardware access): catches
# header and signature mistakes before an ARM toolchain exists.
stubs:
	mkdir -p build
	for f in src/main.c $(CORE) $(STUBS); do 	  $(CC) $(CFLAGS) -DHOST_BUILD -c $$f -o build/$$(basename $$f .c).o || exit 1; done

# Cross-compile for the S32K144's Cortex-M4F with the toolchain already installed in
# WSL for the i.MX 95 AAOS build (see ../PLAN.md).
ARMCC ?= /opt/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-gcc
ARMFLAGS := -std=c11 -Wall -Wextra -Werror -Os -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -Iinc -I../../protocol
arm-check:
	mkdir -p build
	for f in $(CORE) $(STUBS) $(HW) $(IMGEXTRA) src/main.c; do 	  $(ARMCC) $(ARMFLAGS) -DHOST_BUILD -c $$f -o build/arm_$$(basename $$f .c).o || exit 1; done
	$(dir $(ARMCC))arm-none-eabi-size build/arm_*.o

# Full firmware image: startup, generated vector table, flash configuration
# field, clocks, tick, the screen chain and the (mostly stub) application, linked with
# link/s32k144.ld. Verified by size and objdump only: nothing has run on a part yet.
BOOT := src/startup.c src/vectors.c src/fcf.c src/clock.c src/tick.c
IMGEXTRA := src/app_header.c src/pflash_s32k.c boot/boot_main.c
ARMBIN := $(dir $(ARMCC))
ARMLINK := $(ARMFLAGS) -ffunction-sections -fdata-sections -nostartfiles --specs=nano.specs --specs=nosys.specs \
           -Wl,-T,link/s32k144.ld -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map,build/gauges-fw.map
arm: build/gauges-fw.elf
	$(ARMBIN)arm-none-eabi-size build/gauges-fw.elf

build/gauges-fw.elf: $(BOOT) $(CORE) $(STUBS) $(HW) src/main.c link/s32k144.ld $(wildcard inc/*.h)
	mkdir -p build
	$(ARMCC) $(ARMLINK) $(BOOT) $(CORE) $(STUBS) $(HW) src/main.c -lm -o $@

# ---- the bootloader, and the application linked behind it -------------------------------------------------------------------------------
# build/boot.elf is the first 32 KB of program flash; build/app.elf is linked at 0x8000 with the 32-byte image header; mkimage.py turns
# app.elf into the file that tools/can_flash.py sends. `make image` leaves build/gauges-app.bin (the update file) and build/gauges-flash.bin
# (bootloader + application in one piece, for a programmer). Verified by size and objdump only: nothing has run on a part.
BOOTSRC := boot/boot_main.c src/startup.c src/vectors.c src/fcf.c src/clock.c src/tick.c src/bootcore.c src/crc.c src/canmb.c src/can_bittiming.c src/flexcan_s32k.c src/pflash_s32k.c src/boot_request.c
BOOTLINK := $(ARMFLAGS) -DBOOT_BUILD -ffunction-sections -fdata-sections -nostartfiles --specs=nano.specs --specs=nosys.specs \
            -Wl,-T,link/s32k144_boot.ld -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map,build/boot.map
APPSRC := src/startup.c src/vectors.c src/clock.c src/tick.c $(CORE) $(STUBS) $(HW) src/main.c src/app_header.c
APPLINK := $(ARMFLAGS) -DAPP_BUILD -ffunction-sections -fdata-sections -nostartfiles --specs=nano.specs --specs=nosys.specs \
           -Wl,-T,link/s32k144_app.ld -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map,build/app.map

.PHONY: boot app image
boot: build/boot.elf
	$(ARMBIN)arm-none-eabi-size build/boot.elf
build/boot.elf: $(BOOTSRC) link/s32k144_boot.ld $(wildcard inc/*.h) $(wildcard boot/*.c)
	mkdir -p build
	$(ARMCC) $(BOOTLINK) $(BOOTSRC) -lm -o $@
app: build/app.elf
	$(ARMBIN)arm-none-eabi-size build/app.elf
build/app.elf: $(APPSRC) link/s32k144_app.ld $(wildcard inc/*.h)
	mkdir -p build
	$(ARMCC) $(APPLINK) $(APPSRC) -lm -o $@
image: build/gauges-app.bin
build/gauges-app.bin: build/app.elf build/boot.elf tools/mkimage.py
	$(ARMBIN)arm-none-eabi-objcopy -O binary build/app.elf build/app.raw.bin
	$(ARMBIN)arm-none-eabi-objcopy -O binary build/boot.elf build/boot.raw.bin
	python3 tools/mkimage.py build/app.raw.bin build/gauges-app.bin --boot build/boot.raw.bin --flash build/gauges-flash.bin

clean:
	rm -rf build
