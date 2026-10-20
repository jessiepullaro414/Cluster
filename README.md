# Cluster

**How to run everything: [RUNNING.md](RUNNING.md).**

Digital restomod instrument cluster for a 1966 Mustang: round displays in the stock round holes, custom reprinted faceplate, stock outer dash opening (457.2 x 116.69mm hard limit, 441.09 x 105.54mm inner).

The center gauge runs Android Automotive; the four small gauges are driven by a separate MCU board. Both boards share a CAN bus with `ecu-pcb`.

## Boards

| Dir | Role | Core | Board |
|---|---|---|---|
| [display/](display/) | Android center gauge, wireless Android Auto / CarPlay host with sound | Toradex Verdin iMX95 WB SoM (screwed down on M2 standoffs, heatsink-ready), 4in 800-nit round MIPI-DSI panel, TAC5112-Q1 audio codec, USB-C host port | 178.2 x 105.0mm |
| [display-rgb/](display-rgb/) | Variant of display/ with an LVDS-to-RGB bridge for a parallel-RGB round panel (Anders 4.2 in, 1300 nits); routed, but its panel connector is a placeholder until the panel datasheet arrives, so not a fab candidate | same as display/ + TI DS90CF384AQ-Q1 | 229.8 x 105.0mm |
| [gauges/](gauges/) | 4 small aux gauges, resistive sender front end, Hall speed, tach and six 12 V indicator-lamp inputs | NXP S32K144, 4x GC9A01 round SPI | 447.1 x 63.4mm |

