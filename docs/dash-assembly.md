# Dash assembly v1 (2026-10-28)

`mech/build_assembly.py` puts the three routed boards (brain/, panel-tsd/, gauges/, from their
`kicad-cli pcb export step` models) into a faceplate, centre pod and housing tub drawn for them,
adds all five screens, the Verdin module and heatsink and the flat cables, and checks every pair
of solids for overlap. Run `python mech/build_assembly.py` (about 20 s). It writes, under
`mech/out/` (not committed, regenerated):

- `dash_assembly.step`: the whole assembly, about 70 MB, for FreeCAD, Fusion or Onshape
- `dash_assembly.glb` and the web viewer's `mech/viewer/model-*.js` chunks
- `clearance.json`: every clash, the parts under each small screen, cable reach, opening fit

Frame: X right as the driver sees it, Y up, Z toward the driver, origin at the speedometer centre
on the faceplate front.

## The design it proposes (all of it ours, change the constants and re-run)

| Layer | Z, mm | Notes |
|---|---|---|
| Centre pod lip, 127 mm across | +11.0 | owner limit 5 in including the bezel |
| TSD panel glass | +9.8 | 110 mm body sits in the pod, in front of the dash surface |
| Faceplate front | 0.0 | 3 mm, on the 518 x 120 mm trim outline, 34 mm small windows |
| Faceplate back, dash surface | -3.0 | |
| Small screens, lens front | -9.8 | 9.8 mm deep cups, like the stock ones (25 mm) but shallower |
| gauges/ component side, facing forward | -17.8 | J1 (13.8 mm) stops 1 mm behind the faceplate |
| panel-tsd/ bare side, parts facing back, 25 mm low | -22.4 | its J4 faces down, the panel FPC comes up from under gauges/ |
| brain/ bare side, Verdin and heatsink facing back | -31.0 | screen-port FFC goes over its top edge to J4 |
| Heatsink fins | -51.6 | fin height assumed (9 mm) |
| Tub back, vented | -56.0 | stock cluster about 60 mm deep |

The small screens sit on 4 mm printed holders over gauges/, the height the board was laid out for
(its FPC connectors are under the screen centres). The tub is 456.6 x 115.5 mm, 0.3 mm a side in
the 457.2 mm outer opening.

## Findings

1. **The fuel screen (U6, far left) hits J1 and F1.** J1, the power terminal block, is 13.8 mm
   tall and F1, the blade fuse holder, 7.4 mm; both sit inside the 50.2 mm lens circle, 16.8 and
   18.5 mm from its centre. With the screen 4 mm off the board, J1 passes through the screen and its
   cup and F1 runs 3.4 mm into the backlight. The other three screens cover 2 mm of parts or less
   (their FPC connector and 0603 passives). **Fix:** move J1 and F1 outside 25.1 mm of the fuel
   gauge centre (board x 97.11, y 232.34), or put them on the back of the board.
2. **The small screens' cables do not reach their connectors (all four).** The Raystar FPC has
   18.3 mm of free tail past its bonding edge (65.04 mm lens-top to tail end, datasheet p5) and
   leaves the module 21.6 mm from the centre. U6 to U9 sit 0.6 mm below the screen centres, so
   folded under the module the tail needs about 28.1 mm: 9.8 mm short. **Fix:** turn each screen
   180 deg (tail up, image flipped by the GC9A01's MADCTL), move U6 to U9 about 10 mm above the
   screen centre, opening facing up toward the tail. Keeping the tail down instead needs the board
   about 3 mm deeper below the screens (its edge is 9.35 mm below them now).
3. **gauges/ is 447.1 mm wide against the 441.09 mm inner opening** (known since rev C), and its
   centre is 3 mm right of the speedometer centre, so it reaches 226.6 mm right of centre and the tub
   needs nearly the full 457.2 mm outer opening. Check how deep the outer step is on the real dash.
4. Fits: the TSD's 69.8 mm FPC reaches panel-tsd/ J4 with 8.1 mm spare; the screen-port FFC is
   about 106 mm (buy 100 or 120 mm and check); nothing else touches.

## Assumed, not measured

Faceplate thickness and outline, holders, pod, tub walls, panel-tsd/ and brain/ positions, heatsink
fin height (Toradex datasheet not retrieved), the TSD tab width and FPC exit side, and stand-in boxes
for parts with no library 3D model: the four FFC connectors on gauges/ (2.0 mm), the SODIMM socket
(5.2 mm), and several small ICs and FETs (1.2 mm).
