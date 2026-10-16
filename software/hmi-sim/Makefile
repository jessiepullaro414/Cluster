# Dial HMI simulator. Run in WSL (g++ available):  wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/hmi-sim test
FW := ../gauges-fw
CXX ?= g++
CC  ?= gcc
X11INC ?= $(HOME)/x11sdk/root/usr/include
CSRC := $(FW)/src/gfx.c $(FW)/src/font_data.c $(FW)/src/dial.c $(FW)/src/dial_modern.c $(FW)/src/dial_carplay.c $(FW)/src/aux_display.c \
        $(FW)/src/gc9a01.c $(FW)/src/screens.c $(FW)/test/panel_mock.c
COBJ := $(patsubst $(FW)/%.c,build/%.o,$(CSRC))
INC := -I$(FW)/inc -I$(FW)/test -I../../protocol -I.
CFLAGS := -std=c11 -Wall -Wextra -Werror -O2 -D_POSIX_C_SOURCE=200809L $(INC)
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -O2 $(INC)

.PHONY: test run clean
test: build/hmi_sim
	./build/hmi_sim --selftest

run: build/hmi_sim
	./build/hmi_sim

build/%.o: $(FW)/%.c
	mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

build/x11.o: $(FW)/test/harness_x11.c
	mkdir -p build
	$(CC) -std=c11 -Wall -Wextra -Werror -O2 -I$(X11INC) -I$(FW)/test -c $< -o $@

build/hmi_sim: hmi_sim.cpp hmi.h $(COBJ) build/x11.o
	mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ hmi_sim.cpp $(COBJ) build/x11.o -lm -l:libX11.so.6

clean:
	rm -rf build
