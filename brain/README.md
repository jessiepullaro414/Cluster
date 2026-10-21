# brain: the centre-screen board, the same in every car

The Toradex Verdin iMX95 carrier that runs the centre screen, with everything
that does not depend on the car or the panel: the 12 V input and surge
protection (LM74930-Q1), the 5 V buck, the 1.8 V rail, the ignition wake and
sleep control, the private CAN link to the gauges board, the audio codec and
its connectors, the USB-C host port, the MFi daughterboard header, the dial
input and the bench headers.

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
