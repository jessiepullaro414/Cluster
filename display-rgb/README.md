# display-rgb: display carrier variant for a parallel-RGB round panel

A copy of `display/` (2026-10-08, brought up to date with it on 2026-10-19: Verdin standoffs, SQJ460AEP FETs, audio, USB-C, MFi header, six layers) with an **LVDS-to-RGB bridge** added, to try the Anders 4.2 in circular display (part 12575: 720 x 720, 1300 nits, RGB, -30 to +85 C, 105.84 mm active circle; [specifications](https://www.andersdx.com/4.2inch-circular-high-bright-ipstft-display/?tab=specifications)). `display/` is unchanged and still targets the TSD 4.0 in MIPI panel.

**Status: schematic, BOM, placement and routing done (six layers, 229.8 x 105.0 mm). NOT a fab candidate:** the panel's datasheet (connector, pinout, supply voltages, logic level, backlight) has not been received, so the panel connector is a placeholder and the routing to it will change.

## What was added

| Part | Role | Source |
|---|---|---|
| `U16` DS90CF384AQ-Q1 (TSSOP-56) | LVDS receiver: Verdin LVDS0 (4 data lanes + clock) to 24-bit RGB + HS/VS/DE/PCLK. AEC-Q100 Grade 3 (-40..+85 C), 20-65 MHz | TI SNLS345A pin diagram and Figure 3 mapping; orderable DS90CF384AQMTX/NOPB, Active/Production per TI's 11-Nov-2025 package addendum |
| `U17` TLV733P-Q1 | 3.3 V LDO from +5V for the receiver (rail `+3V3_RGB`) | same part gauges/ uses |
| `J18` | **PLACEHOLDER** 50-pin 0.5 mm FPC for the panel, pin order invented | to be replaced from the Anders datasheet |
| `R75`-`R79` | 100 ohm terminations across the five LVDS pairs (the datasheet documents no internal termination) | |
| `R80` | 10 k pull-up keeping PWR_DWN high (receiver always on) | |
| `C85`-`C93` | LDO capacitors, six 100 nF on the receiver supplies, 10 uF bulk | |

(Renumbered 2026-10-19 so the RGB parts no longer collide with display/'s audio, USB and MFi parts.)

Verdin side: LVDS0_D0..D3 and CLK (X1 pins 88-114) feed the receiver; SPI_1 (pins 196/200/202) and GPIO_4 (212; GPIO_2 became display/'s MFi reset) are routed to the panel connector for panel setup and reset. Bit mapping (datasheet Figure 3, recommended): R0-R4 = RxOUT0-4, R5 = 6, R6 = 27, R7 = 5; G0-G2 = 7-9, G3-G5 = 12-14, G6 = 10, G7 = 11; B0 = 15, B1-B4 = 18-21, B5 = 22, B6 = 16, B7 = 17; HS = 24, VS = 25, DE = 26. This is the VESA 24-bit lane layout (RxIN3 carries the top bits), so use the matching data mapping in the device tree.

## Checks that pass
ERC 0 violations; BOM coverage OK; DRC accepted categories only. 720 x 720 at 60 Hz needs roughly 36 MHz, inside the receiver's 65 MHz limit (a 1080 x 1080 panel would need about 80 MHz and would not work with this chip).

## Not known / not done (do not order from this board)
1. Panel connector, pinout, supply voltages (3.3 V vs 1.8 V logic), backlight LED current and voltage, and the dimming method. The existing TPS61165 backlight driver is sized for the TSD panel (182 mA) and is NOT connected to J18; `RGB_LEDA/LEDK` are left for a driver chosen once the datasheet arrives (1300 nits likely needs far more power).
2. Level shifting: the Verdin's SPI and GPIO are 1.8 V. If the panel's setup inputs need 3.3 V levels, a level shifter must be added.
3. The receiver's output clock strobes on the FALLING edge; check the panel's sampling edge. RxOUT23 is a reserved bit and left unconnected. Output series resistors (EMI) are not fitted.
4. LVDS routing quality: the pairs are autorouted over the In1 GND plane, but not length-matched or impedance-controlled, and cross each other near the receiver because the receiver's pin order is IN0, IN1, IN2, CLK, IN3 while the Verdin lists CLK, D0, D1, D2, D3.
5. The board is wider than display/ (229.8 mm vs 178.2 mm) because the new cells share the top row; the TSD parts are all still fitted. Pruning the DSI-only parts (J4, bias converter, JP1/JP2) would win most of that back.

## Routing status (2026-10-19): routed, 0 unconnected

Six layers, routed by `route_board.py` with **0 unconnected items** under the independent `kicad-cli` DRC. Remaining DRC errors are the same accepted categories as display/: `solder_mask_bridge` x10 at the open JP1/JP2 jumpers and `hole_clearance` x4 at the USB-C receptacle's own pegs. `review/layout_checks.py display-rgb` confirms no track of any net on In1 or In4.

The 2026-10-08/09 four-layer attempts never closed: LVDS and RGB nets on In1 split the GND pour into islands, leaving 2 or 3 GND pads open at the receiver and at J1. On six layers In1 and In4 carry only GND (FreeRouting may drop vias into them but not route along them), so that failure mode is gone. `route_board.py` still fences the DSI corridor per layer and verifies it afterwards.

## Build
Same chain as `display/`: `python build_schematic.py`, `python build_pcb.py`, `python route_board.py` (FreeRouting jar in `../tools`), `python ../run_drc.py ClusterDisplayRGB.kicad_pcb`, `python build_bom.py`, `python ../review/layout_checks.py display-rgb`.
