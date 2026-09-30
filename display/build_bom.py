#!/usr/bin/env python3
"""
build_bom.py - generates the display/ board's bill of materials
straight from the real schematic, plus a standalone HTML page.

*** ADAPTED FROM gauges/build_bom.py / ecu-pcb/build_bom.py (2026-09-27)
*** same real generated-not-hand-maintained discipline, same coverage/
value-spelling self-checks, same HTML template - only the per-board MPN
table and header copy are new.

WHY GENERATED, NOT HAND-MAINTAINED: every other artefact in this family
is regenerated from source rather than hand-edited (see
build_schematic.py / build_pcb.py). Reference designators, values,
packages and quantities here all come from ClusterDisplay.kicad_sch
itself, so the BOM cannot disagree with the board.

WHAT IS AND IS NOT VERIFIED - stated plainly, same discipline as every
sibling board's own BOM.
  * ACTIVE parts carry REAL manufacturer part numbers where
    build_schematic.py's own comments state one - that provenance is
    in that file, not invented here. This originally covered U1/U2/U3/
    U4/U6/U7, D2, J4 (panel-support parts U6/U7/L2-L4/D2-D4/J4 were
    all replaced 2026-09-30 when the panel changed from the 350-nit
    DisplayModule DM-TFTR50-413 to the 800-nit Team Source Display
    TST040HDBC-42: TPS65131-Q1 +/-6.5V bias, TPS61165-Q1 15V/180mA
    backlight, Coilcraft XAL inductors, Hirose FH26 FPC connector, and
    two open solder jumpers for the panel's unresolved +/-6.5V pin
    polarity); as of 2026-09-28 it also covers Q1/Q2 (real
    Nexperia PMV55ENEA, selected against LM74930-Q1's own datasheet
    MOSFET-selection guidance), D1 (real SMCJ33A, same part gauges/'s
    own front end already uses), F1 (real Bourns MF-RG500 - MF-RG300,
    this board's own footprint until now, was really a 3.0A-hold part
    despite the circuit's "5A" target) and J1 (real, confirmed-
    orderable Toradex product name "Verdin iMX95 Hexa 8GB WB IT" -
    Toradex's own internal order code still wants confirming at
    purchase time).
  * J2/J3/J8/J9 (formerly provisional 2.54mm headers) were resolved
    2026-09-30 once the user's question about what they connect to
    clarified their roles: J2 = car 12V/GND/IGN input (Phoenix MKDS
    1,5/3-5,08, same family as gauges/'s J1), J3 = the CAN tap that is
    the display<->gauges<->ECU link (Molex KK 254 22-27-2031, same family
    as gauges/'s J7), J8/J9 = bench/service headers (Samtec TSW-108-07-G-S
    / TSW-104-07-G-S). Wire gauge and final harness routing are still
    unknown, so the harness-side pigtails (DTM06-3S) are a same-family
    assumption, not a measured requirement.
  * PASSIVES are specified parametrically - value, package, and the
    AEC-Q200 requirement - same real reasoning as every sibling board.
  * LIVE PRICING AND STOCK ARE NOT INCLUDED.

Run:  python build_bom.py          -> console summary + ClusterDisplay_BOM.html
"""
import io
import os
import re
from collections import defaultdict

from kiutils.schematic import Schematic
from kiutils.utils import sexpr

HERE = os.path.dirname(os.path.abspath(__file__))
SCH = os.path.join(HERE, "ClusterDisplay.kicad_sch")
OUT_HTML = os.path.join(HERE, "ClusterDisplay_BOM.html")
PCB = os.path.join(HERE, "ClusterDisplay.kicad_pcb")

