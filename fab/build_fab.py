#!/usr/bin/env python3
"""
build_fab.py - generate the manufacturing package for display/ and gauges/.

For each board it writes fab/<board>/:
  gerbers/        Gerber (X2, Protel extensions) + Excellon drill, PTH and NPTH
                  separate - the set a board house wants
  <board>_fab.zip the zipped gerbers+drill, ready to upload
  <board>_pos.csv pick-and-place (only needed if the fab assembles)
  <board>_bom.csv one line per orderable part: MPN, manufacturer, designators
  report.txt      DRC status, size, hole/via/track statistics

Nothing is hand-edited. It refuses to package a board with unconnected nets.
Run:  python fab/build_fab.py [display] [gauges]
"""
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
          "F.Mask,B.Mask,Edge.Cuts")
BOARDS = {
    "display": ("ClusterDisplay.kicad_pcb", "ClusterDisplay.kicad_sch"),
    "gauges": ("ClusterGauges.kicad_pcb", "ClusterGauges.kicad_sch"),
}
# DRC categories that are documented and accepted on these boards.
ACCEPTED = {"lib_footprint_mismatch", "silk_edge_clearance", "silk_over_copper",
            "silk_overlap",
            "solder_mask_bridge(JP1/JP2 open jumpers, intended)"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in (0,):
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def drc_status(pcb, out_json):
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--output", out_json, pcb],
                   capture_output=True, text=True)
    d = json.load(open(out_json, encoding="utf-8"))
    by = {}
    for v in d.get("violations", []):
        if v["type"] == "solder_mask_bridge" and any(
                any(f"JP{n}" in it.get("description", "") for n in (1, 2))
                for it in v.get("items", [])):
            by["solder_mask_bridge(JP1/JP2 open jumpers, intended)"] = by.get(
                "solder_mask_bridge(JP1/JP2 open jumpers, intended)", 0) + 1
            continue
        by[v["type"]] = by.get(v["type"], 0) + 1
    unconnected = len(d.get("unconnected_items", []))
    return by, unconnected


def load_bom(board):
    path = os.path.join(ROOT, board, "build_bom.py")
    sys.path.insert(0, os.path.join(ROOT, board))
    spec = importlib.util.spec_from_file_location(f"bom_{board}", path)
    mod = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    os.chdir(os.path.join(ROOT, board))
    try:
        spec.loader.exec_module(mod)
        parts, lines = mod.build()
    finally:
        os.chdir(cwd)
        sys.path.pop(0)
    return parts, lines


def build_board(board):
    pcb_name, _ = BOARDS[board]
    bdir = os.path.join(ROOT, board)
    pcb = os.path.join(bdir, pcb_name)
    out = os.path.join(ROOT, "fab", board)
    gdir = os.path.join(out, "gerbers")
    os.makedirs(gdir, exist_ok=True)
    for f in os.listdir(gdir):
        os.remove(os.path.join(gdir, f))

    by, unconnected = drc_status(pcb, os.path.join(out, "drc.json"))
    unexpected = {k: v for k, v in by.items() if k not in ACCEPTED}
    if unconnected or unexpected:
        raise SystemExit(f"{board}: not fab-ready: {unconnected} unconnected items, "
                         f"unexpected DRC types {unexpected}")

    run([KICAD_CLI, "pcb", "export", "gerbers", "--output", gdir + os.sep,
         "--layers", LAYERS, "--subtract-soldermask", pcb])
    run([KICAD_CLI, "pcb", "export", "drill", "--output", gdir + os.sep,
         "--format", "excellon", "--excellon-units", "mm",
         "--excellon-zeros-format", "decimal", "--excellon-separate-th",
         "--generate-map", "--map-format", "gerberx2", pcb])

    zpath = os.path.join(out, f"{board}_fab.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            if f.lower().endswith((".pdf", ".rpt", ".gbrjob")) or "drl_map" in f:
                continue
            z.write(os.path.join(gdir, f), f)

    pos_raw = os.path.join(out, f"{board}_pos_raw.csv")
    run([KICAD_CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm",
         "--side", "both", "--smd-only", "--output", pos_raw, pcb])
    pos = os.path.join(out, f"{board}_pos.csv")
    with open(pos_raw, encoding="utf-8") as fi, open(pos, "w", newline="", encoding="utf-8") as fo:
        rd = csv.DictReader(fi)
        wr = csv.writer(fo)
        wr.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in rd:
            wr.writerow([r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                         "Top" if r["Side"] == "top" else "Bottom", r["Rot"]])
    os.remove(pos_raw)

    parts, lines = load_bom(board)
    fp_by_ref = {p["ref"]: p["package"] for p in parts}
    bompath = os.path.join(out, f"{board}_bom.csv")
    n_tbd = 0
    with open(bompath, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["Manufacturer Part Number", "Manufacturer", "Quantity", "Designators",
                     "Package", "Category", "Description", "Status"])
        for cat, mpn, mfr, desc, package, qty, refs, qual in lines:
            if qty == 0:
                continue
            status = "NEEDS PART SELECTION" if qual == "TBD" else (
                "PATTERN: confirm in cart" if "[PATTERN" in desc else "ok")
            n_tbd += qual == "TBD"
            wr.writerow([mpn, mfr, qty, refs, package, cat, desc, status])

    rep = [f"{board} fab package", f"  DRC: unconnected 0, accepted findings {by}",
           f"  parts {len(parts)}, BOM lines {sum(1 for l in lines if l[5])}, "
           f"lines needing part selection {n_tbd}",
           f"  gerbers: {sorted(os.listdir(gdir))}"]
    open(os.path.join(out, "report.txt"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    return zpath


def combine(boards):
    """One cart-ready list: same MPN on both boards is summed."""
    agg = {}
    for b in boards:
        with open(os.path.join(ROOT, "fab", b, f"{b}_bom.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                e = agg.setdefault(r["Manufacturer Part Number"], {
                    "mfr": r["Manufacturer"], "desc": r["Description"], "status": r["Status"],
                    "qty": {}, "refs": {}})
                e["qty"][b] = e["qty"].get(b, 0) + int(r["Quantity"])
                e["refs"][b] = r["Designators"]
    path = os.path.join(ROOT, "fab", "combined_bom.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["Manufacturer Part Number", "Manufacturer"] +
                    [f"Qty {b} (per board)" for b in boards] +
                    ["Description", "Status"])
        for mpn in sorted(agg):
            e = agg[mpn]
            wr.writerow([mpn, e["mfr"]] + [e["qty"].get(b, 0) for b in boards] +
                        [e["desc"], e["status"]])
    print(f"combined BOM: {len(agg)} distinct part numbers -> {path}")


if __name__ == "__main__":
    targets = sys.argv[1:] or list(BOARDS)
    for b in targets:
        build_board(b)
    if len(targets) > 1:
        combine(targets)
