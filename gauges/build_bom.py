#!/usr/bin/env python3
"""
build_bom.py - generates the gauges/ board's bill of materials straight
from the real schematic, plus a standalone HTML page.

*** ADAPTED FROM ecu-pcb/build_bom.py (2026-09-27) *** same real
generated-not-hand-maintained discipline, same coverage/value-spelling
self-checks, same HTML template - only the per-board MPN table and
header copy are new.

WHY GENERATED, NOT HAND-MAINTAINED: every other artefact in this family
is regenerated from source rather than hand-edited (see
build_schematic.py / build_pcb.py). Reference designators, values,
packages and quantities here all come from ClusterGauges.kicad_sch
itself, so the BOM cannot disagree with the board.

WHAT IS AND IS NOT VERIFIED - stated plainly, same discipline as
ecu-pcb's own BOM:
  * ACTIVE parts and connectors carry REAL manufacturer part numbers
    where build_schematic.py's own comments state one - that provenance
    is in that file, not invented here.
  * A few parts are genuinely NOT pinned to an exact orderable part
    number in the schematic - the MCU (S32K144's exact memory/package
    suffix), the front-end TVS and MOSFETs' exact manufacturer, and the
    fuse's exact Littelfuse 297-series suffix. These get their own
    "needs real part selection" section below rather than a fabricated
    precise-looking part number - see build_schematic.py's own header
    for what IS cited (S32K144 pin-mux research, PMV37ENEA/SMCJ33A
    parametric choices) versus what's a real remaining purchasing task.
  * PASSIVES are specified parametrically - value, package, and the
    AEC-Q200 requirement - same real reasoning as ecu-pcb's own BOM:
    a 0402/0603 resistor is a commodity chosen on value/package/
    tolerance/qualification, not a unique design-critical device.
  * LIVE PRICING AND STOCK ARE NOT INCLUDED.

Run:  python build_bom.py          -> console summary + ClusterGauges_BOM.html
"""
import io
import os
import re
from collections import defaultdict

from kiutils.schematic import Schematic
from kiutils.utils import sexpr

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import passive_catalog  # noqa: E402  real orderable passives, see that file

HERE = os.path.dirname(os.path.abspath(__file__))
SCH = os.path.join(HERE, "ClusterGauges.kicad_sch")
OUT_HTML = os.path.join(HERE, "ClusterGauges_BOM.html")
PCB = os.path.join(HERE, "ClusterGauges.kicad_pcb")