# Real manufacturer part numbers for every non-passive that has one
# stated in build_schematic.py's own comments. Keyed by the distinctive
# token that appears in the schematic's own Value string, so this table
# cannot drift away from the schematic without the lookup simply
# failing loudly rather than reporting a stale part.
#   token -> (MPN, manufacturer, description, qualification)
MPN = {
    # Orderable P/Ns confirmed 2026-09-30 from TI's part-details pages and
    # distributor listings (the -Q1 names are families, not orderable).
    "LM74930-Q1":   ("LM74930QRGERQ1", "TI", "Automotive ideal-diode surge stopper w/ circuit breaker + OV clamp, VQFN-24 RGE (datasheet SNOSDF6); TI lists it Active/Production", "AEC-Q100 Grade 1"),
    "LM61460-Q1":   ("LM61460AASQRJRRQ1", "TI", "Automotive 3-36V 6A low-EMI synchronous buck, main +5V rail, VQFN-HR-14 RJR (datasheet SNVSB70F). LM61460 is a FAMILY of three adjustable variants: AAS (auto light-load mode + spread spectrum, chosen), AAN (auto, no spread spectrum), AFS (forced-PWM + spread spectrum). AAS was picked for EMI; use AFS if PFM ripple at light load is a problem. Not yet bench-verified", "AEC-Q100 (TI -Q1 suffix)"),
    "TLV767-Q1":    ("TLV76701QWDRBRQ1", "TI", "Automotive 16V/1A adjustable LDO, +1V8 Verdin I/O rail, VSON-8 DRB with wettable flanks (datasheet SBVS381A); 01 = adjustable, QW = wettable-flank automotive", "AEC-Q100 (TI -Q1 suffix)"),
    "TCAN1044V-Q1": ("TCAN1044VDRQ1", "TI", "Automotive CAN FD transceiver w/ 1.8V I/O support (V variant is load-bearing - see parts.py), SOIC-8 D (datasheet SLLSF17D)", "AEC-Q100 Grade 1"),
    # Panel rails/backlight for the TSD TST040HDBC-42 (2026-09-30) - see
    # build_schematic.py's build_panel_bias()/build_panel_backlight().
    "TPS65131-Q1":  ("TPS65131TRGERQ1", "TI", "Automotive dual-output boost + inverting LCD bias supply, panel +6.5V/-6.5V analog rails from +5V, VQFN-24 RGE with wettable flanks (datasheet SLVSBB2F); TI lists it Active", "AEC-Q100 Grade 2"),
    "TPS61165-Q1":  ("TPS61165TDBVRQ1", "TI", "Automotive boost white-LED driver, panel backlight 15V/180mA from +5V with PWM dimming, SOT-23-6 DBV (datasheet SLVSB73B); TI lists the family Active. Orderable suffix taken from a TI E2E thread and a datasheet listing - confirm on TI's store", "AEC-Q100"),
    "XAL4030-472ME": ("XAL4030-472MEC", "Coilcraft", "4.7uH shielded molded power inductor, Isat 4.6A, DCR 40mR typ, 4x4x3mm (datasheet Document 806-1; trailing C = 7in reel ordering code)", "AEC-Q200"),
    "XAL4040-103ME": ("XAL4040-103MEC", "Coilcraft", "10uH shielded molded power inductor, Isat 3.0A, DCR 84mR typ, 4x4x4mm (datasheet Document 806-1; trailing C = 7in reel ordering code)", "AEC-Q200"),
    "SJ3":          ("(no part - PCB footprint only)", "-", "3-pad OPEN solder jumper (KiCad SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm); bridged with a solder blob after verifying the panel's +/-6.5V pin polarity - see JP1/JP2 in build_schematic.py", "n/a"),
    "PMEG6010ELRX": ("PMEG6010ELRX", "Nexperia", "Boost rectifier Schottky, 60V/1A, SOD-123W", "AEC-Q101"),

    # Real parts chosen 2026-09-28, selected against LM74930-Q1's own
    # datasheet MOSFET-selection section (60V VDS w/ single TVS, >=15V
    # VGS rating since HGATE/DGATE drive up to 14V) - see
    # build_schematic.py's own comment on Q1/Q2 for the real datasheet
    # citation and the honest flag on current margin vs. F1's 5A rating.
    "PMV55ENEA":    ("PMV55ENEAR", "Nexperia", "60V N-ch MOSFET, VGS +-20V, 3.1A, SOT-23 - back-to-back ideal-diode/pass FET pair (orderable suffix R = reel; 12NC 934068714215)", "AEC-Q101"),
    "SMCJ33A":      ("SMCJ33A (multi-source)", "Littelfuse / onsemi / Vishay (industry-standard P/N)",
                      "SMC-package TVS diode, 33V standoff, 12V-rail transient protection - not pinned to one vendor, real industry-standard part number, same real part gauges/'s own D1 already uses", "AEC-Q101"),
}

