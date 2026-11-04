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
| `clusterd/` | the glue daemon: private CAN link to LIVI telemetry, settings and heartbeat to gauges/, dial to keys, suspend, parked power-off | **logic real and host-tested** (391 checks); Linux I/O builds for this PC (no ARM64 cross compiler here, so `make arm64` has not been run on this code); end-to-end benches pass against a stand-in LIVI (`aa-bench/bench_clusterd.sh`, 11 checks) and a played sleep (`aa-bench/bench_park.py`, 56 checks); not run on a Verdin |
| `clusterd/web/centre.html` | the centre screen LIVI shows as its custom page: **our speedometer** in the owner's theme (a port of the Android app's ClusterView, all four themes, day/night palette, lamps) and the Settings list | all four themes checked inside LIVI on replayed drive data (`aa-bench/shots/centre-*-in-livi.png`); draws clusterd's state only |
| `livi/livi-round-ui.patch` | LIVI setting `customHideNav`: the custom page fills the window with no navigation rail (for the round panel); upstreamable, off by default | built into the bench LIVI and checked (`aa-bench/shots/cluster-bench-livi-and-small-gauges.png`) |
| `livi/livi_config.py` | LIVI's config for the round panel: projection size, map-shape safe/view areas, dial keys, custom page, MFi bus | selftest passes; not yet loaded by a real LIVI |
| `aa-bench/` | relay from a phone's or emulator's "head unit server" into LIVI, stand-in LIVI, bench script | relay selftest passes; **not yet run against a real phone or emulator** (see its README) |
| `sim/` | **the car on a PC**: a control panel (dial via simulated GPIO, pedals, lamps, ignition via simulated CAN, phone button) that drives LIVI, clusterd and the small gauges; double-click `sim/start_car_sim.cmd` | works on the bench (2026-10-17) |
| `deploy/` | systemd unit, polkit rule, example config | written, untested |
| Platform image | Torizon OS or Toradex BSP with LIVI's arm64 build | not started (needs the Verdin + carrier) |

## How it fits together