# Real manufacturer part numbers for every non-passive that has one
# stated in build_schematic.py's own comments. Keyed by the distinctive
# token that appears in the schematic's own Value string, so this table
# cannot drift away from the schematic without the lookup simply
# failing loudly rather than reporting a stale part.
#   token -> (MPN, manufacturer, description, qualification)
MPN = {
    "S32K144":    ("FS32K144HAT0MLHT", "NXP",
                   "S32K144 Arm Cortex-M4F, 80 MHz (112 MHz HSRUN), 512 KB flash, CAN FD, "
                   "LQFP-64 (suffix MLH = 64-LQFP; MLL would be the 100-pin part), -40..125 C, "
                   "tape and reel; pin-mux verified against NXP's S32K1xx Reference Manual. Orderable "
                   "part number as listed by Newark, Mouser and TrustedParts (checked 2026-10-04); "
                   "confirm the suffix on the NXP part page when ordering",
                   "AEC-Q100 Grade 1"),
    "LMR33630-Q1": ("LMR33630BRNXRQ1", "TI", "3A synchronous buck regulator, +5V rail", "AEC-Q100 G1"),
    "LM74930-Q1":  ("LM74930QRGERQ1", "TI", "Automotive ideal-diode surge stopper with OV clamp and circuit breaker, VQFN-24 RGE; TI lists it Active/Production (same part as display/)", "AEC-Q100 Grade 1"),
    "PMV55ENEA":   ("PMV55ENEAR", "Nexperia", "60V N-ch MOSFET, VGS +-20V, SOT-23: LM74930 pass and ideal-diode FET pair (orderable suffix R = reel)", "AEC-Q101"),
    "TLV733P-Q1":  ("TLV73333PQDBVRQ1","TI", "300mA LDO, +3.3V rail", "AEC-Q100 G1"),
    "TJA1043T":    ("TJA1043T/1J", "NXP", "High-speed CAN transceiver with wake, real wiring reused verbatim from ecu-pcb", "AEC-Q100"),
    # U6-U9 are the board-side FPC CONNECTORS the GC9A01 modules plug into
    # (the module itself is a companion part, appended below). Part number
    # follows Amphenol's F32Q-1A7H1-110NN scheme (NN = contacts): the 11008,
    # 11012, 11020, 11022 and 11050 variants were verified on DigiKey, 11018
    # is the 18-contact member (PATTERN: confirm in the cart). 0.5 mm pitch,
    # right-angle ZIF, BOTTOM contact - order the module's FPC accordingly.
    "RFA401280B-AYW-DNF1": ("F32Q-1A7H1-11018", "Amphenol FCI",
                             "18-position 0.5mm FPC connector, right-angle ZIF, bottom contact, one per GC9A01 "
                             "module [PATTERN: confirm this exact part number in the distributor cart]", "-"),

    "PMV37ENEA":  ("PMV37ENEA", "Nexperia", "N-MOSFET, 12V-rail reverse-protection gate switch / shared backlight low-side switch", "AEC-Q101"),
    "SMCJ33A":    ("SMCJ33A (multi-source)", "Littelfuse / onsemi / Vishay (industry-standard P/N)",
                    "SMC-package TVS diode, 33V standoff, 12V-rail transient protection - not pinned to one vendor, real industry-standard part number", "AEC-Q101"),

    # F1's REAL placed schematic footprint is the HOLDER, not the fuse
    # element (a blade fuse plugs into it, never its own KiCad
    # footprint) - matches on the holder, same real Keystone 3568 part
    # every sibling board's own fuse holder already uses. The element
    # itself is a separate, non-placed orderable line, appended below
    # (same real split ecu-pcb's own BOM makes).
    "Littelfuse 297": ("3568", "Keystone", "Mini blade fuse holder, PCB mount (fuse element ordered separately)", "-"),

    "XAL5050-103ME": ("XAL5050-103MEC", "Coilcraft", "10uH shielded molded power inductor, Isat 4.9A, DCR 41mR typ, 5x5x5mm, AEC-Q200 - meets the LMR33630-Q1 datasheet's rule that Isat not be below the 4.1A low-side limit (datasheet Document 806-1 family; trailing C = 7in reel ordering code)", "AEC-Q200"),
    "Tag-Connect": ("TC2030-IDC-NL", "Tag-Connect", "SWD programming/debug connector, 2x3 1.27mm, no-legs cable version", "-"),

    # Rev B (2026-09-30), gateway architecture: private CAN1 link to
    # display/ and Hall speed input conditioning.
    "TCAN1044V-Q1": ("TCAN1044VDRQ1", "TI", "Automotive CAN FD transceiver w/ VIO pin, SOIC-8 - private CAN1 link to display/ (same part as display/'s transceiver; datasheet SLLSF17D)", "AEC-Q100 Grade 1"),
    "BAV99-Q":      ("BAV99-Q (confirm reel suffix at order time)", "Nexperia", "Dual series high-speed switching diode, SOT-23, used as a rail-to-rail input clamp on the speed and ignition inputs (pin 3 signal, pin 1 GND, pin 2 +3V3; datasheet Rev. 8)", "AEC-Q101"),
}

# Real harness pigtail connectors (the cable-side mate for J1/J7's own
# real board-side footprints below) - real, separately-orderable items,
# but NOT their own board placement (nothing on the schematic/PCB IS a
# DTM06-2S/5S footprint - the board side is the Phoenix/Molex part
# below), so these are appended as extra lines the same way the fuse
# element is, not matched through the placement-coverage token loop.
HARNESS_PIGTAILS = [
    ("DTM06-3S", "TE Connectivity (Deutsch DTM series)", "3-position sealed harness pigtail connector, 12V input + GND + ignition - mates with J1's own board-side terminal block (rev B: was 2-position before the ignition wire was added)", "J1"),
    ("DTM06-5S", "TE Connectivity (Deutsch DTM series)", "5-position sealed harness pigtail connector: CAN0_H/L + 3x sender input - mates with J7's own board-side header", "J7"),
]