**Status: prototype, not yet ordered.** Both boards are six-layer (2026-10-19) and routed with 0 unconnected nets and have generated BOMs (`ClusterDisplay_BOM.html`, `ClusterGauges_BOM.html`). display/ is ERC-clean (0 violations); gauges/ shows 4 known ERC items (a SWCLK pin, the MCU and buck supply pins flagged as undriven, and a `+5V` power-flag note). DRC on display/ reports 10 `solder_mask_bridge` errors that are the intentional open polarity jumpers JP1/JP2, 4 `hole_clearance` errors (the USB-C receptacle J17's own land pattern: its GND pads sit 0.194 mm from its locating pegs against the 0.25 mm default, see `fab/README.md`), plus silkscreen and library-copy warnings. Nothing has been fabricated, powered or firmware-tested. Mechanical fit in the dash is not yet checked against a 3D model, and gauges/ (447.1 mm) is wider than the 441.09 mm inner opening dimension, within the 457.2 mm outer limit.

**Product review, 2026-10-18** (`docs/electrical-review.md` section 8a): the Verdin module now has Toradex's four M2 standoffs (S1/S2 hold-down, S3/S4 for the Verdin Industrial Heatsink) and a keepout that follows the real module outline; the LM74930 FETs on both boards are Vishay SQJ460AEP (PowerPAK SO-8L) instead of the NRND SOT-23 PMV55ENEA; the gauges buck has the datasheet's 2.2 uH / 16 V output parts; the line-out ESD array is bidirectional; the panel-bias outputs use 16 V capacitors; the inner small gauges moved to the measured +/-118 mm. Still open before ordering: the TSD panel's pinout and connector (`docs/rfq-drafts.md` section 1), the Verdin module's availability and heatsink (section 2), the depth stack-up (`docs/mechanical-stackup.md`), the backlight driver's temperature (D-04), the small displays' -20 to +70 C rating (G-15, section 6), and licensing.

## How the boards talk

gauges/ is the gateway. It is the only board that touches the car CAN bus (CAN0, receive-only in firmware) and it forwards filtered values to display/ over a private two-node CAN link (gauges/ CAN1 to display/ CAN). Android therefore cannot transmit on the vehicle bus. The protocol (`protocol/can_protocol.py`, revision 2) generates the DBC, a spec and a C header; the private link carries a rolling counter and CRC-8, and the car-bus side has a selectable Haltech V2 profile. Speed comes from a Hall-effect sender on gauges/ (for cable-driven cars) or from the ECU over CAN. gauges/ also reads six 12 V-active indicator lamps (left/right turn, high beam, brake, alternator, oil; each has a DNP pull-up for a ground-switched lamp). The two turn-signal arrows on the dash are physical: green LEDs (ROHM CSL0902ET1C) on gauges/, each lit straight from its turn-signal wire through a 1.8 k resistor so they flash like the old bulbs even with the software off (their X positions are placeholders until the faceplate drawing exists) and a tach input (ECU or coil-driver output; coil-negative on a points ignition is not validated), sent to display/ in the `Indicators` message (which also carries the dimmer level) and the `Rpm` signal. display/ has a rotary-dial input (J11), an ignition wake circuit, an audio path (balanced stereo line-out J14 and a microphone J15 on a TI TAC5112-Q1 codec), a USB-C host port (J17, 1.5 A, for a phone or a wireless-projection dongle), a DNP 1x6 header (J16) for an Apple MFi coprocessor daughterboard, with I2C, reset and a GPIO-switched 5 V supply and bench headers for the A55 console UART (J12), USB (J13), JTAG (J8) and buttons (J9).

## Known limits of the layouts

- **Six layers, two solid GND planes (2026-10-19).** Stack-up JLC06161H-3313: F.Cu signal, In1 GND, In2 signal, In3 signal plus the +5V (display/) or +3V3 (gauges/) pour, In4 GND, B.Cu signal. Every net except GND gets a net-class layer restriction in the router input (`use_layer F.Cu In2.Cu In3.Cu B.Cu`; FreeRouting ignores a layer_rule "active off"), so In1 and In4 carry no track at all, only the GND fill and vias, and `review/layout_checks.py` fails a board if any other net lands there. Every outer-layer signal has a GND plane 0.0994 mm below it. In2 and In3 sit 0.55 mm from their planes and only 0.11 mm from each other, so a signal on one can couple broadside into the other. On display/ the USB-C phone pair (USB2_DP/DN, about 39 mm) runs about 30 mm on In3, both legs together; the bench USB pair on J13 has one leg on In2 and one on In3 (bench use only). Slow nets that cross a switch node in plan view on In2/In3 (PANEL_BIAS_EN and PANEL_BL_PWM after the 2026-10-20 re-route; `layout_checks.py`) now have the In1 plane between them and the outer-layer switch copper; PG_5V, the buck's own power-good pin, runs on F.Cu 0.15 mm from its switch copper beside U2. Until 2026-10-19 both boards were four-layer with signals routed through the GND and supply pours (about 1.5 m on display/, 9 m on gauges/). gauges/ routes VIN_PROT, VIN_FUSED and +5V at 0.4 mm from the start, and every power net on it now passes `layout_checks.py`'s 20 K current check. Details: `docs/electrical-review.md` section 8b.
- **Battery-path copper on display/ (2026-10-20).** VBAT_IN, VBAT_F, SENSE_OUT, COMMON and +12V_PROT (up to 2.6 A behind the 5 A fuse) now route on the 1 oz outer layers only, at 0.3 mm with 1.0/0.5 mm vias, and after widening each gets an F.Cu pour in a 2 mm band around its own copper (`route_board.py`, `BATTERY_PATH_NETS` and `add_battery_pours()`). No battery copper is on In2/In3 any more (until now about 60 mm of VBAT_F was, which IPC-2221 rates at about 1.3 A). `review/layout_checks.py` now rates each of these nets along the path the current takes (J2 -> F1 -> R1 -> Q2 -> Q1 -> the buck's VIN pins), counting the pour beside a track and the vias, and lists branch copper to milliamp pins (LM74930 sense pins, small caps) separately. R2 and C3 now sit on R1's input side (`display/cells.py`), so nothing lies between R1 and Q2. VBAT_IN, VBAT_F and SENSE_OUT pass; what is left are short necks where the path meets a pin: COMMON 2.0 mm at 0.3 to 0.7 mm at the FETs' source pins, +12V_PROT 2.3 mm at 0.31 to 0.64 mm at the buck's 0.4 mm VIN pins, each 7 mW or less at 2.6 A. Still worth a thermal-camera look at 2.5 A on the first board. display-rgb/ keeps the first route (SENSE_OUT neck beside R2, 12 mW) since it is to be replaced. Details: `docs/electrical-review.md` section 8b.
- **DSI geometry is field-solved.** `review/dsi_impedance.py` solves the four pairs (0.16 mm tracks on F.Cu over In1, 0.0994 mm prepreg) at Z0 51.8 ohm and 96.4 to 103.1 ohm differential for any gap from 0.25 to 1.2 mm; the layout's gaps are 0.34 mm along J1 and 0.44 mm along J4 (99.1 and 100.6 ohm). `dsi_route.py` keeps each leg about 9.5 to 10.2 mm with at most 0.62 mm skew inside a pair. This is a 2-D solve on the board house's nominal stack-up, not a measurement: order with controlled impedance and a coupon (`fab/README.md`).
- The panel connector, the panel bias-pin polarity (open jumpers JP1/JP2; a diode-test check before bridging is in `fab/README.md`) and the wake-pin polarity are unconfirmed. The panel bias rails are set to +5.98 V and -6.05 V, inside the ICNL9707 driver's 4.5 to 6.5 V operating range with margin to its 6.6 V absolute maximum (the panel sheet's 6.5 V is at the top of that range; question 8 in `docs/rfq-drafts.md`).

Open items and rationale live in the working plan, not here. Panel: TSD TST040HDBC-42 (4in round, 800 nits, -30..+80C, 101.52 mm active circle: fits the 105.54 mm dash opening height, but NOT a stock 89.26 mm speedometer hole without cropping, see `docs/mechanical-fit.md`). Harness connectors are decided for both boards (`docs/harness.md`, 2026-10-17). Known TBDs: the panel's unresolved bias-pin polarity (open solder jumpers JP1/JP2), measured sender curves (`docs/sender-calibration.md`: the dash shows the raw sender resistance for this), and everything that needs real hardware. The gauges firmware's key-off sleep (S32K144 VLPS, woken by the ignition line) is written and host-tested, not run on a board.

## Wireless Android Auto / CarPlay hardware (2026-10-16)

Required by the owner. display/ carries the physical pieces: audio codec and connectors, a USB-C host port, the Verdin WB module's Wi-Fi 6 / Bluetooth 5.4 (antennas are a mechanical item) and a reserved DNP MFi access point. **Licensing (Apple MFi for CarPlay, Google's Android Auto receiver terms) is a separate business gate (plan item B5) that hardware does not solve.** Wiring, antenna rules, software bring-up and what is unverified: [docs/audio-and-usb.md](docs/audio-and-usb.md).

## Workflow

Everything is generated from scripts. Never hand-edit the KiCad files; change the script and regenerate. In `display/`, `display-rgb/` or `gauges/`:

```
python build_schematic.py   # schematic + ERC self-checks
python build_pcb.py         # placement + DRC-style self-checks
python route_board.py       # FreeRouting (display/ also adds the DSI pairs), verified against real kicad-cli DRC
python ../review/layout_checks.py <dir>   # GND planes clean, switch-node spacing, fast-net layers, power-path current
python ../run_drc.py <Board>.kicad_pcb
python build_bom.py         # BOM with coverage/value-spelling checks
```

`route_board.py` needs `tools/freerouting-2.2.4.jar` (gitignored, ~57MB; download from the FreeRouting releases) and a JRE.

## Archive

[archive/](archive/) holds superseded work kept for reference only, not maintained:

- `single-board-s32k144-bt817aq/`: the original one-board design (S32K144 + BT817AQ + round ST7701S speedo + 4 GC9A01), fully routed 252/252 before the Android pivot.
- `.../sense-abandoned-bar-panel-attempt/`: an unfinished CAN-only sensor board from the abandoned wide bar-panel direction.

Scripts there use their old relative paths (`tools/`, `run_drc.py`) and will need adjusting to run.
