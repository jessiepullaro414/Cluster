# Depth stack-up: does it all fit behind the faceplate? (first pass, 2026-10-18)

This is a budget, not a CAD check. Every number names its source; the ones marked **unknown** have to be measured or come from a datasheet before the housing is drawn. Nothing here has been built.

## The space

| Item | mm | Source |
|---|---|---|
| Rim to the back plate of the stock cluster | about 60 (studs add about 8) | owner photos with a tape, 2026-10-08, about +/-5 mm (`mechanical-fit.md`) |
| Rim to the speedometer housing | about 85 | same photos |
| Rim to the speedometer cable fitting | about 113 | same photos |
| Speedometer cup: inside diameter, depth | about 102, about 36 | owner caliper, 2026-10-08 |
| Small cups: inside diameter, depth | about 47, about 25 | owner caliper, 2026-10-08 |
| Dash opening (outer, inner) | 457.2 x 116.69, 441.09 x 105.54 | owner drawing, 2026-09-23 |

The owner is making a new housing, so the stock depths are a guide to what the dash behind it allows, not hard limits.

## What has to fit, front to back, at the centre

| Layer | Thickness, mm | Source |
|---|---|---|
| Faceplate and cover glass | **unknown** (faceplate not drawn) | |
| TSD TST040HDBC-42 panel module | 7.8 | TSD datasheet V1.0 outline (`mechanical-fit.md`) |
| FPC to display/ (J4) | 69.8 +/- 0.5 long; bend radius **unknown** | TSD outline |
| display/ carrier PCB | 1.6 | fab stack-up (JLC04161H-7628) |
| Board to module gap (SODIMM 5.2 mm socket) | 2.0 to 3.0 (2.62 nominal) | Toradex Verdin Carrier Board Design Guide V1.2, Fig 112 |
| Verdin module PCB | 1.20 | same, Fig 112 |
| Module top-side components | **unknown**: use Toradex's maximum-height 3D model | Toradex developer site |
| Heatsink base, on the 7.0 mm S3/S4 standoffs | 7.0 above the carrier | design guide 4.4.1 |
| Verdin Industrial Heatsink fins | **unknown** (datasheet not retrieved; its thermal pad is 26 x 22 x 3.175 mm) | Toradex accessory page; asked in `rfq-drafts.md` section 2 |
| Tallest carrier parts on the other side | J17 USB-C receptacle, J2 / J11 / J14 / J15 headers: heights **unknown** here (read them from the footprint 3D models) | |

So the carrier with the module and heatsink is about 1.6 + 7.0 + fins deep, the panel is 7.8 deep, and the cable fitting depth of the stock cluster (about 113 mm) is far more than that needs. The real constraints are the ones still unknown: the heatsink fin height, the FPC bend between panel and carrier, and where air can reach the heatsink in a closed dash.

## Side by side

- display/ is now **178.2 x 105.0 mm** (2026-10-18: larger module keepout for the Verdin standoffs). Its 105.0 mm height uses almost all of the 105.54 mm inner opening, so it must sit behind the faceplate with its long side across the car, or the housing must allow for it.
- gauges/ is **447.1 x 63.4 mm**. Its four screen connectors now sit at +/-118 and +/-197 mm from the centre (owner photos). The inner modules (50.2 mm across) end 92.9 mm from the centre; display/ reaches 89.1 mm either side of its own centre. If both boards sit in one plane they overlap in height (105 + 63 > 116.7 mm), so they stack in depth: the likely arrangement is display/ directly behind the centre panel and gauges/ behind or below it, with the four small screens on FPC tails forward to the faceplate. **Not decided; needs the housing drawing.**

## Radios

The Verdin WB module's two U.FL antenna connectors need cables to antennas outside any metal: a 1966 dash is steel. The antennas belong on the plastic housing or behind a plastic window, spaced apart (`audio-and-usb.md` section 3). Without that, wireless Android Auto and CarPlay will not have range.

## Next measurements (calipers, about 10 minutes)

1. Centre-to-centre distance of the two inner small gauges (replaces the +/-118 mm photo estimate in `gauges/build_pcb.py`, `INNER_GAUGE_OFFSET_MM`).
2. Depth from the rim to the first metal behind the speedometer and behind the small gauges.
3. The free height and width behind the opening where the boards would sit.
