# Host build of the bridge policy and its tests. In WSL:
#   make -C /mnt/c/Users/root/Project/cluster-pcb/software/android/vhal-bridge test
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O2 -Isrc -I../../../protocol

.PHONY: test clean
test: build/test_bridge
	./build/test_bridge

build/test_bridge: test/test_bridge.cpp src/bridge.cpp src/bridge.h ../../../protocol/cluster_codec.h
	mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ test/test_bridge.cpp src/bridge.cpp

clean:
	rm -rf build
