"""Read a KiCad STEP export into named parts with bounding boxes (OCP XCAF)."""
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopLoc import TopLoc_Location


def _name(label):
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def read_parts(path):
    """Return [(name, TopoDS_Shape located in board coords)] for every top-level component."""
    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    assert r.ReadFile(path) == 1, path
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    out = []

    def walk(label, loc, depth):
        if st.IsAssembly_s(label):
            kids = TDF_LabelSequence()
            st.GetComponents_s(label, kids)
            for i in range(1, kids.Length() + 1):
                c = kids.Value(i)
                ref = c
                sub_loc = loc.Multiplied(st.GetLocation_s(c))
                if st.IsReference_s(c):
                    from OCP.TDF import TDF_Label
                    ref = TDF_Label()
                    st.GetReferredShape_s(c, ref)
                if depth == 0:
                    out.append((_name(c) or _name(ref), st.GetShape_s(ref).Moved(sub_loc)))
                else:
                    walk(ref, sub_loc, depth + 1)
        else:
            out.append((_name(label), st.GetShape_s(label).Moved(loc)))

    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), 0)
    return out


def bbox(shape):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b, True)
    return b.Get()


if __name__ == "__main__":
    import sys
    for n, s in read_parts(sys.argv[1]):
        x0, y0, z0, x1, y1, z1 = bbox(s)
        print(f"{n:30s} x {x0:8.2f}..{x1:8.2f} y {y0:8.2f}..{y1:8.2f} z {z0:6.2f}..{z1:6.2f}")