# Real board-side connector part numbers that pair with the pigtails
# above - these are placed as their OWN footprint on this board, not
# just described by the schematic Value string, so they get their own
# BOM lines keyed by REFERENCE rather than by Value-token match.
BOARD_SIDE_CONNECTORS = {
    "J1": ("MKDS 1,5/ 3-5,08 (1715734)", "Phoenix Contact", "3-position 5.08mm screw terminal block, board side of the 12V input + ignition pigtail (rev B: was 2-position)", "-"),
    "J7": ("22-27-2051", "Molex", "5-position KK 254 (2.54mm) header, board side of the CAN0+sender pigtail", "-"),
    "J8": ("22-27-2031", "Molex", "3-circuit KK 254 (2.54mm) vertical header, private CAN1 link to display/ (CAN1_H / CAN1_L / GND); mating housing and crimps are separate Molex KK 254 parts", "-"),
    "J9": ("22-27-2021", "Molex", "2-circuit KK 254 (2.54mm) vertical header, Hall speed sender input (signal + ground); the sender is powered from the car harness, not from this board", "-"),
}

PASSIVE_PREFIXES = ("R", "C", "L", "FB", "Y")


def board_size_mm():
    """Real board outline size, measured from the PCB's own Edge.Cuts
    geometry - same real "derive, don't hardcode" reasoning as ecu-pcb's
    own build_bom.py, re-verified against this project's own newer
    KiCad 10 .kicad_pcb text layout (start/end/layer split across
    separate lines rather than one run - the regex already tolerates
    this via re.S, confirmed against the real file before relying on
    it here rather than assumed)."""
    try:
        pcb = io.open(PCB, encoding="utf-8").read()
    except OSError:
        return None
    xs, ys = [], []
    for m in re.finditer(
            r"\(gr_line\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)"
            r"(?:(?!\(gr_line).)*?Edge\.Cuts", pcb, re.S):
        xs += [float(m.group(1)), float(m.group(3))]
        ys += [float(m.group(2)), float(m.group(4))]
    if not xs:
        return None
    return f"{max(xs) - min(xs):.1f} &times; {max(ys) - min(ys):.1f}"


def load_parts():
    """One entry per real physical part, keyed by Reference - NOT one
    per kiutils schematicSymbol instance. A real multi-unit part (none
    on this board today, but display/build_bom.py's own real J1 -
    Verdin X1, 7 real schematic units sharing one Reference - hit this
    exact bug: a naive one-entry-per-instance count inflated the real
    part total by 6) would otherwise silently double-count. Cheap
    insurance, applied here too even though gauges/ has no multi-unit
    symbols currently."""
    sch = Schematic.from_sexpr(sexpr.parse_sexp(open(SCH, encoding="utf-8").read()))
    parts = {}
    for inst in sch.schematicSymbols:
        ref = next(p.value for p in inst.properties if p.key == "Reference")
        if ref.startswith("#"):
            continue          # power-flag symbols are not physical parts
        if ref in parts:
            continue          # already recorded from an earlier unit
        val = next((p.value for p in inst.properties if p.key == "Value"), "")
        fp = next((p.value for p in inst.properties if p.key == "Footprint"), "")
        parts[ref] = {"ref": ref, "value": val, "package": fp.split(":")[-1]}
    return list(parts.values())


