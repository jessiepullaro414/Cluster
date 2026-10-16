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

The maps window is the largest rectangle of the chosen aspect inside a 680 px safe circle: 4:3 is 544 x 408 px (default), square 481 x 481, 16:9 590 x 332. The lamps (turn, high beam, brake, alternator, oil) sit in the caps above and below it. Whether CarPlay accepts a square or 4:3 surface is **unverified**; no projection exists yet (B5), only the geometry and the placeholder.

## The gauge (what it shows)

| Area | Content |
|---|---|
| Outer ring | speed, 270 degree sweep open at the bottom; 0 to 120 mph or 0 to 200 km/h; tap the centre to switch units |
| Inner ring | engine speed 0 to 7000 rpm, red from 6000 |
| Centre | speed number, unit, digital rpm, battery volts (amber below 11.5 V) |
| Top | turn arrows and high beam |
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
adb shell am broadcast -a com.jessiescars.cluster.SET --ez turn_left true --ez high_beam true --ez brake true --ez alt true --ez oil true
adb shell am broadcast -a com.jessiescars.cluster.SET --ez link_dead true
adb shell am broadcast -a com.jessiescars.cluster.SET --ez phone false --es no_phone home   # no phone; saved choice gauge|home
adb shell am broadcast -a com.jessiescars.cluster.SET --es aspect square --ez flip true      # window shape (saved); flip = show the gauge
adb shell am broadcast -a com.jessiescars.cluster.CLEAR
```

## Feeding the small gauge screens (development)

`TelemetryPublisher` sends `core/Telemetry.encode(state)` (one ASCII line, km/h, rpm, V, %, degC, kPa, `-` for an unavailable reading) over UDP to `10.0.2.2:5005` every 50 ms. `../../gauges-fw/tools/live_screens.py` receives it and drives the C screen code, so the four small screens can be watched moving with the same data as the centre display. Extras on the debug broadcast: `--es units mph|kph` (units on the small screens) and `--es telemetry off|host|host:port`. Needs the `INTERNET` permission, which the car build does not need.

## Known limits

- The "<" at the left edge in emulator screenshots is the stock AAOS system UI. The production image replaces SystemUI.
- The system bars are hidden with the insets API; AAOS may still show its own bars. Unverified on the NXP image.
- Typefaces are the platform's `sans-serif-condensed` and `sans-serif-medium`; the final font is a design choice.
- Colours and layout are a first pass for review, not a finished design; the dial scales (7000 rpm, 120 mph) are guesses to match the car.
- Not done: CarPlay / Android Auto viewport (B5), rotary dial input (B4), real property source (B3), settings from `DisplaySettings` (units, car profile).
