# Cluster software (stubs, 2026-10-14)

Nothing here runs on a car yet. Every file is a stub unless it says otherwise.

| Dir | What | State |
|---|---|---|
| `gauges-fw/` | NXP S32K144 firmware for `gauges/`: inputs, sender conversion, source-priority aggregation, CAN gateway, four GC9A01 gauges, STOP-mode wake | skeleton; `aggregate.c` is real and unit-tested on the host, everything else is a stub |
| `android/` | Android Automotive side for `display/`: VHAL bridge (SocketCAN to vehicle properties), cluster app, rotary dial service | README-level plan and file layout, no code |

The wire protocol is not duplicated here: `../protocol/can_protocol.py` generates `cluster_can.h`, the DBC files and the spec, and both sides use those.

Host build and test of the firmware core (needs gcc, available in WSL here):

```
wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
```
