# Dash assembly v2.2 (2026-10-28)

`mech/build_assembly.py` puts the three routed boards (brain/, panel-tsd/, gauges/, from their
`kicad-cli pcb export step` models) into a housing drawn after the stock 1966 five-dial cluster,
adds all five screens, the Verdin module and heatsink and the flat cables, and checks every pair
of solids for overlap. Run `python mech/build_assembly.py` (about 40 s). It writes, under
`mech/out/` (not committed, regenerated):

- `dash_assembly.step`: the whole assembly, about 70 MB, for FreeCAD, Fusion or Onshape
- `dash_assembly.glb` and the web viewer's `mech/viewer/model-*.js` chunks
- `clearance.json`: every clash, the parts under each small screen, cable reach, opening fit

Frame: X right as the driver sees it, Y up, Z toward the driver, origin at the speedometer centre
on the side panels' front face. The small-screen centres come from gauges/ itself (its 32.4 mm
F.SilkS circles), so the assembly follows the board when it moves.

## The housing (factory shape)

Drawn from the owner's photos of the stock cluster (IMG_1682..1700, see `mechanical-fit.md`). v2.1
gave it depth: the side photos (IMG_1689, IMG_1691) show a deep chrome pan with a rolled outer wall,
not a flat plate. v2.2 gave it the angle: seen end-on (IMG_1689) and from above (the owner's photo of
2026-10-28) the trim is a wedge, its top edge standing out like a hood over the speedometer cup and
its bottom edge shallow, the cup standing out past it.

- **Chrome rim**: the 518 x 120 mm trim outline, its ends leaning in toward the bottom (490 mm across
  at the bottom, ASSUMED from the photo) and rounded at 30 mm (ASSUMED). Its section is lofted round
  the whole outline (`RIM_PROFILE`, ASSUMED): up from the dash surface, a rolled crown, and an inner
  wall that falls to the panels 18.5 mm in from the outline. The part above the panels scales with
  height on the cluster (`RIM_CROWN`, ASSUMED: about 25 mm apart in IMG_1689), so the crown stands
  32 mm out at the top edge and 9 mm at the bottom. The speedometer cup passes through the bottom
  edge. Our 127 mm cup is taller than the 120 mm trim, so the hood cannot run straight over it as the
  stock one does (it would hide the top of the speedometer): it is scooped round the cup's mouth,
  flaring 12 mm out by Z = 40 (`SCOOP`, a styling choice).
- **Black grained side panels** (3 mm), each with a thin chrome bead following its edge, closed
  beside the pod.
- **Small gauges**: chrome bezel collars turned from a tapered section with a rolled top (58 mm
  outside, 48 mm opening, 6 mm high) over black cups. Each cup carries its screen: the lens sits against the cup's
  end with a sleeve round it and a clip lip behind its rim, so nothing stands on the board under the
  screen.
- **Turn indicators**: a 13 x 5.5 mm green lens in a chrome frame high in each side panel, 29 mm
  above the small-gauge centres as on the stock cluster, lit by gauges/ D26/D27 through a light pipe.
- **Speedometer pod**: a turned 127 mm chrome cup with a rolled lip 22 mm in front of the panels and
  a black throat that flares from the TSD glass edge (104 mm) to 116 mm at the lip, notched at the
  bottom for the TSD tab and its FPC, tucked under the hood at the top. The whole 101.52 mm active
  area stays in view up to 32 degrees off-axis (each small face up to 28 degrees past its bezel; the
  hood takes nothing more from above; `clearance.json` `view_angle_deg`). A deeper, stock-depth cup
  would shade more of the speedometer.
- Behind: the vented tub, 456.6 x 115.5 mm, through the dash opening.

| Layer | Z, mm | Notes |
|---|---|---|
| Chrome trim hood, top edge | +32.0 | ASSUMED from IMG_1689 |
| Speedometer pod lip, 127 mm across | +22.0 | owner limit 5 in including the bezel |
| Chrome trim, bottom edge | +9.0 | |
| TSD panel glass | +9.8 | 110 mm body sits in the pod |
| Small chrome bezels, top | +6.0 | |
| Side panels front | 0.0 | |
| Side panels back, dash surface | -3.0 | |
| Small screens, lens front | -9.8 | in their cups |
| gauges/ component side, facing forward | -17.8 | J1 (13.8 mm) stops 1 mm behind the panels |
| panel-tsd/ bare side, parts facing back, 25 mm low | -22.4 | its J4 faces down, the panel FPC comes up from under gauges/ |
| brain/ bare side, Verdin and heatsink facing back | -31.0 | screen-port FFC goes over its top edge to J4 |
| Heatsink fins | -51.6 | fin height assumed (9 mm) |
| Tub back, vented | -56.0 | stock cluster about 60 mm deep |

## Results (v2: no clashes)

v1 found two problems on gauges/; both are fixed in the board (`gauges/build_pcb.py`, re-routed,
0 unconnected, DRC only the accepted silkscreen and library warnings):

1. **Fuel screen vs J1 and F1: fixed.** The INPUT cell (J1 terminal block, 13.8 mm, and F1 fuse
   holder, 7.4 mm) is packed first, along the top edge of the POWER zone, above every screen: 15.6 mm
   and 12.2 mm clear of the fuel screen. The tallest part under any screen is now D1 at 2.3 mm,
   with 4 mm of room.
2. **Small-screen FPC reach: fixed.** U6 to U9 sit on the bottom edge of the board, 11 mm below their
   screen centres, cable entry facing down. The 18.3 mm Raystar tail folds back under the module
   and goes 3.25 mm into the 4.5 mm F32Q body (seated at 3 mm or more, ASSUMED). No screen rotation
   or MADCTL flip. The board grew from 63.4 to 65.6 mm tall.
3. The turn LEDs moved up to the factory window height (29 mm above the small-gauge centres), the
   clamp and resistor in a column below each.

Still open:

- **gauges/ is 447.1 mm wide against the 441.09 mm inner opening** (known since rev C), and its
  centre is 3 mm right of the speedometer centre, so the tub needs nearly the full 457.2 mm outer
  opening. Check how deep the outer step is on the real dash.
- Fits: the TSD's 69.8 mm FPC reaches panel-tsd/ J4 with 8.1 mm spare; the screen-port FFC is
  about 106 mm (buy 100 or 120 mm and check).

## Assumed, not measured

The trim's bottom width, end radius, rim section and hood heights, the scoop round the cup, the bezel
collars and throat flare, panel thickness, the cups that carry the small screens,
the light pipes, the pod depth, tub walls, panel-tsd/ and brain/ positions, heatsink fin height
(Toradex datasheet not retrieved), the TSD tab width and FPC exit side, the F32Q seating depth, and
stand-in boxes for parts with no library 3D model: the four FFC connectors on gauges/ (2.0 mm), the
SODIMM socket (5.2 mm), and several small ICs and FETs (1.2 mm). The ring, cup and gauge spacing
come from the owner's photos and calipers.
