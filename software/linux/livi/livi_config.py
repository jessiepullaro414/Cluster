#!/usr/bin/env python3
"""LIVI settings for the cluster's round centre panel, written into LIVI's config.json.

    python3 livi_config.py --selftest
    python3 livi_config.py --print 0                     # the settings for map shape 0 as JSON
    python3 livi_config.py --apply ~/.config/LIVI/config.json --shape 2
    python3 livi_config.py --apply PATH --shape 0 --mfi-bus 1 --car-name "1966 Mustang"

Map shape (the dial's "Map shape" row, hmi.h: 0 round, 1 square, 2 4:3, 3 16:9):
  * round: the phone draws the whole 720 x 720 square (the corners are simply outside the round glass) and
    keeps its controls inside the largest square that fits the circle: the SAFE area (LIVI sends it as
    content insets to Android Auto and as the safe area to CarPlay).
  * square / 4:3 / 16:9: the picture is cut to the largest rectangle of that shape inside the circle: the
    VIEW area (LIVI turns it into video margins, black outside).

LIVI semantics are from its source (livi-aa-stack config.rs: "The view area becomes margins, the safe area
content insets"; a 720 x 720 screen on Android Auto's 1280 x 720 tier gets 560 px of width margin, so the
phone lays out a 720 x 720 content area). Checked against LIVI 9.5.0, 2026-10-17.

Also set: customHideNav (needs LIVI built with livi-round-ui.patch; a stock LIVI ignores it), the dial's keys (clusterd sends F13 / F14 / Enter + F15 / Backspace to LIVI's core; a click is selectDown then
selectUp, because LIVI passes Android Auto only the press of selectDown and the release comes from selectUp), the custom page
(clusterd's settings page), wireless Android Auto and CarPlay on, and optionally the I2C bus of the Apple
authentication coprocessor on display/ J16 (Verdin I2C_1; the Linux bus number depends on the device tree).
"""
import argparse
import json
import math
import os
import shutil
import sys

PANEL = 720                 # TSD TST040HDBC-42, 720 x 720 round (display/)
SHAPES = ("round", "square", "4:3", "16:9")
ASPECT = {1: 1.0, 2: 4 / 3, 3: 16 / 9}
PAGE_URL = "http://127.0.0.1:4010/"
KEYS = {"knobLeft": "F13", "knobRight": "F14", "selectDown": "Enter", "selectUp": "F15", "back": "Backspace"}


def even_up(x):
    """Round up to an even pixel count, so the rectangle never pokes outside the circle and video stays aligned."""
    n = math.ceil(x - 1e-9)
    return n + (n & 1)


def inscribed_insets(aspect, d=PANEL):
    """Insets (top, bottom, left, right) of the largest aspect-w:h rectangle inside a circle of diameter d."""
    w = d * aspect / math.sqrt(1 + aspect * aspect)
    h = d / math.sqrt(1 + aspect * aspect)
    lr, tb = even_up((d - w) / 2), even_up((d - h) / 2)
    return tb, tb, lr, lr


def settings_for(shape, mfi_bus=None, car_name=None):
    zero = (0, 0, 0, 0)
    if shape == 0:
        view, safe = zero, inscribed_insets(1.0)
    else:
        view, safe = inscribed_insets(ASPECT[shape]), zero
    s = {
        "projectionWidth": PANEL,
        "projectionHeight": PANEL,
        "projectionSafeAreaDrawOutside": True,
        "wirelessAaEnabled": True,
        "wirelessCpEnabled": True,
        "customUrl": PAGE_URL,
        "customHideNav": True,          # livi-round-ui.patch: no navigation rail over our round page
        # 120 instead of LIVI's 180: Android Auto lays itself out smaller, so its bottom bar fits the 508 px safe
        # square (at 180 two app icons were cut off, at 140 the outer two still were; checked on the bench)
        "projectionDpi": 120,
    }
    for name, v in (("View", view), ("Safe", safe)):
        for side, px in zip(("Top", "Bottom", "Left", "Right"), v):
            s[f"projection{name}Area{side}"] = px
    if mfi_bus is not None:
        s["carPlayMfiI2cBus"] = mfi_bus
        s["carPlayMfiPowerGpio"] = -1   # J16's MFI_RST_N is on Verdin GPIO_2, not LIVI's gpiochip0 power line; see README
    if car_name:
        s["carName"] = car_name
    return s


