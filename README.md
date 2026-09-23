# Cluster — KiCad schematic + PCB

Companion KiCad project for "Cluster": a fully digital instrument cluster
that drops into a **stock 1966 Ford Mustang gauge housing**. Sibling to
[`manifold-pcb`](https://github.com/jessiepullaro414/Manifold),
[`ecu-pcb`](https://github.com/jessiepullaro414/ecu-pcb), and
[`thermo-pcb`](https://github.com/jessiepullaro414/Thermo) — same
12V/automotive-grade discipline, same kiutils/kicad-cli script-driven
workflow (see the sibling projects' READMEs for the toolchain itself).

## Status

**Schematic is fully wired and ERC-clean as of 2026-09-22.** All 6 steps
of the build-out plan are done: S32K144 peripheral pin-mux (real, from
NXP's own Reference Manual), CAN0 transceiver (reused from `ecu-pcb`),
4x GC9A01 aux gauges (real Raystar pinout), BT817AQ speedo co-processor
+ ST7701S module (real Bridgetek/Panox pinouts — including a genuinely
new VCC1V2 LDO rail this required, see below), the sensor ADC front
end, and the CAN0+sensor harness connector. `kicad-cli sch erc` is down
to exactly the 4 baseline tool-limitation findings every sibling
board's *finished* schematic carries (power pins ERC can't trace
through a passive; SWCLK driven off-sheet by the debug probe) — zero
unexpected results, zero guessed pins or values anywhere in the file.

**Not started yet:** PCB layout, routing, DRC, and BOM. Also still
open: the physical bezel outer-envelope measurement (README's own open
item below) and the firmware CAN-vs-local-sender priority policy —
neither blocks starting PCB layout.

## Why this project exists

The stock '66 Mustang cluster (2 small gauges — 1 large speedo — 2 small
gauges, chrome bezel) is being replaced with 5 independent digital
displays, one per opening, driven by real sensor data — either the car's
**existing resistive senders** (fuel, oil pressure, coolant temp) read
directly, or **digital values over CAN** from `ecu-pcb` when it's
installed. The **outer bezel envelope must stay stock** so the cluster
still fits the factory dash cutout with no cutting; the individual gauge
*openings* are free to grow, because the chrome faceplate itself is being
reprinted rather than reused.

## Real mechanical reference (user-supplied dimensioned drawing, 2026-09-23)

The user supplied a real dimensioned reference drawing — **the
*inside* dash-opening dimensions, not the decorative outer chrome
bezel** (that's a separate, larger trim piece that overlaps the dash
surface around this opening; not dimensioned here) — with all 5 gauge
openings called out via a width x height / diameter legend. This
supersedes the earlier web-researched approximations below, which are
kept only for the sender/sensor research that's still independently
useful.

| Feature | Size (real, from the reference drawing) |
|---|---|
| Dash opening (outer, the hole everything must fit through) | 18.00" x 4.594" (457.2 x 116.69mm) |
| Inner panel dimension (inside the opening) | 17.361" x 4.155" (441.09 x 105.54mm) |
| Center speedo opening | dia 3.60" (91.44mm) |
| 4x auxiliary gauge openings | dia 1.810" each (45.97mm) |

**This closes the "overall bezel outer envelope" open item** — PCB
layout can now target a real outline that fits within this dash
opening (18.00" x 4.594" is the hard outer limit; 17.361" x 4.155" is
the real usable inner dimension once inside it). The separate chrome
trim ring shown in the very first reference photo is NOT yet
dimensioned — it's cosmetic (screws to the dash face over this
opening) and doesn't constrain the board's own size the way the
opening itself does. Exact hole-center X positions along the row
aren't individually dimensioned on the drawing — inferred
proportionally from it for first-pass placement, refined once real FPC
connector positions are chosen during layout.

Earlier web research (kept for the sender/sensor findings, which don't
depend on the exact bezel dimensions):
- Speedo opening was earlier estimated at 3-3/8" (85.7mm) face / 3-7/16"
  (87.3mm) mount hole — the real drawing's 3.60" (91.44mm) is close but
  not identical; use the real drawing's number.
- Aux gauge openings were earlier estimated at 2-1/16" (52.4mm) stock —
  the real drawing's 1.810" (45.97mm) is meaningfully smaller; use the
  real drawing's number. (The "up to 2-5/8" with a modified bezel"
  headroom claim was about reproduction-housing tolerance, not this
  specific drawing — worth a sanity check once real displays are in
  hand, but the reprinted-faceplate opening can be sized to whatever the
  chosen display module actually needs regardless.)

## Real sensor reference (verified against '65-'66 Mustang service data)

All four stock small-gauge positions share the same resistive-sender
gauge movement, **except** the "amp" gauge, which Ford wired in 1966 as a
voltage-drop sensor in series with the charging circuit, not a true
resistive sender — the common owner upgrade (confirmed across multiple
Mustang forums) is to just wire a real voltmeter into that position
instead of reproducing the factory ammeter's quirky behavior. Digital
Cluster does the same: that position reads **battery/alternator voltage
directly** through a divider, no sender curve needed.

The other three are genuine non-linear resistive senders (same
"log-scale, firmware does the lookup" treatment `thermo-pcb` already
uses for its own resistive temp sender):

| Gauge | Sender range | Reference points |
|---|---|---|
| Fuel level | ~10Ω (full) – ~73Ω (empty) | wire-wound rheostat float sender |
| Oil pressure | ~10Ω (full pressure) – ~70Ω (zero) | log scale — halfway reads 31.6Ω, not 40Ω |
| Coolant temp | ~10Ω (250°F) – ~300Ω (70°F) | genuine Ford spec: 19Ω @ 200°F |

Firmware scope this adds (same category as `thermo-pcb`'s NTC lookup):
3 non-linear resistance-to-value lookup tables, plus one linear
voltage-divider scale for the 4th position.

## Electrical architecture (locked 2026-09-22)

Two decisions were made explicitly rather than guessed:

1. **One hub board, one MCU, 5 SPI-driven displays** — not 5 independent
   smart-display modules on a backbone bus. Matches how `manifold-pcb`
   and `thermo-pcb` are built (single board, single BOM, single firmware
   image) rather than `fascia-pcb`'s split-board approach, which only
   exists there because that panel is physically detached across the
   dash — Cluster's 5 openings are all in one housing, so there's no
   equivalent reason to split.
2. **Center speedo stays large-format, the 4 aux positions keep their
   classic sender-driven roles** (fuel / coolant temp / oil pressure /
   battery voltage) rather than repurposing a position for a
   CAN-sourced tach — keeps the cluster reading like the original car at
   a glance.

**Displays** (both real, sourceable SPI round TFT parts):
- **4x auxiliary gauges:** GC9A01 driver, 1.28", 240x240, IPS, genuine
  4-wire SPI (SCK/MOSI/CS/DC/RST — 5 signal pins, no parallel bus). Fits
  comfortably inside the stock 2-1/16" opening with room to spare, or the
  up-sized 2-5/8" opening if the faceplate goes bigger.
- **1x center speedo:** ST7701S driver, 2.1", 480x480, IPS. This part is
  configured over a thin SPI control link but its actual pixel data path
  is an **18-bit parallel RGB bus**, not 4-wire SPI — a meaningfully
  bigger GPIO/bandwidth cost than the 4 aux displays, not just "a bigger
  version of the same wiring." Flagged as its own interface class for the
  MCU pin-budget pass below.

**Data sources, both live at once:**
- **CAN:** reuse `ecu-pcb`'s real TJA1043T transceiver + FlexCAN wiring
  pattern, one channel tied to the vehicle/`ecu-pcb` bus, for cars running
  that ECU.
- **Local senders:** ADC channels + pull-up dividers reading the fuel/
  oil/temp senders directly (same divider-into-ADC topology `thermo-pcb`
  uses for its own resistive sender) plus one divider on battery voltage
  — for cars without `ecu-pcb`, or as a live fallback when it's present
  but not transmitting.
- Both paths are wired in hardware simultaneously; which one a given
  gauge trusts at any moment is a **firmware policy**, not a board
  variant or a physical switch (open item below).

**MCU:** defaults to NXP S32K144 (the same AEC-Q100 Cortex-M4F part
`manifold-pcb`/`thermo-pcb` already use) rather than `ecu-pcb`'s
Qorivva MPC5606B — Cluster has no microsecond-level real-time firing to
do, so there's no reason to inherit the Qorivva's eMIOS-class timing
hardware.

## MCU pin/peripheral budget (real, verified 2026-09-22)

*Update, same day:* the real pin-by-pin assignment (which physical
S32K144 pad each LPSPI/FlexCAN0/ADC/GPIO signal lands on) is now done —
see `build_schematic.py`'s own citation comment above U1's registration
for the full real list, pulled from the Reference Manual's own embedded
IO-signal-table attachment. The budget estimate below held up: 25 real
pins claimed, no conflicts, comfortable headroom left on the 64-pin
package.

Pulled directly from NXP's own S32K1xx Data Sheet (Rev. 15, 5 March 2026,
Figure 3 "S32K1xx product series comparison" — the real per-part
comparison table, not a generic family blurb). **S32K144 real numbers:**
80 MHz (112 MHz HSRUN), up to 89 I/Os (100-pin LQFP/100-pin MAPBGA
package — the 64-pin LQFP `manifold-pcb`/`thermo-pcb` use has fewer),
**3x LPSPI**, **3x FlexCAN** (1 with CAN-FD), **2x 12-bit ADC x 16
channels = 32 channels total**, **1x FlexIO with only 8 configurable
pins** (documented purpose: UART/SPI/I2C/I2S protocol emulation — not
sized for a parallel display bus), no dedicated LCD/display controller
peripheral of any kind.

**The 4 aux gauges + CAN + local senders fit easily, even on the small
64-pin package**: 1 shared LPSPI bus (SCK+MOSI) + 4 CS + 4 DC + 1 shared
RST for the GC9A01s (~11 pins), 1 FlexCAN instance (2 pins), 4 ADC
channels (fuel/oil/temp/battery), plus the ~9 fixed pins every sibling
board already reserves for crystal/SWD/RESET/power — comfortably under
the ~58 GPIO the 64-pin package leaves after fixed pins.

**The center ST7701S speedo is a real, confirmed blocker, not a tight
budget.** Pulled Sitronix's real ST7701S datasheet (Preliminary V0.1,
2016/12) directly: its own Features section states it is a
**"Single chip WVGA a-Si TFT-LCD Controller/Driver *without Display
RAM*."** Checked the full IM[3:0] interface-mode table (Table 10, all 9
valid combinations) — every single mode is either MIPI DSI or
`RGB + n-bit SPI`, and in every RGB mode the SPI lines (CSX/SCL/SDA/DCX)
are documented as command/register-only; actual pixel data always goes
over the 16-24 line parallel `DB[23:0]` bus plus PCLK/VS/HS/DE. There is
no SPI-only mode with internal frame buffer, unlike the aux gauges'
GC9A01 (which does have internal GRAM and is genuinely SPI-only). That
means the host has to continuously stream a live video signal at the
panel's real refresh rate for as long as the display is on — and the
S32K144 has neither the ~20+ spare dedicated pins nor any peripheral
(FlexIO's 8 pins are the closest thing, and aren't remotely enough) to
generate that signal. **This isn't a pin-count-is-tight problem, it's a
peripheral-doesn't-exist problem** — no amount of re-budgeting the aux
gauges' pins fixes it.

