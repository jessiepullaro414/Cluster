# Dash assembly v2.5 (2026-10-29)

`mech/build_assembly.py` puts the three routed boards (brain/, panel-tsd/, gauges/, from their
`kicad-cli pcb export step` models) into a housing drawn after the stock 1966 five-dial cluster,
adds all five screens, the Verdin module and heatsink, the flat cables and J1's wires, and checks
every pair of solids for overlap. Run `python mech/build_assembly.py` (about 40 s). It writes, under
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
not a flat plate. v2.5 gave it the right angle (owner, 2026-10-29): the car's dash face leans back
toward the bottom, the gauge faces stand square to the driver, and the trim makes up the difference,
so it is about 20 mm deeper at the bottom than at the top (the bulge seen end-on in IMG_1689 and the
owner's photos of 2026-10-28). Only the trim's back edge leans; the panels, the speedometer cup, the
boards and the tub are all square to the driver. (v2.2 to v2.4 tilted the trim's front instead.)

- **Chrome rim**: the 518 x 120 mm trim outline, its ends leaning in toward the bottom (490 mm across
  at the bottom, ASSUMED from the photo) and rounded at 30 mm (ASSUMED). Its section is lofted round
  the whole outline (`RIM_PROFILE`, ASSUMED): a 1.5 mm outer wall from the leaning dash up to the
  panels' plane (3 mm deep at the top edge, 23 mm at the bottom, `DASH_TILT` 9.5 degrees ASSUMED), a
  rolled crown 9 mm in front of the panels all round, and an inner wall that falls to the panels 18.5
  mm in from the outline. The outer roll is chrome, the inner wall black (as on the stock cluster).
  The speedometer cup stands out through the trim top and bottom.
- **Black grained side panels** (3 mm), each with a thin chrome bead following its edge, closed
  beside the pod.
- **Small gauges**: chrome bezel collars turned from a tapered section with a rolled top (58 mm
  outside, 48 mm opening, 6 mm high) over black cups. Like the stock holes (owner, 2026-10-30), each
  cup tapers in from the ring's 48 mm opening at the panel face to a 35 mm window at the glass, 9.8 mm
  deeper, framing the 32.4 mm active area. Each cup carries its screen: the lens sits against the cup's
  end with a sleeve round it and a clip lip behind its rim, so nothing stands on the board under the
  screen.
- **Turn indicators**: a 13 x 5.5 mm green lens in a chrome frame high in each side panel, 29 mm
  above the small-gauge centres as on the stock cluster, lit by gauges/ D26/D27 through a light pipe.
- **Speedometer pod**: a turned 127 mm chrome cup with a rolled lip 22 mm in front of the panels
  (`POD_FRONT`) and a black throat that flares from the TSD glass edge (104 mm) to 116 mm at the lip,
  notched at the bottom for the TSD tab and its FPC. The glass is 13.2 mm behind the lip (`POD_DEPTH`,
  ASSUMED). The whole 101.52 mm active area stays in view up to 32 degrees off-axis (each small face up
  to 28 degrees past its bezel; `clearance.json` `view_angle_deg`). Its lip is 13 mm in front of the
  trim's crown, as on the stock cluster (owner's side photo). A deeper, stock-depth cup would shade
  more of the speedometer.
- Behind: the vented tub, square to the driver, so it crosses the leaning dash at an angle: 456.6 x
  114.5 mm, 116.1 mm tall in the dash's plane against the 116.69 mm opening (it was 115.5 mm tall,
  which would be 117.1 mm in the leaning opening and not pass).

