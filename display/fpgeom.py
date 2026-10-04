"""Footprint loading/geometry and schematic ground-truth helpers shared by
build_pcb.py and the cell placer's preview (cells.py)."""
import os
import re
import subprocess

from kiutils.footprint import Footprint

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_FOOTPRINTS = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
PROJECT_FOOTPRINTS = os.path.join(HERE, "footprints")


def load_footprint(lib_colon_name):
    lib, _, name = lib_colon_name.partition(":")
    project_path = os.path.join(PROJECT_FOOTPRINTS, f"{lib}.pretty", f"{name}.kicad_mod")
    if os.path.isfile(project_path):
        path = project_path
    else:
        path = os.path.join(KICAD_FOOTPRINTS, f"{lib}.pretty", f"{name}.kicad_mod")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"footprint file not found: {path}")
    fp = Footprint.from_file(path)
    fp.libId = lib_colon_name
    return fp


def footprint_bbox(fp):
    """Bounding box from this footprint's pads AND silkscreen/courtyard
    graphics, in its own local (unplaced) coordinate frame."""
    xs, ys = [], []
    for pad in fp.pads:
        hw, hh = pad.size.X / 2, pad.size.Y / 2
        xs += [pad.position.X - hw, pad.position.X + hw]
        ys += [pad.position.Y - hh, pad.position.Y + hh]
    for item in fp.graphicItems:
        if hasattr(item, "start") and hasattr(item, "end"):
            xs += [item.start.X, item.end.X]
            ys += [item.start.Y, item.end.Y]
        elif hasattr(item, "coordinates"):
            xs += [p.X for p in item.coordinates]
            ys += [p.Y for p in item.coordinates]
        elif hasattr(item, "center"):
            r = ((item.end.X - item.center.X) ** 2 + (item.end.Y - item.center.Y) ** 2) ** 0.5
            xs += [item.center.X - r, item.center.X + r]
            ys += [item.center.Y - r, item.center.Y + r]
    if not xs:
        return (-2, -2, 2, 2)
    return (min(xs), min(ys), max(xs), max(ys))


def load_schematic(sch_path, kicad_cli, netlist_path):
    """Returns (parts, pad_net, net_names): parts is ref -> {footprint, value,
    uuid}, pad_net is (ref, pin) -> net name from kicad-cli's own netlist."""
    from kiutils.schematic import Schematic
    from kiutils.utils import sexpr

    sch = Schematic.from_sexpr(sexpr.parse_sexp(open(sch_path, encoding="utf-8").read()))
    parts = {}
    for inst in sch.schematicSymbols:
        ref = next(p.value for p in inst.properties if p.key == "Reference")
        if ref.startswith("#") or ref in parts:
            continue
        fp = next((p.value for p in inst.properties if p.key == "Footprint"), "")
        val = next((p.value for p in inst.properties if p.key == "Value"), "")
        parts[ref] = {"footprint": fp, "value": val, "uuid": inst.uuid}
    result = subprocess.run([kicad_cli, "sch", "export", "netlist", "--format", "kicadsexpr",
                             "--output", netlist_path, sch_path], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"netlist export failed: {result.stderr}")
    txt = open(netlist_path, encoding="utf-8").read()
    pad_net, net_names = {}, []
    for block in re.split(r"\(net\s", txt)[1:]:
        name = re.search(r'\(name "([^"]+)"\)', block).group(1).lstrip("/")
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)
        if len(nodes) < 2:
            continue
        net_names.append(name)
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name
    return parts, pad_net, net_names
