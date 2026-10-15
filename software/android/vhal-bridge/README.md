# vhal-bridge (plan)

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
