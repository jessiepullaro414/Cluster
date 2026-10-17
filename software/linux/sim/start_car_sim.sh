#!/usr/bin/env bash
# Start the whole bench and the car panel: LIVI (the round centre screen, patched, see ../aa-bench/README.md), the
# four small gauges (gauges-fw's harness), clusterd fed by simulated GPIO and a simulated CAN bus, and car_sim.py.
# Runs as root in the Ubuntu-24.04 WSL distro; from Windows double-click start_car_sim.cmd.
# Close the panel to stop clusterd and the harness (LIVI keeps running, so a phone session survives).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
bench=/root/livi-bench
gpio=/tmp/carsim
mkdir -p "$gpio" /root/carsim
printf '0\n' > "$gpio/click"
printf '0\n' > "$gpio/adc"

if ! pgrep -x livi-core > /dev/null; then
    echo "starting LIVI"
    (cd "$bench/app/squashfs-root" && LIVI_AA_TCP_WITHOUT_BT=1 LIVI_AA_H264_ONLY=1 LIVI_PORT=5278 \
        setsid ./livi --no-sandbox > /root/carsim/livi.log 2>&1 &)
    for _ in $(seq 60); do grep -q "compositor display" /root/carsim/livi.log 2>/dev/null && break; sleep 1; done
fi

pkill -x clusterd-bin; pkill -x harness
sleep 0.5
(cd "$repo/software/gauges-fw" && exec ./build/harness --udp 5005 --scale 1.0 > /root/carsim/harness.log 2>&1) &
harness_pid=$!
"$bench/clusterd-bin" --can none --can-udp 5101 --sim-gpio "$gpio" --config "$here/clusterd-sim.conf" \
    --settings /root/carsim/settings.conf --web "$repo/software/linux/clusterd/web" \
    --livi-status /root/.config/LIVI/state/status.json --harness-udp 127.0.0.1:5005 > /root/carsim/clusterd.log 2>&1 &
clusterd_pid=$!
trap 'kill $clusterd_pid $harness_pid 2>/dev/null' EXIT

python3 "$here/car_sim.py" --gpio "$gpio" --can-port 5101
