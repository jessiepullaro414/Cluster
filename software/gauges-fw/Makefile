# Host build of the hardware-independent core. Run in WSL (gcc 11 available):
#   wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O2 -Iinc -I../../protocol

CORE := src/aggregate.c src/inputmath.c
STUBS := src/senders.c src/inputs.c src/can_link.c src/aux_display.c src/power.c

.PHONY: test stubs arm-check clean
test: build/test_aggregate build/test_codec build/test_inputmath
	./build/test_aggregate
	./build/test_codec
	./build/test_inputmath

build/test_inputmath: test/test_inputmath.c src/inputmath.c inc/inputmath.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_inputmath.c src/inputmath.c -lm

build/test_codec: test/test_codec.c ../../protocol/cluster_codec.h ../../protocol/cluster_can.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_codec.c -lm

build/test_aggregate: test/test_aggregate.c $(CORE) inc/aggregate.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ test/test_aggregate.c $(CORE)

# Compile-check the stubs and main on the host (no hardware access): catches
# header and signature mistakes before an ARM toolchain exists.
stubs:
	mkdir -p build
	for f in src/main.c $(CORE) $(STUBS); do 	  $(CC) $(CFLAGS) -DHOST_BUILD -c $$f -o build/$$(basename $$f .c).o || exit 1; done

# Cross-compile the core for the S32K144's Cortex-M4F with the toolchain already
# installed in WSL for the i.MX 95 AAOS build (see ../PLAN.md). Compile only: no
# startup code, linker script or device headers exist yet.
ARMCC ?= /opt/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-gcc
ARMFLAGS := -std=c11 -Wall -Wextra -Werror -Os -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -Iinc -I../../protocol
arm-check:
	mkdir -p build
	for f in $(CORE) $(STUBS) src/main.c; do 	  $(ARMCC) $(ARMFLAGS) -DHOST_BUILD -c $$f -o build/arm_$$(basename $$f .c).o || exit 1; done
	$(dir $(ARMCC))arm-none-eabi-size build/arm_*.o

clean:
	rm -rf build
