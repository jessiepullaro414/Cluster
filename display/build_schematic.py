#!/usr/bin/env python3
"""
build_schematic.py - generates ClusterDisplay.kicad_sch / ClusterDisplay.kicad_sym.

The display-carrier half of Cluster's Android Automotive re-architecture
(see cluster-pcb/README.md and the approved plan at
C:\\Users\\root\\.claude\\plans\\replicated-floating-tiger.md). Ported from
fascia-pcb/build_schematic.py - same real Verdin iMX95 SoM, same real
power tree (LM74930-Q1 + LM61460-Q1 + TLV767-Q1), same real CAN
transceiver (TCAN1044V-Q1) - with fascia's touchscreen-specific
subsystems (PCAP touch, USB-C, the PCM3168A-Q1 audio codec + level
shifters) removed, AND fascia's own SN65DSI85-Q1 DSI-to-LVDS bridge
removed too: this board drives ONE round MIPI-DSI panel behind the
dash's center opening (real target since 2026-09-30: Team Source
Display TST040HDBC-42, 4.0", 720x720, native MIPI-DSI, ICNL9707 driver,
800 nits, -30..+80 C, 101.5 mm active circle that fits the opening
uncropped - it replaced the 350-nit, 127 mm DisplayModule DM-TFTR50-413,
see build_panel()), and that panel speaks DSI natively, so
converting to LVDS and back would be pure overhead fascia's own board
needed (its target panel was LVDS-only) and this one doesn't. Same
script-driven discipline as every sibling project: this script is the
source of truth, never hand-edit the generated .kicad_sch/.kicad_sym.

RE-SCOPED 2026-09-25 (second time this board changed shape): first from
fascia's 10.1" rectangle to a wide bar panel (based on a real i.MX 95
display-pipe-count finding), then from the bar panel to a single round
panel once the user clarified the real intent - restomod, round
displays in the original round openings, with Android specifically on
the CENTER display (the i.MX 95 still only has 1 DSI + 1 LVDS pipe, so
it was never going to drive all 5 - see gauges/build_schematic.py for
where the other 4 round displays live now, wired locally, no OS).

Current stage: the Verdin iMX95 X1 module connector, the 12 V automotive
front end, the 5 V buck, the 1.8 V LDO, the CAN link (to ecu-pcb and to
gauges/'s own S32K144, which needs Android's aggregated gauge data
pushed to it - the user's own request, "the other displays need to get
data from android ... lets add some way for them to communicate"), a
direct MIPI-DSI panel connector (no bridge chip - see build_panel()'s
own docstring for why), the panel's +/-6.5 V bias rails (TPS65131-Q1)
and 15 V/180 mA backlight (TPS61165-Q1), and control/JTAG/RTC. Open:
the panel datasheet's pin table and drawing disagree on which FPC pins
carry +6.5 V vs -6.5 V (hedged with open solder jumpers JP1/JP2), and
its FPC connector (Hirose FH26, 0.3 mm) is inferred, not named.

What IS final at this stage:
  - all 260 X1 pins exist, banked into 5 units by verdin_x1.py (this
    board's own banking - CAN only in the comms bank, no touch/audio)
  - every GND pin is tied to ground, every VCC pin to the +5V rail
  - every pin this board does not use carries a real NoConnect item
  - LM74930-Q1, LM61460-Q1, TLV767-Q1 and TCAN1044V-Q1 are all fully
    wired, every pin netted or NoConnected
  - the module's CAN and full DSI link reach their destinations
"""
import json
import os
import subprocess
import sys
import uuid as uuid_lib

from kiutils.schematic import Schematic
from kiutils.symbol import Symbol, SymbolPin, SymbolLib
from kiutils.items.common import (Position, Property, Effects, Font, Stroke,
                                  Justify)
from kiutils.items.syitems import SyRect, SyPolyLine
from kiutils.items.schitems import (SchematicSymbol, Connection, LocalLabel,
                                    NoConnect, SymbolProjectPath,
                                    SymbolProjectInstance)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from verdin_pinout import X1_PINS                      # noqa: E402
import verdin_x1                                       # noqa: E402
import parts                                           # noqa: E402

LIB = "ClusterDisplay"
OUT_SCH = os.path.join(HERE, "ClusterDisplay.kicad_sch")
OUT_SYM = os.path.join(HERE, "ClusterDisplay.kicad_sym")
OUT_TABLE = os.path.join(HERE, "sym-lib-table")
OUT_PRO = os.path.join(HERE, "ClusterDisplay.kicad_pro")

# A0. The 260-pin connector alone fills an A2; adding the power tree,
# bridge, CAN and audio blocks filled A1 to the point where two sections
# collided and silently merged a net. Each block now gets its own band
# with real separation between them. This project's KiCad notes record that content
# running off a fixed sheet is invisible in the editor and only shows on
# a real fixed-size export, so main() checks every placement against the
# sheet bounds.
PAPER = "A0"
SHEET_W, SHEET_H = 1189.0, 841.0

GRID = 1.27
PITCH = 2.54          # pin-to-pin spacing down a symbol side
LEAD = 5.08           # pin lead length
UNIT_W = 63.5         # body width; wide enough for names like CTRL_RECOVERY_MICO#
STUB = 5.08           # wire length from a power pin out to its power symbol

# Verdin iMX95 pins that are genuinely supplies, not signals. Everything
# else on the connector is typed passive: this is a board-to-board
# connector, so ERC has no business inferring signal direction from it.
POWER_IN = {"GND", "VCC"}

# X1 signal pins that have somewhere to go. Anything not listed and not
# in X1_NC falls through to bank E's catch-all (real NoConnect) via
# verdin_x1.py's own banking - see that file's header for why this board's
# bank D (CAN only) is deliberately narrower than fascia-pcb's own.
X1_NETS = {
    "CAN_1_TX": "CAN1_TXD",     # module drives the transceiver's TXD
    "CAN_1_RX": "CAN1_RXD",     # transceiver's RXD drives the module
    # MIPI DSI into the SN65DSI85-Q1. These are the pairs that stay ON
    # the carrier - the long run to the panel is LVDS out of the bridge.
    "DSI_1_D0_P": "DSI_D0_P", "DSI_1_D0_N": "DSI_D0_N",
    "DSI_1_D1_P": "DSI_D1_P", "DSI_1_D1_N": "DSI_D1_N",
    "DSI_1_D2_P": "DSI_D2_P", "DSI_1_D2_N": "DSI_D2_N",
    # DSI_1_D3 is unused: the TST040HDBC-42 has three data lanes.
    "DSI_1_CLK_P": "DSI_CLK_P", "DSI_1_CLK_N": "DSI_CLK_N",
    # I2C_2_DSI_SDA/SCL dropped: that was the SN65DSI85-Q1 bridge's own
    # config bus, and there is no bridge on this board anymore (direct
    # DSI to the panel - see build_panel()'s own docstring). They fall
    # through to bank C's genuinely-unused pins.
    "GPIO_9_DSI": "DSI_PANEL_EN",
    # Rotary dial (2026-10-02): a 360-degree potentiometer with a push
    # switch, the way automakers add a controller to a screen with no touch.
    # The wiper reads on Verdin ADC_1 (X1 pin 2, ADC_IN0; the datasheet's
    # absolute maximum for ADC pins is 2.1 V, so the pot is powered from the
    # 1.8 V rail), the click on GPIO_1 (X1 pin 206, 1.8 V logic).
    "ADC_1": "DIAL_ADC",
    "GPIO_1": "DIAL_CLICK",
    # CTRL_SLEEP_MOCI# (X1 pin 256) is the module's "enable for carrier
    # peripherals that must be turned off during sleep" (datasheet), 1.8 V.
    # It switches the dial sensor's 5 V supply.
    "CTRL_SLEEP_MOCI#": "SLEEP_MOCI",
    # Ignition wake (rev B): Verdin datasheet Table 9/30 - pin 252 is the
    # default, only guaranteed-compatible wake-up pin, 1.8 V, "wake-capable
    # pin that allows the system to resume from sleep mode", also a regular
    # GPIO (GPIO1_IO10). Active-low by name (the # suffix); software picks
    # the edge. Driven by the ignition network in build_control().
    "CTRL_WAKE1_MICO#": "IGN_WAKE_N",
    "GPIO_10_DSI": "PANEL_BIAS_EN",   # TPS65131-Q1 ENP/ENN
    "PWM_3_DSI": "PANEL_BL_PWM",      # TPS61165-Q1 CTRL (PWM dimming)
    # Control and sequencing.
    "CTRL_PWR_EN_MOCI":  "PWR_EN_MOCI",
    "CTRL_RESET_MOCI#":  "RESET_MOCI",
    "CTRL_RESET_MICO#":  "RESET_MICO",
    "CTRL_PWR_BTN_MICO#": "PWR_BTN",
    "CTRL_RECOVERY_MICO#": "RECOVERY",
    "JTAG_1_TCK":   "JTAG_TCK",
    "JTAG_1_TMS":   "JTAG_TMS",
    "JTAG_1_TDI":   "JTAG_TDI",
    "JTAG_1_TDO":   "JTAG_TDO",
    "JTAG_1_TRST#": "JTAG_TRST",
    "JTAG_1_VREF":  "JTAG_VREF",
    "VCC_BACKUP":   "VBACKUP",
}

# X1 pins this board deliberately does not use, outside the unused bank.
# Each one the Verdin datasheet explicitly permits leaving floating, or
# that this design has no use for. They get real NoConnect items, same as
# bank E, rather than being left to show up as ERC noise.
X1_NC = {
    "DSI_1_D3_P", "DSI_1_D3_N",  # panel has 3 lanes, not 4
    "I2C_2_DSI_SDA", "I2C_2_DSI_SCL",  # bridge-config bus; no bridge on this board
    "CTRL_FORCE_OFF_MOCI#",  # datasheet: "can be left floating"
    "TAMPER0", "TAMPER1",    # SoC tamper detect, unused here
    "PWR_1V8_MOCI",          # the carrier makes its own 1.8 V
    "PMIC_PGOOD",            # module-side power good, not used by us
}


def U():
    return str(uuid_lib.uuid4())


def snap(v):
    """Round onto KiCad's 1.27 mm schematic grid.

    Applied at every placement entry point. This project's KiCad notes
    record that off-grid pin/wire endpoints produce one real
    `endpoint_off_grid` ERC violation each, even when every connection is
    otherwise correct.
    """
    return round(round(v / GRID) * GRID, 2)


# ---------------------------------------------------------------------------
# Symbol library
# ---------------------------------------------------------------------------
lib_symbols = {}          # lib_id -> Symbol
unit_pin_offsets = {}     # (unit_index, pin_number) -> (dx, dy) in symbol space
unit_heights = {}         # unit_index -> drawn body height (mm)


