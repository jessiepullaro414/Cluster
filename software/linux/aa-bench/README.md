# Bench: Android Auto into LIVI with no car, and clusterd with no hardware

## clusterd against a stand-in LIVI (works today)

`bench_clusterd.sh` runs clusterd with no CAN and a scripted dial, and `fake_livi.py` in place of LIVI
(its telemetry endpoint and its `state/status.json`). It checks the page changes, the telemetry pushes, the
dial going to the phone as knob keys, Settings on a long hold, and the settings page server. 11 checks pass
in WSL Ubuntu 22.04.

## Android Auto from an emulator (the owner has an iPhone)

**Can an emulated Android phone drive LIVI? In principle yes, with two unknowns.**

Why it can work: Android Auto's developer settings have a **head unit server** (Android Auto app: tap the
version 10 times for developer mode, then the overflow menu, *Start head unit server*). It listens on TCP
5277 on the phone; Google's Desktop Head Unit reaches it through `adb forward tcp:5277 tcp:5277`. LIVI's
wireless Android Auto listens on TCP 5277 as well (the phone connects to it after the Bluetooth bootstrap).
After the TCP connection the protocol is the same in both directions, and the head unit is the TLS client
either way (LIVI `livi-aa/src/tls.rs`), so `relay.py` connects to both listeners and copies bytes.

```
Android emulator (Google Play image) or a real Android phone on USB
   │  head unit server :5277
   │  adb forward tcp:5277 tcp:5277
   v
relay.py --phone 127.0.0.1:5277 --livi 127.0.0.1:5278
   v
LIVI (LIVI_PORT=5278) on Linux
```

The unknowns, in the order they would bite:

1. **Android Auto inside an emulator.** It needs a Google Play system image and the Android Auto app from the
   Play Store, which needs a Google sign-in (the owner signs in; an agent must not). Google's own testing
   guidance points to a real phone; nothing found says Android Auto runs or refuses to run in an emulator.
   **First experiment**: install it on an emulator and see whether developer mode and the head unit server
   appear. Then check it with Google's Desktop Head Unit before involving LIVI at all.
2. **LIVI only opens its Android Auto port once Bluetooth is up** (`linux_main.rs`: the TCP listener is
   started inside the Bluetooth set-up). WSL has no Bluetooth adapter, so on WSL the port never opens. Options:
   a Linux PC or a Raspberry Pi 5 with Bluetooth (the listener then opens even though the phone never uses
   Bluetooth), or a one-line change to start the listener without Bluetooth (an upstream issue or patch).
   LIVI's AppImage is also tested on Debian Trixie / Ubuntu 26.04 and WSL here is Ubuntu 22.04, which is
   probably too old for it.

**A borrowed Android phone removes unknown 1** and works the same way through `adb forward`.

## CarPlay on the bench

No emulator route: the iPhone needs the Apple authentication coprocessor on the head unit for wired and
wireless CarPlay alike (LIVI: "cannot be emulated"). With a coprocessor on an I2C bus, a Linux PC or Pi
running LIVI takes the iPhone over USB.

## Downloads this would need (not done; ask first)

| What | From | Size |
|---|---|---|
| LIVI-9.5.0-linux-x86_64.AppImage | github.com/f-io/LIVI releases | about 242 MB |
| Android emulator system image, Google Play, x86_64 | Google, through the SDK manager | about 1.5 GB (estimate) |
| Debian Trixie for WSL (if the AppImage will not run on Ubuntu 22.04) | Microsoft Store / Debian | about 100 MB |
