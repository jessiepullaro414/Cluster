"""
Functional banking of the Verdin iMX95 X1 connector for schematic capture.

Ported from fascia-pcb's own verdin_x1.py (same real Verdin iMX95 SoM,
same 260-pin X1 connector - the hardware doesn't change between boards).
The banking RULES below are cluster-pcb/display's own, not fascia's:
this board has no touch controller, but since 2026-10-16 it DOES carry an
audio codec (I2S_1 + I2C_1) and a USB 2.0 host port (USB_2), so those
signal families are banked into D with CAN. The USB_2 SuperSpeed pairs and
the module-specific USB1_TX1/RX1 pairs are still genuinely unused and stay
in bank E (NoConnect).

A 260-pin connector cannot be drawn as one symbol - at 2.54 mm pitch a
single block would be ~330 mm tall, taller than any sheet this project
uses. KiCad's answer is a multi-unit symbol, so this module decides which
pin belongs to which unit.

Banks are derived from the pin NAMES in verdin_pinout.py rather than
hand-listed pin numbers, so that re-running tools/extract_verdin_pinout.py
against a newer datasheet revision cannot silently desynchronise the two
files. The tradeoff is that the rules below must stay exhaustive - which
is exactly what verify() enforces.

Unit letters follow how the board actually uses the connector, not the
datasheet's own ordering:

    A  power and ground
    B  control, sequencing and debug
    C  display - the DSI link to the SN65DSI85-Q1, plus backlight control
    D  communications this board uses - CAN to ecu-pcb/gauges, I2S_1 and
       I2C_1 to the audio codec, the USB_2 host port
    E  everything this board does not use, which gets NoConnect items

Bank E is not filler. Per this project's KiCad notes, a deliberately
unused pin needs a real NoConnect item rather than a stub label, or ERC
reports it as a dangling/isolated label - so the unused pins have to be
enumerated just as carefully as the used ones.
"""
import re

from verdin_pinout import X1_PINS

# Ordered most-specific first; the first match wins, so e.g. I2C_2_DSI
# lands in the display bank rather than the generic comms bank.
_RULES = [
    ("A", r"^(GND|VCC|VCC_BACKUP|PWR_1V8_MOCI|PMIC_PGOOD)$"),
    ("B", r"^(CTRL_|JTAG_|TAMPER)"),
    ("C", r"^(DSI_1_|I2C_2_DSI|PWM_3_DSI|GPIO_9_DSI|GPIO_10_DSI)"),
    # Communications this board uses: CAN to ecu-pcb/gauges, the audio codec's
    # I2S_1 + I2C_1 (2026-10-16: wireless Android Auto / CarPlay need sound),
    # and the USB_2 host port (USB 2.0 pair, VBUS enable, over-current).
    # USB_2 is the Verdin host-only port; USB_1 stays on the bench header J13.
    # USB_2's SuperSpeed lanes and the MSP USB1_TX1/RX1 pairs stay unused (bank
    # E): the port is USB 2.0 only, which is all a phone or a projection dongle
    # needs.
    ("D", r"^(CAN_1_|I2S_1_|I2C_1_|USB_2_D_|USB_2_EN$|USB_2_OC#$)"),
    # Everything else is unused by this board.
    ("E", r".*"),
]

UNIT_NAMES = {
    "A": "Power and ground",
    "B": "Control, sequencing and debug",
    "C": "Display - DSI to bridge, backlight control",
    "D": "Communications - CAN, audio I2S/I2C, USB_2 host",
    "E": "Unused on this board (no-connect)",
}


def bank_of(name):
    """Which unit letter a given Verdin signal name belongs to."""
    for letter, pattern in _RULES:
        if re.match(pattern, name):
            return letter
    raise AssertionError(f"no bank rule matched {name!r}")  # unreachable: E is .*


def banks():
    """{unit letter: [(pin, name), ...]} sorted by pin number."""
    out = {letter: [] for letter, _ in _RULES}
    for pin in sorted(X1_PINS):
        out[bank_of(X1_PINS[pin])].append((pin, X1_PINS[pin]))
    return out


# A unit's pins are split down its left and right sides, so its drawn
# height is about (pins / 2) * 2.54 mm. 80 pins is ~100 mm per side, which
# leaves room to place several units on one sheet. Bank E is the only one
# that exceeds this today.
MAX_PINS_PER_UNIT = 80


