"""
Generates a KiCad schematic (.kicad_sch) for "Cluster": a digital
instrument cluster for a 1966 Ford Mustang, sibling to manifold-pcb/
ecu-pcb/thermo-pcb/fascia-pcb. Same 12V/AEC-Q/automotive-rated
constraint as the rest of the family. Self-contained: all symbols are
embedded generic placeholders (rectangle body, correct pin count/names/
electrical types).

*** STARTING POINT COPIED FROM thermo-pcb, PARTIALLY ADAPTED ***
The generator FRAMEWORK below (register_symbol/place/wire_pins/
section_text/the validation checks, etc) and the 12V power-input-
protection + 5V-buck + 3.3V-LDO stage are reused near-verbatim from
manifold-pcb's own proven, real circuit (via thermo-pcb) - no reason to
re-derive a protection stage that's already correct. The MCU core
(NXP S32K144, same exact part/package thermo-pcb and manifold-pcb use)
is also reused for its FIXED pins only (crystal/SWD/RESET/power) - see
README.md's "MCU pin/peripheral budget" section for the real,
already-completed research confirming this part/package comfortably
covers Cluster's real peripheral needs.

*** PIN-MUX RESEARCH DONE 2026-09-22 (plan Step 1) ***: U1 now exposes
25 real, conflict-checked peripheral pins (LPSPI1 for BT817AQ's QSPI,
LPSPI2 for the shared aux-gauge SPI bus, FlexCAN0, 4x ADC channel, and
9 plain GPIO for CS/DC/reset/backlight/power-down control) - see the
detailed citation comment right above U1's registration below for the
real source (NXP's own S32K1xx Reference Manual embedded IO-signal-
table attachment) and the exact pin list. Every one of those 25 pins is
wired only as far as a real, named label stub this pass, not yet to any
actual peripheral chip.

*** WHAT THIS PASS STILL DOES NOT INCLUDE *** (not guessed, not
stubbed with placeholder pins beyond the MCU-side labels above): the
4x GC9A01 aux-gauge symbols/wiring, the BT817AQ symbol + its link to
the ST7701S speedo module, the TJA1043T CAN transceiver, and the
sensor/ADC divider front end. Each of those needs its own real
datasheet pin-table registration (BT817AQ's real VQFN-64 pinout,
GC9A01's real 8-pin table, TJA1043T reused from ecu-pcb) before it can
be wired - see plan Steps 2-5. Wiring any of them with guessed pins/
values would be exactly the mistake this whole project family has
repeatedly caught and corrected in its own history (see
kicad-file-generation-gotchas).

Connectivity model (same convention as every sibling project):
  * REAL WIRES for the main signal flow.
  * POWER SYMBOLS (+5V / +3V3 / GND / VIN) everywhere a power net is touched.
    Power nets NEVER use local labels (mixing local labels with power-symbol
    nets splits them into separate nets in KiCad).
  * LOCAL LABELS only for genuine cross-sheet-style references.

Geometry: KiCad symbol space is Y-UP; the schematic sheet is Y-DOWN. A pin
defined at (px, py) in a symbol placed at (x, y) rot 0 lands at (x+px, y-py).
Pin 'at' is the electrical connection point; pin angle points TOWARD the body.
"""
import os
import uuid as uuid_lib

from kiutils.schematic import Schematic
from kiutils.symbol import Symbol, SymbolPin
from kiutils.items.common import (Position, Property, Effects, Font, Stroke,
                                  PageSettings, TitleBlock, Justify)
from kiutils.items.syitems import SyRect, SyPolyLine
from kiutils.items.schitems import (SchematicSymbol, Connection, LocalLabel,
                                    SymbolInstance, Text as SchText, NoConnect)


def U():
    return str(uuid_lib.uuid4())


PITCH = 2.54
LEAD = 2.54
POWER_NETS = {"+5V", "+3V3", "GND", "VIN"}

# KiCad's default schematic grid (50 mil). See thermo-pcb/manifold-pcb's own
# build_schematic.py for the full history of why this snap exists (259 real
# endpoint_off_grid ERC hits before it did) - reused verbatim, same reasoning.
GRID = 1.27


def snap(v):
    return round(round(v / GRID) * GRID, 2)

# pin angle points from connection tip toward body (KiCad convention)
SIDE_ANGLE = {'L': 0, 'R': 180, 'T': 270, 'B': 90}
# outward direction of a stub on the SHEET (Y-down) for each side
STUB_DIR = {'L': (-1, 0), 'R': (1, 0), 'T': (0, -1), 'B': (0, 1)}
# label rotation so text reads away from the symbol
LABEL_ANGLE = {'L': 180, 'R': 0, 'T': 90, 'B': 270}


# ---------------------------------------------------------------------------
# Symbol factory
# ---------------------------------------------------------------------------
def layout(sides):
    """sides: {'L'/'R'/'T'/'B': [(number, name, etype), ...]} in top-to-bottom
    (L/R) or left-to-right (T/B) SHEET order. Returns (w, h, pins, side_map)."""
    nL, nR = len(sides.get('L', [])), len(sides.get('R', []))
    nT, nB = len(sides.get('T', [])), len(sides.get('B', []))
    height = max(max(nL, nR, 1) * PITCH + PITCH, PITCH * 2)
    width = max(max(nT, nB, 1) * PITCH + PITCH, PITCH * 2)
    pins, side_map = [], {}

    def add_vertical(entries, x_tip, angle, side):
        n = len(entries)
        for i, (num, name, etype) in enumerate(entries):
            # symbol space is Y-up: first entry gets largest py -> top on sheet
            py = ((n - 1) * PITCH) / 2 - i * PITCH
            pins.append(SymbolPin(electricalType=etype, graphicalStyle="line",
                                  position=Position(round(x_tip, 2), round(py, 2), angle),
                                  length=LEAD, name=name, number=str(num)))
            side_map[str(num)] = side

    def add_horizontal(entries, y_tip, angle, side):
        n = len(entries)
        for i, (num, name, etype) in enumerate(entries):
            px = -((n - 1) * PITCH) / 2 + i * PITCH
            pins.append(SymbolPin(electricalType=etype, graphicalStyle="line",
                                  position=Position(round(px, 2), round(y_tip, 2), angle),
                                  length=LEAD, name=name, number=str(num)))
            side_map[str(num)] = side

    if 'L' in sides:
        add_vertical(sides['L'], -(width / 2 + LEAD), SIDE_ANGLE['L'], 'L')
    if 'R' in sides:
        add_vertical(sides['R'], width / 2 + LEAD, SIDE_ANGLE['R'], 'R')
    if 'T' in sides:
        add_horizontal(sides['T'], height / 2 + LEAD, SIDE_ANGLE['T'], 'T')
    if 'B' in sides:
        add_horizontal(sides['B'], -(height / 2 + LEAD), SIDE_ANGLE['B'], 'B')
    return width, height, pins, side_map


lib_symbols = {}   # lib_id -> (Symbol, side_map, width, height)


