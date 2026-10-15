#!/bin/sh
# One command for everything that can be proven without hardware.
# Run in WSL from anywhere:  sh /mnt/c/Users/root/Project/cluster-pcb/software/check.sh
# The protocol checks need cantools; WSL's python3 has none (and no pip), so
# they are SKIPPED there and must be run with a Python that has it
# (Windows: python protocol/test_protocol.py). The skip is printed, not silent.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
PY=${PYTHON:-python3}

if $PY -c "import cantools" 2>/dev/null; then
    echo "== protocol: DBC, spec and generated C are in sync with the tables"
    (cd "$ROOT/protocol" && $PY test_protocol.py)
    echo "== generated codec test is current"
    (cd "$ROOT/protocol" && $PY gen_codec_test.py >/dev/null && git diff --exit-code -- ../software/gauges-fw/test/test_codec.c)
else
    echo "== protocol checks SKIPPED: no cantools in $PY (run them with a Python that has it)"
fi

echo "== gauges-fw: host tests"
make -C "$HERE/gauges-fw" test

echo "== gauges-fw: Cortex-M4F compile of every file (-Werror)"
make -C "$HERE/gauges-fw" arm-check >/dev/null

echo "== gauges-fw: linked image"
make -C "$HERE/gauges-fw" arm
sh "$HERE/gauges-fw/tools/inspect_elf.sh" "$HERE/gauges-fw/build/gauges-fw.elf" | sed -n 1,12p

echo "all software checks that could run passed"
