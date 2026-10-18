#!/usr/bin/env bash
# End-to-end bench test of clusterd on a PC (WSL is fine), with no CAN, no dial hardware and no LIVI:
# fake_livi.py stands in for LIVI, and a scripted key stream stands in for the dial.
#
#   bash software/linux/aa-bench/bench_clusterd.sh
#
# Checks: the first page, telemetry pushes, maps when a phone arrives, the dial going to the phone as
# knob keys, a 1.6 s hold bringing our speedometer up over the phone (the page server answers /state), a turn
# back to the map, and the gauge on the phone leaving.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here/../clusterd"
make -s build/clusterd
work="$(mktemp -d)"
trap 'kill $(jobs -p) 2>/dev/null || true; rm -rf "$work"' EXIT

python3 "$here/fake_livi.py" --port 4100 --status "$work/status.json" --phone-script "1.5:cp,6.5:none" --log "$work/livi.jsonl" > "$work/fake.out" 2>&1 &
sleep 0.5
# its own ports, so a real LIVI (4000) and clusterd (4010) may keep running beside the bench
printf 'theme = 0\nlivi_port = 4100\npage_port = 4110\n' > "$work/clusterd.conf"
# dial script: t=2.5 turn right (to the phone), click (select), 3.5 hold 1.6 s (Back, then our speedometer),
# 5.5 turn: back to the map; the phone leaves at 6.5 (the gauge again); 7.3 hold: Settings, on the gauge's
# own page; quit at 9
( sleep 2.5; printf d; sleep 0.3; printf c; sleep 0.7; printf m; sleep 2.2; printf d; sleep 1.8; printf h; sleep 1.5; printf q ) |
    ./build/clusterd --can none --dial-stdin --config "$work/clusterd.conf" --settings "$work/settings.conf" \
        --web "$PWD/web" --livi-status "$work/status.json" > "$work/clusterd.out" 2>&1 &
cd_pid=$!
sleep 5.2
state="$(curl -s http://127.0.0.1:4110/state || true)"
page="$(curl -s http://127.0.0.1:4110/ | head -c 200 || true)"
wait $cd_pid || true

echo "--- clusterd"; cat "$work/clusterd.out"
echo "--- fake LIVI"; cat "$work/fake.out"
echo "--- /state at 5.2 s: $state"
fail=0
check() { if grep -q -- "$2" "$1"; then echo "ok    $3"; else echo "FAIL  $3"; fail=1; fi; }
check "$work/clusterd.out" "page /custom" "starts on our speedometer (no phone): the custom page"
check "$work/livi.jsonl" '"speedKph": null' "telemetry pushes reach LIVI (stale values as null)"
check "$work/clusterd.out" "page /$" "phone arrives: maps"
check "$work/clusterd.out" "key knobRight" "turn goes to the phone"
check "$work/clusterd.out" "key select" "click goes to the phone"
check "$work/clusterd.out" "key back" "0.6 s hold is Back"
# gauge and settings share the custom page, so opening Settings from the gauge changes no page
pages="$(grep -o 'page .*' "$work/clusterd.out" | paste -sd' ')"
[ "$pages" = "page /custom page / page /custom page / page /custom" ] && echo "ok    pages in order: gauge, maps (phone), our speedometer (1.6 s hold), maps (turn), gauge (phone gone)" || { echo "FAIL  page order: $pages"; fail=1; }
check "$work/livi.jsonl" '"path": "/custom"' "LIVI was told to open the custom page"
echo "$state" | grep -q '"view":"gauge"' && echo "ok    /state: our speedometer with the phone connected" || { echo "FAIL  /state"; fail=1; }
echo "$state" | grep -q '"veh":{"link":false' && echo "ok    /state carries the vehicle block (no CAN here: link down)" || { echo "FAIL  /state veh"; fail=1; }
echo "$page" | grep -qi "<!doctype html>" && echo "ok    centre page served" || { echo "FAIL  centre page"; fail=1; }
exit $fail
