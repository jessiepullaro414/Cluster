# vhal-bridge (policy library real and host-tested; AAOS glue not started)

Reads CAN1 frames from SocketCAN (`can0` on the Verdin), verifies the rolling counter and CRC-8 (`cluster_crc8` in `../../../protocol/cluster_can.h`: SAE J1850, poly 0x1D, init 0xFF, xorout 0xFF), and publishes vehicle properties. It never transmits anything except `DisplaySettings`, `SpeedCalibration`, `InputConfig` and `DisplayHeartbeat` to gauges/, and nothing on the car bus (gauges/ is the only node on it).

Property mapping, TO VERIFY against AOSP's `VehicleProperty.aidl` for the release in use (names are from memory):

| Message / signal | Vehicle property (candidate) | Notes |
|---|---|---|
| `VehicleMotion.SpeedKph` | `PERF_VEHICLE_SPEED` (m/s) | convert km/h to m/s; honour `SpeedValid` |
| `VehicleMotion.Rpm` | `ENGINE_RPM` | honour `RpmValid` |
| `VehicleMotion.BatteryV` | vendor property | no standard 12 V battery voltage property |
| `VehicleFluids.FuelPct` | `FUEL_LEVEL` (needs capacity) or a percentage property | `DisplaySettings.TankCapacityL` |
| `VehicleFluids.CoolantC` | `ENGINE_COOLANT_TEMP` | |
| `VehicleFluids.OilKpa` | vendor property | standard oil property is level, not pressure |
| `Indicators.TurnLeft/TurnRight` | `TURN_SIGNAL_STATE` | |
| `Indicators.HighBeam` | `HIGH_BEAM_LIGHTS_STATE` | |
| `Indicators.BrakeWarning` | `PARKING_BRAKE_ON` (or a vendor warning) | |
| `Indicators.AlternatorWarning`, `OilWarning` | vendor warning properties | |
| `Indicators.DashLightsOn`, `DashDimmerPct` | `NIGHT_MODE` and the display brightness | |
| `PowerState.IgnitionOn`, `SuspendRequest` | `IGNITION_STATE`, power policy | suspend-to-RAM request |

Stale data: if a message is older than its `CAN_PERIOD_MS_*` times a few, mark the property unavailable (`STATUS_UNAVAILABLE`) rather than holding the last value.

## What exists (2026-10-14)

`src/bridge.{h,cpp}`: pure C++17 library, no Android dependency. `Bridge::on_frame(id, data, len, now_ms)` decodes with the generated `protocol/cluster_codec.h` and adds policy: bad CRC, wrong length or unknown id never change state; an unchanged rolling counter does not refresh freshness (a frozen sender ages out); a property is available only while its message is younger than 3 x the protocol period AND the sender's valid flag is set; speed is converted to m/s. `Bridge::get(Prop, now_ms)` returns value + availability for the property map above. `make test` (WSL) runs `test/test_bridge.cpp`: two golden frames encoded by cantools (independent of every C/C++ encoder here), staleness, the 32-bit clock wrap, CRC, counter wrap and gap counting. Mutation-checked: removing the repeated-counter rule or widening the stale window fails tests.

Still to do (PLAN.md B3): the SocketCAN reader and the AIDL vehicle HAL glue that calls `get()` and publishes `STATUS_UNAVAILABLE` for `available == false`, built inside `~/imx-automotive`; the property names in the table above are still TO VERIFY against that tree's `VehicleProperty.aidl`. That tree no longer exists: it was deleted on 2026-10-18 to free disk space (about 311 GB; no local changes in it), so B3 starts by downloading NXP's `automotive-16.0.0_1.3.0` again and a full build.
