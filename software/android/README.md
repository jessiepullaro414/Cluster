# Android Automotive side

Target: Verdin iMX95 on `../../display` running Android Automotive (AOSP, AAOS). On the production module this is a PORT (NXP's AAOS release supports the 19x19 EVK, see the plan); app-level work can start on the EVK or any AAOS emulator.

| Dir | What | State |
|---|---|---|
| `vhal-bridge/` | decoding policy (CRC, counter, freshness, units) as a host-tested C++ library; SocketCAN reader and AIDL HAL glue still to do | **policy real**, glue plan only |
| `cluster-app/` | full-screen round UI for the panel; runs on the `cluster_round` emulator from a fake data source (real source is B3) | **UI real, unit tested** |
| `emulator/` | `create_avd.ps1` (720 x 720 round AVD) and screenshots | real |
| `rotary-service/` | turns the dial (ADC + click) into Android key/rotary events for the UI and for CarPlay / Android Auto | plan only |

Display shape: the panel is round (4.0 in 720 x 720 today; 1080 x 1080 for 5 in, 720 x 720 for the Anders 4.2 in). CarPlay / Android Auto need a rectangular viewport inside the circle (about 88 x 50 mm at 4.0 in); the cluster app must clip and lay out for that.

The wire protocol is generated: `../../protocol/cluster_private.dbc` and `cluster_can.h`.
