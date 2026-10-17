# Cluster

**How to run everything: [RUNNING.md](RUNNING.md).**

Digital restomod instrument cluster for a 1966 Mustang: round displays in the stock round holes, custom reprinted faceplate, stock outer dash opening (457.2 x 116.69mm hard limit, 441.09 x 105.54mm inner).

The center gauge runs Android Automotive; the four small gauges are driven by a separate MCU board. Both boards share a CAN bus with `ecu-pcb`.

## Boards

| Dir | Role | Core | Board |
|---|---|---|---|
| [display/](display/) | Android center gauge, wireless Android Auto / CarPlay host with sound | Toradex Verdin iMX95 WB SoM, 4in 800-nit round MIPI-DSI panel, TAC5112-Q1 audio codec, USB-C host port | 169.3 x 101.8mm |
| [display-rgb/](display-rgb/) | Variant of display/ with an LVDS-to-RGB bridge for a parallel-RGB round panel (Anders 4.2 in, 1300 nits); placement only, not routed | same as display/ + TI DS90CF384AQ-Q1 | about 211 x 102mm |
| [gauges/](gauges/) | 4 small aux gauges, resistive sender front end, Hall speed, tach and six 12 V indicator-lamp inputs | NXP S32K144, 4x GC9A01 round SPI | 447.1 x 58.3mm |

**Status: prototype, not yet ordered.** Both boards are routed with 0 unconnected nets and have generated BOMs (`ClusterDisplay_BOM.html`, `ClusterGauges_BOM.html`). display/ is ERC-clean (0 violations); gauges/ shows 4 known ERC items (a SWCLK pin, the MCU and buck supply pins flagged as undriven, and a `+5V` power-flag note). DRC on display/ reports 10 `solder_mask_bridge` errors that are the intentional open polarity jumpers JP1/JP2, 4 `hole_clearance` errors (the USB-C receptacle J17's own land pattern: its GND pads sit 0.194 mm from its locating pegs against the 0.25 mm default, see `fab/README.md`), plus silkscreen and library-copy warnings. Nothing has been fabricated, powered or firmware-tested. Mechanical fit in the dash is not yet checked against a 3D model, and gauges/ (447.1 mm) is wider than the 441.09 mm inner opening dimension, within the 457.2 mm outer limit.

## How the boards talk

gauges/ is the gateway. It is the only board that touches the car CAN bus (CAN0, receive-only in firmware) and it forwards filtered values to display/ over a private two-node CAN link (gauges/ CAN1 to display/ CAN). Android therefore cannot transmit on the vehicle bus. The protocol (`protocol/can_protocol.py`, revision 2) generates the DBC, a spec and a C header; the private link carries a rolling counter and CRC-8, and the car-bus side has a selectable Haltech V2 profile. Speed comes from a Hall-effect sender on gauges/ (for cable-driven cars) or from the ECU over CAN. gauges/ also reads six 12 V-active indicator lamps (left/right turn, high beam, brake, alternator, oil; each has a DNP pull-up for a ground-switched lamp). The two turn-signal arrows on the dash are physical: green LEDs (ROHM CSL0902ET1C) on gauges/, each lit straight from its turn-signal wire through a 1.8 k resistor so they flash like the old bulbs even with the software off (their X positions are placeholders until the faceplate drawing exists) and a tach input (ECU or coil-driver output; coil-negative on a points ignition is not validated), sent to display/ in the `Indicators` message (which also carries the dimmer level) and the `Rpm` signal. display/ has a rotary-dial input (J11), an ignition wake circuit, an audio path (balanced stereo line-out J14 and a microphone J15 on a TI TAC5112-Q1 codec), a USB-C host port (J17, 1.5 A, for a phone or a wireless-projection dongle), a reserved DNP access point for Apple's MFi coprocessor (J16) and bench headers for the A55 console UART (J12), USB (J13), JTAG (J8) and buttons (J9).

## Known limits of the layouts

- Both boards are four-layer with GND on In1 and +5V / +3V3 poured on In2, but they are not solid planes: slow signals were routed on the inner layers by the autorouter and the pours fill around them. On display/ about 1.46 m of signal wiring sits on In1 (none inside the DSI corridor; it was about 0.9 m before the audio and USB blocks were added on 2026-10-16) and about 0.88 m on In2; 0.02 m is on B.Cu. That includes the USB 2.0 pair (about 58 mm on In1, 15 mm on F.Cu) and long runs of the analog line-out and microphone nets: nothing keeps them off the inner layers, so hand-route or fence them before fab if the bench shows noise or a flaky USB link. A GND pour was also added on B.Cu (2026-10-17) because, in the dense audio block, many signal vias split the In1 plane into islands and left GND vias unconnected. On gauges/ about 3.9 m sits on In1 and 5.1 m on In2, because it is a 447 mm board with long runs to four displays. Forbidding signals on In1 left 6 to 122 connections unrouted, so it was not adopted.
- The panel DSI lanes on display/ are routed by `dsi_route.py` (about 10.6 to 11.2 mm per leg, at most 0.6 mm skew inside a pair) with an estimated 100 ohm differential geometry that has not been checked with a field solver.
- The panel connector, the panel polarity jumpers and the wake-pin polarity are unconfirmed (see `fab/README.md`).

Open items and rationale live in the working plan, not here. Panel: TSD TST040HDBC-42 (4in round, 800 nits, -30..+80C, 101.52 mm active circle: fits the 105.54 mm dash opening height, but NOT a stock 89.26 mm speedometer hole without cropping, see `docs/mechanical-fit.md`). Known TBDs: harness connectors J2/J3/J8/J9 on display/, the panel's unresolved +/-6.5V pin polarity (open solder jumpers JP1/JP2), CAN protocol, firmware.

## Wireless Android Auto / CarPlay hardware (2026-10-16)

Required by the owner. display/ carries the physical pieces: audio codec and connectors, a USB-C host port, the Verdin WB module's Wi-Fi 6 / Bluetooth 5.4 (antennas are a mechanical item) and a reserved DNP MFi access point. **Licensing (Apple MFi for CarPlay, Google's Android Auto receiver terms) is a separate business gate (plan item B5) that hardware does not solve.** Wiring, antenna rules, software bring-up and what is unverified: [docs/audio-and-usb.md](docs/audio-and-usb.md).

## Workflow

Everything is generated from scripts. Never hand-edit the KiCad files; change the script and regenerate. In `display/` or `gauges/`:

```
python build_schematic.py   # schematic + ERC self-checks
python build_pcb.py         # placement + DRC-style self-checks
python route_board.py       # FreeRouting (display/ also adds the DSI pairs), verified against real kicad-cli DRC
python ../run_drc.py <Board>.kicad_pcb
python build_bom.py         # BOM with coverage/value-spelling checks
```

`route_board.py` needs `tools/freerouting-2.2.4.jar` (gitignored, ~57MB; download from the FreeRouting releases) and a JRE.

## Archive

[archive/](archive/) holds superseded work kept for reference only, not maintained:

- `single-board-s32k144-bt817aq/`: the original one-board design (S32K144 + BT817AQ + round ST7701S speedo + 4 GC9A01), fully routed 252/252 before the Android pivot.
- `.../sense-abandoned-bar-panel-attempt/`: an unfinished CAN-only sensor board from the abandoned wide bar-panel direction.

Scripts there use their old relative paths (`tools/`, `run_drc.py`) and will need adjusting to run.
