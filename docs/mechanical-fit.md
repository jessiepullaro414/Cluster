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
