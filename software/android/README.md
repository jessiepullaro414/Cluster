# Android Automotive side (plan and layout, no code yet)

Target: Verdin iMX95 on `../../display` running Android Automotive (AOSP, AAOS). On the production module this is a PORT (NXP's AAOS release supports the 19x19 EVK, see the plan); app-level work can start on the EVK or any AAOS emulator.

| Dir | What | State |
|---|---|---|
| `vhal-bridge/` | Vehicle HAL service: Linux SocketCAN to Android vehicle properties, decoding the private link | plan only |
| `cluster-app/` | full-screen round UI sized for the panel; reads the Car Property API | plan only |
| `rotary-service/` | turns the dial (ADC + click) into Android key/rotary events for the UI and for CarPlay / Android Auto | plan only |

Display shape: the panel is round (4.0 in 720 x 720 today; 1080 x 1080 for 5 in, 720 x 720 for the Anders 4.2 in). CarPlay / Android Auto need a rectangular viewport inside the circle (about 88 x 50 mm at 4.0 in); the cluster app must clip and lay out for that.

The wire protocol is generated: `../../protocol/cluster_private.dbc` and `cluster_can.h`.
