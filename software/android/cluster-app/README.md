# cluster-app (plan)

Full-screen round instrument UI. Safe drawing area: the active circle (101.5 mm / 720 px on the TSD panel; 105.84 mm / 720 px on the Anders 4.2 in). Reads speed, RPM, fluids, warnings and lighting through the Car Property API; greys out any property reported unavailable. Brightness follows `DashDimmerPct` and `NightMode`. Hosts a CarPlay / Android Auto viewport as a rectangle inscribed in the circle (16:9 gives 88.5 x 49.8 mm at 4.0 in); navigation by the rotary dial.

First milestone: the app on an AAOS emulator fed by a fake property source, round layout only.
