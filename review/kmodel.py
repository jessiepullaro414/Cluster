"""
kmodel.py - read a generated KiCad board the way the review scripts need it.

Two views of one board:
  * Netlist  - from `kicad-cli sch export netlist --format kicadxml` (what the
               schematic says is connected to what, including the symbol's pin
               names and electrical types).
  * Layout   - from the .kicad_pcb with kiutils (absolute pad positions, nets
               per pad, tracks), so a check can ask "how far is this capacitor
               from that supply pin" or "does anything slow run under the switch
               node".

Nothing here edits a KiCad file. The generated files stay script-owned (see
RUNNING.md section 9); the review only reads them.
"""
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from passive_catalog import to_number  # noqa: E402  (value-token parser used by both BOMs)


def find_kicad_cli():
    exe = shutil.which("kicad-cli")
    if exe:
        return exe
    for c in (r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
              r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"):
        if os.path.isfile(c):
            return c
    raise SystemExit("kicad-cli not found")


def value_of(value_str):
    """Numeric value from a schematic Value field such as '100nF X7R ...',
    '80.6k 1% RILIM', '2.49k (AEC-Q200)'. None when the field is a part name."""
    tok = value_str.split()[0] if value_str.split() else ""
    return to_number(tok)


class Node:
    __slots__ = ("ref", "pin", "func", "ptype")

    def __init__(self, ref, pin, func, ptype):
        self.ref, self.pin, self.func, self.ptype = ref, str(pin), func, ptype

    def __repr__(self):
        return f"{self.ref}.{self.pin}"


class Netlist:
    def __init__(self, sch_path):
        self.sch_path = sch_path
        out = os.path.join(tempfile.gettempdir(), "review_netlist_%d.xml" % abs(hash(sch_path)))
        r = subprocess.run([find_kicad_cli(), "sch", "export", "netlist", "--format", "kicadxml",
                            "-o", out, sch_path], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("netlist export failed: " + r.stderr)
        root = ET.parse(out).getroot()
        self.comps = {}          # ref -> dict(value, footprint, libpart)
        for c in root.find("components"):
            ls = c.find("libsource")
            self.comps[c.get("ref")] = dict(value=c.findtext("value") or "",
                                            footprint=c.findtext("footprint") or "",
                                            libpart=ls.get("part") if ls is not None else "")
        self.libpins = {}        # libpart -> {pin: (name, type)}
        lp = root.find("libparts")
        if lp is not None:
            for p in lp:
                d = {}
                pins = p.find("pins")
                if pins is not None:
                    for pin in pins:
                        d[pin.get("num")] = (pin.get("name"), pin.get("type"))
                self.libpins[p.get("part")] = d
        self.nets = {}           # name -> [Node]
        self.pinnet = {}         # (ref, pin) -> net name
        for n in root.find("nets"):
            name = n.get("name").lstrip("/")
            nodes = [Node(x.get("ref"), x.get("pin"), x.get("pinfunction"), x.get("pintype"))
                     for x in n.findall("node")]
            self.nets[name] = nodes
            for nd in nodes:
                self.pinnet[(nd.ref, nd.pin)] = name

    # --- queries -----------------------------------------------------------
    def net_of(self, ref, pin):
        return self.pinnet.get((ref, str(pin)))

    @staticmethod
    def is_nc_net(name):
        return name is None or name.startswith("unconnected-")

    def symbol_pins(self, ref):
        """{pin: (symbol pin name, type)} for the symbol placed as `ref`."""
        return self.libpins.get(self.comps[ref]["libpart"], {})

    def parts_on(self, net, prefix=None):
        return [nd for nd in self.nets.get(net, []) if prefix is None or nd.ref.startswith(prefix)]

    def two_pin_between(self, net_a, net_b, prefix):
        """2-terminal parts of reference prefix `prefix` with one pin on net_a
        and the other on net_b. Returns [(ref, value_float)]."""
        res = []
        refs_a = {nd.ref for nd in self.nets.get(net_a, []) if nd.ref.startswith(prefix)}
        refs_b = {nd.ref for nd in self.nets.get(net_b, []) if nd.ref.startswith(prefix)}
        for ref in sorted(refs_a & refs_b):
            res.append((ref, value_of(self.comps[ref]["value"])))
        return res

    def other_net(self, ref, net):
        """For a 2-pin part, the net on its other pin."""
        nets = [self.pinnet.get((ref, p)) for p in ("1", "2")]
        if nets[0] == net and nets[1] != net:
            return nets[1]
        if nets[1] == net and nets[0] != net:
            return nets[0]
        return None


# ---------------------------------------------------------------------------
def rot_xy(x, y, a):
    """KiCad file rotation (positive = counter-clockwise on screen, y down)."""
    a = math.radians(a)
    c, s = math.cos(a), math.sin(a)
    return (x * c + y * s, -x * s + y * c)


class Layout:
    """Pads, tracks and vias of a .kicad_pcb, read with a plain s-expression walk
    (kiutils 1.4.8 cannot parse the pad (net "name") form KiCad 10 writes)."""

    def __init__(self, pcb_path):
        from kiutils.utils import sexpr
        with open(pcb_path, encoding="utf-8") as f:
            tree = sexpr.parse_sexp(f.read())
        self.pads = {}           # (ref, pad) -> [dict(x, y, net, layers, w, h)]
        self.fp = {}             # ref -> (x, y, angle, footprint name)
        self.tracks = []         # dict(net, layer, width, x1, y1, x2, y2)
        self.vias = []           # dict(net, x, y, size, drill)
        self.edge = []           # Edge.Cuts segment endpoints
        self.zones = []          # dict(net, layers)
        for it in tree:
            if not isinstance(it, list) or not it:
                continue
            tag = it[0]
            if tag == "footprint":
                self._footprint(it)
            elif tag == "segment":
                d = self._kv(it)
                self.tracks.append(dict(net=self._first(d, "net"), layer=self._first(d, "layer"), width=float(self._first(d, "width", 0)),
                                        x1=float(d["start"][0]), y1=float(d["start"][1]),
                                        x2=float(d["end"][0]), y2=float(d["end"][1])))
            elif tag == "via":
                d = self._kv(it)
                self.vias.append(dict(net=self._first(d, "net"), x=float(d["at"][0]), y=float(d["at"][1]),
                                      size=float(d["size"][0]), drill=float(d["drill"][0])))
            elif tag == "gr_line":
                d = self._kv(it)
                if self._first(d, "layer") == "Edge.Cuts":
                    self.edge += [(float(d["start"][0]), float(d["start"][1])), (float(d["end"][0]), float(d["end"][1]))]
            elif tag == "zone":
                d = self._kv(it)
                filled = []      # (layer, [(x, y), ...]) per filled_polygon, as KiCad fractures them
                for ch in it:
                    if isinstance(ch, list) and ch and ch[0] == "filled_polygon":
                        fd = self._kv(ch)
                        pts = [(float(p[1]), float(p[2])) for p in fd.get("pts", []) if isinstance(p, list) and p and p[0] == "xy"]
                        filled.append((self._first(fd, "layer"), pts))
                self.zones.append(dict(net=self._first(d, "net"), layers=d.get("layers") or d.get("layer"), filled=filled))

    @staticmethod
    def _kv(item):
        """{key: value or [values]} for the direct children of an s-expression item."""
        d = {}
        for ch in item[1:]:
            if isinstance(ch, list) and ch and not isinstance(ch[0], list):
                k = str(ch[0])
                rest = ch[1:]
                d[k] = rest
        return d

    @staticmethod
    def _first(d, key, default=None):
        v = d.get(key)
        return v[0] if v else default

    def _footprint(self, it):
        d = self._kv(it)
        at = d.get("at", [0, 0, 0])
        x, y = float(at[0]), float(at[1])
        ang = float(at[2]) if len(at) > 2 else 0.0
        ref = None
        for ch in it:
            if isinstance(ch, list) and ch and ch[0] == "property" and len(ch) > 2 and ch[1] == "Reference":
                ref = ch[2]
        if ref is None:
            return
        self.fp[ref] = (x, y, ang, str(it[1]))
        for ch in it:
            if isinstance(ch, list) and ch and ch[0] == "pad":
                pd = self._kv(ch)
                pat = pd.get("at", [0, 0])
                dx, dy = rot_xy(float(pat[0]), float(pat[1]), ang)
                size = pd.get("size", [0, 0])
                layers = pd.get("layers", [])
                self.pads.setdefault((ref, str(ch[1])), []).append(
                    dict(x=x + dx, y=y + dy, net=self._first(pd, "net"), layers=layers,
                         w=float(size[0]), h=float(size[1])))

    def pad_xy(self, ref, pin):
        lst = self.pads.get((ref, str(pin)))
        if not lst:
            return None
        return lst[0]["x"], lst[0]["y"]

    def dist(self, a, b):
        pa, pb = self.pad_xy(*a), self.pad_xy(*b)
        if pa is None or pb is None:
            return None
        return math.hypot(pa[0] - pb[0], pa[1] - pb[1])

    def board_bbox(self):
        xs = [p[0] for p in self.edge]
        ys = [p[1] for p in self.edge]
        return min(xs), min(ys), max(xs), max(ys)
