# Harness: every connector that carries a wire off display/ and gauges/ (decided 2026-10-17)

## The decision

**Sealed Deutsch DTM06 plugs on the vehicle end of short pigtails; compact header connectors on the boards.** No sealed connector is mounted on either board. Board-to-board links inside the dash are plain KK 254 cables with no Deutsch connector.

### display/

| Ref | Board side (already on the board) | Pigtail / cable | Wire | Pins |
|---|---|---|---|---|
| **J2** battery, ground, ignition. On brain/'s right edge since 2026-11-06, wire mouth facing out | Phoenix MKDS 1,5/3-5,08 (1715734), 3-position screw terminal | wire ferruled into the terminal; **DTM06-3S** plug + WM-3S on the car end | 20 AWG GXL | 1 VBAT, 2 GND, 3 IGN sense |
| **J3** private CAN link | Molex KK 254 22-27-2031, 3-circuit | Molex KK 254 housing 22-01-3037 with crimps at **both ends**, no DTM | 22 AWG twisted pair + ground | to gauges/ J8, same part: 1 CAN H, 2 CAN L, 3 GND |
| **J8**, **J9** (and J12, J13) | Samtec 0.1 in headers | none: bench only | | JTAG; power/recovery/reset buttons (J12 console UART, J13 USB) |

### gauges/

| Ref | Board side | Pigtail / cable | Wire | Pins |
|---|---|---|---|---|
| **J1** battery, ground, ignition | Phoenix MKDS 1,5/3-5,08, 3-position screw terminal | wire ferruled into the terminal; **DTM06-3S** + WM-3S | 20 AWG GXL | 1 VIN, 2 GND, 3 IGN |
| **J7** car CAN + three senders | Molex KK 254 22-27-2051, 5-circuit | **DTM06-6S** + WM-6S (**no 5-way DTM exists**: DTM comes in 2, 3, 4, 6, 8 and 12 ways, so one cavity takes a sealing plug) | 22 AWG GXL; CAN H and L as a twisted pair | 1 CAN0 H, 2 CAN0 L, 3 fuel sender, 4 oil sender, 5 coolant sender |
| **J9** Hall speed | Molex KK 254 22-27-2031, 3-circuit | **DTM06-3S** + WM-3S | 22 AWG GXL | 1 signal, 2 GND, 3 switched 12 V for the sender (VPULL: on only while the board is awake, 148 mA current limit; review 2026-11-03) |
| **J10** lamps and dimmer | Molex KK 254 22-27-2081, 8-circuit | **DTM06-08SA** + WM-8S | 22 AWG GXL | 1 left turn, 2 right turn, 3 high beam, 4 brake, 5 alternator, 6 oil, 7 GND, 8 dimmer feed |
| **J11** tach | Molex KK 254 22-27-2021, 2-circuit | **DTM06-2S** + WM-2S | 22 AWG GXL | 1 tach signal, 2 GND |
| **J12** VR speed (2026-11-04) | Molex KK 254 22-27-2021, 2-circuit | **DTM06-2S** + WM-2S, only on a car with a two-wire VR sensor | 22 AWG GXL twisted pair | 1 sensor wire, 2 sensor wire (either way round; neither is ground) |
| **J8** private CAN link | Molex KK 254 22-27-2031, 3-circuit | the same KK cable as display/ J3 | 22 AWG twisted pair + ground | 1 CAN1 H, 2 CAN1 L, 3 GND |

The senders (J7 pins 3 to 5) are single-wire: their return is the sender's own body, so the car chassis must be a good ground at each sender. The lamp and Hall wires are 12 V signals of a few milliamps; the power wires are fused at the battery end.

## Installing in a car with the stock wiring (review 2026-11-03)

