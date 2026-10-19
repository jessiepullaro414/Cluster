# Mechanical fit: first check against stock-bezel measurements (2026-10-06)

The numbers below are **firsthand owner measurements, not Ford specifications**, supplied by the user on 2026-10-06 as a stand-in until a physical bezel is measured. Two of them disagree and are not averaged.

## Inputs

| Feature | mm | Source / caveat |
|---|---|---|
| Small gauge opening (stock) | 49.53 (1.95 in) | one installer |
| Speedometer opening (stock) | 89.26 (3.514 in) | same installer |
| Speedometer opening, rear of bezel | 87.38 (3.44 in) | a different owner; may be a different spot or bezel |
| Small-gauge cup depth | about 25.4 (1 in) | installer's description |
| Chrome ring above black face | about 6.35 (0.25 in) | installer's description |
| Aftermarket six-gauge bezel: large holes | 85.73 (3 3/8 in) | Mustang Project, a manufacturer figure |
| Aftermarket small holes | 52.39 (2 1/16 in) | same; an owner enlarged the stock holes to fit these, so not a stock size |
| Mounting | 6 screws: 4 upper (#8, 1 in), 2 lower (#8, 3/4 in) | owner report |
| Dash opening (user-supplied earlier) | 457.2 x 116.69 outer, 441.09 x 105.54 inner | unchanged |

Not known yet: outside bezel outline, gauge centre spacing, mounting-hole coordinates, rear housing depth, speedometer cable clearance, lens and curvature.

## What the numbers say about a STOCK-bezel build (no longer the plan)

| Part | Our size | Opening | Result |
|---|---|---|---|
| Center panel (TSD TST040HDBC-42) | 101.52 mm active circle, 720 px | 89.26 mm (stock), 87.38 mm (rear), 85.73 mm (aftermarket) | **Does not fit uncropped.** Visible diameter is 87.9 %, 86.1 % or 84.4 % of the panel: about 633, 620 or 608 of the 720 pixels across, and 77 % of the area at 89.26 mm |
| Small gauges (GC9A01, Raystar RFA401280B) | 32.4 mm active circle | 49.53 mm (stock), 52.39 mm (aftermarket) | The glass fits behind the opening, but fills only 65 % (or 62 %) of its width. Without a faceplate insert there is a 8.5 to 10 mm dark ring around each small display |

**Correction to earlier claims.** "The TSD's 101.5 mm circle fits the opening uncropped" (README, `display/build_schematic.py` comments, plan) was checked against the 105.54 mm inner HEIGHT of the whole dash opening, not against the stock speedometer hole. That check was wrong for a stock-hole build. It is true only if the faceplate is replaced by a custom one with a hole of about 101.5 mm or more.

## Decision (user, 2026-10-06): custom faceplate

"A custom reprinted faceplate was my plan all along." So the stock hole sizes above are NOT constraints; the faceplate is made to suit our displays, and the stock numbers matter only as a sanity check on the dash opening behind it. The earlier "does not fit uncropped" result applies only to a stock-bezel build.

What the faceplate openings must be (from the datasheets, to be confirmed against a physical panel):

| Opening | Size | Basis |
|---|---|---|
| Center panel window | about 102.5 to 104.5 mm diameter (nominal 103.5) | must clear the 101.52 +/- 0.1 mm active circle with placement margin and stay under the 105 mm LCD glass so the glass edge is hidden |
| Small gauge window | at least 33 to 35 mm diameter | 32.4 mm active circle plus margin; the GC9A01 module outline is not yet recorded |

TSD TST040HDBC-42 outline (datasheet drawing, page 4, general tolerance +/-0.2 mm): the module is a **round body of 110 +/- 0.15 mm diameter (backlight) with a 3.5 mm tab and FPC exit, 113.49 +/- 0.15 mm along the FPC axis, 7.8 mm thick**; LCD glass 105 mm (109.27 mm quoted over the glass at the tab), active area 101.52 mm; three screw bosses around the body; FPC about 69.8 +/- 0.5 mm long. Earlier notes only used the 101.52 mm active diameter.

Checks that pass with the custom faceplate:
- 113.49 mm over the tab fits the 116.69 mm outer opening height with 3.2 mm to spare if the FPC axis is vertical; it does NOT fit the 105.54 mm inner dimension, so the 110 mm body must sit behind the faceplate, not inside an inner frame.
- Slot spacing on `gauges/` is 98.5 mm (measured on the routed board: slot centres at 23.7, 122.2, 220.6, 319.0 and 417.5 mm from the board edge, the middle slot being the Android panel). The 110 mm body reaches 55 mm from its centre; a neighbouring small window sits 98.5 mm away, so at least 24 mm remains to the nearest small-gauge window edge even for a 38 mm module.
- These slot centres can now be treated as the faceplate specification: the faceplate is drawn to match the board, not the other way round.

## Other checks that need the missing numbers

- Gauge centre spacing: the four small-gauge connectors on `gauges/` sit at an evenly spaced 98.5 mm estimate across the five-slot row (see Decision); with a custom faceplate this becomes the specification, but it must still fit inside the real dash opening.
- Depth: the small-gauge cup is about 25 mm deep; the display module plus its FPC tail must reach the board. Panel and module thickness are not yet recorded.
- Mounting: six screw positions are known only by type, not by coordinates; our boards' own M3 holes (display 4 corners, gauges 6) are independent of them.
- Display carrier (about 152 x 102 mm) and gauges (447.1 x 58.3 mm) sit behind the bezel; whether the 102 mm height clears the opening depends on the dash structure behind it.

## Next measurement needed from a physical bezel (any one helps)

Centre-to-centre distances of the five openings; outside width and height of the bezel; depth from the face to the back of the dash opening.

## Photo-derived measurements of the user's own cluster (2026-10-08)

Source: 19 photos of the user's own 1965/66 Mustang five-dial cluster (front, back, side, with a 12 in / 30 cm ruler and a Stanley tape in frame), saved at `C:\Users\root\Downloads\iCloud Photos (2)\iCloud Photos\IMG_1682..1700.JPEG` (not committed: about 3 MB each). Read by eye against the tape, **about +/-5 mm**; the tape lay on the table in the plane of the chrome rim, but the photos are not orthographic. Treat as planning numbers, not drawing numbers.

Layout (viewed from the front): **fuel, oil, speedometer (center, large), amps, temp**: two small gauges each side, the speedometer in a deep cup that stands proud of the trim at top and bottom. Two small rectangular indicator windows sit between the gauges (one in each side panel). This matches the 4 + 1 plan.

| Item | Estimate | Notes |
|---|---|---|
| Chrome trim outline | about 518 x 120 mm (20.4 x 4.7 in) | longer and taller than the 457.2 x 116.69 mm opening the user gave earlier, so that figure is the opening behind the trim, not the trim |
| Depth, rim to back plate | about 60 mm | studs add about 8 mm |
| Depth, rim to speedometer housing | about 85 mm | |
| Depth, rim to speedometer cable fitting | about 113 mm | rear projection |
| Small gauge ring | about 61 mm outside, about 50 mm opening | matches the owner figure of 49.5 mm |
| Speedometer ring | about 127 mm outside, about 90 to 95 mm opening | owner figure 89.3 mm |
| Gauge centres from the speedometer centre | **about +/-118 mm (inner pair), +/-197 mm (outer pair)** | measured from two photos that agreed within about 4 mm; the speedometer sits within about 5 mm of the trim's centre |

**Mismatch with our boards.** `gauges/` places the four small-gauge connectors on an even five-slot grid: **+/-98.5 mm and +/-197 mm** from the centre. The outer pair matches the stock layout; the **inner pair is about 20 mm closer to the speedometer than stock (98.5 mm vs about 118 mm)**. With a custom faceplate either is possible, but the stock pattern looks right and leaves more clearance to the 110 mm panel body (46 mm instead of 26 mm to the nearest small module). Moving the inner connectors outward is a one-parameter change in `gauges/build_pcb.py`, then a re-route. **Done 2026-10-18**: `INNER_GAUGE_OFFSET_MM = 118` (photo estimate; replace with a caliper reading), outer pair unchanged at +/-196.9 mm.

Still needed to turn estimates into drawing numbers (calipers, 10 minutes): speedometer cup inside diameter and depth; small cup inside diameter and depth; the centre-to-centre distance of the two inner gauges (one number, gives the +/-118 mm directly); trim outline width and height at the rim; rim-to-back depth.

## Caliper readings from the user (2026-10-08), replacing the photo estimates for the cups

| Item | Reading |
|---|---|
| Speedometer cup inside diameter | about 102 mm |
| Speedometer cup depth | about 36 mm (depends where it is measured) |
| Small cup inside diameter | about 47 mm |
| Small cup depth | about 25 mm |

Checks against our parts:
- **Center panel**: the 101.52 mm active circle just fits a 102 mm bore (0.24 mm clearance), but the 105 mm LCD glass and 110 mm module body do not. The panel therefore cannot sit inside the stock speedometer cup; it sits at or behind the cup's mouth, so the cup either is cut back/replaced by a custom housing or the panel is mounted behind it with the active area looking through the 102 mm bore.
- **Small gauges**: the Raystar RFA401280B-AYW-DNF1 module is **50.20 x 50.20 x 3.99 mm** (touch panel outer diameter 50.20 mm, active area 32.40 mm, tolerance +/-0.3 mm; [Raystar datasheet](https://www.raystar-optronics.com/upload_files/tft-lcd-display-module/1-28-tft/capacitive-touch-screen-display/RFA401280B-AYW-DNF1-datasheet.pdf)). It is larger than the 47 mm stock cup, so it also cannot sit inside the stock cup. Neighbour clearance is fine: small modules 79 mm apart centre to centre (outer to inner), and about 38 mm from the inner module edge to the 110 mm center body.

## Center size limit (user, 2026-10-08): 5 in maximum INCLUDING the bezel

The user is making a totally new housing. The whole center assembly (screen plus bezel) may be at most 5 in (127 mm) across, which is also the size of the stock speedometer ring (about 127 mm outside).

- **TSD TST040HDBC-42 (4.0 in):** module body 110 mm, so 127 - 110 = 17 mm of radial room in total, **8.5 mm per side for the bezel and housing wall**. Fits, with room for a slim bezel and a sealing gasket.
- **A 5 in round panel (127 mm active, about 132 mm body)** cannot fit: the active circle alone equals the limit, leaving nothing for the bezel. Ruled out by this limit, not only by brightness.
- A panel between 4 in and 5 in would need a body of about 118 mm or less to keep a 4 mm bezel; none has been identified, and the 800-nit requirement still applies.
