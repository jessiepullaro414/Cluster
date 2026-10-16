# Software plan (2026-10-14)

Scope: the firmware for `gauges/` (NXP S32K144), the Android Automotive side for `display/` (Verdin iMX95), and the test rig that ties them to the generated protocol. Status of every piece today: stubs (see `README.md`). Hardware is not built, so everything below is ordered so that the most work can be proven on the host before a board exists.

## 1. Build environment (what already exists)

Found on this machine, 2026-10-14:

| What | Where | Used for |
|---|---|---|
| WSL2 Ubuntu 22.04, native, **no Docker** (`docker` is not installed in that distro) | `~/imx-automotive` (NXP `automotive-16.0.0_1.3.0` tree) | the AAOS build for the i.MX 95; set up 2026-08-17/18 |
| `arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi` | `/opt/...` (exported as `AARCH32_GCC_CROSS_COMPILE`) | the AAOS tree's Cortex-M33 System Manager; **also builds our S32K144 code** (verified: `make arm-check` compiles every firmware file for `-mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard`, 1.1 KB total text) |
| `gcc-arm-none-eabi-9-2020-q2-update` | `/opt/...` (`ARMGCC_DIR`) | the older toolchain NXP's Dockerfile pins for the SM; not needed for us |
| `arm-gnu-toolchain-12.3.rel1-...-aarch64-none-linux-gnu` | `/opt/...` | AAOS kernel/bootloader |
| host gcc 11.4 | WSL | firmware host tests |

NXP's own `device/nxp/common/dockerbuild/Dockerfile` in that tree is the authoritative list of pinned toolchains; the "container" was applied natively from it rather than run as Docker. If a separate Docker image exists on another machine, none is visible here.

What is **missing for the S32K144** (it is a different NXP family from the i.MX 95): device header and startup code, a linker script, and a debug probe. NXP's S32 SDK / S32 Design Studio supply the first two but need an NXP login to download; the plan below writes the register layer ourselves from the Reference Manual, the way `../ecu-firmware` already does for the MPC5606B.

Rules: AAOS source and builds stay on the distro's ext4 (never `/mnt/c`); the small firmware tree can build from `/mnt/c` (it does today).

## 2. Tracks, in order

### A. gauges-fw (S32K144)

| # | Step | Proves | Needs | Est. (my time) |
|---|---|---|---|---|
| A0 | skeleton, pins header, `aggregate.c` + host tests | source-priority logic | nothing | **done** |
| A1 | cross-compile check | M4F builds with the installed toolchain | nothing | **done** |
| A2 | startup + vector table + linker script + clock tree + 10 ms tick, `make arm` producing an ELF | boots to `main` | S32K144 RM memory map and SCG chapter (verify addresses, do not guess) | **done to the image** (links; reset path inspected; boots on hardware is unproven) |
| A3 | protocol codec: `../protocol/cluster_codec.h` (generated: struct + pack/unpack per private message with counter and CRC-8, Haltech V2 decode) and a generated C test whose expected bytes come from cantools (independent of the C code; mutation-checked) | wire format | nothing (host tests) | **done** |
| A4 | input math (`inputmath.c`): pulse period to speed and RPM, lamp debounce, dimmer scaling, table lookup; host-tested (sender curves still need real data) | conversions | nothing (host tests) | **done** |
| A5 | FlexCAN driver (CAN0 listen-only, CAN1) | frames on a bus | board + CAN adapter | 4 h + bench |
| A6 | FTM capture, ADC, GPIO, ignition wake | real inputs | board | 4 h + bench |
| A7 | GC9A01 driver and needle gauges on LPSPI2 | the four small gauges | board + screens | 4 h + bench |
| A8 | STOP mode and wake, `PowerState` handshake with display/ | sleep current, wake time | board + meter | 3 h + bench |
| A9 | sender curves from the real senders | gauge accuracy | the user's senders | measurement |

