"""
passive_catalog.py - real, orderable part numbers for this project's passives.

Both boards' build_bom.py call lookup(prefix, value_token, package). A passive
that is not in this catalog is reported as "Needs real part selection" rather
than silently getting a made-up part number, same discipline as the active
parts. Each entry records the rating it was chosen for, because the schematic
Value strings carry only the value.

STATUS OF EACH ENTRY (2026-10-02): "verified" means the exact part number was
found on a distributor or manufacturer page in a web search; "pattern" means it
follows the manufacturer's published numbering scheme and neighbours of the
same series were verified, but the exact string was not seen. Pattern entries
are flagged so they get checked in the distributor cart before ordering.
"""
import re

CAPS = {
    # (value farads, package) -> (MPN, rating note, status)
    (12e-12, "0603"): ("GCM1885C1H120JA16D", "12 pF C0G 50 V", "verified"),
    (15e-12, "0603"): ("GCM1885C1H150JA16D", "15 pF C0G 50 V", "pattern"),
    (18e-12, "0603"): ("GCM1885C1H180JA16D", "18 pF C0G 50 V", "verified"),
    (22e-12, "0603"): ("GCM1885C1H220JA16D", "22 pF C0G 50 V (Murata marks it NRND; still orderable, swap if unavailable)", "verified"),
    (1e-9, "0603"): ("GCM188R71H102KA37D", "1 nF X7R 50 V", "verified"),
    (2.2e-9, "0603"): ("GCM188R71H222KA37D", "2.2 nF X7R 50 V", "pattern"),
    (4.7e-9, "0603"): ("GCM188R71H472KA37D", "4.7 nF X7R 50 V", "verified"),
    (10e-9, "0603"): ("GCM188R71H103KA37D", "10 nF X7R 50 V", "verified"),
    (100e-9, "0603"): ("GCM188R71H104KA57D", "100 nF X7R 50 V", "verified"),
    (220e-9, "0603"): ("GCM188R71H224KA64D", "220 nF X7R 50 V", "verified"),
    (1e-6, "0603"): ("GCM188R71C105KA64D", "1 uF X7R 16 V", "verified"),
    (4.7e-6, "0805"): ("GCM21BR71C475KA73L", "4.7 uF X7R 16 V", "verified"),
    (10e-6, "0805"): ("GCM21BR71A106KE22L", "10 uF X7R 10 V", "verified"),
    (4.7e-6, "1206"): ("GCJ31CC71H475KA01L", "4.7 uF X7R 50 V", "verified"),
    (22e-6, "1206"): ("GCM31CR71A226KE02L", "22 uF X7R 10 V", "verified"),
    (10e-6, "1210"): ("GCM32EC71H106KA03L", "10 uF X7S 50 V", "verified"),
    (100e-6, "CP8x10"): ("EEH-ZA1V101P", "100 uF 35 V hybrid polymer, 8 x 10.2 mm", "verified"),
}
CAP_MFR = {"EEH-ZA1V101P": "Panasonic"}

SENSE = {
    (2e-3, "1206"): ("KRL3216E-C-R002-G-T5", "Susumu", "2 mohm 2% 1206 current sense, AEC-Q200", "verified"),
    (5e-3, "1206"): ("KRL3216E-M-R005-F-T5", "Susumu", "5 mohm 1% 1206 current sense, AEC-Q200 (seen on a distributor listing; confirm series suffix against Susumu's datasheet at order time)", "pattern"),
}

OTHER = {
    # ferrite bead, crystal: keyed by (kind, package) -> entry
    ("FB", "0603"): ("BLM18PG221SH1D", "Murata", "220 ohm @100 MHz ferrite bead, 1.4 A, AEC-Q200", "verified"),
    ("Y", "3225"): ("ABM8AIG-8.000MHZ-12-2Z-T3", "Abracon", "8 MHz 12 pF crystal 3.2 x 2.5 mm, +/-20 ppm, AEC-Q200", "pattern"),
}


def to_number(token):
    """'4.7u' -> 4.7e-6, '4n7' -> 4.7e-9, '49.9k' -> 49900, '2m' -> 2e-3,
    '1.10R' -> 1.1, '100uF' -> 1e-4, '60R' -> 60. Returns None if unparseable."""
    t = token.strip().rstrip("FHfh") if re.search(r"[unpmkKMR]", token) else token.strip()
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "R": 1.0,
            "k": 1e3, "K": 1e3, "M": 1e6}
    m = re.fullmatch(r"(\d+)([punmRkKM])(\d+)", t)
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * mult[m.group(2)]
    m = re.fullmatch(r"([\d.]+)\s*([punmRkKM]?)", t)
    if m:
        return float(m.group(1)) * mult.get(m.group(2), 1.0)
    return None


def pkg_key(package):
    for k in ("0201", "0402", "0603", "0805", "1206", "1210", "2512", "3225"):
        if k in package:
            return k
    if "CP_Elec_8x10" in package:
        return "CP8x10"
    return package


def yageo_code(ohms):
    """AC0603FR-07<code>L resistance code: 10000 -> 10K, 4700 -> 4K7,
    2050 -> 2K05, 60.4 -> 60R4, 1.1 -> 1R1, 100 -> 100R."""
    if ohms >= 1e6:
        v, unit = ohms / 1e6, "M"
    elif ohms >= 1e3:
        v, unit = ohms / 1e3, "K"
    else:
        v, unit = ohms, "R"
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    if "." in s:
        a, b = s.split(".")
        return f"{a}{unit}{b}"
    return f"{s}{unit}"


def lookup(prefix, value_token, package):
    """Return (mpn, manufacturer, description, status) or None."""
    pk = pkg_key(package)
    if prefix in ("FB", "Y") or (prefix == "L" and pk == "0603"):
        key = ("FB" if prefix == "L" else prefix, pk)
        e = OTHER.get(key)
        return (e[0], e[1], e[2], e[3]) if e else None
    n = to_number(value_token)
    if n is None:
        return None
    if prefix == "C":
        for (v, p), (mpn, note, status) in CAPS.items():
            if p == pk and abs(v - n) <= 1e-3 * v:
                return (mpn, CAP_MFR.get(mpn, "Murata"), f"Capacitor, {note}, AEC-Q200", status)
        return None
    if prefix == "R":
        for (v, p), (mpn, mfr, desc, status) in SENSE.items():
            if p == pk and abs(v - n) <= 1e-3 * v:
                return (mpn, mfr, desc, status)
        if pk == "1206":
            # Yageo AC1206 AEC-Q200 series, 200 V working voltage: used where a
            # series resistor must stand off an inductive tach spike.
            return (f"AC1206FR-07{yageo_code(n)}L", "Yageo",
                    f"Resistor {yageo_code(n).replace('K', 'k')} 1% 1206 thick film, 200 V, AEC-Q200", "pattern")
        if pk != "0603":
            return None
        if n == 0:
            return ("AC0603JR-070RL", "Yageo", "0 ohm jumper 0603, AEC-Q200", "pattern")
        code = yageo_code(n)
        return (f"AC0603FR-07{code}L", "Yageo",
                f"Resistor {code.replace('K', 'k')} 1% 0603 thick film, AEC-Q200", "pattern")
    return None
