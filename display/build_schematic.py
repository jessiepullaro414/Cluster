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
dash's center opening (real target: DisplayModule DM-TFTR50-413, 5.0",
1080x1080, native MIPI-DSI, HX8399 driver - a real, orderable, bigger
round panel per the user's own "find a slightly larger round display
... to maximize" request), and that panel speaks DSI natively, so
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
own docstring for why), and control/JTAG/RTC. CONN_PANEL's exact pin
count/pitch is still provisional pending DisplayModule's real datasheet
PDF, same "real part, provisional connector" situation fascia-pcb's own
CONN_PANEL was in at this stage.

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
    "DSI_1_D3_P": "DSI_D3_P", "DSI_1_D3_N": "DSI_D3_N",
    "DSI_1_CLK_P": "DSI_CLK_P", "DSI_1_CLK_N": "DSI_CLK_N",
    # I2C_2_DSI_SDA/SCL dropped: that was the SN65DSI85-Q1 bridge's own
    # config bus, and there is no bridge on this board anymore (direct
    # DSI to the panel - see build_panel()'s own docstring). They fall
    # through to bank C's genuinely-unused pins.
    "GPIO_9_DSI": "DSI_PANEL_EN",
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
    "CTRL_FORCE_OFF_MOCI#",  # datasheet: "can be left floating"
    "CTRL_WAKE1_MICO#",      # "can be left floating if wake is disabled"
    "CTRL_SLEEP_MOCI#",      # no carrier rail is sequenced off in sleep
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
    """
    lib_id = f"{LIB}:Verdin_iMX95_X1"
    parent = Symbol.create_new(
        id=lib_id, reference="J", value="Verdin iMX95",
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
POWER_NETS = {"GND", "+5V", "+12V_PROT", "+1V8", "+3V3", "VBAT_F"}

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
    """
    r, c, l = f"{LIB}:R", f"{LIB}:C", f"{LIB}:L"
    tvs, fuse, nfet = f"{LIB}:TVS", f"{LIB}:FUSE", f"{LIB}:NFET"
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
    flow(conn3, "J2", "Power in",
         {"VBAT": "VBAT_IN", "GND": "GND", "IGN": "IGN_SENSE"})
    flow(fuse, "F1", "5A", {"1": "VBAT_IN", "2": "VBAT_F"})
    flow(tvs, "D1", "TVS 33V", {"1": "VBAT_F", "2": "GND"})
    flow(c, "C1", "100uF", {"1": "VBAT_F", "2": "GND"})

    # RSENSE sits in the input path; CS+ taps it through RSET per the
    # datasheet's "connect a 50-ohm resistor across CS+".
    flow(r, "R1", "2m sense", {"1": "VBAT_F", "2": "SENSE_OUT"})
    flow(r, "R2", "50R", {"1": "VBAT_F", "2": "CS_PLUS"})

    # --- back-to-back FETs ----------------------------------------------
    flow(nfet, "Q2", "NFET pass",
         {"D": "SENSE_OUT", "G": "HGATE", "S": "COMMON"})
    flow(nfet, "Q1", "NFET diode",
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
        ("C4", "open CT", {"1": "TMR", "2": "GND"}),
        ("R3", "RILIM", {"1": "ILIM", "2": "GND"}),
        ("R4", "5k RMON", {"1": "IMON", "2": "GND"}),
        ("R5", "OV top", {"1": "SW_SENSE", "2": "OV_DIV"}),
        ("R6", "OV bot", {"1": "OV_DIV", "2": "GND"}),
        ("R7", "UV top", {"1": "SW_SENSE", "2": "UVLO_DIV"}),
        ("R8", "UV bot", {"1": "UVLO_DIV", "2": "GND"}),
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
        ("C5", "10u in", c, {"1": "+12V_PROT", "2": "GND"}),
        ("C6", "1u VCC", c, {"1": "VCC_LDO", "2": "GND"}),
        ("C7", "100n boot", c, {"1": "BOOT_C", "2": "SW_5V"}),
        ("R9", "RBOOT", r, {"1": "BOOT_R", "2": "BOOT_C"}),
        ("L1", "2.2u", l, {"1": "SW_5V", "2": "+5V"}),
        ("C8", "44u out", c, {"1": "+5V", "2": "GND"}),
        ("R10", "FB top", r, {"1": "+5V", "2": "FB_5V"}),
        ("R11", "FB bot", r, {"1": "FB_5V", "2": "GND"}),
        ("R12", "RT", r, {"1": "RT_5V", "2": "GND"}),
        ("R13", "EN top", r, {"1": "+12V_PROT", "2": "EN_5V"}),
        ("R14", "EN bot", r, {"1": "EN_5V", "2": "GND"}),
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
    flow(c, "C9", "10u in", {"1": "+5V", "2": "GND"})
    flow(c, "C10", "10u out", {"1": "+1V8", "2": "GND"})
    flow(r, "R17", "FB top", {"1": "+1V8", "2": "FB_1V8"})
    flow(r, "R18", "FB bot", {"1": "FB_1V8", "2": "GND"})

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

    flow(conn_can, "J3", "CAN to ECU",
         {"CANH": "CAN1_H", "CANL": "CAN1_L", "GND": "GND"})


def build_panel(x0, y0, usable_h):
    """
    Direct MIPI-DSI panel connector - NO bridge chip.

    RE-SCOPED 2026-09-25: the target panel is now DisplayModule
    DM-TFTR50-413 (5.0", 1080x1080, real MIPI-DSI interface, HX8399
    driver, $119, real datasheet available - a much bigger real round
    panel than the original 2.1" BH021WVC02, per the user's "find a
    slightly larger round display ... to maximize" request now that the
    faceplate is custom anyway). Because this panel speaks DSI natively,
    fascia-pcb's own reason for the SN65DSI85-Q1 bridge (its target
    panel was LVDS-only, and needed a resolution above the Verdin
    module's native LVDS ceiling) simply doesn't apply here - there is
    no LVDS anywhere in this board's real requirement. Wiring the
    Verdin's own DSI_1_* X1 pins straight to the panel is both simpler
    (one fewer real IC, no VCORE/REFCLK/bypass network) and more direct
    than converting to LVDS and back to a digital panel that never
    wanted LVDS in the first place. Real DSI panels are also configured
    over the DSI link itself (command-mode packets), not a separate I2C
    bus the way the SN65DSI85-Q1 needed - so DSI_I2C_SDA/SCL (bridge-
    config-only pins) are dropped from this board's X1_NETS entirely
    (see verdin_x1.py/main() - they now fall through to bank C's
    genuinely-unused pins, same as fascia-pcb's own not-yet-wired items).

    CONN_PANEL is still PROVISIONAL - DisplayModule's product page does
    not list the real FPC connector pin count/pinout, only the 4-lane
    MIPI-DSI electrical interface itself (which IS real: 4 real X1 data-
    lane pairs + 1 real clock pair, all confirmed Verdin pins, not
    guessed). The real datasheet PDF (linked from the product page) needs
    pulling before this connector is final - same "real part, provisional
    connector" state fascia-pcb's own CONN_PANEL was in at this stage.
    """
    lane_pins = []
    n = 1
    for sig in ("D0", "D1", "D2", "D3", "CLK"):
        for pol in ("P", "N"):
            lane_pins.append((n, f"{sig}{pol}", "passive"))
            n += 1
    lane_pins.append((n, "PANEL_EN", "passive"))
    lane_pins.append((n + 1, "GND1", "passive"))
    lane_pins.append((n + 2, "GND2", "passive"))
    conn_panel = build_generic_symbol(f"{LIB}:CONN_PANEL", "J",
                                      "Panel MIPI-DSI", lane_pins)

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

    panel = {}
    for lane, net in (("0", "D0"), ("1", "D1"), ("2", "D2"), ("3", "D3")):
        panel[f"{net}P"] = f"DSI_{net}_P"
        panel[f"{net}N"] = f"DSI_{net}_N"
    panel["CLKP"], panel["CLKN"] = "DSI_CLK_P", "DSI_CLK_N"
    # GPIO_9_DSI was the bridge's own EN pin in fascia-pcb's design; here
    # it does the same real job one level down - a hardware enable/reset
    # line into the panel module itself, which real DSI panel modules
    # commonly expose. Real destination pin TBD pending the datasheet
    # pull, same provisional status as the connector's pin count.
    panel["PANEL_EN"] = "DSI_PANEL_EN"
    panel["GND1"] = panel["GND2"] = "GND"
    flow(conn_panel, "J4", "Panel MIPI-DSI (provisional)", panel)


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

    flow(conn_jtag, "J8", "JTAG debug", {
        "VREF": "JTAG_VREF", "TMS": "JTAG_TMS", "TCK": "JTAG_TCK",
        "TDO": "JTAG_TDO", "TDI": "JTAG_TDI", "TRST": "JTAG_TRST",
        "RESET": "RESET_MICO", "GND": "GND",
    })
    flow(conn_btn, "J9", "Buttons", {
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
        place(x1_lib, "J1", "Verdin iMX95", sx, sy, unit=idx,
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