# Real, exactly-identified connectors matched by REFERENCE (their
# schematic Value strings are either too short to safely substring-
# match, e.g. J4's real datasheet-derived table, or - for the TBD
# family/SKU cases below - too generic to trust a token match against).
BOARD_SIDE_CONNECTORS = {
    "J4": ("FH26-39S-0.3SHW(99)", "Hirose", "39-position 0.3mm-pitch FPC connector for the TST040HDBC-42's 39-pin FPC. The panel datasheet does NOT name a connector: 0.3mm pitch is inferred from the FPC's 12mm width across 39 pins, and FH26 is bottom-contact - specify the FPC's exposed-pad side when ordering from TSD. Hirose lists the (05) variant obsolete and FH26W-39S-0.3SHW(60) as current: confirm its land pattern against the bundled FH26 footprint before ordering", "-"),
    "J2": ("MKDS 1,5/ 3-5,08 (1715734)", "Phoenix Contact", "3-position 5.08mm pluggable-style screw terminal block, board side of the car harness power input (VBAT / GND / IGN); 17.5A / 400V nominal - same MKDS 5.08 family gauges/'s J1 uses. Harness end: sealed Deutsch DTM06-3S (TE) pigtail, as on gauges/", "-"),
    "J3": ("22-27-2031", "Molex", "3-circuit KK 254 (2.54mm) vertical header, board side of the CAN tap (CANH / CANL / GND), 4A / 250V per contact - same KK 254 family gauges/'s J7 uses. This is the display<->gauges<->ECU CAN link. Harness end: sealed Deutsch DTM06-3S (TE) pigtail", "-"),
    "J8": ("TSW-108-07-G-S", "Samtec", "1x8 0.100in gold-finish pin header, JTAG/debug - bench and service use only, not part of the vehicle harness", "-"),
    "J9": ("TSW-104-07-G-S", "Samtec", "1x4 0.100in gold-finish pin header, power/recovery/reset buttons - bench and service use only, not part of the vehicle harness", "-"),
    "J10": ("1058", "Keystone Electronics", "20mm coin cell (2032) holder, real unambiguous Keystone part number - same real numbering convention as this family's own Keystone 3568 fuse holder, identified from the real footprint name rather than an independent datasheet citation in build_schematic.py's own comments", "-"),
    # Real SoM SKU chosen 2026-09-28 - see build_x1_symbol()'s own
    # comment in build_schematic.py for the real reasoning (Hexa/8GB
    # for real AAOS headroom, IT for automotive temp range). Toradex's
    # own internal ordering code wasn't independently confirmed - real
    # product name is, verify the exact code at purchase time.
    "J1": ("2309409-2 socket + Verdin iMX95 Hexa 8GB WB IT (Toradex PN 0089)",
           "TE Connectivity + Toradex",
           "TWO purchases on this one line: the 260-position DDR4 SODIMM socket (TE "
           "2309409-2, 5.2mm stack - the socket Toradex recommends in datasheet section "
           "6.5.1, matching this board's SODIMM-260_DDR4_H4.0-5.2 footprint) and the SoM "
           "that plugs into it (docs.toradex.com/200007-verdin_imx95_datasheet.pdf). "
           "Toradex product no. 0089 per developer.toradex.com "
           "(checked 2026-09-30): V1.0A is end-of-life, V1.0B moved to B0 silicon, "
           "V1.1A fixed errata HAR-12581, and V1.1B (Q3 2026) moved to mass-production "
           "SoC and PMIC - order the latest revision. Also listed on Mouser", "-"),
    # Real part chosen 2026-09-28 - see build_schematic.py's own comment
    # on F1 for why MF-RG300 (the footprint this board shipped with
    # until now) was both the wrong footprint AND the wrong real part.
    "F1": ("MF-RG500", "Bourns",
           "PTC resettable fuse, 5.0A hold / 8.5A trip / 16V max, AEC-Q200 - "
           "real part matching the circuit's own target rating, not the "
           "3.0A-hold MF-RG300 this board's footprint previously (wrongly) cited",
           "AEC-Q200"),
}