def apply(config, shape, mfi_bus=None, car_name=None):
    """Merge into a LIVI config dict; nested blocks (key bindings, custom page per screen) are merged, not replaced."""
    out = dict(config)
    out.update(settings_for(shape, mfi_bus, car_name))
    bindings = dict(out.get("bindings") or {})
    bindings.update(KEYS)
    out["bindings"] = bindings
    custom = dict(out.get("custom") or {"main": False, "cluster": False, "aux": False})
    custom["main"] = True
    out["custom"] = custom
    return out


def selftest():
    assert inscribed_insets(4 / 3) == (144, 144, 72, 72), inscribed_insets(4 / 3)       # 576 x 432 exactly
    assert inscribed_insets(1.0) == (106, 106, 106, 106), inscribed_insets(1.0)          # 509.1 -> 508
    assert inscribed_insets(16 / 9) == (184, 184, 48, 48), inscribed_insets(16 / 9)      # 627.5 x 353.0 -> 624 x 352
    for shape in (1, 2, 3):
        t, b, l, r = settings_for(shape)["projectionViewAreaTop"], settings_for(shape)["projectionViewAreaBottom"], \
                     settings_for(shape)["projectionViewAreaLeft"], settings_for(shape)["projectionViewAreaRight"]
        w, h = PANEL - l - r, PANEL - t - b
        assert math.hypot(w, h) <= PANEL, (shape, w, h)                                  # the corners are inside the glass
        assert settings_for(shape)["projectionSafeAreaTop"] == 0
    r0 = settings_for(0)
    assert r0["projectionViewAreaLeft"] == 0 and r0["projectionSafeAreaLeft"] == 106
    cfg = {"bindings": {"up": "ArrowUp", "back": "Escape"}, "custom": {"main": False, "cluster": True, "aux": False}, "darkMode": True}
    new = apply(cfg, 2, mfi_bus=1)
    assert new["bindings"] == {"up": "ArrowUp", "back": "Backspace", "knobLeft": "F13", "knobRight": "F14", "selectDown": "Enter",
                               "selectUp": "F15"}
    assert new["custom"] == {"main": True, "cluster": True, "aux": False} and new["darkMode"] is True
    assert new["carPlayMfiI2cBus"] == 1 and new["projectionViewAreaTop"] == 144
    assert new["customHideNav"] is True and new["projectionDpi"] == 120
    assert cfg["bindings"]["back"] == "Escape"   # the input is not modified
    print("livi_config selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--print", type=int, choices=range(4), metavar="SHAPE")
    ap.add_argument("--apply", metavar="CONFIG_JSON")
    ap.add_argument("--shape", type=int, choices=range(4), default=0)
    ap.add_argument("--mfi-bus", type=int)
    ap.add_argument("--car-name")
    ap.add_argument("shape_arg", nargs="?", type=int, help="the shape as a bare number (how clusterd's map_shape_cmd calls it)")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    shape = a.shape_arg if a.shape_arg is not None else a.shape
    if a.print is not None:
        print(json.dumps(settings_for(a.print, a.mfi_bus, a.car_name), indent=2))
        return
    if not a.apply:
        ap.error("one of --selftest, --print or --apply")
    path = os.path.expanduser(a.apply)
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        shutil.copyfile(path, path + ".before-cluster")
    new = apply(cfg, shape, a.mfi_bus, a.car_name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)
    os.replace(tmp, path)
    print(f"{path}: map shape {SHAPES[shape]}; restart LIVI (or reconnect the phone) for the projection to pick it up")


if __name__ == "__main__":
    sys.exit(main())