def ref_sort_key(ref):
    m = re.match(r"^([A-Z]+)(\d+)$", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def collapse_refs(refs):
    """R1, R2, R3, R7 -> 'R1-R3, R7' - how a real BOM lists designators."""
    refs = sorted(refs, key=ref_sort_key)
    out, run = [], []

    def flush():
        if not run:
            return
        if len(run) >= 3:
            out.append(f"{run[0]}-{run[-1]}")
        else:
            out.extend(run)
    for r in refs:
        if run:
            pa, na = ref_sort_key(run[-1])
            pb, nb = ref_sort_key(r)
            if pa == pb and nb == na + 1:
                run.append(r)
                continue
            flush()
            run = []
        run.append(r)
    flush()
    return ", ".join(out)


def value_token(value):
    """Leading token of a passive's value string."""
    return value.split()[0] if value.split() else "?"


def tolerance_token(value):
    """A tolerance written into a passive's value string - a real
    ordering requirement, same reasoning as ecu-pcb's own BOM."""
    m = re.search(r"\b(\d+(?:\.\d+)?)\s?%", value)
    return f"{m.group(1)}%" if m else None


_VALUE_MULT = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3,
               "u": 1e-6, "n": 1e-9, "p": 1e-12, "R": 1.0, "": 1.0}


def parse_value(token):
    """Numeric value of a passive's value token - handles both decimal
    (4.7k) and infix (4k7) spellings, same as ecu-pcb's own parser."""
    m = re.match(r"^(\d+)([kKMRunp])(\d+)$", token)
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * _VALUE_MULT[m.group(2)]
    m = re.match(r"^([\d.]+)\s*([kKMmunpR]?)$", token)
    if m:
        return float(m.group(1)) * _VALUE_MULT.get(m.group(2), 1.0)
    return None


def check_value_spellings(lines):
    """Fail if one electrical value reaches the BOM as two order lines
    purely because it was spelled two ways - same real purchasing-bug
    check as ecu-pcb's own BOM."""
    seen = defaultdict(list)
    for _cat, label, _mfr, _desc, package, _qty, refs, _qual in lines:
        parts_ = label.split()
        if len(parts_) < 2:
            continue
        value = parse_value(parts_[0])
        if value is None:
            continue
        tol = next((t for t in parts_[1:] if t.endswith("%")), None)
        seen[(parts_[-1], value, tol, package)].append((label, refs))

    clashes = {k: v for k, v in seen.items() if len(v) > 1}
    if clashes:
        detail = "; ".join(
            f"{k[1]:g} ({k[0]}) split across " + " and ".join(f"'{lb}'" for lb, _ in v)
            for k, v in clashes.items())
        raise AssertionError(
            f"BOM has {len(clashes)} value(s) split across order lines by "
            f"spelling alone: {detail}. Normalise the value token in "
            f"build_schematic.py; if the split is a real tolerance "
            f"difference, write it as e.g. '1k 1%' so it is explicit.")
    print(f"Value-spelling check OK: no value split across two order lines "
          f"({len(seen)} distinct passive line identities)")


