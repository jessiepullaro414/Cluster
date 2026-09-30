# Cluster

Digital restomod instrument cluster for a 1966 Mustang: round displays in the stock round holes, custom reprinted faceplate, stock outer dash opening (457.2 x 116.69mm hard limit, 441.09 x 105.54mm inner).

The center gauge runs Android Automotive; the four small gauges are driven by a separate MCU board. Both boards share a CAN bus with `ecu-pcb`.

## Boards

| Dir | Role | Core | Board |
|---|---|---|---|
| [display/](display/) | Android center gauge | Toradex Verdin iMX95 SoM, 4in 800-nit round MIPI-DSI panel | ~113 x 106mm |
| [gauges/](gauges/) | 4 small aux gauges + resistive sender front end | NXP S32K144, 4x GC9A01 round SPI | 447.1 x 42.6mm |

Both are schematic ERC-clean, fully routed, DRC-clean, and have generated BOMs (`ClusterDisplay_BOM.html`, `ClusterGauges_BOM.html`). CAN0 links display/, gauges/ and ecu-pcb. The data protocol is not designed yet.

Open items and rationale live in the working plan, not here. Panel: TSD TST040HDBC-42 (4in round, 800 nits, -30..+80C, fits the opening uncropped). Known TBDs: harness connectors J2/J3/J8/J9 on display/, the panel's unresolved +/-6.5V pin polarity (open solder jumpers JP1/JP2), CAN protocol, firmware.

## Workflow

Everything is generated from scripts. Never hand-edit the KiCad files; change the script and regenerate. In `display/` or `gauges/`:

```
python build_schematic.py   # schematic + ERC self-checks
python build_pcb.py         # placement + DRC-style self-checks
python route_board.py       # FreeRouting, verified against real kicad-cli DRC
python ../run_drc.py <Board>.kicad_pcb
python build_bom.py         # BOM with coverage/value-spelling checks
```

`route_board.py` needs `tools/freerouting-2.2.4.jar` (gitignored, ~57MB; download from the FreeRouting releases) and a JRE.

## Archive

[archive/](archive/) holds superseded work kept for reference only, not maintained:

- `single-board-s32k144-bt817aq/`: the original one-board design (S32K144 + BT817AQ + round ST7701S speedo + 4 GC9A01), fully routed 252/252 before the Android pivot.
- `.../sense-abandoned-bar-panel-attempt/`: an unfinished CAN-only sensor board from the abandoned wide bar-panel direction.

Scripts there use their old relative paths (`tools/`, `run_drc.py`) and will need adjusting to run.
