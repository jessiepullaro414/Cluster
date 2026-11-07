#!/usr/bin/env python3
"""
make_cnsw_footprint.py - the land pattern of the Wurth WE-CNSW 0603 common-mode choke, written into brain/footprints/.

KiCad's library has the 1206 WE-CNSW but not this size. Everything here is from Wurth's datasheet for 744230900 (rev 002.010),
page 1: body 1.6 x 0.85 mm, pads 0.85 x 0.25 mm with a 0.60 mm gap along the line and 0.25 mm between the lines, so the two
lines sit 0.5 mm apart, centre to centre. That's the USB_1 pair's own pitch (brain/usb_route.py), so the pair runs straight
through the part. Winding 4-3 is the line at -y and winding 1-2 the line at +y, with the dots at 4 and 1. Each winding runs along
the part's length, and the part is the same turned 180 degrees, so nothing depends on which way it's fitted.
(Page 2's test figure draws 1-4 and 2-3 across its DUT box. That's a generic drawing: page 1's schematic and outline agree with
each other. Check it with a meter on the first reel: 1-2 and 3-4 read a fraction of an ohm, 1-4 reads open.)

    python tools/make_cnsw_footprint.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = "Wurth_CMC"
NAME = "L_CommonMode_Wurth_WE-CNSW-0603"
PAD_X, PAD_Y = 0.725, 0.25        # pad centres: 0.60 gap + 0.85 pad
PAD_W, PAD_H = 0.85, 0.25
BODY_X, BODY_Y = 0.8, 0.425
COURT_X, COURT_Y = 1.3, 0.6
PADS = (("1", -PAD_X, PAD_Y), ("2", PAD_X, PAD_Y), ("3", PAD_X, -PAD_Y), ("4", -PAD_X, -PAD_Y))


def rect(x, y, layer, width):
    return (f'\t(fp_rect\n\t\t(start {-x} {-y})\n\t\t(end {x} {y})\n\t\t(stroke\n\t\t\t(width {width})\n\t\t\t(type solid)\n\t\t)\n'
            f'\t\t(fill no)\n\t\t(layer "{layer}")\n\t)\n')


def prop(name, value, y, layer, hide=False):
    h = "\t\t(hide yes)\n" if hide else ""
    return (f'\t(property "{name}" "{value}"\n\t\t(at 0 {y} 0)\n\t\t(layer "{layer}")\n{h}'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def main():
    s = (f'(footprint "{NAME}"\n\t(version 20260206)\n\t(generator "make_cnsw_footprint")\n\t(generator_version "10.0")\n\t(layer "F.Cu")\n'
         '\t(descr "Wurth WE-CNSW 0603 common-mode line filter, land pattern from datasheet 744230900 rev 002.010")\n'
         '\t(tags "common mode choke USB 2.0 AEC-Q200")\n')
    s += prop("Reference", "REF**", -1.4, "F.SilkS")
    s += prop("Value", NAME, 1.5, "F.Fab")
    s += prop("Datasheet", "https://www.we-online.com/components/products/datasheet/744230900.pdf", 0, "F.Fab", hide=True)
    s += prop("Description", "", 0, "F.Fab", hide=True)
    s += '\t(attr smd)\n\t(duplicate_pad_numbers_are_jumpers no)\n'
    s += rect(COURT_X, COURT_Y, "F.CrtYd", 0.05)
    s += rect(BODY_X, BODY_Y, "F.Fab", 0.1)
    for n, x, y in PADS:
        s += (f'\t(pad "{n}" smd rect\n\t\t(at {x} {y})\n\t\t(size {PAD_W} {PAD_H})\n'
              f'\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n\t)\n')
    s += '\t(embedded_fonts no)\n)\n'
    d = os.path.join(ROOT, "brain", "footprints", f"{LIB}.pretty")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{NAME}.kicad_mod"), "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print("wrote", NAME)


if __name__ == "__main__":
    main()
