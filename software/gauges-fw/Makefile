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
	for f in src/main.c $(CORE) $(STUBS); do 	  $(CC) $(CFLAGS) -DHOST_BUILD -c $$f -o build/$$(basename $$f .c).o || exit 1; done

clean:
	rm -rf build