```
 phone (CarPlay / Android Auto) ── Wi-Fi + Bluetooth (MAYA-W260) or USB-C J17 ──┐
                                                                                  v
   ┌─────────────────────── Verdin iMX95, Linux ───────────────────────────────────────────┐
   │  LIVI (Electron + Rust): projection "/", custom page "/custom" (our gauge + settings) │
   │      ^ POST :4000/telemetry  (speed, rpm, coolant, fuel, volts, lamps, night, page)   │
   │      | reads state/status.json (which phone is projecting)       ^ uinput keys        │
   │  clusterd ───────────────────────────────────────────────────────┘ (F13-F15/Enter/BS)│
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
- **Ignition off**: gauges/ sets SuspendRequest with a countdown, clusterd marks the heartbeat "suspending", arms the
  RTC alarm and runs `systemctl suspend` when the countdown ends; ignition back on first cancels. Ignition on later
  resumes the module through CTRL_WAKE1_MICO#. **A car left parked powers off**: see "The parked car" below.

Shared with the Android option, compiled from where it lives: `../android/vhal-bridge/src/bridge.cpp` (CAN
decode, freshness, CRC and counter policy) and `../hmi-sim/hmi.h` (settings rows and dial flows).

## The parked car

**Written and tested on a PC only. RTC wake, the real suspend, the power-off and what the board does then have never
run on a module**: L6 below lists what to check.

A suspended module still draws current (unmeasured; the module datasheet gives no figure). brain/'s ignition latch
(`docs/electrical-review.md` section 9, B-01) means the module holds the board on while it is running or suspended,
and once it powers off with the key off the board falls to about 2.5 uA; the next key on is a cold boot. So clusterd
arms the RTC at every suspend, for `parked_poweroff_hours` (48 by default, 0 turns the timer off, decimals work for
bring-up). After a wake it asks only whether the key is on, not what woke it:

| After a wake | clusterd |
|---|---|
| The wake pin says the key is on, or any PowerState heard since the resume does | carries on as normal and clears the alarm, even if the time is up |
| Nothing says so for 5 s, and the car has been parked for the whole time (within a minute) | `systemctl poweroff` |
| Nothing says so for 5 s, and there is time left | that was a stray wake: suspends again, with the alarm set to what is left |

- **Why on the word of either source.** A dark screen while driving is the failure to avoid, so a broken link (the
  pin still says On) and a broken pin (PowerState still says On) must not cause one.
- **Why 5 s of silence.** gauges/ sleeps at key off with its transceivers in standby, so the link is silent after an
  alarm wake, and also for the first moments of a key-on wake: gauges/ boots in about 0.5 s, sends PowerState every
  500 ms, and Linux has to bring CAN back. What was heard before the sleep does not count: CLOCK_MONOTONIC stopped too,
  so clusterd starts a new decoder and empties its sockets at every resume.
- **The parked time** is measured on CLOCK_BOOTTIME from the first suspend after the key went off. Only a key on
  restarts it, so gauges/ staying awake with the key off cannot keep the module from powering off.
- **The module awake with the key off and nobody to say so** used to mean running until the battery went flat. If the
  pin says Off and no PowerState is heard for 5 s, clusterd treats it as a key off: that catches a module that finished
  booting after the key went off (gauges/ is asleep by then, so no SuspendRequest ever comes), and a broken link. A
  suspend that fails, or that returns with nothing happening for 30 s, is tried again; after 3 in a row the module
  powers off instead. With the timer off (0) it keeps trying and never powers off.
- **The pin is optional in code, not in the car.** Without `--ign`, silence after a wake reads as key off, so a dead
  link at key on would put the screen back to sleep. Leave `--ign` out on a Toradex development carrier with no gauges/
  attached: nothing there holds CTRL_WAKE1_MICO# low, so the pin reads Off and clusterd would suspend 5 s after boot.
- **If the alarm cannot be armed** clusterd does not sleep. It counts as a failed suspend: logged at start and at each
  try, tried three times 5 s apart, then `systemctl poweroff`. Every key on is then a cold boot until the RTC is fixed,
  and that slow start is how the fault shows itself; sleeping without a timer is the flat battery this section is here
  to prevent. Key on during the tries carries on as normal. With the timer off (0) nothing is armed, so this cannot
  happen. **Decided 2026-11-04: do what car makers do.** No source found covers this exact fault, a wake timer that
  cannot be set, but their rule is the same: when sleep cannot be guaranteed, take the lowest-power state and accept a
  slow start. Android Automotive retries a failed suspend for at most 3 minutes and then shuts down
  (`CarPowerManagementService.suspendWithRetries`, "Too many failures trying to suspend. Shut down."), and its power
  controller "isn't required to support the timed turn-on feature". NXP's system basis chips for car ECUs drop to
  fail-safe mode, their lowest-power state, after a failed restart (UJA1069, UJA1065).

Limits accepted for now:

- Key on during a shutdown that has already started: the module ends up off with ignition holding VCC up, so the
  screen stays dark until the next key cycle. The window is the length of a shutdown, once per parked period.
- Key on in the moment between `systemctl suspend` and the kernel starting to suspend: the falling edge is missed and
  the module sleeps with the key on, until the next key cycle or the alarm. A sleep hook that checks the pin could close
  this if it shows up.
- A reboot with the key off may end in power-off, because CTRL_PWR_EN_MOCI falls during a cold reset (B-01). Run updates
  with the key on.

## Device tree notes for L5

There is no device-tree source in this repository yet. These are from mainline Linux's `imx95-verdin.dtsi` and
`imx95-verdin-dev.dtsi` as read on 2026-11-03; Toradex's BSP may differ, and none of this has been compiled:

```dts
/* Ignition. The module tree already has this node, disabled: gpio1 10, GPIO_ACTIVE_LOW, KEY_WAKEUP, wakeup-source.
   The second line wakes on key on only; the default is both edges. */
&verdin_gpio_keys { status = "okay"; };
&verdin_key_wakeup { wakeup-event-action = <EV_ACT_ASSERTED>; };