def build():
    parts = load_parts()
    lines = []          # (category, mpn, mfr, desc, package, qty, refs, qual)

    # --- board-side connectors, matched by REFERENCE not Value token ---
    matched = set()
    for ref, (mpn, mfr, desc, qual) in BOARD_SIDE_CONNECTORS.items():
        if any(p["ref"] == ref for p in parts):
            matched.add(ref)
            pkg = next(p["package"] for p in parts if p["ref"] == ref)
            lines.append(("Connectors", mpn, mfr, desc, pkg, 1, ref, qual))

    # --- non-passives matched by real MPN token -------------------------
    groups = defaultdict(list)
    for p in parts:
        if p["ref"] in matched:
            continue
        prefix = re.match(r"^([A-Z]+)", p["ref"]).group(1)
        if prefix in PASSIVE_PREFIXES and prefix not in ("FB", "L"):
            continue
        hit = next((tok for tok in MPN if tok in p["value"]), None)
        if hit is None:
            continue
        matched.add(p["ref"])
        groups[(hit, p["package"])].append(p["ref"])

    for (tok, package), refs in groups.items():
        mpn, mfr, desc, qual = MPN[tok]
        cat = "Connectors" if tok in ("DTM06-2S", "DTM06-5S", "Tag-Connect") else \
              "Electromechanical" if tok == "Littelfuse 297" else \
              "Displays" if tok.startswith("RFA401280B") else \
              "Semiconductors"
        lines.append((cat, mpn, mfr, desc, package, len(refs), collapse_refs(refs), qual))

    # --- the four GC9A01 screens themselves (companion parts: they plug into
    # U6-U9's connectors, so they are not their own board placement) -------
    lines.append(("Displays", "RFA401280B-AYW-DNF1", "Raystar Optronics",
                  "1.28in 240x240 round GC9A01 TFT module, SPI, with PCAP touch (touch unused), 18-pin 0.5mm FPC "
                  "tail, active area 32.4mm. ORDER DIRECT FROM RAYSTAR (salescontact@raystar-optronics.com): the "
                  "product page lists no price or stock. Ask for the FPC contact fingers on the side that suits the "
                  "bottom-contact Amphenol connector",
                  "FPC module (companion, not a board placement)", 4, "U6-U9 (plug into the connectors)", "-"))

    # --- fuse element (separate real orderable line from the holder
    # above, which was already matched by Value-token like every other
    # non-passive) - a real, separately-purchased item but NOT its own
    # board placement, so it's excluded from the coverage arithmetic
    # below by its own distinctive package label, same real split
    # ecu-pcb's own BOM makes for the same reason. ---
    if any(p["ref"] == "F1" for p in parts):
        lines.append(("Electromechanical", "0297002", "Littelfuse",
                      "2A MINI blade fuse element (main 12V input) - same real "
                      "element ecu-pcb's own BOM already cites", "Mini blade (element)",
                      1, "F1", "-"))

    for mpn, mfr, desc, ref in HARNESS_PIGTAILS:
        if any(p["ref"] == ref for p in parts):
            lines.append(("Connectors", mpn, mfr, desc, "Harness pigtail (not a board placement)", 1, ref, "Automotive sealed"))

    # --- remaining non-passives with NO real MPN yet: real, honest ------
    # "needs real part selection" lines - grouped by their own real
    # Value string (identical Value = same real orderable identity),
    # not silently dropped and not given a fabricated precise MPN.
    tbd_groups = defaultdict(list)
    for p in parts:
        if p["ref"] in matched:
            continue
        prefix = re.match(r"^([A-Z]+)", p["ref"]).group(1)
        if prefix in PASSIVE_PREFIXES and prefix != "FB":
            continue
        matched.add(p["ref"])
        tbd_groups[(p["value"], p["package"])].append(p["ref"])
    for (value, package), refs in tbd_groups.items():
        lines.append(("Needs real part selection", value, "(not yet specified)",
                      f"Schematic Value: \"{value}\" - real manufacturer part number "
                      f"not yet chosen, see build_schematic.py's own header for what "
                      f"IS/ISN'T pinned down", package, len(refs), collapse_refs(refs), "TBD"))

    # --- passives: grouped by real value + package ---------------------
    pgroups = defaultdict(list)
    for p in parts:
        prefix = re.match(r"^([A-Z]+)", p["ref"]).group(1)
        if p["ref"] in matched:
            continue
        if prefix not in PASSIVE_PREFIXES:
            continue
        # DNP parts (value text says "DNP") get their own order line: a part that
        # is not fitted must not be counted into the quantity of the fitted ones.
        pgroups[(prefix, value_token(p["value"]), tolerance_token(p["value"]),
                 p["package"], "DNP" in p["value"])].append(p["ref"])

    kind = {"R": ("Resistor", "thick film, AEC-Q200"),
            "C": ("Capacitor", "X7R/X5R ceramic, AEC-Q200"),
            "L": ("Inductor", "AEC-Q200"),
            "FB": ("Ferrite bead", "AEC-Q200"),
            "Y": ("Crystal", "AEC-Q200")}
    # Value-spelling check runs on the value-based labels BEFORE they are
    # replaced by real part numbers (two spellings of one value would
    # otherwise become two order lines).
    spell_lines = []
    for (prefix, val, tol, package, _dnp), refs in pgroups.items():
        name, _ = kind.get(prefix, ("Part", ""))
        label = f"{val} {tol} {name}" if tol else f"{val} {name}"
        if _dnp:
            label += " (DNP)"
        spell_lines.append(("Passives", label, "", "", package, len(refs), "", ""))
    check_value_spellings(spell_lines)

    for (prefix, val, tol, package, dnp), refs in pgroups.items():
        name, note = kind.get(prefix, ("Part", ""))
        hit = passive_catalog.lookup(prefix, val, package)
        if hit is None:
            label = f"{val} {tol} {name}" if tol else f"{val} {name}"
            lines.append(("Needs real part selection", label, "(not in passive catalog)",
                          f"{name} {val} in {package}: no real part number chosen yet - add it to "
                          f"tools/passive_catalog.py", package, len(refs),
                          collapse_refs(refs), "TBD"))
            continue
        mpn, mfr, desc, status = hit
        if status != "verified":
            desc += " [PATTERN: confirm this exact part number in the distributor cart]"
        if dnp:
            desc += (" [DNP: do not populate. CAN0 split termination, fitted only if this board "
                     "is a bus end-node; the pads stay on the board]")
        lines.append(("Passives", mpn, mfr, desc, package, len(refs),
                      collapse_refs(refs), "AEC-Q200"))

    order = {"Semiconductors": 0, "Displays": 1, "Electromechanical": 2, "Connectors": 3,
             "Passives": 4, "Needs real part selection": 5}
    lines.sort(key=lambda r: (order[r[0]], -r[5], r[1]))
    return parts, lines