def register_symbol(lib_id, ref_prefix, value, footprint, sides,
                    datasheet="~", hide_pin_names=False):
    w, h, pins, side_map = layout(sides)
    sym = Symbol.create_new(id=lib_id, reference=ref_prefix, value=value,
                            footprint=footprint, datasheet=datasheet)
    sym.pinNames = True
    sym.pinNamesOffset = 0.508
    sym.pinNamesHide = hide_pin_names
    sym.hidePinNumbers = False
    sym.properties[0].position = Position(0, h / 2 + 1.8, 0)    # Ref above (sym Y-up)
    sym.properties[1].position = Position(0, -(h / 2 + 1.8), 0)  # Value below
    sym.graphicItems.append(SyRect(
        start=Position(-w / 2, -h / 2), end=Position(w / 2, h / 2),
        stroke=Stroke(width=0.254, type="default")))
    sym.graphicItems[-1].fill.type = "background"
    sym.pins = pins
    lib_symbols[lib_id] = (sym, side_map, w, h)


def register_power_symbol(net, is_gnd):
    lib_id = f"{LIB}:PWR_{net}"
    sym = Symbol.create_new(id=lib_id, reference="#PWR", value=net)
    sym.isPower = True
    sym.pinNames = True
    sym.pinNamesOffset = 0
    sym.pinNamesHide = True
    sym.hidePinNumbers = True
    sym.properties[0].effects.hide = True                      # hide "#PWR" ref
    stroke = Stroke(width=0.254, type="default")
    if is_gnd:
        sym.properties[1].position = Position(0, -4.6, 0)      # value below
        for pts in ([(0, 0), (0, -1.27)],
                    [(-1.27, -1.27), (1.27, -1.27)],
                    [(-0.762, -1.905), (0.762, -1.905)],
                    [(-0.254, -2.54), (0.254, -2.54)]):
            sym.graphicItems.append(SyPolyLine(
                points=[Position(a, b) for a, b in pts], stroke=stroke))
    else:
        sym.properties[1].position = Position(0, 3.9, 0)       # value above bar
        for pts in ([(0, 0), (0, 2.54)],
                    [(-1.016, 2.54), (1.016, 2.54)]):
            sym.graphicItems.append(SyPolyLine(
                points=[Position(a, b) for a, b in pts], stroke=stroke))
    sym.pins = [SymbolPin(electricalType="power_in", graphicalStyle="line",
                          position=Position(0, 0, 90), length=0,
                          name=net, number="1", hide=True)]
    lib_symbols[lib_id] = (sym, {"1": 'T'}, 0, 0)


def register_pwr_flag(net):
    """Real KiCad PWR_FLAG equivalent - see thermo-pcb's own docstring for
    the full reasoning (VIN/GND both enter this board off-sheet via the
    battery, ERC needs an explicit assertion that's expected)."""
    lib_id = f"{LIB}:PWR_FLAG_{net}"
    sym = Symbol.create_new(id=lib_id, reference="#FLG", value=net)
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
    lib_symbols[lib_id] = (sym, {"1": 'T'}, 0, 0)


# ---------------------------------------------------------------------------
# Schematic scaffolding
# ---------------------------------------------------------------------------
sch = Schematic.create_new()
# Grown from A2 to A1 while wiring plan Step 3 (aux gauges) - A2's 420mm
# height had no room left for a 4th subsystem row below the existing
# power/MCU/CAN0 content, same "grow the page when real content doesn't
# fit" move thermo-pcb (A3->A2) and fascia-pcb (straight to A0 given
# known complexity) both already established for this project family.
sch.paper = PageSettings(paperSize="A1")
sch.uuid = U()
sch.titleBlock = TitleBlock(
    title="Cluster - digital instrument cluster, 1966 Mustang, automotive board",
    date="2026-09-22", revision="A",
    company="Generated design spec - verify before fab",
    comments={1: "Power stage + MCU core (fixed pins only) wired and verified. "
                 "Displays/CAN/sensor front end pending real S32K144 pin-mux "
                 "research - see README.md and this file's own header."})

wires, labels, texts, no_connects = [], [], [], []
pin_pos = {}        # (ref, pin_number_str) -> (x, y) on sheet
pwr_count = 0


def add_wire(x1, y1, x2, y2):
    wires.append(Connection(type="wire",
                            points=[Position(round(x1, 2), round(y1, 2)),
                                    Position(round(x2, 2), round(y2, 2))],
                            stroke=Stroke(width=0.0, type="default"), uuid=U()))


def add_label(text, x, y, angle):
    assert text not in POWER_NETS, f"power net {text} must use a power symbol, not a label"
    labels.append(LocalLabel(text=text, position=Position(round(x, 2), round(y, 2), angle),
                             effects=Effects(font=Font(width=1.27, height=1.27)),
                             uuid=U()))


def _instance(lib_id, ref, value, x, y, ref_hidden=False):
    sym, _, _, h = lib_symbols[lib_id]
    inst = SchematicSymbol()
    inst.libId = lib_id
    inst.position = Position(x, y, 0)
    inst.unit = 1
    inst.inBom = not ref.startswith("#")
    inst.onBoard = True
    inst.uuid = U()
    fp = next((p.value for p in sym.properties if p.key == "Footprint"), "")
    ref_eff = Effects(font=Font(width=1.27, height=1.27), hide=ref_hidden)
    val_y = y - sym.properties[1].position.Y   # sheet Y-down flip of value pos
    ref_y = y - sym.properties[0].position.Y
    inst.properties = [
        Property(key="Reference", value=ref, id=0, position=Position(x, ref_y, 0), effects=ref_eff),
        Property(key="Value", value=value, id=1, position=Position(x, val_y, 0),
                 effects=Effects(font=Font(width=1.27, height=1.27))),
        Property(key="Footprint", value=fp, id=2, position=Position(x, y, 0),
                 effects=Effects(font=Font(width=1.27, height=1.27), hide=True)),
    ]
    for pin in sym.pins:
        inst.pins[pin.number] = U()
    sch.schematicSymbols.append(inst)
    sch.symbolInstances.append(SymbolInstance(
        path=f"/{inst.uuid}", reference=ref, unit=1, value=value, footprint=fp))
    return inst


def place_power(net, x, y):
    """Power symbol whose connection point is exactly (x, y)."""
    global pwr_count
    pwr_count += 1
    _instance(f"{LIB}:PWR_{net}", f"#PWR{pwr_count:03d}", net, x, y, ref_hidden=True)


flg_count = 0


def place_pwr_flag(net, x, y):
    """PWR_FLAG instance - joins `net`'s global net by name, same mechanism
    as place_power, doesn't need to sit at any particular existing wire/pin
    coordinate."""
    global flg_count
    flg_count += 1
    _instance(f"{LIB}:PWR_FLAG_{net}", f"#FLG{flg_count:03d}", net, x, y, ref_hidden=True)