A2 was done from the Reference Manual (SRAM ECC zero-fill before any read, watchdog off, SCG crystal to 80 MHz, vector table generated from NXP's interrupt workbook). A5 onward need hardware.

### B. Android Automotive (display/)

| # | Step | Proves | Needs |
|---|---|---|---|
| B0 | layout and property map (`android/`) | the plan | **done** |
| B1 | cluster app on an AAOS emulator with a fake property source; round layout, 720 px safe circle, dimmer and night mode | the UI | **done** (`android/cluster-app`, AVD `cluster_round`; screenshots in `android/emulator/shots`) |
| B2 | VHAL bridge as a standalone C++ library: decode SocketCAN frames from `cluster_private.dbc`, host unit tests with the protocol test vectors | decoding and staleness | **done** (`android/vhal-bridge`; the SocketCAN reader is part of B3) |
| B3 | wire the bridge into the AAOS vehicle HAL in `~/imx-automotive` and build | a real build | WSL tree, hours of build time |
| B4 | rotary service (dial ADC and click to key/rotary events) | the dial | Verdin + display board |
| B5 | CarPlay / Android Auto viewport inside the circle | the phone projection | licensing decisions (below) |
| B6 | suspend-to-RAM and wake on ignition | wake time | Verdin module, System Manager port |

### C. Test rig and tooling
1. `tools/can_replay.py` (**done**, `--selftest` passes): replays a scripted drive as Haltech V2 car-bus frames (`--role car`, bench ECU for gauges/ CAN0) or as private-link frames with rolling counter and CRC-8 (`--role gauges`, feeds the Android VHAL bridge with no gauges/ board). Encoded from the DBCs by cantools. Sending needs a CAN adapter; `--dry-run` and the in-process self-test do not.
2. Generate more of the protocol side: C decode helpers (A3) and a C++/Kotlin decode table from the same Python table, so firmware, bridge and DBC cannot drift.
3. `software/check.sh` (**done**): host firmware tests, `make arm-check`, `make arm` and the image inspection, in WSL. The protocol checks need cantools, which WSL's python3 lacks (and it has no pip), so the script prints a SKIPPED line there; run `python protocol/test_protocol.py` from Windows.

## 3. Decisions
Made by the user, 2026-10-14:
1. **Own register layer**, written from the S32K144 Reference Manual (no NXP SDK, no login). Every address and bit is checked against the RM's register diagrams, as in `ecu-firmware`.
2. **Debug probe: SEGGER J-Link.** Before buying, confirm in SEGGER's supported-device list that it covers the S32K144, and match the cable to `gauges/` J2, a Tag-Connect TC2030 footprint (our symbol has SWDIO on pin 1 and SWCLK on pin 3: check that against the Tag-Connect pinout and the J-Link's 10-pin Cortex layout, which is not the same connector).
3. **Android platform: the user will buy one NXP 19x19 EVK; until it arrives the emulator is the platform.** B1 and B2 therefore target the emulator and host tests first.

Made by the user, 2026-10-15:
4. **The centre display stays CarPlay / Android Auto maps.** Speed, rpm and the fluids move to the four small screens (default left to right: fuel + volts, **speed**, rpm, coolant + oil; `gauges-fw/inc/screens.h`, host-tested). This also keeps speed visible with Android off or asleep. With no phone connected the centre shows what the user chose, the gauge or home (`CenterLogic`, a saved setting); the dial click flips maps and gauge. The turn and warning lamps sit in the caps above and below the map window. Open: whether CarPlay accepts a square or 4:3 surface on a 720 x 720 display (unverified; the window shape is a setting, 4:3 by default, 16:9 is the safe fallback), and what "home" is on the production image.

Still open, with a recommendation:
5. **Bare-metal cooperative loop vs RTOS.** Recommend bare-metal: one 10 ms tick, interrupts only for CAN, capture and wake.
6. **CarPlay / Android Auto licensing**: Apple's CarPlay program and Google's Android Auto receiver for AAOS both involve licences; which route and when is a business decision. Nothing in B1 to B4 depends on it.

## 4. Verification discipline (same as the hardware)
Every register address and bit comes from the Reference Manual, not memory; stubs say so. Host tests for every pure function; `make arm-check` must stay clean with `-Werror`; any message layout comes from the generated header, never retyped. Measure, then claim.

## 5. First actions
1. A2: read the S32K144 Reference Manual's memory map, SCG and FlexCAN chapters (needs the RM; the sibling `manifold-pcb` / `thermo-pcb` notes show where it was fetched before), then write startup, linker script, clocks and the 10 ms tick.
2. B1: the cluster app on the emulator with a fake property source.
3. C1: `can_replay.py` once a CAN adapter is chosen.

## 6. Android emulator (installed 2026-10-15)
- Android Studio 2026.2.1.8 (winget `Google.AndroidStudio`), SDK in `%LOCALAPPDATA%\Android\Sdk` with command-line tools, emulator 37.2.12, platform-tools and `platforms;android-35`.
- Image `system-images;android-35-ext15;android-automotive;x86_64` (Android 15, Google APIs, no Play Store). **Not Android 16**: Google publishes no automotive image newer than API 35 in the stable channel, while the NXP tree is `automotive-16.0.0`, so API behaviour can differ; the real target stays the EVK.
- AVD `aaos_cluster` (device `automotive_1024p_landscape`). Verified headless boot: `sys.boot_completed`, release 15, characteristics `automotive`, `car_service` and the `IVehicle` HAL present. `cmd car_service inject-vhal-event` exists, which is the planned way to feed B1 fake properties.
- Start: `emulator -avd aaos_cluster -no-window -no-audio -gpu swiftshader_indirect` (drop `-no-window` to see it). `sdkmanager` is a deprecated shim for Google's new Android CLI and splits package ids at `;`: quote them as `'"platforms;android-35"'` in PowerShell.
- A round 720x720 cluster is not a stock device definition; B1 will need a secondary/distant display or a custom hardware profile.
