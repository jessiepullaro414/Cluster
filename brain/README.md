# brain: the centre-screen board, the same in every car

The Toradex Verdin iMX95 carrier that runs the centre screen, with everything
that does not depend on the car or the panel: the 12 V input and surge
protection (LM74930-Q1), the 5 V buck, the 1.8 V rail, the ignition wake and
sleep control, the private CAN link to the gauges board, the audio codec and
its connectors, two USB-C host ports (J17 on USB_2 and, since 2026-11-06, J19
on USB_1; [docs/audio-and-usb.md](../docs/audio-and-usb.md)), the MFi daughterboard
header, the dial input and the bench headers.

Power (review 2026-11-03, `docs/electrical-review.md` section 9): the
ignition switches the board on through the LM74930's EN pin, and the
module's CTRL_PWR_EN_MOCI holds it on while the module is on or suspended.
So the key starts the module from any state (it boots whenever VCC
appears), and once software powers the module off with the key off, the
board draws only the LM74930's 2.5 uA shutdown current. How long to stay
suspended before powering off is a software setting.

It started as a copy of `display/` (now `archive/display-1966/`, the 1966
Mustang's one-panel carrier). The panel connector, the panel's bias supply,
its polarity jumpers and its backlight driver moved to the panel's own board
(`panel-tsd/`). In their place are two screen ports:

| Port | Ref | Video | Connector |
|---|---|---|---|
| A | J4 | MIPI DSI, 4 lanes + clock | Hirose FH12-40S, 40 contacts |
| B | J18 | LVDS0 + LVDS1 (one single- or dual-link panel) | Hirose FH12-50S, 50 contacts |

Each port has its own current-limited 5 V switch (U6, U7: TPS2557-Q1, 1.61 to
1.98 A), panel reset / enable / backlight-PWM lines held low until software
drives them, an I2C bus, and an analog panel-ID pin. The pin tables and the
rules for a panel board are in [docs/screen-ports.md](../docs/screen-ports.md),
generated from `tools/screen_ports.py`, which this board and every panel board
are built from.

The pairs from the Verdin socket to each port are planned, not autorouted
(`fan_route.py`): straight on F.Cu over the In1 GND plane, 0.16 mm, with GND
guard tracks where the socket has a ground pin between pairs and no length
difference inside a pair. The autorouter is fenced out of both corridors.

Build: `python build_schematic.py`, `python build_pcb.py`, `python route_board.py`,
`python ../run_drc.py ClusterBrain.kicad_pcb`, `python build_bom.py`,
`python ../review/layout_checks.py brain`, `python ../review/review_netlist.py brain`.

Not known yet: whether the Verdin iMX95 drives DSI and LVDS as two independent
screens at once (the i.MX 95 itself can; question 9 in `docs/rfq-drafts.md`
section 2), and Hirose's per-contact rating and contact side for the FH12 (the
design assumes 0.5 A).