- **Grounds.** Take both boards' ground wires (gauges J1 pin 2, brain J2 pin 2) to one stud under the dash, and run a dedicated ground wire (12 AWG or heavier) from that stud to the engine block, as aftermarket gauge makers ask. The senders return through the engine block (oil, coolant) and the tank and body (fuel); the body-to-engine strap carries every body load's return current, so the two grounds commonly sit tens to hundreds of millivolts apart. The gauges firmware measures each sender with its excitation on and off and cancels that offset (`software/gauges-fw/src/senders.c`), down to about -480 mV; beyond that a sender shows no reading. A good ground keeps it well inside that range.
- **The stock ALT (ammeter) gauge.** The 1966 gauge is a shunt ammeter: the charging current stays in the harness and two small wires carry the shunt's voltage to the gauge. Both sit at battery voltage. The cluster shows battery volts instead (the owner's decision, 2026-11-04: every one of these cars gets a voltmeter), so cap and insulate both wires (do not join them to anything); the charging circuit itself is not affected.
- **The old instrument voltage regulator** was part of the stock cluster. The senders connect straight to J7; nothing replaces the regulator.
- **Constant battery feed.** The stock cluster has only ignition-switched feeds. J1 pin 1 (gauges) and J2 pin 1 (brain) need a new fused battery wire (fuse at the battery end, docs above); pin 3 of each takes the ignition feed.
- **Dash lights (J10 pin 8).** Connect the instrument-lamp feed from the headlight switch to pin 8. Nothing else goes on that circuit: no resistor and no leftover bulb, though radio, heater-control and clock lamps can stay (owner's decision, 2026-11-04). The switch dims through a rheostat, which only drops voltage while current flows, so with the stock cluster's bulbs gone the board draws the current itself to read the knob: about 40 mA for 10 ms, four times a second, only with the key and the lights on. Incandescent lamps left on the circuit will not show it. An LED bulb on a rheostat might show a faint 4 Hz flicker with the knob well down; check that if any are fitted. **One thing to measure:** the firmware takes 12 ohm as the rheostat's full value (`IM_DIM_RHEO_FULL_OHM`, `inputmath.h`), which is an estimate, because no figure for this switch was found. Disconnect the battery, set the knob to its dimmest, and read the ohms from the switch's battery terminal to its instrument-lamp terminal. With a lower value the lowest setting stays above 0 %; with a higher one the screens reach 0 % before the end of the knob's travel.
- **Warning lamps (J10 pins 1-6).** Inputs are 12 V-active. A lamp that is switched to ground (an oil-pressure or brake-warning switch) needs its DNP 4.7 k pull-up fitted (R60-R75, to VPULL, which is off with the car off). On a car whose alternator regulator is excited through its warning lamp (a Ford 3G conversion, or a 1967-on car with a charge lamp), the lamp's current is what turns the regulator on: keep a 500 ohm, 1 W resistor in that circuit from the ignition feed when the bulb is removed, or the alternator will not charge.
- **Car CAN bus termination.** The board carries a 120 ohm split terminator (R4/R5) that is switched in by bridging the solder jumpers JP1 and JP2. Bridge both when the cluster is one end of the bus (a two-node ECU + cluster bus usually is); leave them open on a longer bus that already has its two terminators.
- **Speed sensor: one or the other, nothing to set.** J9 powers a three-wire Hall sender (12 V supply, ground, signal) from pin 3. J12 takes a two-wire variable-reluctance sensor directly (4R70W, AOD-E and some T56 transmissions; owner's decision, 2026-11-04): no converter box. Either way round; run the pair twisted and away from ignition leads. The firmware uses whichever input is reporting; set the sensor's pulses per mile on the display as for a Hall sender (Ford's speed signal is commonly quoted at 8000 per mile, but tyres and axle ratio change it, so calibrate against GPS). **A sensor shared with a PCM or a transmission controller** can stay connected to it: tap both wires and ground neither. Each wire sees 47 k into the board and under 1 uA, so the other unit should not notice, but check it on the first car. If only one wire can be reached, take J12 pin 2 to ground instead; the threshold rises from about 110 mV to about 200 mV peak.
- **Tach.** J11 takes an ECU or ignition-box tach output (12 V square wave) or a points/electronic coil's negative terminal. The input filter and firmware blanking reject the coil's ringing after each spark; check the reading against a timing light's tach on the first car.

## Why

- **Why no sealed header on a board.** TE's board-mount DTM header with enough pins is the 12-way DTM13-12PA: right angle, 4.19 mm centre line, 2 rows, 61 x 37 mm, 25.7 mm tall, with its own screw mounts, IP67/IP6K9K, -55 to 125 C ([TE listing](https://www.te.com/en/product-DTM13-12PA-R008.html), [TE drawing of its 24-way sibling](https://datasheet.octopart.com/DTM13-12PA-12PB-R008-TE-Connectivity-datasheet-180428408.pdf)). That is about an eighth of the display board for three power wires, and the smaller DTM06/DTM04 housings are wire-to-wire only (found for thermo/ on 2026-08-10). I could not get a footprint drawing for the 12-way and did not guess one. If a sealed header ever becomes a requirement, download TE's footprint and 3D model and redo the floorplan around it.
- **J3/J8 have no DTM.** The BOM called display J3 "the CAN tap to the ECU": wrong, the display is on the private link only (gauges/ is the gateway, `software/PLAN.md`). The link joins two boards inside one dash, where nothing needs sealing.
- **Wire sizes come from the two crimps that meet in a pigtail.**
  - Molex's KK 254 crimp terminal (08-50-0113 / 08-50-0114, tin) takes **22 to 30 AWG** and nothing thicker ([Digi-Key](https://www.digikey.com/en/products/detail/08-50-0114/WM1114-ND/26475), [RS](https://au.rs-online.com/web/p/products/1729178)).
  - The DEUTSCH size-20 solid socket contact **0462-201-20141** (nickel, indent crimp, 7.5 A typical, TE confirms the part, [TE page](https://www.te.com/en/product-0462-201-20141.html)) is shown in TE's application specification 114-151004 crimped on **20 AWG GXL**, and the specification lists the HDT-50-00 hand tool for 12-20 AWG and the HDT-48-00 for 12-22 AWG. The contact's own permitted wire range is on its customer drawing, which I could not retrieve; resellers quote 16-20, 18-20, 20-22, 22-18 and 24-20 AWG for it.
  - So **22 AWG is the one size both could take**, and it is not confirmed for the DTM contact. Before ordering any quantity, crimp one DTM contact on 22 AWG GXL with an HDT-48-00 and pull-test it (the wire must show in the inspection hole). If the contact will not hold it, the board end of those pigtails has to change: a screw terminal like J1 (takes 20 AWG), not a KK header, which means a layout change.
  - The power pigtails (J1, J2) avoid the question: 20 AWG GXL is TE's own nominal wire for the contact, it fits the MKDS terminal (26-14 AWG; 0.25-1.5 mm^2 with a ferrule, [Phoenix figures as listed by Farnell](https://uk.farnell.com/phoenix-contact/1715734/terminal-block-wire-to-brd-3pos/dp/3041530)), and it carries several amps easily.
- **Fusing.** F1 on each board protects the board, not the wire up to it. Fuse each power feed at the battery end: 5 A or less for display/, 3 A or less for gauges/ (its own fuse is 2 A and it draws about 0.3 A).
- **Honest limit.** The DTM04 receptacle side that the plugs mate with is not designed here: the car-side lead and where the feeds are tapped belong to the car's wiring.

## What to buy

| For | Part | Qty |
|---|---|---|
| Each DTM plug | TE DEUTSCH plug housing: DTM06-3S (display J2, gauges J1, gauges J9), DTM06-6S (gauges J7), DTM06-2S (gauges J11, and J12 on a car with a VR sensor), DTM06-08SA (gauges J10) | 2 + 1 + 2 + 1 for gauges, 1 for display |
| | wedge lock for each plug: WM-3S, WM-6S, WM-2S, WM-8S (listed as WM-8S for the 8-way DTM plug; W8S is the DT-series part, so check the fit) | one per housing |
| | DEUTSCH size-20 solid socket contact 0462-201-20141 | 3 + 3 (display J2, gauges J1) + 5 (J7) + 3 (J9) + 2 (J11) + 2 (J12) + 8 = 26, plus spares |
| | DTM size-20 sealing plug for the unused cavity of the DTM06-6S (0413-204-2005 is the usual number; confirm) | 1, plus a few for spare cavities |
| | mating DTM04-nP receptacle + WM-nP wedge, only if the car-side lead is built too | |
| Power pigtails | 20 AWG GXL wire in 3 colours; ferrules for 0.5 mm^2 (Phoenix AI 0,5 series) | about 0.5 m each; 3 per pigtail |
| KK 254 ends | housings 22-01-3027 (2), -3037 (3), -3057 (5), -3087 (8) (the 22-01-30x7 pattern is Molex's friction-ramp crimp housing; confirm each number) | 2-way for J11 and J12; 3-way for J9, J3 and J8 (one each); 5-way for J7; 8-way for J10 |
| | crimp terminal 08-50-0113 or 08-50-0114 (22-30 AWG; one distributor lists 0114 obsolete: check stock) | 23 at the gauges end (J7 5, J9 3, J10 8, J11 2, J12 2, J8 3) and 3 at the display end of the J3/J8 cable, plus spares |
| Signal wire | 22 AWG GXL, several colours; 22 AWG twisted pair for CAN | by the metre |
| Tools | a crimper for DEUTSCH size 20 (TE HDT-48-00) and a KK 254 crimper for the Molex terminals | |

## Not covered

- brain/ also has the dial header J11 (KK 254), the audio headers J14/J15 (JST XH), the USB-C ports J17 and J19 and the panel flex connector J4. All are in the dash; none uses a sealed connector.
- The board BOMs still carry the older wording: gauges/ names a **DTM06-5S** (which does not exist; J7 needs the 6S) and an older DTM06-3S pigtail note on J8. Those lines live in `gauges/build_bom.py` and `build_schematic.py`, which have uncommitted changes from the electrical review, so they are listed here rather than patched; display/'s BOM is updated.