def place(lib_id, ref, value, x, y, conn=None):
    """Place a part. conn maps pin number -> one of:
         ('wire',)                   no stub; a wire will be drawn to the pin later
         ('label', NAME[, stub_len]) stub outward + local label
         ('pwr', NET[, stub_len])    stub (+riser if horizontal) + power symbol
         ('nc',)                     no-connect flag directly on the pin
       default: ('label', <pin name>, LEAD)"""
    x, y = snap(x), snap(y)
    conn = {str(k): v for k, v in (conn or {}).items()}
    sym, side_map, w, h = lib_symbols[lib_id]
    _instance(lib_id, ref, value, x, y)

    for pin in sym.pins:
        num = pin.number
        px = round(x + pin.position.X, 2)
        py = round(y - pin.position.Y, 2)   # Y-flip: symbol Y-up -> sheet Y-down
        pin_pos[(ref, num)] = (px, py)
        if pin.electricalType == "no_connect" and num not in conn:
            no_connects.append(NoConnect(position=Position(px, py), uuid=U()))
            continue
        mode = conn.get(num, ('label', pin.name, LEAD))
        kind = mode[0]
        if kind == 'wire':
            continue
        if kind == 'nc':
            no_connects.append(NoConnect(position=Position(px, py), uuid=U()))
            continue
        side = side_map[num]
        dx, dy = STUB_DIR[side]
        stub = mode[2] if len(mode) > 2 else LEAD
        ex, ey = round(px + dx * stub, 2), round(py + dy * stub, 2)
        add_wire(px, py, ex, ey)
        if kind == 'label':
            name = mode[1]
            if name in ("~", ""):
                raise ValueError(f"{ref}.{num}: generic pin needs a net in conn")
            add_label(name, ex, ey, LABEL_ANGLE[side])
        elif kind == 'pwr':
            net = mode[1]
            if side in ('T', 'B'):
                place_power(net, ex, ey)
            else:
                rise = PITCH if net == "GND" else -PITCH   # sheet Y-down: up = -Y
                add_wire(ex, ey, ex, ey + rise)
                place_power(net, ex, ey + rise)


def off(lib_id, num):
    """Sheet-space offset of a pin from its symbol origin."""
    sym, _, _, _ = lib_symbols[lib_id]
    for p in sym.pins:
        if p.number == str(num):
            return p.position.X, -p.position.Y
    raise KeyError(num)


def wire_pins(refA, pinA, refB, pinB, label=None, label_x=None):
    (x1, y1), (x2, y2) = pin_pos[(refA, str(pinA))], pin_pos[(refB, str(pinB))]
    assert abs(y1 - y2) < 0.01 or abs(x1 - x2) < 0.01, \
        f"{refA}.{pinA} -> {refB}.{pinB} not aligned: ({x1},{y1}) vs ({x2},{y2})"
    add_wire(x1, y1, x2, y2)
    if label:
        lx = label_x if label_x is not None else (x1 + x2) / 2
        add_label(label, lx, y1, 0)


def section_text(s, x, y):
    texts.append(SchText(text=s, position=Position(x, y, 0),
                         effects=Effects(font=Font(height=2.0, width=2.0,
                                                   thickness=0.35, bold=True),
                                          justify=Justify(horizontally="left"))))


# ---------------------------------------------------------------------------
# Symbol definitions
# ---------------------------------------------------------------------------
LIB = "Cluster"
def P(num, name, etype):
    return (num, name, etype)

for net in ("+5V", "+3V3", "VIN"):
    register_power_symbol(net, is_gnd=False)
register_power_symbol("GND", is_gnd=True)
register_pwr_flag("VIN")
register_pwr_flag("GND")

