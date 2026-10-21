# panel-tsd: panel board for the TSD TST040HDBC-42

A small board that sits behind the Team Source Display TST040HDBC-42 (4.0 in
round, 720 x 720, 800 nits, native MIPI DSI) and carries everything that belongs
to that panel:

* J4, the panel's 39-pin FPC connector (Hirose FH26-39S, inferred: the panel
  datasheet does not name one);
* U6, the TPS65131-Q1 bias supply, set to +5.98 V / -6.05 V (inside the ICNL9707
  driver's 4.5 to 6.5 V range), with the open polarity jumpers JP1/JP2 because the
  panel datasheet's table and drawing disagree on which pins take which rail;
* U7, the TPS61165-Q1 backlight boost, 182 mA into the panel's 15 V LED string;
* J1, the input from the brain board's screen port A (Hirose FH12-40S, same pin
  order, [docs/screen-ports.md](../docs/screen-ports.md)), and R1, the 2.0 k
  panel-ID resistor.

The circuits are display/'s, moved here unchanged (same designators). Before
bridging JP1/JP2, check the real panel with a meter's diode test
(`fab/README.md`).

The DSI pairs (three lanes and the clock) are autorouted on F.Cu and B.Cu only,
the two layers right above a solid GND plane, at 0.16 mm: each leg is about 52
ohm on its own, so a pair stays near 100 ohm even where the router separates its
legs. They have to cross on the way (the port carries each pair N then P in the
Verdin's lane order, the panel FPC P then N in its own), so the router uses a few
vias. `route_board.py` prints each leg's length and the skew inside each pair.

Six layers (JLC06161H-3313), the same stack-up as the brain board.

Build: `python build_schematic.py`, `python build_pcb.py`, `python route_board.py`,
`python ../run_drc.py ClusterPanelTSD.kicad_pcb`, `python build_bom.py`,
`python ../review/layout_checks.py panel-tsd`, `python ../review/review_netlist.py panel-tsd`.