/* USB_1 is client-only: it is the bench header J13, and USB_1_ID is not pulled up on brain/. */
/ { /delete-node/ connector; };          /* the module tree's gpio-usb-b-connector, watching USB_1_ID (SODIMM 161) */
&usb2 {
    status = "okay";
    dr_mode = "peripheral";              /* the module tree has "otg" */
    /delete-property/ usb-role-switch;
    /delete-property/ vbus-supply;       /* USB_1_EN is not connected on brain/ */
    /delete-node/ port;
};
```

- **USB_1 client-only.** The Verdin Carrier Board Design Guide's table for unused USB signals gives two choices for
  USB_1_ID: pull it up to 1.8 V, or set the port to client-only in software. brain/ leaves it on a header pin with no
  pull-up, so a role switch would read a floating pin. The Android option's tree needs the same.
- **The dial click needs a gpio-keys node of its own**, here named `dial-click`. clusterd treats any key event on
  `--click` as the click, and any key down on `--ign` as the ignition, so the two must not share a node. The module
  tree's `gpio-keys` node, with only the wake pin in it, is what `--ign` opens.
- **Key codes.** Keep KEY_WAKEUP on the ignition. systemd-logind acts on KEY_POWER, KEY_SLEEP and KEY_SUSPEND, and with
  one of those the key would shut the module down or put it to sleep. It does not act on KEY_WAKEUP.
- **The RTC.** `rtc_wakealarm` has to name an RTC that can wake the module. In the mainline tree rtc0 is the on-module
  Epson RX8130 with no interrupt wired, so it has no `wakealarm` file (the kernel hides it unless the RTC's device can
  wake). rtc1 is the System Manager's (`scmi_bbm`, driver `rtc-imx-sm-bbm`), which declares itself wake-capable; that
  is the default here. Whether its alarm really wakes the module from suspend is not known until L6.

## Hardware: what brain/ already has, and what Linux needs from it

No board change is needed for this option.

| Function | brain/ | Linux side |
|---|---|---|
| Private CAN link | TCAN1044V-Q1 on Verdin CAN_1 | SocketCAN; the interface name is a device-tree fact (`can_if` in clusterd.conf), 500 kbit/s |
| Dial angle | Piher PSC-360 on J11, scaled to Verdin ADC_1 | IIO sysfs `in_voltageN_raw` (`--adc`); the valid band and detents per turn are settings |
| Dial click | GPIO_1 | a `gpio-keys` device-tree node of its own, read as evdev (`--click`) |
| Ignition wake | CTRL_WAKE1_MICO# (X1 252) | `gpio-keys` with `wakeup-source`, so ignition on resumes from suspend-to-RAM; its state read as evdev too (`--ign`, EVIOCGKEY) |
| Parked power-off | Ignition latch: LM74930 EN = ignition OR CTRL_PWR_EN_MOCI (B-01) | RTC alarm through `rtc_wakealarm`, then `systemctl poweroff`; the latch does the rest |
| Bench USB | J13 on USB_1 (USB_1_ID not pulled up) | client-only in the device tree (notes above) |
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
- In a container clusterd needs the host's logind (its D-Bus socket) for the two power commands, the wake RTC's sysfs
  file and the evdev nodes. Not worked out; `deploy/` assumes a plain systemd image.

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
wsl -d Ubuntu-22.04 -- python3 /mnt/c/Users/root/Project/cluster-pcb/software/linux/aa-bench/bench_park.py
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
| L5 | Torizon/Debian image for the Verdin: device tree (CAN, ADC, gpio-keys, wake, codec, MFi bus, USB_1 client-only), LIVI, clusterd | open: Verdin + carrier |
| L6 | Suspend/resume measured, the parked power-off proven (below), CarPlay with a real coprocessor | open |

**L6, the parked power-off.** Set `parked_poweroff_hours = 0.05` (3 minutes). On brain/, with a meter in the battery
feed:

1. Which `/sys/class/rtc/rtcN/wakealarm` exists, and does writing `+60` to it wake the module from suspend?
2. Does `--ign` read correctly: key on, key off, and straight after a resume? With the wrong polarity in the device
   tree, every key off would read as a key on.
3. Is `clusterd: resumed after N s` right? CLOCK_BOOTTIME has to count the sleep. If it does not, no resume is noticed:
   clusterd would read every wake as a suspend that never happened, decide 30 s late, and power off after the third.
4. With the key off: suspend, alarm, power-off, and the board falling to the first power-up checklist's figure
   (`docs/electrical-review.md` 9.5). Does CTRL_PWR_EN_MOCI fall and the latch let go?
5. Key on at each stage: during the suspend countdown, while suspended, in the 5 s after the alarm, during the shutdown.
6. Are `systemctl suspend` and `poweroff` allowed for the cluster user (`deploy/50-clusterd-power.rules`)?

## Not done here

- No Linux image or device tree yet (needs the module); the notes above are what it has to contain.
- `TripCommand` is sent but nothing in the Settings rows bumps it yet (the trip reset UX is undecided, as on Android).
- The "Map shape" row changes LIVI's config through `map_shape_cmd`; LIVI picks it up on restart or reconnect.
- Turn-by-turn data: LIVI exposes the phone's navigation maneuvers (`state/navigation.json`); showing them
  on a small gauge screen would need a new private-link message. Not started.
