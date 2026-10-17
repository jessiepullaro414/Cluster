# Cluster software (stubs, 2026-10-14)

Nothing here runs on a car yet. Every file is a stub unless it says otherwise.

| Dir | What | State |
|---|---|---|
| `gauges-fw/` | NXP S32K144 firmware for `gauges/`: inputs, sender conversion, source-priority aggregation, CAN gateway, four GC9A01 gauges, STOP-mode wake | skeleton; `aggregate.c` is real and unit-tested on the host, everything else is a stub |
| `android/` | Android Automotive side for `display/`: VHAL bridge (SocketCAN to vehicle properties), cluster app, rotary dial service | README-level plan and file layout, no code |
| `linux/` | **second option** for `display/` (2026-10-17): Linux + the open-source LIVI receiver for CarPlay / Android Auto, with `clusterd` gluing the private CAN link, the dial and LIVI together; the Android option stays | `clusterd` logic real and host-tested, bench-tested against a stand-in LIVI; see [linux/README.md](linux/README.md) |

The wire protocol is not duplicated here: `../protocol/can_protocol.py` generates `cluster_can.h`, the DBC files and the spec, and both sides use those.

The plan, build environment and decisions: [PLAN.md](PLAN.md).

Host build and test of the firmware core (needs gcc, available in WSL here):

```
wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
```