def main():
    parts, lines = build()
    NON_PLACEMENT_PACKAGES = {"Mini blade (element)", "Harness pigtail (not a board placement)",
                              "FPC module (companion, not a board placement)"}
    placements = sum(r[5] for r in lines if r[4] not in NON_PLACEMENT_PACKAGES)
    print(f"BOM: {len(lines)} orderable line items covering {placements} placements "
          f"(schematic has {len(parts)} real parts)")
    by_cat = defaultdict(int)
    for r in lines:
        by_cat[r[0]] += 1
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n} line items")
    assert placements == len(parts), \
        f"BOM covers {placements} placements but schematic has {len(parts)} parts"
    print("Coverage check OK: every schematic part appears on exactly one BOM line")
    check_value_spellings([l for l in lines if l[0] != "Needs real part selection"])

    html = render_html(lines, parts)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT_HTML}")


def render_html(lines, parts):
    from html import escape
    rows = []
    current = None
    for cat, mpn, mfr, desc, package, qty, refs, qual in lines:
        if cat != current:
            current = cat
            rows.append(f'<tr class="cat"><td colspan="7">{escape(cat)}</td></tr>')
        qcls = "q-yes" if qual not in ("-", "TBD") else ("q-tbd" if qual == "TBD" else "q-na")
        rows.append(
            "<tr>"
            f'<td class="mpn">{escape(mpn)}</td>'
            f"<td>{escape(mfr)}</td>"
            f'<td class="desc">{escape(desc)}</td>'
            f'<td class="pkg">{escape(package)}</td>'
            f'<td class="qty">{qty}</td>'
            f'<td class="refs">{escape(refs)}</td>'
            f'<td><span class="{qcls}">{escape(qual)}</span></td>'
            "</tr>")
    table = "\n".join(rows)
    total_lines = len(lines)
    total_parts = len(parts)
    board = board_size_mm() or "see repo"
    return HTML_TEMPLATE.replace("{{TABLE}}", table) \
                        .replace("{{LINES}}", str(total_lines)) \
                        .replace("{{PARTS}}", str(total_parts)) \
                        .replace("{{BOARD}}", board)