def units():
    """
    The actual multi-unit symbol units, in schematic order.

    Returns [(unit_label, description, [(pin, name), ...]), ...] with unit
    number = index + 1. Banks larger than MAX_PINS_PER_UNIT are split
    across several units so no single one is too tall to draw; the split
    is done here rather than in the banking rules so the *semantic*
    grouping stays readable.
    """
    out = []
    b = banks()
    for letter in ("A", "B", "C", "D", "E"):
        entries = b[letter]
        if not entries:
            continue
        if len(entries) <= MAX_PINS_PER_UNIT:
            out.append((letter, UNIT_NAMES[letter], entries))
            continue
        # Split evenly rather than filling to the cap, so the pieces are
        # balanced instead of one full unit and one nearly empty.
        nparts = -(-len(entries) // MAX_PINS_PER_UNIT)
        size = -(-len(entries) // nparts)
        for i in range(nparts):
            chunk = entries[i * size:(i + 1) * size]
            if chunk:
                out.append((f"{letter}{i + 1}",
                            f"{UNIT_NAMES[letter]} ({i + 1}/{nparts})",
                            chunk))
    return out


def verify():
    """
    Prove the banking is a true partition of the connector.

    Every pin exactly once, nothing invented, nothing dropped. This is the
    check that makes it safe to derive banks from name patterns instead of
    an explicit 260-entry list.
    """
    problems = []
    b = banks()

    assigned = [pin for entries in b.values() for pin, _ in entries]
    if len(assigned) != len(set(assigned)):
        dupes = {p for p in assigned if assigned.count(p) > 1}
        problems.append(f"pins assigned to more than one bank: {sorted(dupes)}")

    missing = set(range(1, 261)) - set(assigned)
    if missing:
        problems.append(f"pins in no bank: {sorted(missing)}")

    extra = set(assigned) - set(range(1, 261))
    if extra:
        problems.append(f"pins outside 1..260: {sorted(extra)}")

    # The display bank is what this whole board is built around, so assert
    # its exact contents rather than trusting the pattern to have caught
    # them. These numbers are from Verdin iMX95 datasheet Table 22.
    expected_c = {23, 25, 29, 31, 35, 37, 41, 43, 47, 49,   # DSI lanes + clock
                  53, 55,                                    # I2C_2_DSI
                  17, 19, 21}                                # bridge EN, PWM, BKL EN
    got_c = {pin for pin, _ in b["C"]}
    if got_c != expected_c:
        problems.append(f"display bank wrong: missing {sorted(expected_c - got_c)}, "
                        f"unexpected {sorted(got_c - expected_c)}")

    # Bank D is exactly CAN_1, I2C_1, I2S_1 and the USB_2 USB 2.0 pins; the
    # USB_2 SuperSpeed lanes and USB1_TX1/RX1 must stay in the unused bank.
    names_d = {name for _, name in b["D"]}
    names_e = {name for _, name in b["E"]}
    expected_d = {20, 22,                      # CAN_1 TX/RX
                  12, 14,                      # I2C_1 SDA/SCL
                  30, 32, 34, 36, 38,          # I2S_1 BCLK/SYNC/D_OUT/D_IN/MCLK
                  181, 183, 185, 187}          # USB_2 D-/D+/EN/OC#
    got_d = {pin for pin, _ in b["D"]}
    if got_d != expected_d:
        problems.append(f"comms bank wrong: missing {sorted(expected_d - got_d)}, "
                        f"unexpected {sorted(got_d - expected_d)}")
    for should_be_unused in ("USB_2_SSTX_P", "USB_2_SSTX_N", "USB_2_SSRX_P",
                             "USB_2_SSRX_N", "USB1_TX1_P", "USB1_RX1_P",
                             "I2S_2_BCLK", "USB_1_D_P", "USB_1_D_N"):
        if should_be_unused not in names_e:
            problems.append(f"{should_be_unused} should be in the unused "
                            f"bank on this board, is not")
    for needed in ("CAN_1_TX", "CAN_1_RX", "I2S_1_BCLK", "I2S_1_SYNC",
                   "I2S_1_D_OUT", "I2S_1_D_IN", "I2S_1_MCLK", "I2C_1_SDA",
                   "I2C_1_SCL", "USB_2_D_P", "USB_2_D_N", "USB_2_EN", "USB_2_OC#"):
        if needed not in names_d:
            problems.append(f"{needed} should be in the comms bank, is not")

    # Splitting banks into units must not lose or duplicate a pin either.
    u_pins = [pin for _, _, entries in units() for pin, _ in entries]
    if sorted(u_pins) != list(range(1, 261)):
        problems.append(f"units() does not cover 1..260 exactly once "
                        f"({len(u_pins)} pins, {len(set(u_pins))} distinct)")
    for label, _, entries in units():
        if len(entries) > MAX_PINS_PER_UNIT:
            problems.append(f"unit {label} has {len(entries)} pins, over the "
                            f"{MAX_PINS_PER_UNIT} cap")

    return problems


if __name__ == "__main__":
    import sys

    # Signal names are ASCII, but the family summary below uses a
    # multiplication sign; cp1252 stdout would mangle it.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    problems = verify()
    b = banks()
    for letter in ("A", "B", "C", "D", "E"):
        entries = b[letter]
        print(f"\n=== Unit {letter}: {UNIT_NAMES[letter]} ({len(entries)} pins) ===")
        if letter == "E":
            # Too many to list usefully; summarise by signal family.
            fams = {}
            for _, name in entries:
                fam = re.match(r"^[A-Z0-9]+(?:_[0-9]+)?", name).group(0)
                fams[fam] = fams.get(fam, 0) + 1
            print("   " + ", ".join(f"{k}×{v}" for k, v in sorted(fams.items())))
        else:
            for pin, name in entries:
                print(f"   {pin:3d}  {name}")

    print("\n=== symbol units ===")
    for i, (label, desc, entries) in enumerate(units(), start=1):
        print(f"   unit {i} ({label}): {len(entries):3d} pins  "
              f"~{len(entries) / 2 * 2.54:5.1f} mm/side   {desc}")

    print()
    if problems:
        print("BANKING INVALID:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"banking OK: {sum(len(v) for v in b.values())} pins partitioned across "
          f"{len(b)} banks -> {len(units())} symbol units")
