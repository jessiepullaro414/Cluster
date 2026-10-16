# Host build of the hardware-independent core. Run in WSL (gcc 11 available):
#   wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2 -Iinc -I../../protocol

# Real, host-testable code (no hardware access).
CORE := src/aggregate.c src/inputmath.c src/screens.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gc9a01.c src/aux_display.c
# Still stubs (need the board).
STUBS := src/senders.c src/inputs.c src/can_link.c src/power.c
# Real code that touches registers: compiled and linked for the target, never run on the host.
HW := src/panel_hal_s32k.c

# Sources of the screen chain for tests that use the mock panel.
SCREEN := test/panel_mock.c src/aux_display.c src/dial.c src/dial_modern.c src/dial_carplay.c src/dial_factory.c src/gfx.c src/font_data.c src/face.c src/face_data.c src/gc9a01.c src/screens.c

.PHONY: test stubs arm-check arm preview bench harness golden golden-update golden-dump sim clean
test: build/test_aggregate build/test_codec build/test_inputmath build/test_screens build/test_gfx build/test_dial build/test_gc9a01 build/harness_cli
	./build/test_aggregate
	./build/test_codec
	./build/test_inputmath
	./build/test_screens
	./build/test_gfx
	./build/test_dial
	./build/test_gc9a01
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

build/test_codec: test/test_codec.c ../../protocol/cluster_codec.h ../../protocol/cluster_can.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_codec.c -lm

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
	for f in $(CORE) $(STUBS) $(HW) src/main.c; do 	  $(ARMCC) $(ARMFLAGS) -DHOST_BUILD -c $$f -o build/arm_$$(basename $$f .c).o || exit 1; done
	$(dir $(ARMCC))arm-none-eabi-size build/arm_*.o

# Full firmware image: startup, generated vector table, flash configuration
# field, clocks, tick, the screen chain and the (mostly stub) application, linked with
# link/s32k144.ld. Verified by size and objdump only: nothing has run on a part yet.
BOOT := src/startup.c src/vectors.c src/fcf.c src/clock.c src/tick.c
ARMBIN := $(dir $(ARMCC))
ARMLINK := $(ARMFLAGS) -ffunction-sections -fdata-sections -nostartfiles --specs=nano.specs --specs=nosys.specs \
           -Wl,-T,link/s32k144.ld -Wl,--gc-sections -Wl,-Map,build/gauges-fw.map
arm: build/gauges-fw.elf
	$(ARMBIN)arm-none-eabi-size build/gauges-fw.elf

build/gauges-fw.elf: $(BOOT) $(CORE) $(STUBS) $(HW) src/main.c link/s32k144.ld $(wildcard inc/*.h)
	mkdir -p build
	$(ARMCC) $(ARMLINK) $(BOOT) $(CORE) $(STUBS) $(HW) src/main.c -lm -o $@

clean:
	rm -rf build