HTML_TEMPLATE = r"""<title>Gauges Bill of Materials</title>
<style>
  :root{
    --paper:#fbfaf8; --panel:#ffffff; --ink:#1a1d21; --muted:#6b6f76;
    --rule:#e4e1dc; --rule-soft:#efedea;
    --accent:#1d4e89; --brass:#8a6a24;
    --ok:#2f6b45; --ok-bg:#e9f2ec;
    --warn:#8a5a00; --warn-bg:#f8efdd;
    --none:#6b6f76; --none-bg:#eeecea;
    --shadow:0 1px 2px rgba(26,29,33,.05);
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]){
      --paper:#14161a; --panel:#1b1e23; --ink:#e9e7e3; --muted:#9aa0a8;
      --rule:#2c3037; --rule-soft:#23272d;
      --accent:#7fb0ec; --brass:#d3ab5c;
      --ok:#77d7a2; --ok-bg:#16301f;
      --warn:#efbe73; --warn-bg:#33260f;
      --none:#9aa0a8; --none-bg:#24282e;
      --shadow:none;
    }
  }
  :root[data-theme="dark"]{
    --paper:#14161a; --panel:#1b1e23; --ink:#e9e7e3; --muted:#9aa0a8;
    --rule:#2c3037; --rule-soft:#23272d;
    --accent:#7fb0ec; --brass:#d3ab5c;
    --ok:#77d7a2; --ok-bg:#16301f;
    --warn:#efbe73; --warn-bg:#33260f;
    --none:#9aa0a8; --none-bg:#24282e;
    --shadow:none;
  }

  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{
    margin:0; background:var(--paper); color:var(--ink);
    font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  .wrap{max-width:1120px; margin:0 auto; padding:52px 22px 80px;
        display:flex; flex-direction:column; gap:30px}

  .eyebrow{margin:0; font-size:11.5px; font-weight:700; letter-spacing:.18em;
           text-transform:uppercase; color:var(--brass)}
  h1{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
     font-weight:600; font-size:clamp(32px,5vw,50px); line-height:1.08;
     letter-spacing:-.015em; margin:10px 0 0; text-wrap:balance}
  .standfirst{margin:14px 0 0; color:var(--muted); max-width:64ch; font-size:17px}
  .rule{height:1px; background:var(--rule); border:0; margin:0}

  .figures{display:flex; flex-wrap:wrap; border:1px solid var(--rule);
           border-radius:4px; background:var(--panel); box-shadow:var(--shadow); overflow:hidden}
  .fig{flex:1 1 150px; padding:16px 20px; border-right:1px solid var(--rule-soft)}
  .fig:last-child{border-right:0}
  .fig b{display:block; font-size:26px; line-height:1.15; letter-spacing:-.02em;
         font-variant-numeric:tabular-nums;
         font-family:"Iowan Old Style",Palatino,Georgia,serif; font-weight:600}
  .fig span{display:block; margin-top:3px; font-size:11.5px; letter-spacing:.08em;
            text-transform:uppercase; color:var(--muted)}

  .note{border-left:2px solid var(--accent); padding:2px 0 2px 20px;
        display:flex; flex-direction:column; gap:10px}
  .note h2{font-family:"Iowan Old Style",Palatino,Georgia,serif;
           font-size:19px; font-weight:600; margin:0; letter-spacing:-.01em}
  .note p{margin:0; font-size:15px; color:var(--muted); max-width:70ch}
  .note strong{color:var(--ink); font-weight:600}

  .tablewrap{border:1px solid var(--rule); border-radius:4px; background:var(--panel);
             box-shadow:var(--shadow); overflow-x:auto}
  table{border-collapse:collapse; width:100%; min-width:920px; font-size:14px}
  thead th{position:sticky; top:0; z-index:1; background:var(--panel);
           text-align:left; font-size:10.5px; font-weight:700; letter-spacing:.12em;
           text-transform:uppercase; color:var(--muted);
           padding:15px 16px 11px; border-bottom:1px solid var(--rule); white-space:nowrap}
  tbody td{padding:11px 16px; border-bottom:1px solid var(--rule-soft); vertical-align:top}
  tbody tr:last-child td{border-bottom:0}
  tr.cat td{background:var(--paper); color:var(--brass);
            font-size:10.5px; font-weight:700; letter-spacing:.16em; text-transform:uppercase;
            padding:11px 16px; border-bottom:1px solid var(--rule); border-top:1px solid var(--rule)}
  .mpn,.pkg,.refs{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
  .mpn{font-size:13px; font-weight:600; white-space:nowrap}
  .desc{color:var(--muted); min-width:260px}
  .pkg{font-size:12px; color:var(--muted); white-space:nowrap}
  .qty{text-align:right; font-variant-numeric:tabular-nums; font-weight:700; white-space:nowrap}
  .refs{font-size:12px; color:var(--muted)}
  .q-yes,.q-tbd,.q-na{display:inline-block; padding:2px 9px; border-radius:3px;
                      font-size:11px; font-weight:700; letter-spacing:.03em; white-space:nowrap}
  .q-yes{color:var(--ok); background:var(--ok-bg)}
  .q-tbd{color:var(--warn); background:var(--warn-bg)}
  .q-na{color:var(--none); background:var(--none-bg)}

  footer{color:var(--muted); font-size:14px; max-width:72ch}
  footer p{margin:0}
  footer code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
              font-size:13px; color:var(--ink)}
  a{color:var(--accent)}
  a:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  @media (prefers-reduced-motion:reduce){*{animation:none !important; transition:none !important}}
  @media (max-width:640px){
    .wrap{padding:32px 15px 60px; gap:24px}
    .fig{flex-basis:50%; border-bottom:1px solid var(--rule-soft)}
  }
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">Jessie&rsquo;s Cars &middot; Cluster / gauges</p>
    <h1>Gauges Bill of Materials</h1>
    <p class="standfirst">Every part on the small round-gauge board of the Mustang
    restomod cluster &mdash; an NXP S32K144 hub driving 4 real GC9A01 round TFT
    modules plus the local resistive-sender ADC front end, with CAN0 out to both
    ecu-pcb and display/'s own Android carrier.</p>
  </header>

  <div class="figures">
    <div class="fig"><b>{{LINES}}</b><span>Line items</span></div>
    <div class="fig"><b>{{PARTS}}</b><span>Placements</span></div>
    <div class="fig"><b>4</b><span>Copper layers</span></div>
    <div class="fig"><b>{{BOARD}}</b><span>Board, mm</span></div>
  </div>

  <div class="note">
    <h2>How to read this list</h2>
    <p><strong>Active parts and connectors</strong> carry real manufacturer part
    numbers wherever <code>build_schematic.py</code>'s own comments state one -
    that provenance lives in the schematic generator, not invented here.</p>
    <p><strong>A "Needs real part selection" section is real, not an error.</strong>
    The 12V front-end TVS/reverse-protection FETs' exact manufacturer and the
    S32K144's own exact memory/package order suffix were never pinned down to a
    single orderable P/N in this project's design passes - they're flagged here
    rather than given a fabricated-precise part number.</p>
    <p><strong>Passives are specified parametrically</strong> &mdash; value, package
    and the AEC-Q200 requirement &mdash; rather than pinned to one vendor, the same
    real reasoning ecu-pcb's own BOM uses.</p>
    <p><strong>Pricing and stock are not included.</strong> Nothing here was checked
    against a distributor's live catalogue.</p>
  </div>

  <div class="tablewrap">
    <table>
      <thead>
        <tr>
          <th scope="col">Part number</th><th scope="col">Manufacturer</th>
          <th scope="col">Description</th><th scope="col">Package</th>
          <th scope="col">Qty</th><th scope="col">Designators</th>
          <th scope="col">Qualification</th>
        </tr>
      </thead>
      <tbody>
{{TABLE}}
      </tbody>
    </table>
  </div>

  <hr class="rule">

  <footer>
    <p>Generated directly from the project schematic by <code>build_bom.py</code>, so
    quantities and designators cannot drift from the board. What remains before
    ordering: real part selection for the flagged TBD lines, and a purchasing pass
    for live pricing and availability on everything else.</p>
  </footer>
</div>
"""


if __name__ == "__main__":
    main()