# --- Power stage: reused VERBATIM from manifold-pcb/thermo-pcb's own proven
# circuit (same real parts, same real datasheet-verified pin tables) - no
# reason to re-derive a reverse-battery-protection + buck + LDO stage this
# project family has already built and fab-verified twice. See thermo-pcb's
# own build_schematic.py for the original research/citations behind each
# part choice; not re-derived or re-justified here.
register_symbol(f"{LIB}:Fuse", "F", "2A holder for Littelfuse 297-series MINI blade fuse",
                "Fuse:Fuseholder_Blade_Mini_Keystone_3568",
                {'L': [P(1, "~", "passive")], 'R': [P(2, "~", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:TVS_V", "D", "SMCJ33A", "Diode_SMD:D_SMC",
                {'T': [P(1, "~", "passive")], 'B': [P(2, "~", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:C_V", "C", "100nF", "Capacitor_SMD:C_0603_1608Metric",
                {'T': [P(1, "~", "passive")], 'B': [P(2, "~", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:L_H", "L", "10uH", "Inductor_SMD:L_1210_3225Metric",
                {'L': [P(1, "~", "passive")], 'R': [P(2, "~", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:R_V", "R", "10k", "Resistor_SMD:R_0603_1608Metric",
                {'T': [P(1, "~", "passive")], 'B': [P(2, "~", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:XTAL", "Y", "8MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
                {'R': [P(1, "OSC_IN", "passive"), P(2, "OSC_OUT", "passive")],
                 'L': [P(3, "OSC_IN", "passive"), P(4, "OSC_OUT", "passive")]},
                hide_pin_names=True)
register_symbol(f"{LIB}:MOSFET_N", "Q", "PMV37ENEA automotive (AEC-Q101)", "Package_TO_SOT_SMD:SOT-23",
                {'L': [P(2, "S", "passive")], 'R': [P(3, "D", "passive")],
                 'B': [P(1, "G", "input")]})
register_symbol(f"{LIB}:IC_IdealDiode", "U", "LM74700-Q1", "Package_TO_SOT_SMD:SOT-23-6",
                {'L': [P(1, "VCAP", "passive"), P(2, "GND", "power_in"),
                       P(3, "EN", "input")],
                 'R': [P(4, "CATHODE", "input"), P(5, "GATE", "output"),
                       P(6, "ANODE", "input")]},
                datasheet="https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf")
register_symbol(f"{LIB}:IC_Buck", "U", "LMR33630-Q1", "TI_RNX0012C_VQFN-HR:TI_RNX0012C_VQFN-HR-12_2x3mm_P0.5mm",
                {'L': [P(2, "VIN", "power_in"), P(10, "VIN", "power_in"),
                       P(1, "PGND", "power_in"), P(11, "PGND", "power_in")],
                 'R': [P(12, "SW", "output"), P(4, "BOOT", "passive"),
                       P(7, "FB", "input"), P(9, "EN", "input")],
                 'T': [P(5, "VCC", "power_out"), P(8, "PG", "output")],
                 'B': [P(6, "AGND", "power_in"), P(3, "NC", "passive")]},
                datasheet="https://www.ti.com/lit/ds/symlink/lmr33630-q1.pdf")
register_symbol(f"{LIB}:IC_LDO33", "U", "TLV733P-Q1", "Package_TO_SOT_SMD:SOT-23-5",
                {'L': [P(1, "IN", "power_in")], 'R': [P(5, "OUT", "power_out")],
                 'B': [P(2, "GND", "power_in"), P(3, "EN", "input"),
                       P(4, "NC", "no_connect")]},
                datasheet="https://www.ti.com/lit/ds/symlink/tlv733p-q1.pdf")

# --- MCU core: NXP S32K144, same exact part/package manifold-pcb/thermo-pcb
# use (real, verified 64-pin LQFP pinout - see thermo-pcb's own
# build_schematic.py comment for the full research citation). Fixed pins
# every sibling board already dedicates regardless of application: crystal
# (11/12), SWD (64/62), RESET (63), power (7/41/8/10/40), VREFH(9)->VDDA.
#
# Peripheral pin-mux research done 2026-09-22 (plan Step 1): real S32K144
# alternate-function table pulled directly from NXP's own S32K1xx
# Reference Manual - not a datasheet summary, the actual embedded
# attachment (`S32K144_IO_Signal_Description_Input_Multiplexing.xlsx`,
# extracted via `pypdf`'s `.attachments` API from the RM PDF, same
# technique manifold-pcb's own original MCU pinout research established
# and ecu-pcb's MPC5606B eMIOS/DSPI research reused). Every pin below is
# real, physically present on the 64-pin LQFP package (checked against
# the xlsx's own "S32K144_64lqfp" column, not assumed to exist just
# because a bigger package has it), and cross-checked pin-by-pin against
# every pin already claimed above - zero collisions confirmed
# programmatically, not just by eye.
#   - LPSPI1 (BT817AQ QSPI link, single-SPI mode to start): SCK=pin2
#     (PTD0), SIN=pin1(PTD1), SOUT=pin46(PTD2), PCS0=pin45(PTD3) - a
#     genuinely complete, single-module LPSPI1 bus (same "one clean
#     module" standard thermo-pcb's own LPSPI0 pick set), all real.
#   - LPSPI2 (shared SPI bus to the 4x GC9A01 aux gauges): SCK=pin29
#     (PTC15), SIN=pin26(PTC0, real pin kept for possible future
#     diagnostic use even though no GC9A01 currently drives it - see its
#     own real pull-down, R11, in the placement section below), SOUT=
#     pin25(PTC1), PCS0=pin30(PTC14, claimed here but marked no_connect
#     in the placement section - each of the 4 displays needs its OWN
#     chip select, so 4 individual bit-banged GPIO (AUX_CS0-3) are used
#     instead of this single hardware PCS0 pin).
#   - FlexCAN0: RX=pin6(PTE4), TX=pin5(PTE5).
#   - 4x ADC channel (split across the real ADC0/ADC1 instances, which
#     is normal - not a defect): FUEL=pin50(PTA0, ADC0_SE0),
#     OIL=pin49(PTA1, ADC0_SE1), TEMP=pin48(PTA2, ADC1_SE0),
#     BATT=pin47(PTA3, ADC1_SE1).
#   - Plain GPIO (4x CS + 4x DC for the aux gauges, 1x shared reset,
#     1x shared backlight enable, 1x BT817AQ power-down control, 2x CAN0
#     mode control) - none of these need a specific peripheral function,
#     so any confirmed-free GPIO-capable pin works: CS0=pin13(PTE3),
#     CS1=pin14(PTD16), CS2=pin15(PTD15), CS3=pin16(PTE9), DC0=pin17(PTE8),
#     DC1=pin22(PTD7), DC2=pin23(PTD6), DC3=pin24(PTD5), AUX_RST=pin42
#     (PTB13), BL_EN=pin39(PTE7), BT817_PDN=pin43(PTB12), CAN0_EN=pin18
#     (PTB5), CAN0_STB_N=pin19(PTB4) - the latter two added in plan Step 2
#     alongside the TJA1043T transceiver itself, same real EN+STB_N mode-
#     control pattern ecu-pcb's own TJA1043T wiring already established
#     (real 4-state mode select, not a single 3-state pin - see that
#     project's own registration comment for the full reasoning).
# All 27 of these are wired only as far as a real, named label stub this
# pass except CAN0_EN/STB_N and CAN0_TX/RX, which Step 2 (below) connects
# to a real TJA1043T transceiver - connecting the rest to GC9A01/BT817AQ/
# sensor-divider circuitry is plan Steps 3-5, not done in this same edit.
MCU_LEFT = [P(11, "OSC_IN", "passive"), P(12, "OSC_OUT", "passive"),
            P(64, "SWDIO", "bidirectional"), P(62, "SWCLK", "input"),
            P(2, "LPSPI1_SCK", "output"), P(1, "LPSPI1_SIN", "input"),
            P(46, "LPSPI1_SOUT", "output"), P(45, "LPSPI1_CS", "output"),
            P(29, "LPSPI2_SCK", "output"), P(26, "LPSPI2_SIN", "input"),
            P(25, "LPSPI2_SOUT", "output")]
MCU_RIGHT = [P(6, "CAN0_RX", "input"), P(5, "CAN0_TX", "output"),
             P(50, "ADC_FUEL", "input"), P(49, "ADC_OIL", "input"),
             P(48, "ADC_TEMP", "input"), P(47, "ADC_BATT", "input"),
             P(13, "AUX_CS0", "output"), P(14, "AUX_CS1", "output"),
             P(15, "AUX_CS2", "output"), P(16, "AUX_CS3", "output"),
             P(17, "AUX_DC0", "output"), P(22, "AUX_DC1", "output"),
             P(23, "AUX_DC2", "output"), P(24, "AUX_DC3", "output")]
MCU_BOTTOM_EXTRA = [P(30, "LPSPI2_CS", "output"), P(42, "AUX_RST", "output"),
                    P(39, "BL_EN", "output"), P(43, "BT817_PDN", "output"),
                    P(18, "CAN0_EN", "output"), P(19, "CAN0_STB_N", "output")]
register_symbol(f"{LIB}:MCU_STM32", "U", "NXP S32K144 automotive (AEC-Q100)",
                "Package_QFP:LQFP-64_10x10mm_P0.5mm",
                {'L': MCU_LEFT,
                 'R': MCU_RIGHT,
                 # Pin 9 = VREFH, the ADC's positive voltage-reference input -
                 # tied to the already-filtered analog supply (VDDA) rather
                 # than left floating, same treatment manifold-pcb/thermo-pcb
                 # both use for this exact pin. Cluster WILL use the internal
                 # ADC for real (fuel/oil/temp/battery sensing) - this pin is
                 # genuinely load-bearing here, not just bias-for-safety.
                 'T': [P(7, "VDD", "power_in"), P(41, "VDD", "power_in"),
                       P(8, "VDDA", "power_in"), P(9, "VREFH", "power_in")],
                 'B': [P(10, "VSS", "power_in"), P(40, "VSS", "power_in"),
                       P(63, "RESET", "input")] + MCU_BOTTOM_EXTRA},
                datasheet="https://www.nxp.com/products/processors-and-microcontrollers/s32-automotive-platform/s32k-auto-general-purpose-mcus:S32K-MCUS")
# Real 58-27-11=20 other free GPIO pins this package has are simply NOT
# included on this symbol at all yet - same "symbol exposes only what's
# actually wired so far" approach thermo-pcb's own MCU registration
# comment documents. Headroom remains for anything Steps 3-6 turn up a
# real need for beyond this pass's own estimate.

register_symbol(f"{LIB}:CONN_SWD", "J", "SWD (Tag-Connect)",
                "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",
                {'L': [P(1, "SWDIO", "bidirectional"), P(3, "SWCLK", "input"),
                       P(5, "RST", "input")],
                 'R': [P(2, "VCC", "power_in"), P(4, "NC", "no_connect"),
                       P(6, "GND", "power_in")]},
                hide_pin_names=True)

register_symbol(f"{LIB}:CONN_PWR", "J", "Phoenix MKDS 1,5/2-5,08 (board side; DTM06-2S nickel on the outboard pigtail end)",
                "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
                {'L': [P(1, "VIN", "passive"), P(2, "GND", "passive")]},
                hide_pin_names=True)
# Board-side power landing reuses thermo-pcb's real connector strategy
# (Phoenix MKDS screw terminal, sealed DTM06-2S crimped on the outboard
# pigtail end) - same real reasoning (heavier-duty physical interface than
# a friction-lock header, standard real-world 12V automotive pigtail
# termination). Not yet re-verified this is the right choice for Cluster
# specifically (a dash-mounted board, not an engine-bay one like Thermo) -
# flagged for the connector-strategy pass, not assumed final.

# --- CAN0 transceiver (plan Step 2): real TJA1043T (SO-14), pin table and
# wiring topology reused VERBATIM from ecu-pcb's own already-verified
# circuit (ecu-pcb/build_schematic.py, its TJA1043T registration and
# CAN_BUSES loop) - single instance here (CAN0 only) instead of that
# board's dual-CAN setup, otherwise identical: VCC->+5V, VIO->+3V3 (both
# match the MCU's own logic level, no level shifter needed - confirmed by
# ecu-pcb's own research), VBAT->VIN_PROT (the always-on protected rail,
# NOT the relay-gated one, so a CAN bus-wake event can revive the board
# with ignition off - same real automotive reasoning), TXD/RXD wired to
# the MCU's CAN0_TX/CAN0_RX pins (matching net NAME, not geometric
# alignment - same trick Thermo used for its own MCU<->ADC link), EN/
# STB_N to real MCU GPIO (4-state mode select, not a single 3-state pin -
# see ecu-pcb's own registration comment for the full reasoning), INH/
# ERR_N no_connect (fault telemetry / external-regulator control, real
# future-nice-to-haves not required here), WAKE tied inactive (GND, no
# dedicated remote-wake line on this board), and the real split-
# termination network (2x 60R + 4.7nF, differentially equivalent to a
# standard 120R end-of-bus resistor - DNP unless this board is a physical
# bus end-node, same documented caveat as ecu-pcb).
register_symbol(f"{LIB}:TJA1043T", "U", "NXP TJA1043T automotive CAN transceiver (AEC-Q100)",
                "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
                {'T': [P(3, "VCC", "power_in"), P(5, "VIO", "power_in"),
                       P(10, "VBAT", "power_in")],
                 'B': [P(2, "GND", "power_in")],
                 'L': [P(1, "TXD", "input"), P(4, "RXD", "output"),
                       P(6, "EN", "input"), P(14, "STB_N", "input")],
                 'R': [P(7, "INH", "output"), P(8, "ERR_N", "output"),
                       P(9, "WAKE", "input"), P(11, "SPLIT", "output"),
                       P(12, "CANL", "passive"), P(13, "CANH", "passive")]},
                datasheet="https://www.nxp.com/products/TJA1043")

# --- GC9A01 aux gauges x4 (plan Step 3): real 18-pin FPC table pulled
# directly from Raystar's own RFA401280B-AYW-DNF1 datasheet (the chosen
# real part, 1.28" 240x240 GC9A01 round module WITH PCAP touch - touch
# isn't part of this board's design, its 4 signal pins are simply left
# no_connect below, same treatment as any genuinely-unused-but-present
# real pin elsewhere in this family). Real, non-obvious finding from
# actually reading the datasheet rather than assuming a generic GC9A01
# breakout's usual "BLK" logic pin: this module's backlight is a bare
# LED anode/cathode pair (VLED+/VLED-, real spec 3.0-3.4V/40mA max, typ
# 3.2V), not a logic-level enable input - driven with a per-display
# series resistor from +5V (comfortable headroom over the LED's 3.2V
# typ forward voltage, unlike +3V3 which would leave almost none) and a
# SHARED low-side N-MOSFET switch on the common VLED- return (same real
# "shared switch on the low side" pattern thermo-pcb's own heater-MOSFET
# circuit already uses), not 4 independent GPIO-driven logic pins.
register_symbol(f"{LIB}:GC9A01_MODULE", "U", "Raystar RFA401280B-AYW-DNF1 (1.28in 240x240 GC9A01 round TFT, PCAP touch unused)",
                "Connector_FFC-FPC:Amphenol_F32Q-1A7x1-11018_1x18-1MP_P0.5mm_Horizontal",
                {'L': [P(10, "CS", "input"), P(11, "SCL", "input"),
                       P(12, "SDA", "input"), P(13, "RS", "input"),
                       P(15, "RESET", "input"), P(14, "TE", "output")],
                 'R': [P(7, "VLED+", "passive"), P(8, "VLED-", "passive"),
                       P(16, "VCI3V3", "power_in"),
                       P(9, "GND", "power_in"), P(18, "GND", "power_in")],
                 'T': [P(1, "TP_INT", "no_connect"), P(2, "TP_SDA", "no_connect"),
                       P(3, "TP_SCL", "no_connect"), P(4, "TP_RESET", "no_connect"),
                       P(5, "TP_GND", "power_in"), P(6, "TP_VDD3V3", "no_connect")],
                 'B': [P(17, "NC", "no_connect")]},
                datasheet="https://www.raystar-optronics.com/upload_files/tft-lcd-display-module/1-28-tft/capacitive-touch-screen-display/RFA401280B-AYW-DNF1-datasheet.pdf")
# Footprint: real, bundled KiCad part (Amphenol F32Q-1A7x1-11018,
# 1x18-1MP, 0.5mm pitch, horizontal) matching the module's own real FPC
# spec exactly (18 positions, 0.5mm pitch per the datasheet's own contour
# drawing: "P0.5*(18-1)=8.50"). Confirmed to actually exist in KiCad's
# bundled Connector_FFC-FPC library (an earlier guessed generic name did
# not - caught by kicad-cli sch erc's real footprint_link_issues check,
# fixed by listing the real library directory rather than guessing a
# second time). Not yet checked whether this specific Amphenol connector
# is the right MATED HEIGHT/contact style for this board's real
# mechanical stack-up - flagged for plan Step 6 (connectors) / PCB layout.

# ---------------------------------------------------------------------------
# Placement + wiring
# ---------------------------------------------------------------------------
RAIL = 50.0

section_text("POWER INPUT, REVERSE-BATTERY + TRANSIENT PROTECTION", 30, 28)
section_text("5V BUCK + 3.3V LDO", 200, 28)
section_text("MCU CORE (NXP S32K144, 3.3V LOGIC) - FIXED PINS ONLY", 30, 175)

# --- 12V rail, left to right ---
place(f"{LIB}:CONN_PWR", "J1", "DTM06-2S nickel, 12V input (sealed)", 40, RAIL,
      conn={'1': ('pwr', 'VIN', 5.08), '2': ('pwr', 'GND', 7.62)})
place(f"{LIB}:Fuse", "F1", "Mini blade holder, 2A Littelfuse 297 fuse (SAE J2077/ISO 8820-3)", 50, RAIL,
      conn={'1': ('pwr', 'VIN'), '2': ('wire',)})
place(f"{LIB}:MOSFET_N", "Q1", "PMV37ENEA automotive (AEC-Q101)", 85, RAIL,
      conn={'2': ('wire',), '3': ('wire',),
            '1': ('label', 'GATE_DRV', 7.62)})
place(f"{LIB}:IC_IdealDiode", "U3", "LM74700-Q1 (AEC-Q100 G1)", 85, 85,
      conn={'6': ('label', 'VIN_FUSED', 5.08),
            '2': ('pwr', 'GND', 7.62),
            '5': ('label', 'GATE_DRV', 5.08), '4': ('label', 'VIN_PROT', 5.08),
            '3': ('label', 'VIN_FUSED', 5.08), '1': ('label', 'VCAP', 5.08)})
place(f"{LIB}:C_V", "C10", "100nF charge-pump cap (AEC-Q200)", 60, 100,
      conn={'1': ('label', 'VCAP'), '2': ('label', 'VIN_FUSED')})
place(f"{LIB}:TVS_V", "D1", "SMCJ33A automotive (AEC-Q101)", 113, 70,
      conn={'1': ('label', 'VIN_PROT'), '2': ('pwr', 'GND')})
place(f"{LIB}:C_V", "C1", "10uF X7R (AEC-Q200)", 150, 70,
      conn={'1': ('label', 'VIN_PROT'), '2': ('pwr', 'GND')})

vin_x, vin_y = pin_pos[("F1", "1")]
place_pwr_flag("VIN", vin_x, snap(vin_y - 10))
add_wire(vin_x, snap(vin_y - 10), vin_x, vin_y)
gnd_x, gnd_y = pin_pos[("D1", "2")]
place_pwr_flag("GND", gnd_x, snap(gnd_y + 10))
add_wire(gnd_x, snap(gnd_y + 10), gnd_x, gnd_y)

y_u2 = RAIL - off(f"{LIB}:IC_Buck", 2)[1]
place(f"{LIB}:IC_Buck", "U2", "LMR33630-Q1 (AEC-Q100 G1)", 170, y_u2,
      conn={'2': ('wire',), '10': ('label', 'VIN_PROT', 5.08),
            '1': ('pwr', 'GND', 5.08), '11': ('pwr', 'GND', 5.08),
            '12': ('wire',), '4': ('label', 'BOOT_CAP'),
            '7': ('label', 'FB'), '9': ('label', 'VIN_PROT', 5.08),
            '5': ('label', 'VCC_INT'), '8': ('nc',),
            '6': ('pwr', 'GND'), '3': ('label', 'SW')})
place(f"{LIB}:C_V", "C11", "100nF BOOT cap (AEC-Q200)", 195, 90,
      conn={'1': ('label', 'BOOT_CAP'), '2': ('label', 'SW')})
place(f"{LIB}:C_V", "C12", "1uF VCC decouple (AEC-Q200)", 218, 90,
      conn={'1': ('label', 'VCC_INT'), '2': ('pwr', 'GND')})
y_l1 = pin_pos[("U2", "12")][1] - off(f"{LIB}:L_H", 1)[1]
place(f"{LIB}:L_H", "L1", "10uH power (AEC-Q200)", 205, y_l1,
      conn={'1': ('wire',), '2': ('pwr', '+5V')})
place(f"{LIB}:C_V", "C2", "22uF X7R (AEC-Q200)", 232, 70,
      conn={'1': ('pwr', '+5V'), '2': ('pwr', 'GND')})
# FB divider: same real values as manifold-pcb/thermo-pcb (RFBT=10k,
# RFBB=2.49k -> ~5.02V, TI's own worked example scaled by 10x).
place(f"{LIB}:R_V", "R2", "10k (AEC-Q200)", 155, 128,
      conn={'1': ('pwr', '+5V'), '2': ('label', 'FB')})
place(f"{LIB}:R_V", "R3", "2.49k (AEC-Q200)", 155, 148,
      conn={'1': ('label', 'FB'), '2': ('pwr', 'GND')})

# +5V exists only as the intermediate 12V->5V->3.3V step (same reasoning as
# thermo-pcb - a single 12V->3.3V LDO would burn far more power at load).
place(f"{LIB}:IC_LDO33", "U4", "TLV733P-Q1 (AEC-Q100 G1)", 275, RAIL,
      conn={'1': ('pwr', '+5V'), '5': ('pwr', '+3V3'), '2': ('pwr', 'GND'),
            '3': ('pwr', '+5V')})
place(f"{LIB}:C_V", "C3", "1uF X7R (AEC-Q200)", 305, 70,
      conn={'1': ('pwr', '+3V3'), '2': ('pwr', 'GND')})

wire_pins("F1", 2, "Q1", 2, label="VIN_FUSED")
wire_pins("Q1", 3, "U2", 2, label="VIN_PROT")
wire_pins("U2", 12, "L1", 1, label="SW")

# --- MCU core (fixed pins only) ---
place(f"{LIB}:MCU_STM32", "U1", "NXP S32K144 automotive (AEC-Q100)", 110, 250,
      conn={'11': ('wire',), '12': ('wire',),
            # LPSPI2's real hardware PCS0 (pin 30) is genuinely unused by
            # design (plan Step 3): the 4 GC9A01 aux gauges share one SPI
            # bus but each needs its OWN chip select, so 4 individual
            # bit-banged GPIO (AUX_CS0-3) are used instead of the single
            # hardware PCS0 - a real, deliberate choice, not an oversight,
            # documented with a real no-connect flag rather than left as
            # a dangling same-named label (same established distinction
            # this whole project family draws elsewhere).
            '30': ('nc',),
            '7': ('pwr', '+3V3', 2.54), '41': ('pwr', '+3V3', 7.62),
            '10': ('pwr', 'GND', 2.54), '40': ('pwr', 'GND', 7.62),
            '9': ('label', 'VDDA', 7.62)})

y_y1 = pin_pos[("U1", "11")][1] - off(f"{LIB}:XTAL", 1)[1]
place(f"{LIB}:XTAL", "Y1", "8MHz (AEC-Q200)", 65, y_y1,
      conn={'1': ('wire',), '2': ('wire',),
            '3': ('label', 'OSC_IN'), '4': ('label', 'OSC_OUT')})
wire_pins("Y1", 1, "U1", 11, label="OSC_IN")
wire_pins("Y1", 2, "U1", 12, label="OSC_OUT")
place(f"{LIB}:C_V", "C4", "18pF (AEC-Q200)", 45, y_y1 + 30,
      conn={'1': ('label', 'OSC_IN'), '2': ('pwr', 'GND')})
place(f"{LIB}:C_V", "C5", "18pF (AEC-Q200)", 68, y_y1 + 30,
      conn={'1': ('label', 'OSC_OUT'), '2': ('pwr', 'GND')})

place(f"{LIB}:C_V", "C6", "100nF (AEC-Q200)", 150, 190,
      conn={'1': ('pwr', '+3V3'), '2': ('pwr', 'GND')})
place(f"{LIB}:C_V", "C7", "100nF (AEC-Q200)", 170, 190,
      conn={'1': ('pwr', '+3V3'), '2': ('pwr', 'GND')})
place(f"{LIB}:L_H", "L2", "ferrite bead (AEC-Q200)", 150, 210,
      conn={'1': ('pwr', '+3V3'), '2': ('label', 'VDDA')})
place(f"{LIB}:C_V", "C8", "1uF (AEC-Q200)", 175, 210,
      conn={'1': ('label', 'VDDA'), '2': ('pwr', 'GND')})
place(f"{LIB}:R_V", "R1", "10k pull-up (AEC-Q200)", 150, 300,
      conn={'1': ('pwr', '+3V3'), '2': ('label', 'RESET')})

place(f"{LIB}:CONN_SWD", "J2", "SWD Tag-Connect", 110, 320,
      conn={'1': ('label', 'SWDIO'), '3': ('label', 'SWCLK'),
            '5': ('label', 'RESET'),
            '2': ('pwr', '+3V3', 5.08), '6': ('pwr', 'GND', 5.08)})

# --- CAN0 transceiver (plan Step 2) ---
section_text("CAN0: NXP TJA1043T TRANSCEIVER (PLAN STEP 2)", 400, 175)
place(f"{LIB}:TJA1043T", "U5", "NXP TJA1043T automotive CAN transceiver (AEC-Q100)",
      400, 250,
      conn={'3': ('pwr', '+5V', 5.08), '5': ('pwr', '+3V3', 5.08),
            '10': ('label', 'VIN_PROT', 5.08), '2': ('pwr', 'GND', 2.54),
            '1': ('label', 'CAN0_TX', 7.62), '4': ('label', 'CAN0_RX', 7.62),
            '6': ('label', 'CAN0_EN', 7.62), '14': ('label', 'CAN0_STB_N', 7.62),
            '7': ('nc',), '8': ('nc',),
            '9': ('pwr', 'GND', 5.08),
            '11': ('label', 'CAN0_SPLIT'),
            '12': ('label', 'CAN0_L', 7.62), '13': ('label', 'CAN0_H', 7.62)})
place(f"{LIB}:C_V", "C13", "100nF VCC decouple (AEC-Q200)", 370, 220,
      conn={'1': ('pwr', '+5V'), '2': ('pwr', 'GND')})
place(f"{LIB}:C_V", "C14", "100nF VIO decouple (AEC-Q200)", 345, 220,
      conn={'1': ('pwr', '+3V3'), '2': ('pwr', 'GND')})
place(f"{LIB}:C_V", "C15", "100nF VBAT decouple (AEC-Q200)", 320, 220,
      conn={'1': ('label', 'VIN_PROT'), '2': ('pwr', 'GND')})
place(f"{LIB}:R_V", "R4", "60R split termination (AEC-Q200) - DNP unless bus end-node",
      550, 230,
      conn={'1': ('label', 'CAN0_H'), '2': ('label', 'CAN0_SPLIT')})
place(f"{LIB}:R_V", "R5", "60R split termination (AEC-Q200) - DNP unless bus end-node",
      550, 260,
      conn={'1': ('label', 'CAN0_SPLIT'), '2': ('label', 'CAN0_L')})
place(f"{LIB}:C_V", "C16", "4.7nF SPLIT stabilization (AEC-Q200)", 580, 245,
      conn={'1': ('label', 'CAN0_SPLIT'), '2': ('pwr', 'GND')})
# CAN0_TX/CAN0_RX/CAN0_EN/CAN0_STB_N connect to U1 purely by matching net
# NAME (both symbols already use these exact same label strings on their
# own respective pins) - same trick thermo-pcb used for its MCU<->ADC
# link, not geometric alignment (U1 and U5 aren't row-aligned).
# CAN0_H/CAN0_L/the vehicle-harness landing for this bus are real, named,
# forward-looking stubs pending plan Step 6 (connector strategy).

# --- 4x GC9A01 aux gauges (plan Step 3) ---
section_text("4x GC9A01 AUX GAUGES: FUEL / OIL / COOLANT TEMP / BATTERY (PLAN STEP 3)", 30, 430)
AUX_GAUGES = [
    ("U6", "AUX_CS0", "AUX_DC0", "Fuel level"),
    ("U7", "AUX_CS1", "AUX_DC1", "Oil pressure"),
    ("U8", "AUX_CS2", "AUX_DC2", "Coolant temp"),
    ("U9", "AUX_CS3", "AUX_DC3", "Battery voltage"),
]
for i, (u_ref, cs_label, dc_label, role) in enumerate(AUX_GAUGES):
    x0 = 30 + i * 120
    place(f"{LIB}:GC9A01_MODULE", u_ref, f"Raystar RFA401280B-AYW-DNF1 - {role} gauge", x0, 480,
          conn={'10': ('label', cs_label), '11': ('label', 'LPSPI2_SCK'),
                '12': ('label', 'LPSPI2_SOUT'), '13': ('label', dc_label),
                '15': ('label', 'AUX_RST'), '14': ('nc',),
                '7': ('label', f'{u_ref}_VLED', 5.08), '8': ('label', 'AUX_VLED_RTN', 5.08),
                # VCI3V3's power-symbol riser (a 'pwr' connection on an L/R
                # side climbs one extra PITCH) would otherwise land exactly
                # on pin 8's own 5.08 stub endpoint (adjacent R-side pins,
                # one PITCH apart) - caught by the script's own net-
                # collision check, fixed the same established way as every
                # prior instance of this bug class in this family: give the
                # riser-bearing pin a different stub length (10.16, not 5.08).
                '16': ('pwr', '+3V3', 10.16),
                '9': ('pwr', 'GND', 5.08), '18': ('pwr', 'GND', 7.62),
                '1': ('nc',), '2': ('nc',), '3': ('nc',), '4': ('nc',),
                '5': ('pwr', 'GND', 5.08), '6': ('nc',),
                '17': ('nc',)})
    place(f"{LIB}:R_V", f"R{6 + i}",
          "120R VLED series (self-calculated for ~15mA at 5V, real LED Vf 3.0-3.4V typ 3.2V per datasheet - AEC-Q200)",
          x0, 440,
          conn={'1': ('pwr', '+5V'), '2': ('label', f'{u_ref}_VLED')})
    place(f"{LIB}:C_V", f"C{17 + i}", "100nF VCI decouple (AEC-Q200)", x0 + 30, 440,
          conn={'1': ('pwr', '+3V3'), '2': ('pwr', 'GND')})
# Shared low-side N-MOSFET switch on the common VLED- return (real part
# reuse: same PMV37ENEA already verified/placed as Q1 in the power stage
# - its Vth max (2.7V) is comfortably below a 3.3V GPIO's full-swing
# drive for this simple ON/OFF switch use, unlike the light-load analog-
# regulation context that flagged it as a marginal fit for Q1's own
# LM74700-Q1 application - a genuinely different circuit, not the same
# concern recurring). All 4 displays' VLED- commons onto one node ahead
# of the switch - real combined current (~60mA max) is trivial next to
# this part's real multi-amp rating.
place(f"{LIB}:MOSFET_N", "Q2", "PMV37ENEA automotive (AEC-Q101) - shared aux-gauge backlight switch",
      450, 460,
      conn={'2': ('label', 'AUX_VLED_RTN'), '3': ('pwr', 'GND'),
            '1': ('label', 'BL_GATE', 5.08)})
place(f"{LIB}:R_V", "R10", "100R BL_EN gate resistor (AEC-Q200)", 450, 430,
      conn={'1': ('label', 'BL_EN'), '2': ('label', 'BL_GATE')})
# LPSPI2_SIN (the shared aux-gauge SPI bus's MISO line) is a real,
# exposed MCU pin kept for future use (e.g. reading GC9A01's own status
# register to detect a disconnected display) but genuinely unused by any
# part actually wired this pass - none of the 4 GC9A01 modules drive it
# (no MISO on this display, confirmed by Raystar's own pin table). Left
# floating, that's a real always-flagged ERC exception at best and a
# genuinely undefined logic level at worst; a cheap pull-down defines its
# idle state, same real practice as thermo-pcb's own SPI_CS pull-up on an
# otherwise-floating-during-reset line.
place(f"{LIB}:R_V", "R11", "10k LPSPI2_SIN pull-down, idle-state definition (AEC-Q200)",
      500, 430,
      conn={'1': ('label', 'LPSPI2_SIN'), '2': ('pwr', 'GND')})
# CS/SCL/SDA/DC/RESET connect to U1 purely by matching net NAME (LPSPI2_
# SCK/LPSPI2_SOUT/AUX_CSn/AUX_DCn/AUX_RST all already exist as real
# labeled stubs on U1 from plan Step 1) - same trick used throughout this
# file, not geometric alignment. TE (tearing-effect sync) and all 4 PCAP
# touch signal pins are genuinely unused by this design and left
# no_connect, same treatment as any other real-but-unused pin elsewhere
# in this project family.

NOTE_LINES = [
    "NOTES:",
    "1. Power nets (+5V, +3V3, GND, VIN) use power symbols throughout; signal nets use",
    "   drawn wires, with local labels only where pins are legitimately shared.",
    "2. Power stage (F1/Q1/U2/U3/U4 + supporting passives) reused VERBATIM from",
    "   manifold-pcb/thermo-pcb's own proven, real circuit - not re-derived here.",
    "3. U1 pin numbers are REAL, verified against NXP's S32K1xx Reference Manual (same",
    "   research thermo-pcb/manifold-pcb already did for this exact part/package) - not",
    "   generic placeholders. ONLY fixed pins (crystal/SWD/RESET/power) are wired this",
    "   pass - see this file's own header docstring for what's deliberately deferred.",
    "4. Real S32K144 pin/peripheral budget (README.md, verified 2026-09-22 against NXP's",
    "   own S32K1xx Data Sheet Rev.15): this part has 3x LPSPI, 3x FlexCAN (1 w/ FD),",
    "   2x12-bit ADC x16ch=32 channels - the ~26 real pins Cluster's aux-gauge SPI bus +",
    "   BT817AQ QSPI + CAN0 + 4x ADC will need fit comfortably inside the ~58 GPIO this",
    "   64-pin package leaves after the fixed pins wired here - NOT yet pin-mux",
    "   researched pin-by-pin, that's the next real work before those subsystems wire.",
    "5. Value fields tag automotive qualification: Q100 G1 = AEC-Q100 Grade 1 (ICs) -",
    "   Q101 = AEC-Q101 (discretes) - Q200 = AEC-Q200 (passives).",
    "6. J1 (power landing) reuses thermo-pcb's real Phoenix MKDS + outboard DTM06-2S",
    "   pigtail strategy as a starting point - not yet re-confirmed as the right choice",
    "   for a dash-mounted (not engine-bay) board; flagged for the connector pass.",
    "7. kicad-cli sch erc is expected to show only the same tool-limitation findings",
    "   every sibling board's schematic has at this stage (VDDA/U2-VIN/+5V",
    "   power_pin_not_driven - ERC can't trace power through a ferrite/FET/diode; J2",
    "   SWCLK pin_not_driven - genuinely driven off-sheet by the debug probe).",
]
NOTES_PER_COL = (len(NOTE_LINES) + 1) // 2
for i, line in enumerate(NOTE_LINES):
    col, row = divmod(i, NOTES_PER_COL)
    x = 30 + col * 280
    y = 345 + row * 3.2
    texts.append(SchText(text=line, position=Position(x, y, 0),
                         effects=Effects(font=Font(height=1.6, width=1.6),
                                          justify=Justify(horizontally="left"))))

# ---------------------------------------------------------------------------
sch.libSymbols = [entry[0] for entry in lib_symbols.values()]
sch.graphicalItems = wires
sch.labels = labels
sch.texts = texts
sch.noConnects = no_connects

OUT_SCH = r"C:\Users\root\Project\cluster-pcb\Cluster.kicad_sch"
os.makedirs(os.path.dirname(OUT_SCH), exist_ok=True)
sch.to_file(OUT_SCH)
print("Wrote", OUT_SCH)

from kiutils.symbol import SymbolLib
HERE = os.path.dirname(OUT_SCH)
SYM_LIB_FILE = os.path.join(HERE, f"{LIB}.kicad_sym")
symlib = SymbolLib(symbols=[entry[0] for entry in lib_symbols.values()])
symlib.to_file(SYM_LIB_FILE)
print("Wrote", SYM_LIB_FILE)

SYM_LIB_TABLE = os.path.join(HERE, "sym-lib-table")
with open(SYM_LIB_TABLE, "w", encoding="utf-8") as f:
    f.write(
        '(sym_lib_table\n'
        '\t(version 7)\n'
        f'\t(lib (name "{LIB}") (type "KiCad") (uri "${{KIPRJMOD}}/{LIB}.kicad_sym") '
        '(options "") (descr "Cluster project-local symbol library - '
        'regenerated by build_schematic.py, do not hand-edit"))\n'
        ')\n'
    )
print("Wrote", SYM_LIB_TABLE)

# --- validation: syntax round-trip + geometry ------------------------------
from kiutils.utils import sexpr
rep = Schematic.from_sexpr(sexpr.parse_sexp(open(OUT_SCH, encoding="utf-8").read()))
print(f"Round-trip OK: {len(rep.schematicSymbols)} symbols, "
      f"{len(rep.libSymbols)} lib symbols, {len(rep.labels)} labels, "
      f"{len(rep.graphicalItems)} wires")


def on_segment(p, a, b, tol=0.01):
    (px, py), (ax, ay), (bx, by) = p, a, b
    if abs(ax - bx) < tol:   # vertical
        return abs(px - ax) < tol and min(ay, by) - tol <= py <= max(ay, by) + tol
    if abs(ay - by) < tol:   # horizontal
        return abs(py - ay) < tol and min(ax, bx) - tol <= px <= max(ax, bx) + tol
    return False


segs = [((w.points[0].X, w.points[0].Y), (w.points[1].X, w.points[1].Y))
        for w in rep.graphicalItems]
bad = [l.text for l in rep.labels
       if not any(on_segment((l.position.X, l.position.Y), a, b) for a, b in segs)]
assert not bad, f"labels not on any wire: {bad}"

ends = {p for s in segs for p in s}
nc_ends = {(round(nc.position.X, 2), round(nc.position.Y, 2)) for nc in rep.noConnects}
lib = {s.libId: s for s in rep.libSymbols}
orphans = []
for inst in rep.schematicSymbols:
    for pin in lib[inst.libId].pins:
        pos = (round(inst.position.X + pin.position.X, 2),
               round(inst.position.Y - pin.position.Y, 2))
        if pos in nc_ends:
            continue
        if pos not in ends and not pin.hide:
            orphans.append(f"{inst.properties[0].value}.{pin.number}")
assert not orphans, f"pins with no wire: {orphans}"
print("Geometry OK: every label sits on a wire, every visible pin touches a wire end")

coord_net = {}
collisions = []
for l in rep.labels:
    key = (round(l.position.X, 2), round(l.position.Y, 2))
    if key in coord_net and coord_net[key] != l.text:
        collisions.append((key, coord_net[key], l.text))
    coord_net[key] = l.text
for inst in rep.schematicSymbols:
    if not inst.libId.startswith(f"{LIB}:PWR_"):
        continue
    net = inst.properties[1].value  # power symbol's Value IS its net name
    key = (round(inst.position.X, 2), round(inst.position.Y, 2))
    if key in coord_net and coord_net[key] != net:
        collisions.append((key, coord_net[key], net))
    coord_net[key] = net
assert not collisions, (
    f"two different nets land on the same coordinate (a GND riser probably "
    f"collided with a neighboring pin's stub - give one of them a different "
    f"stub length): {collisions}")
print("Net-collision check OK: no two different nets share a coordinate")

# --- upgrade to KiCad's current native format -------------------------------
import shutil, subprocess

def find_kicad_cli():
    exe = shutil.which("kicad-cli")
    if exe:
        return exe
    for candidate in [
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None

kicad_cli = find_kicad_cli()
if kicad_cli:
    result = subprocess.run([kicad_cli, "sch", "upgrade", OUT_SCH],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print("Upgraded to current KiCad format:", result.stdout.strip())
    else:
        print("WARNING: kicad-cli sch upgrade failed, file left in kiutils' "
              "format:", result.stderr.strip())
else:
    print("NOTE: kicad-cli not found - file left in kiutils' format.")