| Layer | Z, mm | Notes |
|---|---|---|
| Speedometer pod lip, 127 mm across | +22.0 | owner limit 5 in including the bezel |
| Chrome trim, crown | +9.0 | all round |
| TSD panel glass | +8.8 | 110 mm body sits in the pod |
| Small chrome bezels, top | +6.0 | |
| Side panels front | 0.0 | |
| Side panels back; dash surface at the trim's top edge | -3.0 | |
| Small screens, lens front | -9.8 | in their cups |
| gauges/ component side, facing forward | -17.8 | J1 (13.8 mm) stops 1 mm behind the panels |
| panel-tsd/ bare side, parts facing back, 25 mm low | -22.4 | its J4 faces down, the panel FPC comes up from under gauges/ |
| Dash surface at the trim's bottom edge | -23.1 | the dash leans 9.5 degrees (ASSUMED) |
| brain/ bare side, Verdin and heatsink facing back | -31.0 | screen-port FFC goes over its top edge to J4. Since it shrank to 127.5 x 95.3 mm (2026-11-06) its centre is at X +17.7, Y -3: J4 lines up with panel-tsd/ J1, so the ribbon has no sideways run, and panel-tsd/'s lower standoffs still land on it |
| Heatsink fins | -51.6 | fin height assumed (9 mm) |
| Tub back, vented | -56.0 | stock cluster about 60 mm deep |

## Results (v2: no clashes)

v1 found two problems on gauges/; both are fixed in the board (`gauges/build_pcb.py`, re-routed,
0 unconnected, DRC only the accepted silkscreen and library warnings):

1. **Fuel screen vs J1 and F1: fixed.** The INPUT cell (J1 terminal block, 13.8 mm, and F1 fuse
   holder, 7.4 mm) is packed first, along the top edge of the board, above every screen: 11.5 mm and
   14.6 mm clear of the fuel screen's lens, 9.6 and 12.7 mm of its cup. The tallest part under any
   screen is now the screen's own connector at 2.0 mm (a stand-in box), with 4 mm of room.
2. **Small-screen FPC reach: fixed.** U6 to U9 sit on the bottom edge of the board, 11 mm below their
   screen centres, cable entry facing down. The 18.3 mm Raystar tail folds back under the module
   and goes 3.25 mm into the 4.5 mm F32Q body (seated at 3 mm or more, ASSUMED). No screen rotation
   or MADCTL flip. The board grew from 63.4 to 65.6 mm tall, and is 61.0 mm since 2026-11-06.
3. The turn LEDs moved up to the factory window height (29 mm above the small-gauge centres), the
   clamp and resistor in a column below each.
4. **J1's wires (2026-11-06, `electrical-review.md` G-39).** J1's wire mouth now faces the top edge of
   gauges/, 0.8 mm in from it, and the board's top edge came down 4.9 mm against the screens. The
   three wires are in the clash check: out of the mouths toward the tub's top wall, a bend back past
   the board's edge, and on to the tub's back. Mouth to wall is 9.7 mm against the 9.2 mm they need
   (`clearance.json`, `j1_wires`). On the old outline it would have been 4.8 mm.

Still open:

- **gauges/ is 447.1 mm wide against the 441.09 mm inner opening** (known since rev C), and its
  centre is 3 mm right of the speedometer centre, so the tub needs nearly the full 457.2 mm outer
  opening. Check how deep the outer step is on the real dash.
- Fits: the TSD's 69.8 mm FPC reaches panel-tsd/ J4 with 8.6 mm spare; the screen-port FFC is
  about 91 mm since brain/ shrank (buy 100 mm and check).
- **No way out of the tub is drawn** for J1's wires or any other connector's. The model takes J1's
  wires to the tub's back. A slot in the tub's top wall right in front of the mouth would need no
  bend at all, and the 0.5 mm spare above stops mattering.

## Assumed, not measured

The trim's bottom width, end radius and rim section, the dash's lean, the cup depth, the bezel
collars and throat flare, panel thickness, the cups that carry the small screens,
the light pipes, the pod depth, tub walls, J1's wires (2.2 mm, a 6.6 mm bend, a 1.5 mm ferrule stub),
panel-tsd/ and brain/ positions, heatsink fin height
(Toradex datasheet not retrieved), the TSD tab width and FPC exit side, the F32Q seating depth, and
stand-in boxes for parts with no library 3D model: the four FFC connectors on gauges/ (2.0 mm), the
SODIMM socket (5.2 mm), and several small ICs and FETs (1.2 mm). The ring, cup and gauge spacing
come from the owner's photos and calipers.
