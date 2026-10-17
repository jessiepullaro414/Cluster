# How to run everything

A map of every command in this repo: what it does, where to run it, and what it needs. Everything here was run on the owner's Windows 11 machine with WSL2 (Ubuntu 22.04) and the Android emulator. **Nothing has run on real hardware yet**; the firmware runs against a mock panel, and the Android app runs on an emulator with fake data.

Paths below are relative to this folder (`cluster-pcb/`, i.e. `C:\Users\root\Project\cluster-pcb`).

| I want to... | Go to |
|---|---|
| Run every automated check in one go | [1](#1-check-everything) |
| See the four small gauge screens | [3](#3-see-the-small-gauge-screens-the-harness-window) |
| Run the Android app on the emulator | [4](#4-the-android-app-and-the-emulator) |
| Try the dial | [5](#5-the-dial) |
| Regenerate the CAN protocol, fonts, faces | [7](#7-regenerating-generated-files) |
| Rebuild the circuit boards | [9](#9-the-circuit-boards-display-and-gauges) |

## 0. One-time setup

**Windows**

- Python 3.14 for Windows (the scripts below use `C:\Users\root\AppData\Local\Python\pythoncore-3.14-64\python.exe`, called `python` in this document) with `pip install pillow cantools kiutils pypdf`.
- Android Studio (its bundled JDK is used: `C:\Program Files\Android\Android Studio\jbr`), the Android SDK with platform-tools, emulator, `platforms;android-35` and the image `system-images;android-35-ext15;android-automotive;x86_64`.
- KiCad (for `kicad-cli`) and a Java runtime, only for the boards.
- `tools/freerouting-2.2.4.jar` (git-ignored, about 57 MB; download from the FreeRouting releases), only for routing the boards.

**WSL Ubuntu 22.04** (run `wsl -d Ubuntu-22.04`)

- `gcc`, `g++`, `make` (apt), and the Arm toolchain at `/opt/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi` (used for the Cortex-M4F build checks).
- WSLg is built into Windows 11 and shows the Linux windows (harness, dial simulator) on the desktop.
- Once, for the windows (headers only, no root needed): `sh software/gauges-fw/tools/get_x11_headers.sh` (unpacks X11 headers into `~/x11sdk`).

**Font file** (only to regenerate fonts): `software/refs/fonts/Inter.ttf` (git-ignored; the download link is in `software/gauges-fw/tools/gen_font.py`).

### Calling WSL from Windows

From PowerShell:

```powershell
wsl.exe -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw test
```

From Git Bash, stop Git Bash rewriting the path first (`MSYS_NO_PATHCONV=1 wsl -d Ubuntu-22.04 -- ...`). Long one-liners with quotes tend to lose their quoting; put the commands in a small script file and run `wsl.exe -d Ubuntu-22.04 -- bash /mnt/c/.../script.sh`.

## 1. Check everything

One command runs every check that can be proven without hardware (host tests, the 60 s simulated drive, the Arm compile and link, the pin check, the vhal-bridge tests):

```powershell
wsl.exe -d Ubuntu-22.04 -- sh /mnt/c/Users/root/Project/cluster-pcb/software/check.sh
```

The protocol checks need `cantools`, which WSL's Python lacks, so `check.sh` prints "SKIPPED" for them. Run them with Windows Python:

```powershell
cd protocol
python test_protocol.py          # DBC, spec and generated C agree with the tables, independent cantools check
python gen_codec_test.py         # regenerates software/gauges-fw/test/test_codec.c; git must show no change
```

Android unit tests are separate, see section 4.

## 2. The gauge firmware (`software/gauges-fw`), in WSL

`cd /mnt/c/Users/root/Project/cluster-pcb/software/gauges-fw`, then:

| Command | What it does |
|---|---|
| `make test` | builds and runs every host test: aggregation, codec, input maths, screens, renderer, dial change tracking (a random walk of 3,840+ updates must equal a full redraw), the GC9A01 driver against a mock panel, the fault manager (a model of the watchdog), the odometer and the settings store (power cut at every flash command), the inputs and senders, the CAN link and bit timing, the bootloader core (power cut at every flash command of an update) and the Python update tool against it, the harness self test, and the golden pictures |
| `make sim` | 60 virtual seconds of driving in every theme (also with speed on the centre screen): bus load, the 10 ms tick budget, panel equals model |
| `make golden` | compares 196 stored picture checksums. A styling change shows as `CHANGED`; look at the pictures with `make golden-dump` (PNGs in `build/golden`), then accept with `make golden-update` |
| `make arm-check` | compiles every file for the Cortex-M4F with `-Werror` |
| `make arm` | links `build/gauges-fw.elf` and prints its size. `sh tools/inspect_elf.sh` shows sections, vectors and the flash configuration field |
| `make boot`, `make app`, `make image` | the bootloader (first 32 KB), the application linked behind it at 0x8000, and `build/gauges-app.bin` (the update file) plus `build/gauges-flash.bin` (both in one piece for a programmer). `python3 tools/can_flash.py --interface socketcan --channel can0 build/gauges-app.bin` sends an update (needs python-can and a CAN adapter on the private link); `--emit frames.txt` writes the frames without a bus. See the "Firmware update" section of `software/gauges-fw/README.md` |
| `make preview` or `./build/preview <preset 0-4> <imperial\|metric> <classic\|modern\|carplay\|factory> [center]` | renders the four screens through the real driver into `build/screen_N.ppm`; `python3 tools/montage.py out.png 2` joins them into a PNG (presets: 0 cruise, 1 warnings, 2 no data, 3 idle, 4 redline) |
| `make bench` | counts the rendering work of typical updates |
| `make harness` | builds the harness with its window (see 3); `make build/harness_cli` has no window |
| `make clean` | removes `build/` |

The harness without a window works on the command line, for example `./build/harness_cli --selftest`, `--sim 60 --units-switch --theme factory --center`, `--golden check test/golden_screens.txt`.

## 3. See the small gauge screens (the harness window)

This shows the real C screen code on a mock GC9A01 panel in a window, fed either by a built-in drive or live from the Android app.

```powershell
powershell -ExecutionPolicy Bypass -File software\gauges-fw\tools\run_harness.ps1            # build, open the window, point the Android app at it
powershell -ExecutionPolicy Bypass -File software\gauges-fw\tools\run_harness.ps1 -NoAndroid # window only
```

It listens on UDP 5005 and tells the app where to send (`adb shell am broadcast ... --es telemetry <WSL ip>:5005`). **The WSL address changes after a reboot, and the app forgets it when it is reinstalled or force-stopped**: run the script again, or send the broadcast yourself:

```powershell
$ip = (wsl.exe -d Ubuntu-22.04 -- hostname -I).Trim().Split(" ")[0]
adb shell am broadcast -a com.jessiescars.cluster.SET --es telemetry "${ip}:5005"
```

Keys in the window: `Space` pause, `D` built-in drive, `M` manual, `A` Android feed, `R` replay, `U` units, `T` theme, `C` speed on the centre screen, `1`-`6` toggle an input valid/invalid, arrows change speed and rpm, `F` `C` `O` `B` change fuel, coolant, oil and battery (lower case down, upper case up), `Tab` zooms, `S` saves a picture, `Q` quits (the full list is the `usage()` text in `software/gauges-fw/test/harness.c`). Options include `--udp PORT`, `--theme`, `--center`, `--record FILE`, `--replay FILE`, `--scale X` and `--shot out.png --after 3`.

If the Android feed stops, the window keeps running on its own simulated sensors (the real board has its own senders), and says so in the HUD and in `/tmp/harness.log` (in WSL).

## 4. The Android app and the emulator

### Create and start the emulator

```powershell
powershell -File software\android\emulator\create_avd.ps1                 # once: AVD "cluster_round", 720 x 720, round, Android 15 automotive
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd cluster_round -no-audio -no-snapshot-save -gpu swiftshader_indirect
powershell -File software\android\emulator\hide_stock_cluster.ps1         # optional: blanks the image's second "Welcome, ClusterHome" display (-Undo to restore)
```

### Build, test, install

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
cd software\android\cluster-app
.\gradlew.bat --offline testDebugUnitTest assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb shell am start -n com.jessiescars.cluster/.MainActivity
```

### Drive it from adb

The app uses fake data (a 30 second drive). The debug broadcasts override it:

```powershell
adb shell am broadcast -a com.jessiescars.cluster.SET --ef speed_kph 120 --ef rpm 6400 --ez night true --ef dimmer 30
adb shell am broadcast -a com.jessiescars.cluster.SET --es theme factory --es units mph         # classic | modern | carplay | factory
adb shell am broadcast -a com.jessiescars.cluster.SET --ez phone true --es phone_kind carplay    # a phone is projecting (carplay | androidauto)
adb shell am broadcast -a com.jessiescars.cluster.SET --ez phone false --es no_phone gauge       # no phone; show gauge | home
adb shell am broadcast -a com.jessiescars.cluster.SET --ez flip true                             # show the speedometer instead of the maps
adb shell am broadcast -a com.jessiescars.cluster.SET --ez match_carplay true                    # small screens take the CarPlay look while CarPlay is on screen
adb shell am broadcast -a com.jessiescars.cluster.SET --ez settings true                         # open the settings list
adb shell am broadcast -a com.jessiescars.cluster.CLEAR                                         # reset the overrides
```

The full list of extras is in the comment at the top of `MainActivity.java` and in `software/android/cluster-app/README.md`.

### Screenshots

The emulator has two displays, so name the main one:

```powershell
adb shell dumpsys SurfaceFlinger --display-id          # the first id is the main display
adb exec-out screencap -d <id> -p > shot.png
```

## 5. The dial

What it does (the same flow as the desktop simulator, section 6):

| Where | Turn | Click | Hold |
|---|---|---|---|
| Home (maps / speedometer) | flips maps and speedometer (with keys; the emulator panel has nothing to move focus to, so use click) | flips maps and speedometer | opens settings |
| Settings list | moves the highlight | enters edit mode on the row | closes the list |
| Editing a row | changes the value, the small screens follow at once | (the emulator's controller ignores it) | cancels (key path) |
| any | | | **Back** leaves edit mode (keeps the value), then closes the list |

**With the emulator's Car rotary panel** (Extended Controls, three dots, "Car rotary"): click the curved arrows to turn, the centre circle to press (hold about a second for a long press), the back arrow for Back. Android's rotary controller, an accessibility service, handles this panel: it moves focus between the app's views and presses the focused one.

**Without the controller** (keys sent straight to the app, as `software/android/rotary-service` is planned to do in the car): `adb shell input keyevent KEYCODE_NAVIGATE_NEXT` / `KEYCODE_NAVIGATE_PREVIOUS` turn, `KEYCODE_DPAD_CENTER` clicks (`--longpress` holds), `KEYCODE_BACK` is Back.

**If the dial misbehaves**, every key and scroll event the app receives is logged:

```powershell
adb logcat -c                    # clear, then use the dial
adb logcat -d -s ClusterInput    # what the app saw
adb logcat -d | Select-String RotaryController   # what Android's rotary controller did with the panel clicks
```

## 6. The dial simulator (`software/hmi-sim`)

A desktop window with the round centre screen and the four small screens, and a simulated dial. Proof of concept for trying menu flows.

```powershell
powershell -File software\hmi-sim\run.ps1                       # build and open the window
wsl.exe -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/hmi-sim test   # self test
```

Window: mouse wheel or arrow keys turn, left button or Space/Enter clicks (hold 0.6 s for a long press), `P` toggles the phone with CarPlay, `Esc` long press, `Q` quits. Headless scripted pictures: `build/hmi_sim --script "H,R,R,C,shot=out.png"` (R/L turn, C click, H hold). See `software/hmi-sim/README.md`.

## 7. Regenerating generated files

Never hand-edit these; change the source and regenerate.

| Output | Command (from the folder shown) |
|---|---|
| `protocol/*.dbc`, `can_protocol.md`, `cluster_can.h`, `cluster_codec.h` | `protocol`: `python can_protocol.py` then `python test_protocol.py` |
| `software/gauges-fw/test/test_codec.c` | `protocol`: `python gen_codec_test.py` |
| Fonts `src/font_data.c` | `software/gauges-fw`: `python tools/gen_font.py` (needs Pillow and `refs/fonts/Inter.ttf`) |
| Factory-theme faces `src/face_data.c` and `docs/screens/factory_faces.png` | `software/gauges-fw`: `python tools/gen_faces.py` |
| Interrupt vector table `src/vectors.c` | `software/gauges-fw`: `python tools/gen_vectors.py` |
| Golden pictures | `make golden-update` (in WSL), after looking at `make golden-dump` |
| README previews in `docs/screens/` | `./build/preview ...` then `tools/montage.py` (section 2) |

## 8. Other tools

- `software/android/vhal-bridge`: `make test` in WSL (the CAN-to-vehicle-property policy library; also run by `check.sh`).
- `software/tools/can_replay.py`: replays a scripted drive onto a CAN bus (`--role car` for the car side, `--role gauges` for the private link) for bench work with a real adapter.
- `software/gauges-fw/tools/check_pins.py`: checks the HAL pins against `gauges_pins.h` (also run by `check.sh`). `check_vendor_block.py` re-derives the GC9A01 register tables from Zephyr's open-source driver and compares them byte for byte; it needs two reference files that are not committed (`software/refs/raystar/display_gc9x01x.c` and `gc9x01x.yaml`, from the Zephyr repository).

## 9. The circuit boards (`display/` and `gauges/`)

Everything is generated by scripts. In `display/` or `gauges/`:

```powershell
python build_schematic.py   # schematic + ERC self-checks
python build_pcb.py         # placement + design-rule self-checks
python route_board.py       # FreeRouting (display/ also adds the DSI pairs), verified by a real kicad-cli DRC
python ..\run_drc.py ClusterDisplay.kicad_pcb     # or ClusterGauges.kicad_pcb
python build_bom.py         # BOM with coverage and value-spelling checks
```

Needs `kiutils`, `kicad-cli`, a JRE and the FreeRouting jar (section 0). The generated KiCad files are written next to the scripts; open them in KiCad to look. See `README.md` for the board status and known limits. `display/` is being extended (audio, USB host, wireless) in a separate working session: expect its scripts and outputs to change.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make: ... No such file or directory` with a path starting `C:/Program Files/Git/...` | Git Bash rewrote the path. Use `MSYS_NO_PATHCONV=1`, or call `wsl.exe` from PowerShell |
| The small-screen window is not there | WSL restarted or the window was closed. Run `run_harness.ps1` again; check `/tmp/harness.log` in WSL |
| The small screens show the built-in drive, not the app | The app lost its target. Re-run `run_harness.ps1` or send the `--es telemetry` broadcast (section 3) |
| Gradle: "SDK location not found" | Set `ANDROID_HOME` as in section 4 (or create `local.properties` with `sdk.dir=`) |
| `adb exec-out screencap` writes a warning into the PNG | Pass the display id with `-d` (section 4) |
| The emulator shows the stock launcher, not the app | After an emulator restart run `adb shell am start -n com.jessiescars.cluster/.MainActivity` |
| The dial does nothing | Section 5: read `adb logcat -d -s ClusterInput`. With the panel, steps: turn once to focus, then press |
| A PDF/datasheet download is blocked (ti.com, mouser.com) | Try another host for the same document (Toradex docs, Farnell); see the notes in `software/gauges-fw` sources for what was verified |

## Where the decisions live

- `software/PLAN.md`: the software plan, decisions with dates, build environment notes.
- `README.md` (repo root): boards, how they talk, known limits.
- `docs/mechanical-fit.md`, `docs/rfq-drafts.md`: dash dimensions and the supplier questions (none sent).
- `software/gauges-fw/README.md`, `software/android/cluster-app/README.md`: the firmware and app in detail.

## 11. Electrical design review scripts (`review/`)

`docs/electrical-review.md` is the written review; the scripts that produced its numbers re-run after any regeneration:
`python review/review_netlist.py gauges|display` (pin-by-pin against datasheet tables in `review/expected.py`, decoupling per supply pin,
exit status 1 on any FAIL), `review/layout_checks.py`, `review/surge_sim.py`, `review/thermal_derating.py`, `review/dsi_impedance.py`,
`review/connector_audit.py`. They only read the generated KiCad files.

## 12. The demo video (`software/demo`)

**Since 2026-10-17 `media/cluster-demo.mp4` is the Linux-option demo** (1080p, 1 min 46 s): the round centre is LIVI on Linux showing our speedometer, the settings and real Android Auto from the phone emulator (Google Maps navigating), next to the four small gauges, all fed by one replayed drive. Made the same three-step way from the bench in `software/linux/aa-bench/README.md`: `py software/demo/record_livi_demo.py` (drives the dial through clusterd's pipe and the phone through adb, captures LIVI's window with PrintWindow via `wincap.py`, so other windows may cover it; it retries the phone and marks the waits to cut, because the emulator's arm64 Android Auto and Maps crash now and then under ARM translation), `py software/demo/compose_livi_demo.py <workdir>`, then `encode_demo.mjs` as below; `py software/demo/make_livi_site_assets.py <workdir> <outdir>` cuts the website stills. "py" here is the real Python (`%LOCALAPPDATA%\Python\bin\python.exe`; the `python` on PATH is the Store stub). The earlier Android Automotive video is kept as `media/cluster-demo-aaos-emulator.mp4` and is made as follows.

The Android Automotive video (1080p, about 1 min 47 s) shows the centre gauge in the emulator and the four small gauges from the real firmware drawing code, laid out like the dash, with captions. It is made in three steps from the running emulator and harness (nothing is faked): `py software/demo/record_demo.py` drives the app through the storyboard with the debug broadcasts, records the emulator with `adb screenrecord` and has the harness dump its four panels (`--frames`); `py software/demo/compose_demo.py <workdir>` lines the two up on the wall clock and draws the layout and captions; `node software/demo/encode_demo.mjs <workdir>/out_frames media/cluster-demo.mp4` encodes H.264 with Chrome's own encoder, no ffmpeg needed. Do not touch the PC while the first step runs (about two minutes; the harness window opens on the desktop). The Claude desktop app keeps the Android SDK under its package cache, which is where `adbtools.py` looks for adb.
