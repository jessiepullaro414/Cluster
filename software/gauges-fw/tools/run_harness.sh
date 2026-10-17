#!/bin/bash
# Start the screen harness window (WSLg) listening for the Android feed. Called by run_harness.ps1; a script file, not
# an inline bash -c, because Start-Process does not keep the quoting of a long argument.
cd "$(dirname "$0")/.." || exit 1
pkill -x harness
DISPLAY=${DISPLAY:-:0} exec ./build/harness --udp "${1:-5005}" --record /tmp/android_feed.txt $HARNESS_EXTRA 2>/tmp/harness.log
