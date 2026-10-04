# Cluster

Digital restomod instrument cluster for a 1966 Mustang: round displays in the stock round holes, custom reprinted faceplate, stock outer dash opening (457.2 x 116.69mm hard limit, 441.09 x 105.54mm inner).

The center gauge runs Android Automotive; the four small gauges are driven by a separate MCU board. Both boards share a CAN bus with `ecu-pcb`.

## Boards

| Dir | Role | Core | Board |
|---|---|---|---|
| [display/](display/) | Android center gauge | Toradex Verdin iMX95 SoM, 4in 800-nit round MIPI-DSI panel | about 152 x 102mm |
| [gauges/](gauges/) | 4 small aux gauges, resistive sender front end, Hall speed, tach and six 12 V indicator-lamp inputs | NXP S32K144, 4x GC9A01 round SPI | 447.1 x 58.3mm |

**Status: prototype, not yet ordered.** Both boards are routed with 0 unconnected nets and have generated BOMs (`ClusterDisplay_BOM.html`, `ClusterGauges_BOM.html`). display/ is ERC-clean (0 violations); gauges/ shows 4 known ERC items (a SWCLK pin, the MCU and buck supply pins flagged as undriven, and a `+5V` power-flag note). DRC on display/ reports 10 `solder_mask_bridge` errors that are the intentional open polarity jumpers JP1/JP2, plus silkscreen and library-copy warnings. Nothing has been fabricated, powered or firmware-tested. Mechanical fit in the dash is not yet checked against a 3D model, and gauges/ (447.1 mm) is wider than the 441.09 mm inner opening dimension, within the 457.2 mm outer limit.

## How the boards talk

gauges/ is the gateway. It is the only board that touches the car CAN bus (CAN0, receive-only in firmware) and it forwards filtered values to display/ over a private two-node CAN link (gauges/ CAN1 to display/ CAN). Android therefore cannot transmit on the vehicle bus. The protocol (`protocol/can_protocol.py`, revision 2) generates the DBC, a spec and a C header; the private link carries a rolling counter and CRC-8, and the car-bus side has a selectable Haltech V2 profile. Speed comes from a Hall-effect sender on gauges/ (for cable-driven cars) or from the ECU over CAN. gauges/ also reads six 12 V-active indicator lamps (left/right turn, high beam, brake, alternator, oil; each has a DNP pull-up for a ground-switched lamp) and a tach input (ECU or coil-driver output; coil-negative on a points ignition is not validated), sent to display/ in the `Indicators` message and the `Rpm` signal. display/ has a rotary-dial input (J11), an ignition wake circuit, and bench headers for the A55 console UART (J12), USB (J13), JTAG (J8) and buttons (J9).

## Known limits of the layouts

- Both boards are four-layer with GND on In1 and +5V / +3V3 poured on In2, but they are not solid planes: slow signals were routed on the inner layers by the autorouter and the pours fill around them. On display/ about 925 mm of signal wiring sits on In1 (none inside the DSI corridor, none under the +5V buck or the backlight boost, about 17 mm under the panel-bias converter) and about 790 mm on In2. On gauges/ about 3.9 m sits on In1 and 5.1 m on In2, because it is a 447 mm board with long runs to four displays. Forbidding signals on In1 left 6 to 122 connections unrouted, so it was not adopted.
- The panel DSI lanes on display/ are routed by `dsi_route.py` (about 10.6 to 11.2 mm per leg, at most 0.6 mm skew inside a pair) with an estimated 100 ohm differential geometry that has not been checked with a field solver.
- The panel connector, the panel polarity jumpers and the wake-pin polarity are unconfirmed (see `fab/README.md`).

Open items and rationale live in the working plan, not here. Panel: TSD TST040HDBC-42 (4in round, 800 nits, -30..+80C, fits the opening uncropped). Known TBDs: harness connectors J2/J3/J8/J9 on display/, the panel's unresolved +/-6.5V pin polarity (open solder jumpers JP1/JP2), CAN protocol, firmware.

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