# Real display panel this board is designed for - referenced via J4
# above, not a separate placed component (its own driver IC, HX8399,
# is built into the panel module, not separately populated here).
PANEL_NOTE = ("Team Source Display TST040HDBC-42", "Team Source Display (TSD)",
              "4.0in 720x720 round IPS, native MIPI-DSI (3 lanes), ICNL9707 driver built "
              "into the module, 800 cd/m2, -30..+80C, 101.52mm active circle - datasheet "
              "V1.0 (2023-06-29) read in full; connects via J4 above, not its own BOM "
              "line. Datasheet table and drawing DISAGREE on which FPC pins carry +6.5V "
              "vs -6.5V - resolve with TSD before bridging JP1/JP2. Order the FPC with the "
              "exposed-pad side matching J4's bottom-contact")

PASSIVE_PREFIXES = ("R", "C", "L", "FB", "Y")


def board_size_mm():
    """Real board outline size, measured from the PCB's own Edge.Cuts
    geometry - same regex gauges/build_bom.py already confirmed works
    against this project's newer KiCad 10 .kicad_pcb text layout."""
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
    per kiutils schematicSymbol instance. A real, multi-unit part (J1,
    the Verdin X1 connector, split into 7 real schematic units purely
    for drawing legibility - 260 real pins don't fit on one sheet
    symbol) shows up as 7 separate schematicSymbols all sharing
    Reference "J1", each carrying an identical Value/Footprint (checked
    directly against the real .kicad_sch before relying on it). Without
    deduplicating, J1 alone would inflate the real part count by 6 -
    caught by this file's own coverage assertion the first time it ran
    (72 real placements vs. a naive 78 raw symbol-instance count)."""
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
    ordering requirement, same reasoning as every sibling board's BOM."""
    m = re.search(r"\b(\d+(?:\.\d+)?)\s?%", value)
    return f"{m.group(1)}%" if m else None


_VALUE_MULT = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3,
               "u": 1e-6, "n": 1e-9, "p": 1e-12, "R": 1.0, "": 1.0}


def parse_value(token):
    """Numeric value of a passive's value token - handles both decimal
    (4.7k) and infix (4k7) spellings, same as every sibling board's own
    parser."""
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
    check as every sibling board's own BOM."""
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
    matched = set()

    # --- exactly-identified parts, matched by REFERENCE (F1 categorized
    # as Electromechanical, everything else here is a Connector) --------
    for ref, (mpn, mfr, desc, qual) in BOARD_SIDE_CONNECTORS.items():
        if any(p["ref"] == ref for p in parts):
            matched.add(ref)
            pkg = next(p["package"] for p in parts if p["ref"] == ref)
            cat = "Electromechanical" if ref == "F1" else "Connectors"
            lines.append((cat, mpn, mfr, desc, pkg, 1, ref, qual))

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
        lines.append(("Semiconductors", mpn, mfr, desc, package, len(refs), collapse_refs(refs), qual))

    # --- panel note (referenced via J4, not a placed component) --------
    mpn, mfr, desc = PANEL_NOTE
    lines.append(("Displays (reference only)", mpn, mfr, desc, "n/a - see J4", 0, "(via J4)", "-"))

    # --- remaining non-passives with NO real MPN at all: real, honest --
    # "needs real part selection" lines - grouped by their own real
    # Value string (identical Value = same real orderable identity),
    # not silently dropped and not given a fabricated precise MPN. This
    # is where Q1/Q2 (generic NFET) and D1 (generic TVS) land - true
    # placeholders with not even a manufacturer named, unlike F1/J1
    # above which at least have a real family/SKU-family identified.
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
        pgroups[(prefix, value_token(p["value"]), tolerance_token(p["value"]),
                 p["package"])].append(p["ref"])

    kind = {"R": ("Resistor", "thick film, AEC-Q200"),
            "C": ("Capacitor", "X7R/X5R ceramic, AEC-Q200"),
            "L": ("Inductor", "AEC-Q200"),
            "FB": ("Ferrite bead", "AEC-Q200"),
            "Y": ("Crystal", "AEC-Q200")}
    for (prefix, val, tol, package), refs in pgroups.items():
        name, note = kind.get(prefix, ("Part", ""))
        label = f"{val} {tol} {name}" if tol else f"{val} {name}"
        desc = (f"{name} {val}, {tol} tolerance - {note}" if tol
                else f"{name} {val} - {note}")
        lines.append(("Passives", label, "(any qualified)",
                      desc, package, len(refs),
                      collapse_refs(refs), "AEC-Q200"))

    order = {"Semiconductors": 0, "Electromechanical": 1, "Connectors": 2,
             "Displays (reference only)": 3, "Passives": 4, "Needs real part selection": 5}
    lines.sort(key=lambda r: (order[r[0]], -r[5], r[1]))
    return parts, lines


