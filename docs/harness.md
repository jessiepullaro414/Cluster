# Harness connectors for display/ (decided 2026-10-17)

Scope: the connectors on the display board that carry a wire off the board. The gauges board needs the same pass (see "Not covered" below).

## The decision

**Sealed Deutsch DTM06 plugs on the vehicle end of short pigtails; compact header connectors on the board.** No sealed connector is mounted on the display board. J3 is not a vehicle-harness connector at all.

| Ref | Board side (part already on the board) | What plugs in | Wire | Where it goes |
|---|---|---|---|---|
| **J2** | Phoenix MKDS 1,5/3-5,08 (1715734), 3-position screw terminal | pigtail with the wire ferruled into the terminal, DTM06-3S plug on the car end | 18 AWG automotive wire (TXL/GXL class) | car harness: pin 1 VBAT (switched or constant battery, see note), pin 2 GND, pin 3 IGN sense |
| **J3** | Molex KK 254 22-27-2031, 3-circuit | Molex KK 254 housing 22-01-3037 with crimp terminals, **both ends**, no DTM | 22 AWG twisted pair plus a ground wire | gauges/ J8, the same part: pin 1 CAN H, pin 2 CAN L, pin 3 GND. Short, inside the dash |
| **J8** | Samtec TSW-108-07-G-S, 1x8 0.1 in | nothing in the car | | bench only: JTAG |
| **J9** | Samtec TSW-104-07-G-S, 1x4 0.1 in | nothing in the car | | bench only: power, recovery, reset buttons |

(J8 and J9 never see a harness: leave them unpopulated on a production unit or cover them behind the service flap. J12 and J13 are bench headers of the same kind.)

## Why

- **Why not a sealed header on the board.** TE's board-mount DTM header with enough pins is the 12-way DTM13-12PA: right angle, 4.19 mm centre line, 2 rows, 61 x 37 mm footprint, 25.7 mm tall, with its own screw mounts, 7.5 A per contact, IP67/IP6K9K, -55 to 125 C ([TE listing](https://www.te.com/en/product-DTM13-12PA-R008.html), [customer drawing of the 24-way sibling](https://datasheet.octopart.com/DTM13-12PA-12PB-R008-TE-Connectivity-datasheet-180428408.pdf)). That is one eighth of the board for three power wires; the smaller DTM06/DTM04 housings are wire-to-wire only (this was found for thermo/ on 2026-08-10 and is why the other boards in this project use a pigtail). The board's hole pattern for the 12-way part is not in the data TE publishes in PDF, so I did not guess one. If a sealed header ever becomes a requirement, download TE's footprint and STEP, then the display floorplan has to be redone around it.
- **Why J3 has no DTM.** It was labelled "the CAN tap to the ECU" in the BOM, which is wrong: the display board is on the private link only and never touches the car bus (gauges/ is the gateway, `software/PLAN.md`). J3 joins two boards inside the same dash. A sealed connector protects against engine-bay water, and this is not there.
- **The wire-gauge gap that decides the wire sizes.** Molex's KK 254 crimp terminal 08-50-0114 takes 22 to 30 AWG ([Digi-Key listing](https://www.digikey.com/en/products/detail/08-50-0114/WM1114-ND/26475)); the DTM size-20 contacts take 16 to 20 AWG. No wire is crimpable into both. So the pairing "KK 254 header, DTM06 plug on a pigtail" that the other boards use has no single wire that fits both ends unless the pigtail is soldered or screwed at the board end. J2 avoids it: the MKDS terminal takes 26 to 14 AWG, and 0.25 to 1.5 mm^2 with a ferrule ([Phoenix catalogue figures as listed by Farnell](https://uk.farnell.com/phoenix-contact/1715734/terminal-block-wire-to-brd-3pos/dp/3041530)), so 18 AWG (0.82 mm^2) goes into both the screw terminal and the DTM contact. J3 avoids it by having no DTM.
- **Wire size for J2.** The 5 A blade fuse F1 is on the board, so it protects the board and not the wire up to it: put a 5 A (or smaller) fuse at the battery end of that wire. 18 AWG carries 5 A with margin; TE lists 7.5 A per size-20 contact on its DTM headers.

## What to buy for the display harness

| For | Part | Qty | Notes |
|---|---|---|---|
| J2 pigtail, car end | TE DEUTSCH DTM06-3S plug housing | 1 | the plug that mates a DTM04-3P receptacle on the car side |
| | TE WM-3S wedge lock | 1 | one per plug housing |
| | DEUTSCH size-20 socket contacts for 16-20 AWG (0462-201-20141 nickel is the usual number; **confirm on TE's page before ordering, not verified here**) | 3 | |
| | DTM04-3P receptacle and WM-3P wedge lock | 1 each | only if the car-side lead is also built; the pigtail alone does not need them |
| | 18 AWG TXL or GXL wire | about 0.5 m | colour: red VBAT, black GND, a third colour (yellow) IGN |
| | wire-end ferrules for 0.75 to 1.0 mm^2 (Phoenix AI series) | 3 | for the screw terminal |
| J3 cable | Molex 22-01-3037 KK 254 housing | 2 | |
| | Molex 08-50-0114 crimp terminal, 22-30 AWG (one distributor lists it obsolete: check stock, 08-50-0032 is the other common KK 254 terminal in the same range) | 6 | |
| | 22 AWG twisted pair plus one ground wire, 120 ohm class pair if possible | the length between the boards | keep it short and twist the pair along all of it |

## Not covered by this decision

- **gauges/** has the same pairing on J7, J9, J10 and J11 (KK 254 headers, DTM06 pigtails to the car). Unless the pigtail wire is soldered to the board, no one wire fits a KK crimp terminal (22 AWG or thinner) and a DTM size-20 contact (20 AWG or thicker) at the same time. Those connectors do leave the dash. The fix is the same kind: pick a wire that both ends accept, or terminate the pigtail on a screw terminal. Not done here.
- **display/** also has the dial header J11 (KK 254, in-dash), the audio headers J14/J15 (JST XH, in-dash), the USB-C port J17 and the panel flex connector J4. None of them leaves the car through a sealed connector.
- The car-side half of every connector (where the 12 V and the ignition wire are tapped, the car-side connector) belongs to the car's wiring and has not been designed.