## Center speedo: display co-processor (decided 2026-09-22)

Real, automotive-qualified answer found and chosen — a **Bridgetek
BT817AQ** ("BT817A Automotive Advanced Video Engine"), verified directly
from its own datasheet:

- **AEC-Q100 Grade 2** (-40 to 105°C), VQFN-64 — genuinely automotive,
  not a consumer part pressed into service.
- **QSPI to the host MCU** (up to 30MHz, SPI mode 0, single/dual/quad
  configurable) — a third LPSPI instance on the S32K144 (of the 3
  available, with one already used for the aux gauges) drives this with
  no contention.
- **29-signal parallel RGB output** (DISP/PCLK/VSYNC/HSYNC/DE + 8 bits
  each R/G/B), PCLK up to 96MHz, natively supports 1280x800/800x600/
  800x480 and is register-programmable for any timing in between —
  480x480 is comfortably within range. This feeds the ST7701S module's
  RGB input directly; BT817AQ becomes the thing that continuously
  generates the video stream the ST7701S needs, not the S32K144.
- Real bonus, not just a workaround: BT817AQ is part of Bridgetek's
  **EVE (Embedded Video Engine)** family — it has on-chip "Display List
  RAM" and a command-list graphics engine (lines, arcs, rotated bitmaps,
  text), so the S32K144 sends compact drawing commands ("needle at this
  angle") over QSPI rather than pushing a raw framebuffer — meaningfully
  simpler firmware than bit-pushing would have been even if the S32K144
  *could* drive the RGB bus itself.

This keeps the "one hub MCU reads sensors/CAN and makes decisions"
architecture intact — BT817AQ is a fixed-function rendering helper, the
same role `fascia-pcb`'s SN65DSI85-Q1 bridge plays for its own display,
not a second brain.

*Update 2026-09-22 (plan Step 4, now done):* pin-level wiring is
complete — the ST7701S module's 3-wire serial init (SDA/SCK/CS, plus a
4th spare GPIO for its RESET pin) lands on BT817AQ's own spare GPIO0-3,
keeping speedo init self-contained as planned. One real thing the
architecture pass above didn't catch: BT817A's digital core rail
(VCC1V2) turned out to be a genuine external 1.28V supply, not
internally regulated from VCC — a new TPS7A16-Q1 adjustable LDO
(AEC-Q100) + FB divider was added specifically for it. Real RGB666
wiring (BT817AQ's 24-bit RGB output down to the module's 18-bit input)
follows the module's own documented bit order, not a guess.

