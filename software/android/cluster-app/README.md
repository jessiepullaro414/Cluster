# cluster-app (B1: centre display on the emulator, fake data source)

Full-screen round instrument UI for the centre display. The target is a 720 x 720 round panel (TSD TST040HDBC-42, 101.5 mm active, 180 ppi); the view draws in a 720 px design space inside a circle of radius 340, so nothing important is in the cropped corners.

## Centre display modes (decision 2026-10-15)

The centre is **CarPlay / Android Auto maps**; speed, rpm and fluids are on the four small screens (`../../gauges-fw/inc/screens.h`). `core/CenterLogic` decides what the round screen shows:

| Phone projecting | Dial click | No-phone setting | Shows |
|---|---|---|---|
| yes | no | any | maps window (`ProjectionView`, placeholder content) |
| yes | flipped | any | the gauge below |
| no | n/a | gauge | the gauge below |
| no | n/a | home | home (placeholder) |

The map is **round by default** (decision 2026-10-16, from the owner's reference picture): the picture fills the whole circle and the panel's edge crops it. The old rectangular windows remain as choices: the largest rectangle of the chosen aspect inside a 680 px safe circle, 4:3 is 544 x 408 px, square 481 x 481, 16:9 590 x 332. **No turn indicators** (the dash has physical ones). Only lamps that are lit (high beam, brake, alternator, oil) appear, in a row along the lower edge. Whether CarPlay accepts a square or 4:3 surface is **unverified**; no projection exists yet (B5), only the geometry and the placeholder.

## Settings (the way the user changes the look)

A long press (or the MENU key) opens a list on the round display: **Gauge theme** (Classic or Modern, for the four small screens), **Units**, **No phone shows** (Gauge or Home) and **Map shape** (Round, Square, 4:3, 16:9). Touch a row, or use the rotary dial (up and down move, click changes), and press Done or BACK. The choices are saved. The theme is sent to the gauges board in `DisplaySettings.GaugeTheme` (the VHAL bridge will do this over CAN, B3; today it goes in the development telemetry line to the test harness). Logic and tests: `core/Settings`.

## The gauge (what it shows)

| Area | Content |
|---|---|
| Outer ring | speed, 270 degree sweep open at the bottom; 0 to 120 mph or 0 to 200 km/h; tap the centre to switch units |
| Inner ring | engine speed 0 to 7000 rpm, red from 6000 |
| Centre | speed number, unit, digital rpm, battery volts (amber below 11.5 V) |
| Top | high beam (no turn indicators: the dash has physical ones) |
| Bottom | brake, alternator and oil lamps |
| Night | headlights on (`DashLightsOn`) switches to an amber palette whose brightness follows `DashDimmerPct` (20 % to 100 %). This scales what the app draws; the panel backlight is a separate platform setting |
| No data | link lost: every reading becomes `--`, and "NO DATA" shows. A stale value is never shown |

Screenshots from the emulator are in `../emulator/shots/` (`maps_*`, `flipped_gauge`, `nophone_*` for the centre modes).

## Layout

```
app/src/main/java/com/jessiescars/cluster/
  core/        pure Java, no Android: Reading, VehicleState, Gauge (scale maths), Units,
               Palette (day/night), DriveScenario (the fake data)        <- unit tested
  ClusterView  the drawing
  MainActivity fake source loop + adb debug broadcasts, HOME-capable
app/src/test/  JUnit 4 tests of core/
```

`VehicleState` mirrors the property list of `../vhal-bridge` (`Bridge::get`), so the real source (B3: SocketCAN, then the AAOS vehicle HAL) only has to produce a `VehicleState`; the view does not change. `DriveScenario` is the same 30 s drive as `../../tools/can_replay.py`.

## Build and run (Windows, no Android Studio window needed)

```
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
set ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk
gradlew.bat testDebugUnitTest assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb shell am start -n com.jessiescars.cluster/.MainActivity
```

The emulator profile is `../emulator/create_avd.ps1` (AVD `cluster_round`: 720 x 720, 180 dpi, circular flag, Android 15 automotive image). Start it with `emulator -avd cluster_round -gpu swiftshader_indirect`.

Screenshot the main display (the emulator has two, so name it; without `-d` adb prefixes a warning to the PNG):
`adb exec-out screencap -d <id> -p > shot.png`, where `<id>` comes from `adb shell dumpsys SurfaceFlinger --display-id` (the first one).

## Driving it from adb

```
adb shell am broadcast -a com.jessiescars.cluster.SET --ef speed_kph 120 --ef rpm 6400 --ez night true --ef dimmer 30
adb shell am broadcast -a com.jessiescars.cluster.SET --ez high_beam true --ez brake true --ez alt true --ez oil true
adb shell am broadcast -a com.jessiescars.cluster.SET --ez link_dead true
adb shell am broadcast -a com.jessiescars.cluster.SET --ez phone false --es no_phone home   # no phone; saved choice gauge|home
adb shell am broadcast -a com.jessiescars.cluster.SET --es aspect round --ez flip true       # map shape (saved); flip = show the gauge
adb shell am broadcast -a com.jessiescars.cluster.SET --es theme modern --es units kph       # small-screen theme and units (saved)
adb shell am broadcast -a com.jessiescars.cluster.SET --ez settings true                     # open the settings list; then: adb shell input keyevent KEYCODE_DPAD_DOWN / KEYCODE_DPAD_CENTER
adb shell am broadcast -a com.jessiescars.cluster.CLEAR
```

## Feeding the small gauge screens (development)

`TelemetryPublisher` sends `core/Telemetry.encode(state)` (one ASCII line, km/h, rpm, V, %, degC, kPa, `-` for an unavailable reading) over UDP every 50 ms, by default to `10.0.2.2:5005` (the PC the emulator runs on). The test harness in `../../gauges-fw` (`tools/run_harness.ps1`) listens, runs the real C screen code on the data and shows the four round screens, and tells the app where to send with `--es telemetry <WSL ip>:5005`. Other extras on the debug broadcast: `--es units mph|kph` (units on the small screens) and `--es telemetry off|host|host:port`. Needs the `INTERNET` permission, which the car build does not need.

## Known limits

- The "<" at the left edge in emulator screenshots is the stock AAOS system UI. The production image replaces SystemUI.
- The system bars are hidden with the insets API; AAOS may still show its own bars. Unverified on the NXP image.
- Typefaces are the platform's `sans-serif-condensed` and `sans-serif-medium`; the final font is a design choice.
- Colours and layout are a first pass for review, not a finished design; the dial scales (7000 rpm, 120 mph) are guesses to match the car.
- Not done: CarPlay / Android Auto viewport (B5), rotary dial input (B4), real property source (B3), settings from `DisplaySettings` (units, car profile).
