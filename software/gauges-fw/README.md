# gauges-fw (S32K144, stubs)

Target: NXP S32K144, 64-LQFP, on `../../gauges`. Pin numbers below come from the gauges schematic comments (which were read from NXP's S32K1xx IO table); `inc/gauges_pins.h` is the single place they live.

## Layout (follows `../../../ecu-firmware`: inc/, src/, test/)

| File | Job | State |
|---|---|---|
| `src/main.c` | init order and a 10 ms scheduler loop | stub |
| `src/aggregate.c` | source priority: Hall vs car-bus speed, tach vs car-bus RPM, car vs local fluids | **real, tested** |
| `src/senders.c` | resistive fuel / oil / coolant / battery ADC to engineering units | stub, needs measured sender curves |
| `src/inputs.c` | FTM1 capture for speed (CH4) and tach (CH5), six lamp GPIOs, dimmer ADC, ignition wake | stub |
| `src/can_link.c` | CAN0 (car bus, listen-only) and CAN1 (private link) with counter + CRC-8 from `cluster_can.h` | stub |
| `src/aux_display.c` | four GC9A01 gauges on LPSPI2 | stub |
| `src/power.c` | STOP mode, ignition wake, `PowerState` message | stub |
| `test/test_aggregate.c` | host unit tests for `aggregate.c` | real |

## Rules this firmware must keep
- CAN0 stays in **listen-only**: gauges/ never transmits on the car bus.
- Every private message carries a rolling counter and CRC-8 (SAE J1850, 0x1D, init 0xFF, xorout 0xFF) exactly as `cluster_can.h` defines.
- Each value carries a valid flag and a source; stale car-bus data (older than `CLUSTER_CAR_BUS_TIMEOUT_MS`) falls back to the local sender.
- Display liveness: no `DisplayHeartbeat` for `CLUSTER_DISPLAY_TIMEOUT_MS` sets `DisplayOffline`, but gauges/ keeps running.

## Toolchain
A real ARM build is not set up: the S32K144 needs NXP's S32 Design Studio / S32 SDK or `arm-none-eabi-gcc` plus the S32K1xx headers, and none is installed here. Until that decision is made, only the hardware-independent core builds, on the host with gcc.

## Not decided yet
- Toolchain and SDK (S32DS + S32 SDK vs bare CMSIS + `arm-none-eabi-gcc`).
- Clock tree (80 MHz run vs 112 MHz HSRUN).
- Sender curves (measure the real fuel / oil / coolant senders).
- Debounce and polarity policy per lamp channel (`InputConfig.LampInvertMask`).
