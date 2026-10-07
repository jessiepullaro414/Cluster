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

## What the numbers say about our parts

| Part | Our size | Opening | Result |
|---|---|---|---|
| Center panel (TSD TST040HDBC-42) | 101.52 mm active circle, 720 px | 89.26 mm (stock), 87.38 mm (rear), 85.73 mm (aftermarket) | **Does not fit uncropped.** Visible diameter is 87.9 %, 86.1 % or 84.4 % of the panel: about 633, 620 or 608 of the 720 pixels across, and 77 % of the area at 89.26 mm |
| Small gauges (GC9A01, Raystar RFA401280B) | 32.4 mm active circle | 49.53 mm (stock), 52.39 mm (aftermarket) | The glass fits behind the opening, but fills only 65 % (or 62 %) of its width. Without a faceplate insert there is a 8.5 to 10 mm dark ring around each small display |

**Correction to earlier claims.** "The TSD's 101.5 mm circle fits the opening uncropped" (README, `display/build_schematic.py` comments, plan) was checked against the 105.54 mm inner HEIGHT of the whole dash opening, not against the stock speedometer hole. That check was wrong for a stock-hole build. It is true only if the faceplate is replaced by a custom one with a hole of about 101.5 mm or more.

## Choices this forces (the user decides)

1. **Keep the stock bezel holes.** The center UI must keep everything that matters inside a circle of about 600 px diameter (radius 300 px, a safe margin inside the 608 to 633 px that show). The panel's outer ring is hidden behind the bezel. The small gauges need a faceplate ring that covers the dark gap, or the bezel opening has to be reduced.
2. **Replace the faceplate** (the project's original idea: a custom reprinted faceplate). Then the opening can be 101.5 mm or more for the center and about 33 to 36 mm for the small gauges. This needs the real bezel outline and the gauge centre spacing, and it conflicts with "round displays in the stock round holes".
3. **A smaller center panel** that fits 85 to 89 mm: re-opens the panel choice (the 800-nit requirement and the DSI/Verdin plan would have to be re-checked). Not recommended before choice 1 or 2 is ruled out.

## Other checks that need the missing numbers

- Gauge centre spacing: the four small-gauge connectors on `gauges/` sit at an evenly spaced estimate across the original five-slot row; this can only be verified against the real centre positions.
- Depth: the small-gauge cup is about 25 mm deep; the display module plus its FPC tail must reach the board. Panel and module thickness are not yet recorded.
- Mounting: six screw positions are known only by type, not by coordinates; our boards' own M3 holes (display 4 corners, gauges 6) are independent of them.
- Display carrier (about 152 x 102 mm) and gauges (447.1 x 58.3 mm) sit behind the bezel; whether the 102 mm height clears the opening depends on the dash structure behind it.

## Next measurement needed from a physical bezel (any one helps)

Centre-to-centre distances of the five openings; outside width and height of the bezel; depth from the face to the back of the dash opening.
