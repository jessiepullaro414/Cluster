# Linux option for the centre display (second option, beside Android Automotive)

Decided by the owner, 2026-10-17: **keep Android Automotive as it is, and build Linux + LIVI as a second
option**, ready to switch to if it proves better. Nothing in `../android/` was changed or removed; the two
options share the protocol, the CAN decoder and the dial flows.

**Why a Linux option at all.** The centre screen's main job is the phone's maps (PLAN.md decision 4). An
AOSP build of Android Automotive does not include an Android Auto or CarPlay receiver: car makers license
those (Google's Android Auto certification through its accredited labs, Apple's MFi/CarPlay programme) or
buy a middleware stack. The one open, maintained receiver found is **LIVI** (github.com/f-io/LIVI,
GPL-3.0-or-later, 9.5.0 on 2026-10-17), and it runs on Linux, not Android. Linux on the Verdin iMX95 is
also Toradex-supported, where Android Automotive on it is a port.

## Status

| Piece | What | State |
|---|---|---|
| `clusterd/` | the glue daemon: private CAN link to LIVI telemetry, settings and heartbeat to gauges/, dial to keys, suspend | **logic real and host-tested** (149 checks); Linux I/O builds; end-to-end bench passes against a stand-in LIVI (`aa-bench/bench_clusterd.sh`, 11 checks); not run on a Verdin |
| `clusterd/web/centre.html` | the centre screen LIVI shows as its custom page: **our speedometer** in the owner's theme (a port of the Android app's ClusterView, all four themes, day/night palette, lamps) and the Settings list | all four themes checked inside LIVI on replayed drive data (`aa-bench/shots/centre-*-in-livi.png`); draws clusterd's state only |
| `livi/livi-round-ui.patch` | LIVI setting `customHideNav`: the custom page fills the window with no navigation rail (for the round panel); upstreamable, off by default | built into the bench LIVI and checked (`aa-bench/shots/cluster-bench-livi-and-small-gauges.png`) |
| `livi/livi_config.py` | LIVI's config for the round panel: projection size, map-shape safe/view areas, dial keys, custom page, MFi bus | selftest passes; not yet loaded by a real LIVI |
| `aa-bench/` | relay from a phone's or emulator's "head unit server" into LIVI, stand-in LIVI, bench script | relay selftest passes; **not yet run against a real phone or emulator** (see its README) |
| `deploy/` | systemd unit, example config | written, untested |
| Platform image | Torizon OS or Toradex BSP with LIVI's arm64 build | not started (needs the Verdin + carrier) |

## How it fits together

```
 phone (CarPlay / Android Auto) ── Wi-Fi + Bluetooth (MAYA-W260) or USB-C J17 ──┐
                                                                                  v
   ┌─────────────────────── Verdin iMX95, Linux ───────────────────────────────────────────┐
   │  LIVI (Electron + Rust): projection "/", custom page "/custom" (our gauge + settings) │
   │      ^ POST :4000/telemetry  (speed, rpm, coolant, fuel, volts, lamps, night, page)   │
   │      | reads state/status.json (which phone is projecting)       ^ uinput keys        │
   │  clusterd ───────────────────────────────────────────────────────┘ (F13/F14/Enter/BS)│
   │      ^ SocketCAN (CAN_1)     ^ IIO ADC_1 (dial angle)   ^ evdev gpio-keys (click)     │
   └──────┼──────────────────────────────────────────────────────────────────────────────┘
          │ private link: 0x300-0x310 in, 0x400-0x4F0 out (protocol/cluster_private.dbc)
       gauges/ (S32K144): the four small screens, the car bus, the senders
```

- **LIVI owns the screen.** Its pages: `/` projection (or its home with no phone), and `/custom`, an iframe of
  clusterd's own page, which draws **our speedometer** (the same design as the Android app's ClusterView, in the
  owner's theme) or the Settings list. LIVI's own landscape dashboard is not used. clusterd changes page by pushing
  `{"path": ...}` in the telemetry stream, which LIVI opens once per change.
- **The dial goes to clusterd, never to a page.** clusterd runs hmi-sim's state machine (`../hmi-sim/hmi.h`,
  the flows the owner tries in the simulator) in `clusterd/src/shell.h`, with one addition: while a phone
  is projecting and the maps are in front, turns and clicks go to the phone as knob keys, a 0.6 s hold is
  the phone's Back, and holding on to 1.5 s opens our Settings. That is a **proposal to try**, like the rest
  of hmi.h.
- **Vehicle data reaches the phone too.** LIVI passes telemetry on to Android Auto and CarPlay (speed for
  navigation, lights and night mode for day/night maps). Stale values go out as null, never as old numbers.
- **gauges/ sees the same messages as with Android**: DisplaySettings (theme, units, brightness, centre shows
  speed), SpeedCalibration, InputConfig, TripCommand and the DisplayHeartbeat, every second and on change,
  each with its own rolling counter, packed by the generated `protocol/cluster_codec.h`.
- **Ignition off** follows the existing plan: gauges/ sets SuspendRequest with a countdown, clusterd marks the
  heartbeat "suspending" and runs `systemctl suspend` when the countdown ends; ignition back on first cancels.

Shared with the Android option, compiled from where it lives: `../android/vhal-bridge/src/bridge.cpp` (CAN
decode, freshness, CRC and counter policy) and `../hmi-sim/hmi.h` (settings rows and dial flows).

## Hardware: what display/ already has, and what Linux needs from it