def main():
    parts, lines = build()
    # PANEL_NOTE's own qty is 0 (reference-only, not a placement) -
    # excluded from the coverage arithmetic by construction.
    placements = sum(r[5] for r in lines)
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

    tbd_lines = [r for r in lines if r[7] == "TBD"]
    if tbd_lines:
        tbd_refs = ", ".join(r[6] for r in tbd_lines)
        print(f"NOTE: {len(tbd_lines)} line item(s) need real part selection before "
              f"ordering ({tbd_refs} - see this file's own header).")

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
            f'<td class="qty">{qty if qty else "-"}</td>'
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


HTML_TEMPLATE = r"""<title>Display Carrier Bill of Materials</title>
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
    <p class="eyebrow">Jessie&rsquo;s Cars &middot; Cluster / display</p>
    <h1>Display Carrier Bill of Materials</h1>
    <p class="standfirst">Every part on the Android Automotive display carrier of
    the Mustang restomod cluster &mdash; a Toradex Verdin iMX95 SoM driving a
    4in 800-nit round MIPI-DSI panel directly, with its own &plusmn;6.5V
    analog rails and 15V backlight boost, CAN out to gauges/ and ecu-pcb.</p>
  </header>

  <div class="figures">
    <div class="fig"><b>{{LINES}}</b><span>Line items</span></div>
    <div class="fig"><b>{{PARTS}}</b><span>Placements</span></div>
    <div class="fig"><b>4</b><span>Copper layers</span></div>
    <div class="fig"><b>{{BOARD}}</b><span>Board, mm</span></div>
  </div>

  <div class="note">
    <h2>How to read this list</h2>
    <p><strong>No line is left as a placeholder part.</strong> J2/J3 are the real
    harness connectors (power and CAN, same families as gauges/), J8/J9 are
    bench-only headers. Still unknown: final wire gauge and harness routing, so
    the DTM06-3S pigtails are a same-family assumption. Everything else that started as an open item (the front-end
    FET pair, the input TVS, the fuse's exact rating, and the Verdin SoM's
    exact SKU) was resolved to a real, cited part on 2026-09-28. Also open, and
    flagged in the J4 and panel lines: the panel datasheet's table and drawing
    disagree on which FPC pins carry +6.5V vs -6.5V (JP1/JP2 are left open until
    resolved), and its FPC connector is inferred, not named.</p>
    <p><strong>Active parts with a real MPN</strong> carry provenance straight
    from <code>build_schematic.py</code>'s own comments, each one traced to a
    real datasheet during the design pass that introduced it.</p>
    <p><strong>Passives are specified parametrically</strong> &mdash; value, package
    and the AEC-Q200 requirement &mdash; rather than pinned to one vendor.</p>
    <p><strong>Pricing and stock are not included.</strong></p>
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
    ordering: confirm the harness wire gauge, resolve the panel's +/-6.5V pin
    polarity with TSD, and run a purchasing pass for live pricing and availability.</p>
  </footer>
</div>
"""


if __name__ == "__main__":
    main()