## Known open items (real, not placeholder — none of this is guessed)

1. **Overall bezel outer envelope** — needs a real caliper measurement of
   the physical stock cluster, not a web lookup. This is now the
   binding blocker on PCB layout specifically: the board's real shape
   has to roughly match the bezel's own 2-small/1-large/2-small plan
   view (see `build_schematic.py`'s own header on why this is genuinely
   new territory, not a copy of any sibling board's sizing model).
2. **Firmware source-priority policy** (CAN vs. local sender per gauge,
   and fallback behavior) — doesn't block hardware work, needed before
   firmware bring-up.
3. **PCB layout: placement done 2026-09-23, DRC-clean (unrouted).**
   `build_pcb.py` places all 74 real parts. The 5 display connectors
   (J3 speedo + 4x GC9A01 aux gauges) sit in a row along the board's
   bottom edge at evenly-spaced X positions (real hole-center spacing
   isn't individually dimensioned in the user's reference image, only
   sizes — explicit, flagged estimate, confirmed with the user as the
   right way to proceed rather than blocking). Everything else is
   organized into real functional zones spread across the full width —
   each display gets its own small local cluster of support parts
   directly above it (backlight resistor/cap; the speedo's whole
   BT817AQ+LDO+crystal subsystem sits above J3), and the board-wide
   subsystems (power input, MCU, CAN0, the aux-gauge backlight switch,
   the sender dividers) are arranged left-to-right above those.

   Board is **447.1 x 51.3mm**. The width genuinely can't shrink below
   the real 441mm target (the 5 connectors have to reach across the
   dash opening's real width to land under their own gauge holes,
   regardless of how little circuitry exists) — but the height started
   at 102.5mm only because the code anchored the display row to the
   *opening's own* 105.5mm inner height, which nothing actually
   requires the board to fill (user: "i think we can make it smaller.
   no reason to make it so big right?" — correct). Reworked to size
   height from the real, packed content instead (bottom margin +
   display row + each display's own local cluster + the core
   subsystems, stacked) — landed at 51.3mm, under half the original,
   still comfortably inside the 116.69mm hard limit.

   Front silkscreen also marks where each of the 5 real display modules
   actually sits (user: "where are the screens?") — the GC9A01/ST7701S
   glass isn't a PCB footprint (it's off-board, plugged into a small
   edge connector via FPC), so nothing round showed up in a render by
   default. A real circle at each display's position, sized from its
   own datasheet Active Area spec (32.4mm aux gauges, 53.28mm speedo),
   is a genuine mechanical reference for checking alignment against the
   reprinted faceplate, not just decoration.

   Back silkscreen carries an original tachometer-face design (0-8
   sweep, redline arc, resting needle, "x1000 RPM" caption) plus a
   CLUSTER wordmark — replacing the reused sibling-board logo per user
   request ("make it look cool") — drawn directly as KiCad vector
   primitives, not traced from any existing artwork.

   `kicad-cli pcb drc` is clean except real, documented, expected
   findings: the same benign `lib_footprint_mismatch` category every
   sibling board's finished PCB carries, plus silk-clearance findings
   from the screen-outline circles (deliberately bigger than their own
   connector, by design — the real glass overhangs it).

   **6 real M3 mounting/standoff holes added** (4 corners + 2 along the
   top edge) — a board this long and thin needs more than 2 support
   points to avoid real flex/vibration in a dash-mounted automotive
   environment. Adding them shrank the tach-face artwork's own safe
   drawing area, which surfaced two more real bugs, both fixed: the
   first attempt placed the 2 extra holes at naive 1/3 and 2/3
   board-width fractions and landed directly on real components (fixed
   by using the actual empty gaps between core zones instead of a
   guessed position), and the gauge face's internal tick/number/caption
   sizes were tuned for its original ~42mm radius and didn't shrink
   when the real safe area forced a smaller radius, causing real
   overlapping numbers (fixed by scaling every internal offset and text
   size proportionally to the actual radius).

   **Not done yet:** routing, a real board-outline shape (currently a
   plain rectangle — the real housing has a scalloped/contoured
   profile, not a rectangle), and BOM.