No board change is needed for this option.

| Function | display/ | Linux side |
|---|---|---|
| Private CAN link | TCAN1044V-Q1 on Verdin CAN_1 | SocketCAN; the interface name is a device-tree fact (`can_if` in clusterd.conf), 500 kbit/s |
| Dial angle | Piher PSC-360 on J11, scaled to Verdin ADC_1 | IIO sysfs `in_voltageN_raw` (`--adc`); the valid band and detents per turn are settings |
| Dial click | GPIO_1 | a `gpio-keys` device-tree node, read as evdev (`--click`) |
| Ignition wake | CTRL_WAKE1_MICO# (X1 252) | `gpio-keys` with `wakeup-source`, so ignition on resumes from suspend-to-RAM |
| Audio | TAC5112-Q1 on I2S_1 + I2C_1 | an ALSA sound card in the device tree; whether a mainline or TI driver covers the TAC5112 is **not checked** |
| Wi-Fi / Bluetooth | MAYA-W260 on the WB module (simultaneous station + access point per the Verdin datasheet) | LIVI runs its own access point (hostapd) and BlueZ profiles for wireless CarPlay and Android Auto |
| USB-C host | J17 on USB_2 | wired Android Auto and wired CarPlay |
| Apple coprocessor | J16 (DNP): I2C_1 SDA/SCL, MFI_RST_N on GPIO_2, GND | LIVI probes I2C addresses **0x10 and 0x11** (its iap2-mfi crate), clear of the codec at 0x50. Its optional power line is a pin on `/dev/gpiochip0` only, so leave it at -1 and hold MFI_RST_N released with a device-tree `gpio-hog`. Set the bus with `livi_config.py --mfi-bus N` |

## Platform

- **Torizon OS 7.4.0 or newer** added the Verdin iMX95 machines (Toradex release notes); Torizon 7.1.0
  shipped GPU-accelerated Chromium for the iMX95. LIVI's arm64 AppImage is tested upstream on Debian Trixie,
  so a Debian Trixie container under Torizon is the natural home. **Not confirmed**: a GPU-enabled Weston
  container for the iMX95 (Toradex lists graphical containers only for some modules) and LIVI's GStreamer
  hardware decode on the iMX95's VPU (LIVI falls back to software decode).
- The plain Toradex BSP reference image (Yocto) is the fallback if the container route fights the GPU.
- Suspend-to-RAM on the iMX95 depends on the System Manager firmware either way (PLAN.md B6).

## Licensing and what is honest to say

- **LIVI is GPL-3.0-or-later and "not affiliated with or endorsed by Apple or Google"** (its README).
- **Android Auto in LIVI uses a head-unit certificate and private key issued by "Google Automotive Link"
  to JVC Kenwood** (`native/livi-helperd/crates/livi-aa/src/cert.rs`), the one open-source receivers such
  as OpenAuto/aasdk have used for years. It works because phones accept that certificate; it is not a
  licence. For one car that is the owner's call; for anything sold it is not acceptable, and Google's
  certification route (plan item B5) applies.
- **CarPlay needs a genuine Apple MFi authentication coprocessor** on J16. LIVI states it neither ships nor
  bypasses one. How a private builder obtains one is still the open question it was.

## Run the tests

```
wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/linux/clusterd test
wsl -d Ubuntu-22.04 -- bash /mnt/c/Users/root/Project/cluster-pcb/software/linux/aa-bench/bench_clusterd.sh
wsl -d Ubuntu-22.04 -- python3 /mnt/c/Users/root/Project/cluster-pcb/software/linux/livi/livi_config.py --selftest
wsl -d Ubuntu-22.04 -- python3 /mnt/c/Users/root/Project/cluster-pcb/software/linux/aa-bench/relay.py --selftest
```

From Git Bash, prefix `MSYS_NO_PATHCONV=1` and use `wsl -e`, or the `/mnt/c/...` paths get rewritten.

## Steps (L track, beside the B track in PLAN.md)

| # | Step | State |
|---|---|---|
| L0 | Architecture, LIVI integration points read from its source | done (this file) |
| L1 | clusterd logic + host tests; Linux I/O; bench against a stand-in LIVI | done |
| L2 | LIVI config for the round panel and the dial | script done; untested in LIVI |
| L3 | Real LIVI on a PC with Android Auto from an emulator or phone via `aa-bench/relay.py` | **done 2026-10-17**: Android Auto from an emulator projects in LIVI (round 720 px layout), clusterd's replayed drive shows on LIVI's dashboard, the dial opens our settings page; round-panel findings in `aa-bench/README.md` |
| L4 | LIVI on a Linux board with Wi-Fi + Bluetooth (wireless Android Auto end to end) | open: hardware |
| L5 | Torizon/Debian image for the Verdin: device tree (CAN, ADC, gpio-keys, wake, codec, MFi bus), LIVI, clusterd | open: Verdin + carrier |
| L6 | Suspend/resume measured, CarPlay with a real coprocessor | open |

## Not done here

- No Linux image or device tree yet (needs the module).
- `TripCommand` is sent but nothing in the Settings rows bumps it yet (the trip reset UX is undecided, as on Android).
- The "Map shape" row changes LIVI's config through `map_shape_cmd`; LIVI picks it up on restart or reconnect.
- Turn-by-turn data: LIVI exposes the phone's navigation maneuvers (`state/navigation.json`); showing them
  on a small gauge screen would need a new private-link message. Not started.