def build_x1_symbol():
    """
    The Verdin iMX95 X1 connector as one multi-unit KiCad symbol.

    Each unit gets its pins split down its two sides, first half on the
    left, second half on the right, in ascending pin order so the drawing
    can be read against the datasheet's own tables.

    Real SKU chosen (2026-09-28): "Verdin iMX95 Hexa 8GB WB IT" - a real,
    confirmed-orderable Toradex product (independently listed on both
    Mouser US and Mouser UK under this exact name), not a placeholder.
    Hexa (6-core) + 8GB LPDDR5 gives real headroom for Android Automotive
    (a real OS + display compositor workload, not a bare-metal firmware
    role like this family's other MCU-based boards), and IT (industrial
    temperature) matches every other automotive-grade part on this board
    rather than a commercial-temp module in a dash-mounted enclosure.
    Toradex's own internal ordering code for this SKU wasn't independently
    confirmed - verify the exact Toradex part number at purchase time,
    same real "confirmed product, purchasing pass still owed" status
    ecu-pcb's own BOM already carries for its own long-lead parts.
    """
    lib_id = f"{LIB}:Verdin_iMX95_X1"
    parent = Symbol.create_new(
        id=lib_id, reference="J", value="Verdin iMX95 Hexa 8GB WB IT",
        footprint=parts.FOOTPRINTS["Verdin_iMX95_X1"],
        datasheet="https://docs.toradex.com/200007-verdin_imx95_datasheet.pdf")
    parent.pinNames = True
    parent.pinNamesOffset = 0.508
    parent.hidePinNumbers = False

    for idx, (label, desc, entries) in enumerate(verdin_x1.units(), start=1):
        half = -(-len(entries) // 2)          # ceil, so left side takes the extra
        left, right = entries[:half], entries[half:]
        rows = max(len(left), len(right), 1)
        height = rows * PITCH + PITCH
        unit_heights[idx] = height

        child = Symbol(libraryNickname=None, entryName="Verdin_iMX95_X1",
                       unitId=idx, styleId=1)
        child.graphicItems.append(SyRect(
            start=Position(-UNIT_W / 2, -height / 2),
            end=Position(UNIT_W / 2, height / 2),
            stroke=Stroke(width=0.254, type="default")))
        child.graphicItems[-1].fill.type = "background"

        def add_side(items, x_tip, angle):
            n = len(items)
            for i, (pin, name) in enumerate(items):
                # Symbol space is Y-up, so the first entry needs the
                # largest y to land at the TOP of the drawn body.
                py = ((n - 1) * PITCH) / 2 - i * PITCH
                etype = "power_in" if name in POWER_IN else "passive"
                child.pins.append(SymbolPin(
                    electricalType=etype, graphicalStyle="line",
                    position=Position(round(x_tip, 2), round(py, 2), angle),
                    length=LEAD, name=name, number=str(pin)))
                unit_pin_offsets[(idx, pin)] = (round(x_tip, 2), round(py, 2))

        # Pin angle points from the connection tip toward the body, so a
        # left-hand pin is 0 and a right-hand pin is 180.
        add_side(left, -(UNIT_W / 2 + LEAD), 0)
        add_side(right, UNIT_W / 2 + LEAD, 180)
        parent.units.append(child)

    lib_symbols[lib_id] = parent
    return lib_id


def build_power_symbol(net, is_gnd):
    lib_id = f"{LIB}:PWR_{net}"
    sym = Symbol.create_new(id=lib_id, reference="#PWR", value=net)
    sym.isPower = True
    sym.pinNames = True
    sym.pinNamesOffset = 0
    sym.pinNamesHide = True
    sym.hidePinNumbers = True
    sym.properties[0].effects.hide = True
    stroke = Stroke(width=0.254, type="default")
    if is_gnd:
        sym.properties[1].position = Position(0, -4.6, 0)
        shapes = ([(0, 0), (0, -1.27)],
                  [(-1.27, -1.27), (1.27, -1.27)],
                  [(-0.762, -1.905), (0.762, -1.905)],
                  [(-0.254, -2.54), (0.254, -2.54)])
    else:
        sym.properties[1].position = Position(0, 3.9, 0)
        shapes = ([(0, 0), (0, 2.54)], [(-1.016, 2.54), (1.016, 2.54)])
    for pts in shapes:
        sym.graphicItems.append(SyPolyLine(
            points=[Position(a, b) for a, b in pts], stroke=stroke))
    sym.pins = [SymbolPin(electricalType="power_in", graphicalStyle="line",
                          position=Position(0, 0, 90), length=0,
                          name=net, number="1", hide=True)]
    lib_symbols[lib_id] = sym
    return lib_id


def build_pwr_flag(net):
    """
    PWR_FLAG equivalent - asserts that `net` is driven from off-sheet.

    +5V enters this stage with no regulator on the sheet yet, so ERC's
    power_pin_not_driven fires without this. Drawn as an arrow so it does
    not read as another supply if opened in the GUI.
    """
    lib_id = f"{LIB}:PWR_FLAG_{net}"
    sym = Symbol.create_new(id=lib_id, reference="#FLG", value=f"PWR_FLAG {net}")
    sym.isPower = True
    sym.pinNames = True
    sym.pinNamesOffset = 0
    sym.pinNamesHide = True
    sym.hidePinNumbers = True
    sym.properties[0].effects.hide = True
    sym.properties[1].position = Position(0, 3.9, 0)
    stroke = Stroke(width=0.254, type="default")
    for pts in ([(0, 0), (0, 2.54)], [(0, 2.54), (-0.889, 1.651)],
                [(0, 2.54), (0.889, 1.651)]):
        sym.graphicItems.append(SyPolyLine(
            points=[Position(a, b) for a, b in pts], stroke=stroke))
    sym.pins = [SymbolPin(electricalType="power_out", graphicalStyle="line",
                          position=Position(0, 0, 90), length=0,
                          name=net, number="1", hide=True)]
    lib_symbols[lib_id] = sym
    return lib_id


# ---------------------------------------------------------------------------
# Schematic
# ---------------------------------------------------------------------------
sch = Schematic.create_new()
sch.paper.paperSize = PAPER
sch.uuid = U()


def place(lib_id, ref, value, x, y, unit=1, hide_ref=False, body_h=None):
    """
    Place a symbol instance.

    `body_h` is the drawn height of THIS unit. A multi-unit symbol carries
    one set of property positions shared by every unit, so leaving them at
    the library default stacks the reference and value on top of each
    other in the middle of the body. Passing the unit's own height moves
    the reference above it and the value below it. Note the sheet is
    Y-down, so "above" is the smaller y.
    """
    x, y = snap(x), snap(y)
    inst = SchematicSymbol(
        libraryNickname=lib_id.split(":")[0], entryName=lib_id.split(":")[1],
        position=Position(x, y, 0), unit=unit, inBom=True, onBoard=True,
        uuid=U())
    src = lib_symbols[lib_id]
    for i, p in enumerate(src.properties):
        if body_h is not None and i in (0, 1):
            gap = body_h / 2 + 2.54
            pos = Position(x, y - gap if i == 0 else y + gap, 0)
        else:
            pos = Position(x + p.position.X, y - p.position.Y, 0)
        prop = Property(key=p.key, value=(ref if i == 0 else
                                          (value if i == 1 else p.value)),
                        id=i, position=pos,
                        effects=Effects(font=Font(width=1.27, height=1.27)))
        if i == 0 and hide_ref:
            prop.effects.hide = True
        if i >= 2:
            prop.effects.hide = True
        inst.properties.append(prop)
    inst.instances.append(SymbolProjectInstance(
        name=LIB, paths=[SymbolProjectPath(sheetInstancePath=f"/{sch.uuid}",
                                           reference=ref, unit=unit)]))
    sch.schematicSymbols.append(inst)
    return inst


def add_wire(x1, y1, x2, y2):
    sch.graphicalItems.append(Connection(
        type="wire",
        points=[Position(snap(x1), snap(y1)), Position(snap(x2), snap(y2))],
        stroke=Stroke(width=0.0, type="default"), uuid=U()))


def pin_xy(unit, pin, sym_x, sym_y):
    """Sheet coordinates of an X1 pin.

    Symbol space is Y-up while the sheet is Y-down, so the symbol-space
    offset is added in X and SUBTRACTED in Y.
    """
    dx, dy = unit_pin_offsets[(unit, pin)]
    return snap(sym_x + dx), snap(sym_y - dy)


# ---------------------------------------------------------------------------
# Generic parts and the declarative net list
# ---------------------------------------------------------------------------
# Rails get power symbols; everything else gets a stub wire and a local
# label. This project's KiCad notes are explicit that the two mechanisms
# do NOT merge - a label "GND" makes net "/GND" while a power symbol makes
# global "GND" - so each net must pick one and stick to it.
# VBAT_F and +12V_PROT are rails too, not signals: they feed power_in
# pins, so ERC needs them driven. Both arrive through passive parts (a
# fuse, and the ideal-diode FET), so nothing on the sheet "drives" them
# and each needs a PWR_FLAG the same way GND and +5V do.
# PANEL_BIAS_VIN is TPS65131-Q1's RC-filtered control supply (+5V through
# R37): ERC cannot trace a power pin through a resistor, so it gets the
# same PWR_FLAG treatment as the other rails.
POWER_NETS = {"GND", "+5V", "+12V_PROT", "+1V8", "+3V3", "VBAT_F",
              "PANEL_BIAS_VIN"}

# net -> a real (x, y) on that net, for anchoring PWR_FLAGs. This project's
# KiCad notes record that a flag merged only by name, with nothing
# touching it graphically, does not satisfy power_pin_not_driven.
power_net_points = {}

# Rails that a real part actually drives, i.e. something on the net has a
# power_out pin. Those must NOT get a PWR_FLAG: two power outputs on one
# net is a pin_to_pin conflict, and the flag exists precisely to stand in
# for a driver that is not on the sheet.
driven_nets = set()

# Every coordinate a net is terminated at, so two blocks drifting into
# each other can be caught by construction. Keyed on the point, valued
# with (net, owning reference). Covers pin positions AND stub endpoints -
# an earlier version only scanned label positions and therefore missed a
# stub whose endpoint landed on another block's pin.
net_points = {}

generic_pins = {}      # lib_id -> [(num, name, etype), ...]
generic_offsets = {}   # (lib_id, num) -> (dx, dy) symbol space
generic_heights = {}   # lib_id -> body height


def build_generic_symbol(lib_id, ref_prefix, value, pins, footprint=None):
    """A rectangular symbol, pins split first-half left / second-half right."""
    half = -(-len(pins) // 2)
    left, right = pins[:half], pins[half:]
    rows = max(len(left), len(right), 1)
    height = rows * PITCH + PITCH
    longest = max((len(p[1]) for p in pins), default=1)
    # Width must be a multiple of 2.54, NOT merely snapped to 1.27: pins
    # sit at +/-(width/2 + LEAD), so an odd multiple of 1.27 puts every
    # pin half a grid step off. That breaks the assumption place_part's
    # snap() relies on, and shows up not as one tidy error but as a
    # cascade - off-grid pins, then wires whose ends miss those pins,
    # then dangling no-connects and isolated labels on the nets that
    # failed to form. This project's KiCad notes warn to verify the
    # pin-layout math rather than trust a single snap point; this is that
    # precondition being violated.
    width = max(15.24, 2.54 * -(-(longest * 2.0 + 7.62) // 2.54))

    if footprint is None:
        footprint = parts.FOOTPRINTS.get(lib_id.split(":", 1)[1], "")
    sym = Symbol.create_new(id=lib_id, reference=ref_prefix, value=value,
                            footprint=footprint)
    sym.pinNames = True
    sym.pinNamesOffset = 0.508
    sym.graphicItems.append(SyRect(
        start=Position(-width / 2, -height / 2),
        end=Position(width / 2, height / 2),
        stroke=Stroke(width=0.254, type="default")))
    sym.graphicItems[-1].fill.type = "background"

    def side(items, x_tip, angle):
        n = len(items)
        for i, (num, name, etype) in enumerate(items):
            py = ((n - 1) * PITCH) / 2 - i * PITCH
            sym.pins.append(SymbolPin(
                electricalType=etype, graphicalStyle="line",
                position=Position(round(x_tip, 2), round(py, 2), angle),
                length=LEAD, name=name, number=str(num)))
            generic_offsets[(lib_id, num)] = (round(x_tip, 2), round(py, 2))

    side(left, -(width / 2 + LEAD), 0)
    side(right, width / 2 + LEAD, 180)

    lib_symbols[lib_id] = sym
    generic_pins[lib_id] = pins
    generic_heights[lib_id] = height
    return lib_id


# Two-terminal parts all share one shape; three-terminal N-FET its own.
PASSIVE_PINS = [(1, "1", "passive"), (2, "2", "passive")]
NFET_PINS = [(1, "G", "input"), (2, "D", "passive"), (3, "S", "passive")]

rail_syms = {}     # net -> power symbol lib_id


def rail(net):
    """Power symbol for `net`, created on first use."""
    if net not in rail_syms:
        rail_syms[net] = build_power_symbol(net, is_gnd=(net == "GND"))
    return rail_syms[net]


def place_part(lib_id, ref, value, x, y, nets):
    """
    Place a part and terminate every one of its pins.

    `nets` maps pin NAME to net name. A pin whose name is absent, or maps
    to None, gets a real NoConnect item rather than being left dangling -
    same rule the unused X1 pins follow.
    """
    place(lib_id, ref, value, x, y, body_h=generic_heights[lib_id])
    for num, name, etype in generic_pins[lib_id]:
        dx, dy = generic_offsets[(lib_id, num)]
        px, py = snap(x + dx), snap(y - dy)
        net = nets.get(name)
        if net is not None and etype == "power_out":
            driven_nets.add(net)
        if net is None:
            sch.noConnects.append(NoConnect(position=Position(px, py), uuid=U()))
            continue
        out = -1 if dx < 0 else 1
        wx, wy = snap(px + out * STUB), py
        for pt in ((px, py), (wx, wy)):
            prev = net_points.get(pt)
            if prev and prev[0] != net:
                print(f"  ERROR: {pt} carries both {prev[0]} (via {prev[1]}) "
                      f"and {net} (via {ref})")
            net_points[pt] = (net, ref)
        add_wire(px, py, wx, wy)
        if net in POWER_NETS:
            place(rail(net), f"#PWR_{ref}_{num}", net, wx, wy, hide_ref=True)
            power_net_points.setdefault(net, (wx, wy))
        else:
            add_label(net, wx, wy, 0 if out > 0 else 180)


def add_label(text, x, y, angle):
    assert text not in POWER_NETS, \
        f"power net {text} must use a power symbol, not a label"
    sch.labels.append(LocalLabel(
        text=text, position=Position(snap(x), snap(y), angle),
        effects=Effects(font=Font(width=1.27, height=1.27),
                        justify=Justify(horizontally="left")),
        uuid=U()))


def build_common_symbols():
    """
    The generic two- and three-terminal parts every block reuses.

    Built once, before any section runs. They used to be created inside
    build_power_tree(), which worked only while that happened to be the
    first block called - reordering the sections turned it into a
    KeyError. Shared state belongs at the top, not in whichever caller
    ran first.
    """
    build_generic_symbol(f"{LIB}:R", "R", "R", PASSIVE_PINS)
    build_generic_symbol(f"{LIB}:C", "C", "C", PASSIVE_PINS)
    build_generic_symbol(f"{LIB}:L", "L", "L", PASSIVE_PINS)
    build_generic_symbol(f"{LIB}:TVS", "D", "TVS", PASSIVE_PINS)
    build_generic_symbol(f"{LIB}:FUSE", "F", "Fuse", PASSIVE_PINS)
    build_generic_symbol(f"{LIB}:NFET", "Q", "NFET", NFET_PINS)
    build_generic_symbol(f"{LIB}:TLV767-Q1", "U", "TLV767-Q1", parts.TLV767_Q1)


def build_power_tree(x0, y0, usable_h):
    """
    12 V automotive front end and the main 5 V buck.

    Topology follows TI's own reference circuit for the LM74930-Q1,
    "VBAT 12-V or 24-V With 200-V Unsuppressed Load Dump - Output Clamp".
    The back-to-back FET arrangement is the part worth reading carefully:
    Q2 (pass, HGATE) and Q1 (ideal diode, DGATE) share a COMMON source
    node, and both the A and OUT pins sit on it.

    POWER STAGE VALUES (2026-10-02). Until now every resistor and capacitor
    in this block carried only a placeholder name inherited from the
    fascia-pcb port ("RILIM", "OV top", "RT", "FB top"...), which is not
    orderable. They are now calculated from TI's own datasheets:

    LM74930-Q1 (SNOSDF6, section 8.2.2, equations 12-17):
      * RSET (R2) = 49.9 ohm, the 50 ohm the datasheet says to use with
        CS+ (recommended 50-100 ohm).
      * RSENSE (R1) = 2 mohm. The default short-circuit threshold is 20 mV,
        so the short-circuit limit is 20 mV / 2 mohm = 10 A, above the 8.5 A
        trip of F1 so the fuse stays the last line of defence.
      * RILIM (R3), Eq. 15: 12 x RSET / (ILIM x RSENSE). For a 5 A circuit
        breaker (F1's hold current) that is 12 x 50 / (5 x 0.002) = 60 kohm,
        60.4 kohm as the standard 1% value.
      * CTMR (C4), Eq. 16: TOC = 1.2 x C / 82.3 uA. 100 nF gives about
        1.5 ms of overcurrent blanking (the datasheet example uses 68 nF for
        1 ms).
      * RIMON (R4), Eq. 17: V(IMON) = 0.9 x VSENSE x RIMON / RSET. 10 kohm
        gives 1.8 V at 5 A (VSENSE = 10 mV), which keeps IMON inside a 1.8 V
        ADC range if it is ever read. It is not connected to anything yet.
      * UV divider (R7/R8), Eq. 12 with the datasheet's 0.55 V falling
        threshold: 100 k / 11.5 k gives the datasheet example's 5.5 V cut-off
        (above a cold-crank dip). OV divider (R5/R6), Eq. 13: OV rising
        threshold 0.6 V, 100 k / 2.05 k gives 0.6 x (100 + 2.05) / 2.05 =
        29.9 V. With OVCLAMP tied to OV the output is CLAMPED there during a
        load dump, which keeps the LM61460-Q1 (42 V absolute maximum) safe.
      * CVS (C2) and CCAP (C3) 100 nF per the pin descriptions (VS and CAP).

    LM61460-Q1 (SNVSB70F, Tables 10-2 and 10-5, 5 V output at 2.1 MHz, above
    the AM band):
      * RFBT (R10) 100 kohm / RFBB (R11) 24.9 kohm (VREF = 1 V gives 5.02 V),
        CFF (C58) 22 pF across RFBT.
      * RT (R12) = 6.04 kohm for 2100 kHz (datasheet Table 10-5; the
        datasheet's own spec points are 5.76 kohm = 2.2 MHz, 33.2 kohm =
        400 kHz).
      * L1 = 1 uH, Coilcraft XEL5030-102ME (the part Table 10-5 used for 5 V
        2.1 MHz): Isat 16.9 A against the 11.5 A maximum high-side current
        limit, DCR 7 mohm typical.
      * COUT = 3 x 22 uF (C8, C54, C59), CIN = 2 x 4.7 uF (C5, C55) plus
        2 x 100 nF (C56, C57), one pair per VIN pin, per Table 10-5.
      * RBOOT (R9) 0 ohm, CBOOT (C7) 100 nF, CVCC (C6) 1 uF per Table 10-2.
      * EN (R13/R14): the enable threshold is 1.263 V rising with 28 %
        hysteresis, so 100 k / 24.9 k starts the buck at 1.263 x (124.9 /
        24.9) = 6.3 V and stops it near 4.6 V.
    C1 is a hold-up capacitor on the protected 12 V rail, where the LM74930
    datasheet (section 8.2.2.8) puts one, not on the unprotected input side
    where it would sit across a reverse-battery event. Panasonic
    EEH-ZA1V101P, 100 uF 35 V hybrid polymer, 8 x 10.2 mm, AEC-Q200.
    """
    r, c, l = f"{LIB}:R", f"{LIB}:C", f"{LIB}:L"
    tvs, fuse, nfet = f"{LIB}:TVS", f"{LIB}:FUSE", f"{LIB}:NFET"
    # Real package choices (2026-10-02 power-stage audit): see POWER STAGE
    # VALUES below. Each distinct package is its own symbol so the footprint
    # follows the real part, not a one-size-fits-all 0603.
    c1206 = build_generic_symbol(f"{LIB}:C_1206", "C", "C", PASSIVE_PINS)
    cpol = build_generic_symbol(f"{LIB}:CP_HYBRID", "C", "C", PASSIVE_PINS)
    l5030 = build_generic_symbol(f"{LIB}:L_5030", "L", "L", PASSIVE_PINS)
    rsense = build_generic_symbol(f"{LIB}:R_1206", "R", "R", PASSIVE_PINS)
    conn3 = build_generic_symbol(f"{LIB}:CONN3", "J", "Power in",
                                 [(1, "VBAT", "passive"), (2, "GND", "passive"),
                                  (3, "IGN", "passive")])
    u_fe = build_generic_symbol(f"{LIB}:LM74930-Q1", "U", "LM74930-Q1",
                                parts.LM74930_Q1)
    u_bk = build_generic_symbol(f"{LIB}:LM61460-Q1", "U", "LM61460-Q1",
                                parts.LM61460_Q1)

    # Simple column-major grid. The X1 connector units already occupy the
    # left two thirds of the sheet, so the power tree gets its own band on
    # the right; `flow` wraps to the next column rather than running off
    # the bottom, and main() still checks every placement against the
    # sheet bounds afterwards.
    COL_W, ROW_H = 78.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        """
        Place the next part, advancing by its ACTUAL height.

        A fixed row pitch is wrong here because the parts are wildly
        different sizes - a 2-pin resistor next to the 24-pin LM74930-Q1,
        which is taller than one row and silently overlapped its
        neighbours on the first attempt. ERC cannot see overlapping
        symbols, so this has to be right by construction.
        """
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    # --- input and protection -------------------------------------------
    flow(conn3, "J2", "Phoenix MKDS 1,5/3-5,08 power in (DTM06-3S pigtail)",
         {"VBAT": "VBAT_IN", "GND": "GND", "IGN": "IGN_SENSE"})
    # Real part (2026-09-28): Bourns MF-RG500 - the "5A" target in this
    # net's own name was real, but the footprint chosen when this board
    # was first laid out (Fuse_Bourns_MF-RG500's own sibling,
    # Fuse_Bourns_MF-RG300) was really a 3.0A-hold part, not 5A -
    # Bourns' own real MF-RG datasheet confirms the family's numeric
    # suffix IS the hold current in centiamps (300=3.0A, 500=5.0A), each
    # with its own real (different) physical package size, not a shared
    # footprint - MF-RG500 needed its own real footprint swap in
    # parts.py, not just a Value/comment fix.
    flow(fuse, "F1", "MF-RG500 (Bourns, 5.0A hold/8.5A trip, AEC-Q200)",
         {"1": "VBAT_IN", "2": "VBAT_F"})
    # Real part (2026-09-28): same SMCJ33A gauges/ already uses for the
    # identical real role (12V-rail input surge clamp ahead of an ideal-
    # diode/back-to-back-FET front end) - same net topology, same real
    # justification, industry-standard multi-source part number.
    flow(tvs, "D1", "SMCJ33A", {"1": "VBAT_F", "2": "GND"})
    flow(cpol, "C1", "100u 35V hybrid polymer hold-up (Panasonic EEH-ZA1V101P)",
         {"1": "+12V_PROT", "2": "GND"})

    # RSENSE sits in the input path; CS+ taps it through RSET per the
    # datasheet's "connect a 50-ohm resistor across CS+".
    flow(rsense, "R1", "2m 2% sense (Susumu KRL3216E-C-R002-G-T5)",
         {"1": "VBAT_F", "2": "SENSE_OUT"})
    flow(r, "R2", "49.9R 1% RSET", {"1": "VBAT_F", "2": "CS_PLUS"})

    # --- back-to-back FETs ----------------------------------------------
    # Real part (2026-09-28): Nexperia PMV55ENEA - selected against
    # LM74930-Q1's own datasheet section "MOSFET Q2 Selection" (SNOSDF6
    # section 8.2.2.9/8.2.2.10), which states two real requirements for
    # BOTH FETs in this pair: 60V VDS with this board's real single
    # (not back-to-back-pair) input TVS, and a MOSFET with >=15V VGS
    # rating since HGATE/DGATE can drive up to 14V. PMV55ENEA is a real,
    # SOT-23, AEC-Q101 part with VDS=60V and VGS=+-20V (checked against
    # its own real datasheet, not assumed) - satisfies both criteria
    # with real margin. Its 3.1A continuous rating is below F1's own 5A
    # hold current; real automotive ideal-diode designs commonly run
    # the series FET below the fuse's DC rating and rely on SOA/pulse
    # withstand for real fault duration rather than continuous ID alone,
    # but this board's own real steady-state current draw (dominated by
    # U2's buck feeding the Verdin module) hasn't been independently
    # measured/verified against this part's own SOA curve - flagged
    # honestly as a real follow-up, not silently assumed fine.
    flow(nfet, "Q2", "PMV55ENEA (AEC-Q101, 60V/20V VGS) pass",
         {"D": "SENSE_OUT", "G": "HGATE", "S": "COMMON"})
    flow(nfet, "Q1", "PMV55ENEA (AEC-Q101, 60V/20V VGS) diode",
         {"S": "COMMON", "G": "DGATE", "D": "+12V_PROT"})

    # --- LM74930-Q1 ------------------------------------------------------
    flow(u_fe, "U1", "LM74930-Q1", {
        "DGATE": "DGATE", "A": "COMMON", "SW": "SW_SENSE",
        "UVLO": "UVLO_DIV", "OV": "OV_DIV", "EN": "VBAT_F",
        "MODE": "VBAT_F", "NC1": None, "TMR": "TMR",
        "IMON": "IMON", "ILIM": "ILIM", "FLT": "PWR_FLT",
        "GND": "GND", "HGATE": "HGATE", "OUT": "COMMON",
        # OVCLAMP tied to OV selects clamp-with-circuit-breaker rather
        # than plain disconnect. This one net is the whole reason the
        # module rides through a load dump instead of rebooting.
        "OVCLAMP": "OV_DIV", "NC2": None,
        "ISCP": "+12V_PROT", "CS-": "SENSE_OUT", "CS+": "CS_PLUS",
        "NC3": None, "VS": "VBAT_F", "CAP": "CAP_CP", "C": "+12V_PROT",
        # Exposed pad deliberately floating - the datasheet forbids
        # grounding it, so this NoConnect is load-bearing.
        "EP": None,
    })

    for ref, val, nets in [
        ("C2", "100n CVS", {"1": "VBAT_F", "2": "GND"}),
        ("C3", "100n CCAP", {"1": "CAP_CP", "2": "VBAT_F"}),
        ("C4", "100n CTMR", {"1": "TMR", "2": "GND"}),
        ("R3", "60.4k RILIM", {"1": "ILIM", "2": "GND"}),
        ("R4", "10k RIMON", {"1": "IMON", "2": "GND"}),
        ("R5", "100k OV top", {"1": "SW_SENSE", "2": "OV_DIV"}),
        ("R6", "2.05k OV bot", {"1": "OV_DIV", "2": "GND"}),
        ("R7", "100k UV top", {"1": "SW_SENSE", "2": "UVLO_DIV"}),
        ("R8", "11.5k UV bot", {"1": "UVLO_DIV", "2": "GND"}),
    ]:
        flow(c if ref.startswith("C") else r, ref, val, nets)

    # --- LM61460-Q1 5 V buck ---------------------------------------------
    flow(u_bk, "U2", "LM61460-Q1", {
        "BIAS": "+5V", "VCC": "VCC_LDO", "AGND": "GND", "FB": "FB_5V",
        "PGOOD": "PG_5V", "RT": "RT_5V", "EN/SYNC": "EN_5V",
        "VIN1": "+12V_PROT", "PGND1": "GND", "SW": "SW_5V",
        "PGND2": "GND", "VIN2": "+12V_PROT",
        "RBOOT": "BOOT_R", "CBOOT": "BOOT_C",
    })
    for ref, val, lib, nets in [
        ("C5", "4.7u CIN VIN1", c1206, {"1": "+12V_PROT", "2": "GND"}),
        ("C55", "4.7u CIN VIN2", c1206, {"1": "+12V_PROT", "2": "GND"}),
        ("C56", "100n CHF VIN1", c, {"1": "+12V_PROT", "2": "GND"}),
        ("C57", "100n CHF VIN2", c, {"1": "+12V_PROT", "2": "GND"}),
        ("C6", "1u VCC", c, {"1": "VCC_LDO", "2": "GND"}),
        ("C7", "100n boot", c, {"1": "BOOT_C", "2": "SW_5V"}),
        ("R9", "0R RBOOT", r, {"1": "BOOT_R", "2": "BOOT_C"}),
        ("L1", "1u XEL5030-102ME 2.1MHz", l5030, {"1": "SW_5V", "2": "+5V"}),
        ("C8", "22u COUT", c1206, {"1": "+5V", "2": "GND"}),
        ("C54", "22u COUT", c1206, {"1": "+5V", "2": "GND"}),
        ("C59", "22u COUT", c1206, {"1": "+5V", "2": "GND"}),
        ("R10", "100k FB top", r, {"1": "+5V", "2": "FB_5V"}),
        ("R11", "24.9k FB bot", r, {"1": "FB_5V", "2": "GND"}),
        ("C58", "22p CFF", c, {"1": "+5V", "2": "FB_5V"}),
        ("R12", "6.04k RT", r, {"1": "RT_5V", "2": "GND"}),
        ("R13", "100k EN top", r, {"1": "+12V_PROT", "2": "EN_5V"}),
        ("R14", "24.9k EN bot", r, {"1": "EN_5V", "2": "GND"}),
        # FLT and PGOOD are open-drain and do nothing without these.
        ("R15", "100k FLT pu", r, {"1": "PWR_FLT", "2": "+5V"}),
        ("R16", "100k PG pu", r, {"1": "PG_5V", "2": "+5V"}),
    ]:
        flow(lib, ref, val, nets)


def build_1v8_and_can(x0, y0, usable_h):
    """
    The 1.8 V rail and the CAN FD link to ecu-pcb.

    The 1.8 V rail exists because the Verdin's I/O is 1.8 V logic: it
    feeds the CAN transceiver's VIO here, and the SN65DSI85-Q1 bridge
    later. An LDO rather than a buck, deliberately - small load, and no
    switching noise added to a board carrying LVDS next to a car radio.
    """
    r = f"{LIB}:R"
    c = f"{LIB}:C"
    u_ldo = f"{LIB}:TLV767-Q1"
    u_can = build_generic_symbol(f"{LIB}:TCAN1044V-Q1", "U", "TCAN1044V-Q1",
                                 parts.TCAN1044V_Q1)
    conn_can = build_generic_symbol(f"{LIB}:CONN_CAN", "J", "CAN",
                                    [(1, "CANH", "passive"),
                                     (2, "CANL", "passive"),
                                     (3, "GND", "passive")])

    # This block sits BELOW the X1 connector units rather than beside
    # them, so it gets a short usable height and wraps into more columns.
    COL_W, ROW_H = 78.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    # --- 1.8 V LDO -------------------------------------------------------
    # EN has an internal pull-up and may float, but tying it to the input
    # is explicit about intent and costs nothing.
    flow(u_ldo, "U3", "TLV767-Q1", {
        "IN": "+5V", "OUT": "+1V8", "FB": "FB_1V8",
        "GND": "GND", "GND2": "GND",
        # Gated by the module rather than tied on: CTRL_PWR_EN_MOCI is
        # exactly the "carrier peripherals may power up" signal, and it
        # stays high through sleep.
        "EN": "PWR_EN_MOCI",
        "NC1": None, "NC2": None, "EP": "GND",
    })
    # TLV767-Q1 (SBVS381A): VFB = 0.8 V, VOUT = VFB x (1 + R1/R2). 124 k /
    # 100 k gives 0.8 x 2.24 = 1.792 V (1.8 V nominal, inside the panel's
    # 1.75-1.85 V IOVCC window); the divider current is 8 uA, above the 5 uA
    # below which the datasheet requires a feed-forward capacitor. CIN/COUT
    # must be at least 1 uF effective; 10 uF 10 V X7R in 0805 leaves margin
    # for the datasheet's "expect up to 50 % less at bias".
    c0805_ldo = build_generic_symbol(f"{LIB}:C_0805", "C", "C", PASSIVE_PINS)
    flow(c0805_ldo, "C9", "10u CIN", {"1": "+5V", "2": "GND"})
    flow(c0805_ldo, "C10", "10u COUT", {"1": "+1V8", "2": "GND"})
    flow(r, "R17", "124k FB top", {"1": "+1V8", "2": "FB_1V8"})
    flow(r, "R18", "100k FB bot", {"1": "FB_1V8", "2": "GND"})

    # --- CAN FD ----------------------------------------------------------
    flow(u_can, "U4", "TCAN1044V-Q1", {
        "TXD": "CAN1_TXD", "RXD": "CAN1_RXD",
        "VCC": "+5V",      # 4.5-5.5 V part supply
        "VIO": "+1V8",     # matches the module's 1.8 V logic
        "GND": "GND", "CANH": "CAN1_H", "CANL": "CAN1_L",
        "STB": "CAN1_STB",
    })
    flow(c, "C11", "100n VCC", {"1": "+5V", "2": "GND"})
    flow(c, "C12", "100n VIO", {"1": "+1V8", "2": "GND"})

    # Split termination rather than a single 120R: the midpoint capacitor
    # shunts common-mode noise to ground, which is worth having on a bus
    # leaving the enclosure on a harness in a car.
    flow(r, "R19", "60R term", {"1": "CAN1_H", "2": "CAN1_SPLIT"})
    flow(r, "R20", "60R term", {"1": "CAN1_SPLIT", "2": "CAN1_L"})
    flow(c, "C13", "4n7 split", {"1": "CAN1_SPLIT", "2": "GND"})

    # STB has an internal pull-up, so the part wakes in STANDBY. Pulling
    # it down selects normal mode by default; a module GPIO can be added
    # later to reclaim low-power standby.
    flow(r, "R21", "10k STB pd", {"1": "CAN1_STB", "2": "GND"})

    flow(conn_can, "J3", "Molex KK-254 22-27-2031 private CAN link to gauges/ J8",
         {"CANH": "CAN1_H", "CANL": "CAN1_L", "GND": "GND"})


def build_panel(x0, y0, usable_h):
    """
    Direct MIPI-DSI panel connector - NO bridge chip.

    RE-SCOPED 2026-09-30: the panel is now the Team Source Display (TSD)
    TST040HDBC-42 - 4.0" round IPS, 720x720, ICNL9707 driver, native
    MIPI DSI, 800 cd/m2, -30..+80 C operating, active circle 101.52 mm
    (datasheet V1.0, 2023-06-29). It replaces DisplayModule's
    DM-TFTR50-413, which was rejected on three real counts found on
    2026-09-30: 350 nits (CDTech's guidance is >=800 nits for direct
    sun, and the user's call was "we have to use the 800 nit"), only
    -20..+60 C operating, and a 127 mm active circle that is taller than
    the dash opening (105.54 mm inner / 116.69 mm outer), so it would
    have been cropped at 12 and 6 o'clock. The TSD's 101.52 mm circle
    fits the 105.54 mm inner height uncropped.

    Real 39-pin FPC table (datasheet section 3): GND 1/6/9/12/15/17/19/
    23/27/31/35/39, LEDA 2-3, LEDK 4-5, "VSP +6.5 V" 7-8, "VSN -6.5 V"
    10-11, IOVCC (1.8 V) 13-14, RESET 16, TE 18, LAN2 P/N 24/26, CLK P/N
    28/30, LAN1 P/N 32/34, LAN0 P/N 36/38, NC 20-22/25/29/33/37. Three
    data lanes + clock; the Verdin's fourth lane (DSI_1_D3) is unused.

    **REAL DATASHEET CONFLICT, NOT RESOLVED - hedged in hardware.** The
    interface table says pins 7-8 = VSP (+6.5 V) and 10-11 = VSN
    (-6.5 V). The same PDF's mechanical drawing header row (rendered and
    read at 400 dpi) says the opposite: 7-8 = "VDD(-6.3V)" and 10-11 =
    "VDD(+6.3V)". Feeding the wrong polarity would destroy the panel, so
    neither is assumed: the two pin groups (PANEL_PIN_A = pins 7-8,
    PANEL_PIN_B = pins 10-11) each connect to the +6.5 V and -6.5 V rails
    through a 3-pad OPEN solder jumper (JP1/JP2). Table reading: bridge
    JP1 pads 1-2 and JP2 pads 2-3. Drawing reading: JP1 2-3 and JP2 1-2.
    Confirm with TSD (or by probing a sample's FPC) BEFORE bridging
    either; unbridged, the panel simply has no analog supply.

    Connector: Hirose FH26-39S-0.3SHW (0.3 mm pitch, 39 positions, KiCad
    bundled footprint). The datasheet does not name a connector; 0.3 mm
    pitch is inferred from the FPC's 12 mm width across 39 pins, and the
    0.2 mm FPC thickness matches the FH26 family. FH26 is bottom-contact;
    the FPC's exposed-pad side must be specified when ordering (TSD lists
    customisable FPC). Hirose lists FH26-39S-0.3SHW(05) as obsolete and
    FH26W-39S-0.3SHW(60) as the current variant - confirm the land pattern
    before ordering.

    IOVCC (1.8 V, datasheet 1.75-1.85) reuses the existing +1V8 rail. VSP/
    VSN and the backlight are new circuits: build_panel_bias() and
    build_panel_backlight(). TE is left open. RESET (DSI_PANEL_EN from
    the Verdin's GPIO_9_DSI) and the bias enable are pulled low so the
    panel is held in reset with no analog rails until software releases
    them.
    """
    # Symbol pin number, name, electrical type - straight from the
    # datasheet's own pin table (section 3), pins 1-39.
    real_panel_pins = [
        (1, "GND", "power_in"), (2, "LEDA", "passive"), (3, "LEDA", "passive"),
        (4, "LEDK", "passive"), (5, "LEDK", "passive"), (6, "GND", "power_in"),
        # Typed passive on purpose: these pins are fed only through the
        # open polarity jumpers JP1/JP2, and ERC would (correctly) call
        # an unbridged jumper "not driven".
        (7, "VPIN_A", "passive"), (8, "VPIN_A", "passive"),
        (9, "GND", "power_in"),
        (10, "VPIN_B", "passive"), (11, "VPIN_B", "passive"),
        (12, "GND", "power_in"),
        (13, "IOVCC", "power_in"), (14, "IOVCC", "power_in"),
        (15, "GND", "power_in"), (16, "RESET", "input"),
        (17, "GND", "power_in"), (18, "TE", "output"),
        (19, "GND", "power_in"),
        (20, "NC", "no_connect"), (21, "NC", "no_connect"),
        (22, "NC", "no_connect"),
        (23, "GND", "power_in"), (24, "LAN2_P", "input"),
        (25, "NC", "no_connect"), (26, "LAN2_N", "input"),
        (27, "GND", "power_in"), (28, "CLK_P", "input"),
        (29, "NC", "no_connect"), (30, "CLK_N", "input"),
        (31, "GND", "power_in"), (32, "LAN1_P", "input"),
        (33, "NC", "no_connect"), (34, "LAN1_N", "input"),
        (35, "GND", "power_in"), (36, "LAN0_P", "input"),
        (37, "NC", "no_connect"), (38, "LAN0_N", "input"),
        (39, "GND", "power_in"),
    ]
    assert len(real_panel_pins) == 39
    conn_panel = build_generic_symbol(
        f"{LIB}:CONN_PANEL", "J", "TST040HDBC-42 (Hirose FH26-39S-0.3SHW)",
        real_panel_pins)
    jumper = build_generic_symbol(
        f"{LIB}:SOLDERJUMPER3", "JP", "SJ3",
        [(1, "A", "passive"), (2, "COM", "passive"), (3, "B", "passive")])
    r = f"{LIB}:R"

    COL_W, ROW_H = 78.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    panel = {
        "GND": "GND",
        "LAN0_P": "DSI_D0_P", "LAN0_N": "DSI_D0_N",
        "LAN1_P": "DSI_D1_P", "LAN1_N": "DSI_D1_N",
        "LAN2_P": "DSI_D2_P", "LAN2_N": "DSI_D2_N",
        "CLK_P": "DSI_CLK_P", "CLK_N": "DSI_CLK_N",
        "IOVCC": "+1V8",
        "VPIN_A": "PANEL_PIN_A", "VPIN_B": "PANEL_PIN_B",
        "LEDA": "PANEL_BL_LEDA", "LEDK": "PANEL_BL_LEDK",
        # Panel hardware reset - GPIO_9_DSI reaches this net via X1_NETS.
        "RESET": "DSI_PANEL_EN",
        "TE": None, "NC": None,
    }
    flow(conn_panel, "J4", "TST040HDBC-42 panel", panel)
    flow(jumper, "JP1",
         "SJ3 OPEN: bridge 1-2 if datasheet TABLE is right (7-8=+6.5V), "
         "2-3 if DRAWING is - VERIFY POLARITY FIRST",
         {"A": "PANEL_VSP", "COM": "PANEL_PIN_A", "B": "PANEL_VSN"})
    flow(jumper, "JP2",
         "SJ3 OPEN: bridge 2-3 if datasheet TABLE is right (10-11=-6.5V), "
         "1-2 if DRAWING is - VERIFY POLARITY FIRST",
         {"A": "PANEL_VSP", "COM": "PANEL_PIN_B", "B": "PANEL_VSN"})
    flow(r, "R43", "100k bias-enable pulldown",
         {"1": "PANEL_BIAS_EN", "2": "GND"})
    flow(r, "R50", "100k panel-reset pulldown",
         {"1": "DSI_PANEL_EN", "2": "GND"})


def build_panel_bias(x0, y0, usable_h):
    """
    +6.5 V / -6.5 V analog rails for the TST040HDBC-42 panel.

    Datasheet section 6: VSP typ +6.5 V, VSN typ -6.5 V (the mechanical
    drawing labels them +/-6.3 V - part of the polarity/value ambiguity
    hedged by JP1/JP2, see build_panel()). Panel current is "TBD" in the
    datasheet; the design assumes well under 100 mA per rail and the part
    is good for ~200 mA each.

    Real part: TI TPS65131-Q1 - AEC-Q100 Grade 2, split-rail boost +
    inverter, VIN 2.7-5.5 V (runs from +5V), VPOS 3.2-15 V, VNEG -15..-2 V
    (TI SLVSBB2F, RGE package). Topology is the datasheet's own Figure 8-1:
      * Boost: +5V -> L2 -> INP node -> D2 -> VPOS. VPOS = 1.213 V x
        (1 + R1/R2)  [datasheet Eq. 1]. R2 = 130k, R1 = 562k gives
        1.213 x (1 + 562/130) = 6.457 V.
      * Inverter: +5V -> INN; OUTN node -> L3 -> GND; D3 anode = VNEG,
        cathode = OUTN node. VNEG = -1.213 V x R3/R4 [Eq. 2], with R4 from
        FBN to VREF (NOT GND). R4 = 100k, R3 = 536k gives -6.502 V.
      * L2, L3 = 4.7 uH (datasheet: optimised for 3.3-6.8 uH). Coilcraft
        XAL4030-472ME: Isat 4.6 A typ vs the 1.95 A nominal switch limit.
      * 4.7 uF at each converter input, 22 uF at each output (Fig. 8-1),
        10 nF at CP, 4.7 nF at CN, 220 nF at VREF, R = 100 ohm + 100 nF
        filter into VIN (Fig. 8-1's R7/C3).
      * Feed-forward caps: datasheet Eq. 11/12 C9 = 6.8 uV-s / R1,
        C10 = 7.5 uV-s / R3 -> 12 pF and 15 pF (E12).
      * BSW (load-disconnect PMOS gate) left floating - datasheet: leave
        floating if the external PMOS is not used. NC pins no-connect.
      * ENP/ENN together are PANEL_BIAS_EN (Verdin GPIO_10_DSI, 1.8 V,
        above the part's 1.4 V VIH) with a 100k pulldown, so software
        can sequence the rails after IOVCC. PSP/PSN tied low = forced PWM
        (no power-save burst ripple on the panel's analog supplies).
    Rectifiers: Nexperia PMEG6010ELRX (60 V / 1 A Schottky, AEC-Q101) -
    same real part as D4; pad 1 = cathode, pad 2 = anode.
    """
    assert abs(1.213 * (1 + 562 / 130) - 6.5) < 0.1
    assert abs(1.213 * 536 / 100 - 6.5) < 0.1
    r, c = f"{LIB}:R", f"{LIB}:C"
    c1206 = build_generic_symbol(f"{LIB}:C_1206", "C", "C", PASSIVE_PINS)
    c0805 = build_generic_symbol(f"{LIB}:C_0805", "C", "C", PASSIVE_PINS)
    l47 = build_generic_symbol(f"{LIB}:L_4U7", "L", "L", PASSIVE_PINS)
    schottky = build_generic_symbol(f"{LIB}:SCHOTTKY_SOD123W", "D", "Schottky",
                                    PASSIVE_PINS)
    u_bias = build_generic_symbol(f"{LIB}:TPS65131-Q1", "U", "TPS65131-Q1",
                                  parts.TPS65131_Q1)

    COL_W, ROW_H = 78.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    flow(u_bias, "U6", "TPS65131-Q1", {
        "INP1": "PANEL_BOOST_SW", "INP2": "PANEL_BOOST_SW",
        "PGND1": "GND", "PGND2": "GND", "AGND": "GND", "EP": "GND",
        "VIN": "PANEL_BIAS_VIN",
        "INN1": "+5V", "INN2": "+5V",
        "BSW": None, "NC1": None, "NC2": None,
        "ENP": "PANEL_BIAS_EN", "ENN": "PANEL_BIAS_EN",
        "PSP": "GND", "PSN": "GND",
        "OUTN1": "PANEL_INV_SW", "OUTN2": "PANEL_INV_SW",
        "VNEG": "PANEL_VSN", "FBN": "PANEL_FBN", "VREF": "PANEL_VREF",
        "CN": "PANEL_CN", "CP": "PANEL_CP",
        "FBP": "PANEL_FBP", "VPOS": "PANEL_VSP",
    })
    flow(r, "R37", "100R VIN filter", {"1": "+5V", "2": "PANEL_BIAS_VIN"})
    flow(c, "C42", "100n VIN filter (AEC-Q200)",
         {"1": "PANEL_BIAS_VIN", "2": "GND"})
    flow(c0805, "C40", "4.7u boost in (AEC-Q200)", {"1": "+5V", "2": "GND"})
    flow(c0805, "C41", "4.7u inverter in (AEC-Q200)", {"1": "+5V", "2": "GND"})
    flow(l47, "L2", "4.7u boost (Coilcraft XAL4030-472ME)",
         {"1": "+5V", "2": "PANEL_BOOST_SW"})
    flow(schottky, "D2", "PMEG6010ELRX (AEC-Q101, 60V/1A)",
         {"1": "PANEL_VSP", "2": "PANEL_BOOST_SW"})
    flow(c1206, "C46", "22u VPOS out 16V (AEC-Q200)",
         {"1": "PANEL_VSP", "2": "GND"})
    flow(r, "R38", "562k VPOS top R1 (see docstring)",
         {"1": "PANEL_VSP", "2": "PANEL_FBP"})
    flow(r, "R39", "130k VPOS bottom R2 (see docstring)",
         {"1": "PANEL_FBP", "2": "GND"})
    flow(c, "C48", "12p VPOS feed-forward (AEC-Q200)",
         {"1": "PANEL_VSP", "2": "PANEL_FBP"})
    flow(l47, "L3", "4.7u inverter (Coilcraft XAL4030-472ME)",
         {"1": "PANEL_INV_SW", "2": "GND"})
    flow(schottky, "D3", "PMEG6010ELRX (AEC-Q101, 60V/1A)",
         {"1": "PANEL_INV_SW", "2": "PANEL_VSN"})
    flow(c1206, "C47", "22u VNEG out 16V (AEC-Q200)",
         {"1": "PANEL_VSN", "2": "GND"})
    flow(r, "R40", "536k VNEG top R3 (see docstring)",
         {"1": "PANEL_VSN", "2": "PANEL_FBN"})
    flow(r, "R41", "100k VNEG bottom R4 to VREF (see docstring)",
         {"1": "PANEL_FBN", "2": "PANEL_VREF"})
    flow(c, "C49", "15p VNEG feed-forward (AEC-Q200)",
         {"1": "PANEL_VSN", "2": "PANEL_FBN"})
    flow(c, "C43", "220n VREF (AEC-Q200)",
         {"1": "PANEL_VREF", "2": "GND"})
    flow(c, "C44", "10n CP comp (AEC-Q200)", {"1": "PANEL_CP", "2": "GND"})
    flow(c, "C45", "4n7 CN comp (AEC-Q200)", {"1": "PANEL_CN", "2": "GND"})


def build_panel_backlight(x0, y0, usable_h):
    """
    Backlight boost driver for the TST040HDBC-42.

    Datasheet sections 1/7: 20 LEDs, 180 mA, Vf 15 V typ, 2.7 W - the
    array is 5 series x 4 parallel per the drawing's circuit diagram, all
    tied to one LEDA/LEDK pair (2 pins each). This is ~3.6x the power of
    the rejected DM-TFTR50-413's backlight and is the price of 800 nits.

    Real part: TI TPS61165-Q1 - AEC-Q100, SOT-23-6 boost white-LED driver,
    VIN 3-18 V, up to 38 V out, 1.2 MHz, 1.2 A typ switch limit (0.96 A
    min / 1.44 A max), VFB = 0.2 V, CTRL = enable + PWM dimming 5-100 kHz
    (TI SLVSB73B). Powered from +5V, NOT +12V_PROT: a boost cannot
    regulate a 15 V output from a 9-16 V (and load-dumped) input, while
    +5V -> 15 V is always a real boost. The previous AL8853AQ design
    (6 V minimum VIN, 37 V / 20 mA panel) is gone with the old panel.
      * R42 = 1.10 ohm sets ILED = 0.2 V / 1.10 = 182 mA (178-185 mA over
        the datasheet's 196-204 mV VFB window) vs the panel's 180 mA.
      * L4 = 10 uH (datasheet range 10-22 uH), Coilcraft XAL4040-103ME:
        Isat 3.0 A, above the 1.44 A worst-case switch limit.
      * D4 = PMEG6010ELRX (60 V, 1 A, AEC-Q101); TI recommends a fast
        Schottky with VR above the 38 V OVP threshold.
      * C51 = 220 nF COMP (datasheet: 220 nF suits most applications).
        C50 = 10 uF input, C52 = 4.7 uF / 50 V output (datasheet CO range
        1-10 uF; a 50 V X7R part keeps most of its capacitance at 15 V,
        unlike a 25 V part, and is the same verified part as C5/C55).
      * Output-current check (datasheet Eq. 3/4 logic): at VIN = 4.75 V,
        VOUT = 15.2 V the boost duty is ~0.69; with the 0.96 A MINIMUM
        limit the deliverable output is roughly 0.24 A, so 180 mA has
        only ~1.3x margin at the worst corner. Flagged, not hidden.
      * Thermal, flagged: 2.7 W of LED load through a SOT-23-6 (RthJA
        210 C/W) - internal FET loss is only ~0.1-0.2 W but must be
        checked on a prototype at 85 C ambient.
      * CTRL <- PANEL_BL_PWM (Verdin PWM_3_DSI, 1.8 V, above the 1.2 V VIH).
        This resolves the old "backlight dimming not wired" gap: the PWM
        duty sets VFB. Keep the PWM between 5 and 100 kHz; held low
        >2.5 ms it shuts the converter down.
      * +5V load: 2.7 W / ~0.88 = ~3.1 W = ~0.65 A extra on LM61460-Q1's
        6 A rail.
    """
    r, c = f"{LIB}:R", f"{LIB}:C"
    c1206 = f"{LIB}:C_1206"
    c0805 = f"{LIB}:C_0805"
    l10 = build_generic_symbol(f"{LIB}:L_10U", "L", "L", PASSIVE_PINS)
    schottky = f"{LIB}:SCHOTTKY_SOD123W"
    u_bl = build_generic_symbol(f"{LIB}:TPS61165-Q1", "U", "TPS61165-Q1",
                                parts.TPS61165_Q1)

    COL_W, ROW_H = 78.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    flow(u_bl, "U7", "TPS61165-Q1", {
        "VIN": "+5V", "GND": "GND", "SW": "BL_SW",
        "CTRL": "PANEL_BL_PWM",
        "FB": "PANEL_BL_LEDK", "COMP": "BL_COMP",
    })
    flow(c0805, "C50", "10u BL input (AEC-Q200)", {"1": "+5V", "2": "GND"})
    flow(l10, "L4", "10u BL boost (Coilcraft XAL4040-103ME)",
         {"1": "+5V", "2": "BL_SW"})
    flow(schottky, "D4", "PMEG6010ELRX (AEC-Q101, 60V/1A)",
         {"1": "PANEL_BL_LEDA", "2": "BL_SW"})
    flow(c1206, "C52", "4.7u BL output, 50V part (AEC-Q200)",
         {"1": "PANEL_BL_LEDA", "2": "GND"})
    flow(c, "C51", "220n BL COMP (AEC-Q200)", {"1": "BL_COMP", "2": "GND"})
    flow(r, "R42", "1.10R LED current sense (0.2V/1.10=182mA)",
         {"1": "PANEL_BL_LEDK", "2": "GND"})


def build_control(x0, y0, usable_h):
    """
    Power sequencing, reset, recovery and the JTAG header.

    The important connection here is CTRL_PWR_EN_MOCI: it is the module's
    own "carrier peripherals may power up now" output, and it stays high
    through sleep. Gating the 1.8 V and 3.3 V LDOs with it means the
    carrier rails follow the module rather than racing it at power-on.
    """
    r, c = f"{LIB}:R", f"{LIB}:C"
    conn_jtag = build_generic_symbol(f"{LIB}:CONN_JTAG", "J", "JTAG",
                                     [(1, "VREF", "passive"),
                                      (2, "TMS", "passive"),
                                      (3, "TCK", "passive"),
                                      (4, "TDO", "passive"),
                                      (5, "TDI", "passive"),
                                      (6, "TRST", "passive"),
                                      (7, "RESET", "passive"),
                                      (8, "GND", "passive")])
    conn_btn = build_generic_symbol(f"{LIB}:CONN_BTN", "J", "Buttons",
                                    [(1, "PWR_BTN", "passive"),
                                     (2, "RECOVERY", "passive"),
                                     (3, "RESET", "passive"),
                                     (4, "GND", "passive")])
    conn_cell = build_generic_symbol(f"{LIB}:CONN_CELL", "J", "RTC cell",
                                     [(1, "VBAT", "passive"),
                                      (2, "GND", "passive")])

    COL_W, ROW_H = 80.0, 26.0
    cur = {"col": 0, "y": y0}

    def flow(lib, ref, value, nets):
        h = generic_heights[lib]
        need = max(ROW_H, h + 12.0)
        if cur["y"] + need > y0 + usable_h:
            cur["col"] += 1
            cur["y"] = y0
        place_part(lib, ref, value,
                   x0 + cur["col"] * COL_W, cur["y"] + h / 2, nets)
        cur["y"] += need

    flow(conn_jtag, "J8", "Samtec TSW-108-07-G-S JTAG (bench only)", {
        "VREF": "JTAG_VREF", "TMS": "JTAG_TMS", "TCK": "JTAG_TCK",
        "TDO": "JTAG_TDO", "TDI": "JTAG_TDI", "TRST": "JTAG_TRST",
        "RESET": "RESET_MICO", "GND": "GND",
    })
    flow(conn_btn, "J9", "Samtec TSW-104-07-G-S buttons (bench only)", {
        "PWR_BTN": "PWR_BTN", "RECOVERY": "RECOVERY",
        "RESET": "RESET_MICO", "GND": "GND",
    })
    # These are active-low inputs to the module and are asserted by
    # shorting to ground, so each needs a pull-up to idle high. RECOVERY
    # already has a 10k pull-up on the module, but a local one costs
    # nothing and makes the intent readable on the drawing.
    for ref, net in (("R44", "PWR_BTN"), ("R45", "RECOVERY"),
                     ("R46", "RESET_MICO")):
        flow(r, ref, "10k pullup", {"1": net, "2": "+1V8"})
    flow(r, "R47", "10k pullup", {"1": "RESET_MOCI", "2": "+1V8"})
    flow(r, "R48", "10k JTAG Vref", {"1": "JTAG_VREF", "2": "+1V8"})

    # --- Ignition wake (rev B, 2026-09-30) --------------------------------
    # The Verdin sleeps (suspend-to-RAM) with ignition off and resumes when
    # ignition goes on, via its wake-capable pin CTRL_WAKE1_MICO# (X1 252,
    # 1.8 V). The ignition wire arrives on J2 with NO front-end protection,
    # so the network is built to survive load dump / ISO 7637 pulses:
    #   IGN -> R51 56k -> gate node (R52 33k to GND) -> Q3 gate
    # 9 V ignition gives 3.3 V at the gate (above PMV55ENEA's 2.4 V max
    # Vth); 16 V gives 5.9 V. D5 (BAV99-Q, AEC-Q101) clamps the gate node to
    # GND and +5V, so even an 80 V pulse through 56k is only ~1.4 mA into the
    # clamp and the gate never sees more than ~5.7 V (Vgs max is 20 V).
    # Q3 pulls IGN_WAKE_N low when ignition is on; R53 10k pulls it up to
    # +1V8 when off. The +1V8 LDO (U3) is always on while the 5 V buck runs,
    # so the idle level survives suspend. 10k is stiff enough against the
    # SoC pad's reset-state pull-down (the datasheet lists one but not its
    # value). The pin is also readable as a GPIO, so Android can see key
    # state directly in addition to gauges/'s PowerState message.
    # Verdin datasheet does not state the wake polarity: it is a software
    # edge setting, confirm on the module.
    nfet_sym = f"{LIB}:NFET"
    bav99 = build_generic_symbol(f"{LIB}:D_BAV99", "D", "BAV99-Q clamp",
                                 [(1, "A1", "passive"), (2, "K2", "passive"),
                                  (3, "CA", "passive")])
    flow(r, "R51", "56k ignition series", {"1": "IGN_SENSE", "2": "IGN_GATE"})
    flow(r, "R52", "33k ignition divider bottom", {"1": "IGN_GATE", "2": "GND"})
    flow(c, "C53", "10n ignition filter", {"1": "IGN_GATE", "2": "GND"})
    flow(bav99, "D5", "BAV99-Q ignition clamp (AEC-Q101)",
         {"A1": "GND", "K2": "+5V", "CA": "IGN_GATE"})
    flow(nfet_sym, "Q3", "PMV55ENEA ignition wake pulldown",
         {"G": "IGN_GATE", "D": "IGN_WAKE_N", "S": "GND"})
    flow(r, "R53", "10k wake pull-up to +1V8", {"1": "+1V8", "2": "IGN_WAKE_N"})

    # --- Rotary dial input (J11), 2026-10-02 -----------------------------
    # Dial: Amphenol Piher PSC-360 (user's choice, 2026-10-02), a contactless
    # Hall-effect end-of-shaft angle sensor: endless rotation with NO dead
    # band, 12-bit, 50 million cycles, -40..+125 C (Piher PSC-360 datasheet).
    # Analog (ratiometric) output option, 5 V +/-10 % supply, about 8.5 mA
    # for the single-output version. Its "switch output" is a programmable
    # ANGLE-threshold output, NOT a push button: the click is a separate
    # normally-open switch wired to J11 pin 4.
    #   J11: 1 = sensor 5 V (switched), 2 = sensor signal, 3 = ground (sensor
    #   and switch return), 4 = click switch to ground.
    # The sensor's 5 V comes through U8, a TPS22918-Q1 load switch, so it is
    # OFF during suspend (8.5 mA would otherwise be a constant drain); U8's
    # ON pin is the Verdin's CTRL_SLEEP_MOCI# (1.8 V, above the 1.0 V VIH).
    # The output is ratiometric to the 5 V supply (up to about 5.5 V), but the
    # Verdin ADC pin tolerates 2.1 V, so R54/R58 divide by 0.316 (22.1k /
    # 10.2k: 5.5 V -> 1.74 V, 5.0 V -> 1.58 V), then 1k / 100nF filter into
    # ADC_1. Divider impedance 32 kohm; the 100 nF filter capacitor supplies
    # the ADC's sampling charge. Ratiometric means the supply tolerance moves
    # the absolute reading by a couple of percent: harmless for relative
    # rotation, and software can calibrate the wrap point. BAV99-Q clamps on
    # both external lines. KNOWN LIMIT: the clamp turns on near 2.5 V, a
    # little above the ADC's 2.1 V absolute maximum; the divider and 1k
    # resistor limit fault current, fine for a short in-cabin cable.
    # The sensor comes with fly leads (brown supply, blue ground, black
    # signal); connector assembly is on request from Piher or crimp a KK 254
    # housing yourself. Verdin wake: none from the dial.
    conn_dial = build_generic_symbol(
        f"{LIB}:CONN_DIAL", "J", "Molex KK-254 22-27-2041 rotary dial",
        [(1, "DIAL_5V", "passive"), (2, "SIG", "passive"),
         (3, "GND", "passive"), (4, "CLICK", "passive")])
    u_dsw = build_generic_symbol(f"{LIB}:TPS22918-Q1", "U", "TPS22918-Q1",
                                 parts.TPS22918_Q1)
    flow(conn_dial, "J11", "Molex KK-254 22-27-2041, rotary dial (PSC-360 + click)",
         {"DIAL_5V": "DIAL_5V", "SIG": "DIAL_SIG_RAW", "GND": "GND",
          "CLICK": "DIAL_CLICK_RAW"})
    flow(u_dsw, "U8", "TPS22918-Q1 (AEC-Q100 G2) dial 5V switch", {
        "VIN": "+5V", "GND": "GND", "ON": "SLEEP_MOCI",
        "CT": None, "QOD": None, "VOUT": "DIAL_5V"})
    flow(c, "C60", "1u dial switch CIN", {"1": "+5V", "2": "GND"})
    flow(c, "C63", "1u dial 5V filter", {"1": "DIAL_5V", "2": "GND"})
    flow(r, "R54", "22.1k dial signal divider top", {"1": "DIAL_SIG_RAW", "2": "DIAL_DIV"})
    flow(r, "R58", "10.2k dial signal divider bottom", {"1": "DIAL_DIV", "2": "GND"})
    flow(r, "R55", "1k dial signal series", {"1": "DIAL_DIV", "2": "DIAL_ADC"})
    flow(c, "C61", "100n dial signal filter", {"1": "DIAL_ADC", "2": "GND"})
    flow(bav99, "D6", "BAV99-Q dial signal clamp (AEC-Q101)",
         {"A1": "GND", "K2": "+1V8", "CA": "DIAL_ADC"})
    flow(r, "R56", "1k dial click series", {"1": "DIAL_CLICK_RAW", "2": "DIAL_CLICK"})
    flow(r, "R57", "10k dial click pull-up to +1V8", {"1": "+1V8", "2": "DIAL_CLICK"})
    flow(c, "C62", "100n dial click debounce", {"1": "DIAL_CLICK", "2": "GND"})
    flow(bav99, "D7", "BAV99-Q dial click clamp (AEC-Q101)",
         {"A1": "GND", "K2": "+1V8", "CA": "DIAL_CLICK"})

    # RTC backup. The datasheet is explicit that a current-limiting
    # resistor of at least 47k must sit between the cell and VCC_BACKUP -
    # a lower value can stop the module booting.
    flow(conn_cell, "J10", "RTC coin cell",
         {"VBAT": "VBACKUP_CELL", "GND": "GND"})
    flow(r, "R49", "47k min", {"1": "VBACKUP_CELL", "2": "VBACKUP"})
    flow(c, "C39", "100n", {"1": "VBACKUP", "2": "GND"})


def main():
    x1_lib = build_x1_symbol()
    gnd_lib = rail("GND")
    v5_lib = rail("+5V")
    flag5_lib = build_pwr_flag("+5V")
    flaggnd_lib = build_pwr_flag("GND")

    units = verdin_x1.units()

    # Lay the units out in two rows. Widths are known (UNIT_W + leads +
    # room for the power symbols hanging off the pins), heights come from
    # the pin counts, so this is a fixed layout rather than a packer.
    col_pitch = 145.0
    positions = []
    for idx, (label, desc, entries) in enumerate(units):
        row, col = divmod(idx, 4)
        positions.append((70.0 + col * col_pitch, 95.0 + row * 210.0))

    n_gnd = n_v5 = n_nc = n_sig = 0
    gnd_net_xy, v5_net_xy = [], []
    for idx, ((label, desc, entries), (sx, sy)) in enumerate(
            zip(units, positions), start=1):
        place(x1_lib, "J1", "Verdin iMX95 Hexa 8GB WB IT", sx, sy, unit=idx,
              body_h=unit_heights[idx])

        for pin, name in entries:
            px, py = pin_xy(idx, pin, sx, sy)
            out = -1 if unit_pin_offsets[(idx, pin)][0] < 0 else 1

            if name in ("GND", "VCC"):
                # A short wire outward, then the power symbol at its far
                # end. The symbol's own pin sits at its local (0,0) with
                # zero length, so it must land exactly on a point of the
                # net - the wire's endpoint provides that. Placing the
                # symbol directly on the X1 pin also connects, but buries
                # the pin name under the symbol graphic; the wire buys
                # readability without giving up the connection.
                wx, wy = snap(px + out * STUB), py
                add_wire(px, py, wx, wy)
                if name == "GND":
                    place(gnd_lib, f"#PWR{pin}", "GND", wx, wy, hide_ref=True)
                    gnd_net_xy.append((wx, wy))
                    power_net_points.setdefault("GND", (wx, wy))
                    n_gnd += 1
                else:
                    place(v5_lib, f"#PWR{pin}", "+5V", wx, wy, hide_ref=True)
                    v5_net_xy.append((wx, wy))
                    power_net_points.setdefault("+5V", (wx, wy))
                    n_v5 += 1
            elif name in X1_NETS:
                out = -1 if unit_pin_offsets[(idx, pin)][0] < 0 else 1
                wx, wy = snap(px + out * STUB), py
                for pt in ((px, py), (wx, wy)):
                    prev = net_points.get(pt)
                    if prev and prev[0] != X1_NETS[name]:
                        print(f"  ERROR: {pt} carries both {prev[0]} "
                              f"(via {prev[1]}) and {X1_NETS[name]} (via J1)")
                    net_points[pt] = (X1_NETS[name], "J1")
                add_wire(px, py, wx, wy)
                add_label(X1_NETS[name], wx, wy, 0 if out > 0 else 180)
                n_sig += 1
            elif name in X1_NC or label.startswith("E"):
                # Deliberately unused. This project's KiCad notes record
                # that a stub wire plus a unique local label reads to ERC
                # as a dangling label - a real NoConnect is the fix.
                sch.noConnects.append(NoConnect(position=Position(px, py),
                                                uuid=U()))
                n_nc += 1

    build_common_symbols()

    # Each block gets its own band. The x origins are spaced so that no
    # block's rightmost labels can reach the next block's leftmost stubs;
    # the net-collision check below is what proves it. Fewer blocks than
    # fascia-pcb's own layout (no audio, no USB), so there's real spare
    # room on this sheet - left as-is rather than re-packed, since a
    # sparser A0 sheet costs nothing and re-tuning the band coordinates
    # is exactly the kind of "looks different, proves nothing" busywork
    # the net-collision check below already guards against for free.
    build_panel(60.0, 430.0, 370.0)
    build_1v8_and_can(300.0, 430.0, 370.0)
    build_power_tree(660.0, 60.0, 700.0)
    build_control(60.0, 60.0, 280.0)
    build_panel_bias(920.0, 60.0, 330.0)
    build_panel_backlight(920.0, 400.0, 400.0)

    # Neither rail has a regulator on the sheet yet, so nothing drives
    # them and ERC's power_pin_not_driven fires. Assert they come from
    # off-sheet with PWR_FLAGs - placed COINCIDENT with a real point on
    # each net, because this project's KiCad notes record that a flag
    # relying only on name-based net merging, with no wire or coincident
    # point touching it, does not satisfy that ERC check.
    undriven = [n for n in sorted(power_net_points) if n not in driven_nets]
    for n, net in enumerate(undriven, start=1):
        place(build_pwr_flag(net), f"#FLG{n}", f"PWR_FLAG {net}",
              *power_net_points[net], hide_ref=True)
    print(f"  PWR_FLAGs on undriven rails: {', '.join(undriven)}")
    if driven_nets:
        print(f"  rails with a real driver (no flag): "
              f"{', '.join(sorted(driven_nets))}")

    # Every footprint named in parts.FOOTPRINTS must really exist. A typo
    # in a library path is otherwise invisible until the netlist reaches
    # the PCB editor and silently drops the part.
    # Two roots: KiCad's own libraries, and this project's generated
    # ones. The LM61460-Q1's VQFN-HR package has no stock footprint,
    # so it lives in footprints/ and is built by
    # tools/build_lm61460_footprint.py.
    fp_roots = [
        os.path.join('C:' + os.sep, 'Program Files', 'KiCad', '10.0',
                     'share', 'kicad', 'footprints'),
        os.path.join(HERE, 'footprints'),
    ]
    missing_fp = []
    for name, fp in sorted(parts.FOOTPRINTS.items()):
        if not fp:
            continue
        lib, _, fpname = fp.partition(':')
        rel = os.path.join(lib + '.pretty', fpname + '.kicad_mod')
        if not any(os.path.exists(os.path.join(r, rel))
                   for r in fp_roots):
            missing_fp.append(f"{name} -> {fp}")
    if missing_fp:
        print(f"  ERROR: {len(missing_fp)} footprint(s) not found:")
        for m in missing_fp:
            print("    ", m)
    unassigned = [n for n, fp in parts.FOOTPRINTS.items() if not fp]
    if unassigned:
        print(f"  footprints still to generate: {', '.join(unassigned)}")

    # Net-collision check. Sections are laid out independently, so two
    # of them can drift into the same region and land a stub endpoint of
    # one net exactly on top of another's. That silently MERGES the two
    # nets - electrically catastrophic and invisible on a casual look at
    # the drawing. ERC does report it (multiple_net_names) but only after
    # the fact and only for the pair it happens to notice; this checks
    # every terminated point directly.
    at = {}
    for lab in sch.labels:
        at.setdefault((lab.position.X, lab.position.Y), set()).add(
            (lab.text, "label"))
    for sym in sch.schematicSymbols:
        # PWR_FLAGs are placed coincident with their own net ON PURPOSE,
        # so they are not collisions - skip them.
        if sym.entryName.startswith("PWR_FLAG_"):
            continue
        if sym.entryName.startswith("PWR_"):
            ref = sym.properties[0].value if sym.properties else "?"
            at.setdefault((sym.position.X, sym.position.Y), set()).add(
                (sym.entryName[4:], ref))
    clashes = {p: n for p, n in at.items()
               if len({net for net, _ in n}) > 1}
    if clashes:
        print(f"  ERROR: {len(clashes)} coordinate(s) carry more than one net:")
        for pos, names in list(clashes.items())[:8]:
            print(f"    {pos}: {sorted(names)}")

    # Sheet extent sanity check - this project's KiCad notes record content
    # silently running off a fixed-size sheet with no warning in the editor.
    for s in sch.schematicSymbols:
        if not (0 < s.position.X < SHEET_W and 0 < s.position.Y < SHEET_H):
            print(f"  WARNING: {s.entryName} at "
                  f"({s.position.X}, {s.position.Y}) is off the {PAPER} sheet")

    SymbolLib(symbols=list(lib_symbols.values())).to_file(OUT_SYM)
    sch.libSymbols = list(lib_symbols.values())
    sch.to_file(OUT_SCH)

    # kicad-cli only resolves ${KIPRJMOD} in sym-lib-table when a project
    # file exists next to the schematic; without it every placed symbol
    # draws a lib_symbol_issues warning ("configuration does not include
    # the symbol library"). Written only when absent, because KiCad
    # rewrites this file with its full default settings the first time the
    # project is opened and those settings are the user's, not ours.
    if not os.path.exists(OUT_PRO):
        with open(OUT_PRO, "w", encoding="utf-8") as f:
            json.dump({
                "board": {}, "boards": [],
                "libraries": {"pinned_footprint_libs": [],
                              "pinned_symbol_libs": []},
                "meta": {"filename": f"{LIB}.kicad_pro", "version": 1},
                "net_settings": {}, "pcbnew": {}, "schematic": {},
                "sheets": [], "text_variables": {},
            }, f, indent=2)

    # Without this, KiCad has the symbols embedded in the .kicad_sch but no
    # library registered to check them against, and ERC reports one
    # lib_symbol_issues warning per placed symbol.
    with open(OUT_TABLE, "w", encoding="utf-8") as f:
        f.write("(sym_lib_table\n")
        f.write("\t(version 7)\n")
        f.write(f'\t(lib (name "{LIB}") (type "KiCad") '
                f'(uri "${{KIPRJMOD}}/{LIB}.kicad_sym") (options "") '
                f'(descr "{LIB} project-local symbol library - regenerated '
                f'by build_schematic.py, do not hand-edit"))\n')
        f.write(")\n")

    total_pins = sum(len(e) for _, _, e in units)
    print(f"wrote {os.path.basename(OUT_SYM)} and {os.path.basename(OUT_SCH)}")
    print(f"  X1: {total_pins} pins across {len(units)} units")
    print(f"  connected: {n_gnd} GND, {n_v5} VCC")
    print(f"  no-connect: {n_nc}")
    print(f"  signal nets wired: {n_sig}")
    print(f"  left for later stages: "
          f"{total_pins - n_gnd - n_v5 - n_nc - n_sig}")


if __name__ == "__main__":
    main()
