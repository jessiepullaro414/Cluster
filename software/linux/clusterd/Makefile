# clusterd: host tests and the Linux build. In WSL:
#   make -C /mnt/c/Users/root/Project/cluster-pcb/software/linux/clusterd test      # logic tests
#   make -C ... build/clusterd                                                       # the daemon, for this machine
#   make -C ... arm64                                                                # for the Verdin (needs aarch64-linux-gnu-g++)
# The CAN decoder is the Android option's vhal-bridge and the dial flows are hmi-sim's, compiled from
# where they live so both options share one copy.
CXX      ?= g++
ARMCXX   ?= aarch64-linux-gnu-g++
BRIDGE   := ../../android/vhal-bridge/src
HMI      := ../../hmi-sim
PROTO    := ../../../protocol
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O2
INC      := -Isrc -I$(BRIDGE) -I$(HMI) -I$(PROTO)
LOGIC    := src/dial_angle.cpp src/link_tx.cpp src/telemetry.cpp src/state_io.cpp $(BRIDGE)/bridge.cpp
HDRS     := $(wildcard src/*.h) $(BRIDGE)/bridge.h $(HMI)/hmi.h $(PROTO)/cluster_codec.h

.PHONY: test arm64 clean
test: build/test_clusterd
	./build/test_clusterd
	python3 -c "import json; d = json.load(open('build/telemetry_sample.json')); assert d['speedKph'] == 88.5 and d['turnSignal'] == 'right', d; print('telemetry sample is valid JSON')"

build/test_clusterd: test/test_clusterd.cpp $(LOGIC) $(HDRS)
	mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -o $@ test/test_clusterd.cpp $(LOGIC)

build/clusterd: src/main_linux.cpp $(LOGIC) $(HDRS)
	mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -o $@ src/main_linux.cpp $(LOGIC)

arm64: build/clusterd-arm64
build/clusterd-arm64: src/main_linux.cpp $(LOGIC) $(HDRS)
	mkdir -p build
	$(ARMCXX) $(CXXFLAGS) $(INC) -static-libstdc++ -o $@ src/main_linux.cpp $(LOGIC)

clean:
	rm -rf build
