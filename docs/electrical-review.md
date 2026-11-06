# Electrical design review of display/ and gauges/ (2026-10-17)

Scope: both boards before anything is fabricated. Nothing here has been built, powered or measured; every number is
a datasheet figure or a calculation, and each is labelled with how sure it is. gauges/ was reviewed and fixed. display/
was first reviewed read-only while another session was editing it, then, once that session committed (c307bf5, audio/USB-C/wireless),
re-reviewed on the committed board; D-01 and D-02 were then fixed in its scripts and the board regenerated.

Everything is re-runnable from `review/`:

```
python review/review_netlist.py gauges          # item 1: pin-by-pin vs datasheet tables, decoupling per supply pin
python review/review_netlist.py display         # (display: add --sch/--pcb to point at a scratch copy of HEAD)
python review/connector_audit.py gauges         # item 2: what sits between every connector pin and the silicon
python review/surge_sim.py                      # item 3: ISO 7637-2 / 16750-2 pulses through fuse, TVS, LM74930, bulk, buck
python review/thermal_derating.py all           # item 4: rail budgets, dissipation, capacitor bias, resistor power, copper
python review/layout_checks.py gauges           # items 4 and 5: switch-node clearance, fast-net length, track capacity
python review/dsi_impedance.py                  # item 5: DSI pair impedance, closed form and 2-D field solve
```

`review/expected.py` holds the datasheet tables (each block names its source and revision). `review/kmodel.py` reads the
netlist (`kicad-cli sch export netlist`) and the `.kicad_pcb`.

## 0. Summary

**2026-11-03: section 9 is the latest pass** (a product review before fabrication): both boards' 12 V input stages rewired to TI's
LM74930 topology (F-01 to F-03), an ignition power latch on brain/ (B-01), and on gauges/ sender readings that cancel the
engine-to-dash ground offset, key-off drain removed and a switched 12 V pull-up / sensor rail (G-30 to G-35). The text below it
is the 2026-10-17 review, kept as it was.

**What the review found that would have stopped or damaged the first run (all in gauges/, all fixed in the scripts):**

1. **J2 SWD connector pinout was wrong for every Tag-Connect cable** (SWDIO on 1, VCC on 2, RST on 5, GND on 6; the
   cable wants 1 VCC, 2 SWDIO, 3 nRESET, 4 SWCLK, 5 GND, 6 SWO). A programmer would have put its ground on RESET and
   its SWDIO output on the 3.3 V rail.
2. **Y1 (8 MHz crystal) was shorted to itself.** The Abracon ABM8AIG datasheet says pads 1 and 3 are the crystal, 2 and 4
   are ground; the symbol tied 1 and 3 together as OSC_IN and put 2 and 4 on OSC_OUT. The firmware falls back to the
   48 MHz internal clock when the crystal does not start, so it would have "worked" at the wrong clock.
3. **The MCU's decoupling capacitors were 19 mm and 30 mm from the VDD pins, VDDA's 35 mm** (NXP asks for 2 mm); the
   TJA1043's VBAT capacitor 16 mm, the LDO's input capacitor 18 mm. Measured from the routed board, now cells placed around the ICs.
4. **A +75 V ISO 7637-2 pulse 2a overshoots VIN_PROT to about 39.5 V** (LMR33630-Q1 absolute maximum 38 V) because the
   LM74930's overvoltage comparator needs 4 to 7 us to act while only about 3.5 uF of effective capacitance is there to absorb
   the pulse. Two more 10 uF 50 V parts bring the simulated peak to 31.5 V.
5. SPI SCK/MOSI run about 440 mm across the board unterminated; BL_GATE and the TJA1043 EN/STB_N inputs floated while the
   MCU is in reset; the CAN lines, the three sender wires and the Hall wire had no surge/ESD part; battery-side and +5V copper
   was 0.2 mm where 0.4 to 0.6 mm is needed.

**The items that most needed a decision, and where they stand now:**

* **G-08** (fixed with a 3.6 V zener on +3V3, D33, pending its datasheet) A sender wire shorted to battery while the car is off would
  have pumped the 3.3 V rail up toward the wire voltage (the LDO cannot sink current and the 1 k pull-ups are tied to the rail), taking the MCU and four displays with it.
* **D-01 / D-02** (fixed and re-routed) display/ battery path: the 5 A fuse fed `VBAT_IN`/`VBAT_F` through 0.2 mm tracks on 0.5 oz inner layers,
  and the TVS footprint was a 600 W SMB while the BOM orders an SMC part.
* **G-15** The GC9A01 modules (and the display panel) are rated -20 to +70 C / -30 to +80 C; the Verdin 85 C; a dash in the sun is hotter.

Fixed in the scripts and verified: see section 8 for the final routing and DRC result.

## 1. Findings

Severity: **High** = would stop the board working, damage a part, or leave the owner with a bad failure; **Medium** = out of a
datasheet recommendation or rating with a plausible failure; **Low** = hygiene, margin or something to confirm. Status:
**fixed** = changed in the scripts, regenerated and DRC-checked; **open** = needs an owner decision or the other session.
IDs: G- = gauges/, D- = display/, X- = both, S- = sibling projects.

| ID | Sev | Board | Ref | Evidence | Fix / recommendation | Status |
|---|---|---|---|---|---|---|
| G-03 | High | gauges | J2 | Tag-Connect TC2030-CTX datasheet: 1 VCC, 2 SWDIO, 3 nRESET, 4 SWCLK, 5 GND, 6 SWO. Board had 1 SWDIO, 2 VCC, 3 SWCLK, 4 NC, 5 RST, 6 GND. `review_netlist.py` failed all six pins | Symbol and wiring changed to the cable order; SWO left open (PTA10, the only SWO pin, is SPEED_IN) | fixed |
| G-04 | High | gauges | Y1 | Abracon ABM8AIG datasheet: pad 1 and 3 crystal, 2 and 4 GND. Netlist had 1 and 3 on OSC_IN, 2 and 4 on OSC_OUT | Symbol now XTAL1 (1), GND (2), XTAL2 (3), GND (4); verified in the netlist | fixed |
| G-05 | High | gauges | C6, C7, C8, L2, R1, Y1 | NXP S32K1xx DS Rev 15 Table 7 note 7: decoupling within 2 mm of the pin. Routed board: C7 19 mm from pin 41, C6 30 mm from pin 7, C8 35 mm from pins 8/9 | MCU cell (`gauges/cells.py`): capacitors pulled to the VDD, VDDA, VSS pins, crystal and its caps to pins 11/12, reset pull-up to pin 63. Now 3.4 to 4.5 mm pad centre to pad centre (about 2 mm edge to pin tip) | fixed |
| G-06 | Medium | gauges | U5, U10, U4 | VBAT capacitor C15 16 mm from U5.10, LDO input capacitor C2 18 mm from U4.1, CAN decaps 9 to 12 mm | CAN0, CAN1 and LDO cells; added C58 (1 uF) at the LDO input as TI's datasheet recommends | fixed |
| G-07 | High | gauges | D1, C1, U2 | `surge_sim.py`: ISO 7637-2 pulse 2a at the Level IV 75 V (TCAN1044 DS 6.3): VIN_PROT peak 39.5 V with 3.5 uF effective (10 uF 50 V X7S at the 30 V clamp), against the LMR33630-Q1 absolute maximum VIN of 38 V. LM74930 OV de-glitch 4 to 7 us (SNOSDF6 6.6). At Level III (50 V) 30.7 V, fine | Added C59, C60 (10 uF 50 V X7S 1210, catalogue part GCM32EC71H106KA03L): 10.5 uF effective, peak 31.5 V. Bench-test pulse 2a before relying on it | fixed (verify on bench) |
| X-01 | Medium | both | Q1, Q3 / Q1, Q2 | Same simulation: during pulse 2a the FET pair carries about 27 A for a few us while the input capacitance charges; PMV55ENEA IDM is 12.6 A (tp <= 10 us, 25 C, Nexperia 21 Mar 2016). It is a transient but twice the pulse rating | Bench-test ISO 7637-2 pulse 2a at Level III and IV; if it fails use FETs with 100 A+ pulse ratings (PowerPAK/DPAK, 60 V, VGS 20 V) | fixed 2026-10-18: Q1/Q3 (gauges) and Q1/Q2 (display) are Vishay SQJ460AEP, IDM 180 A (bench-test pulse 2a anyway) |
| G-08 | High | gauges | R16-R18, D12-D14, D33 | A wire shorted to the 14.4 V rail puts (14.4-3.3)/1k = 11 mA through each 1 k pull-up into +3V3: 123 mW in a 0603 (rated 62 mW derated to 85 C). With the car off the 3V3 load is a few hundred uA and the LDO cannot sink current, so +3V3 would rise toward the wire voltage and the MCU, four displays and the clamps (all fed from it) would see up to ~12 V (GC9A01 VCI absolute maximum 4.6 V, S32K144 5.8 V) | R16-R18 are now 1206. **D33, an onsemi SZMMSZ3V6T1G 3.6 V automotive zener on +3V3, absorbs the pump**: three shorted wires push about 31 mA (3 x (14.4 - 4.0)/1k) through it, 0.13 W of its 0.5 W, and the rail should settle near 4.0 to 4.5 V (3.78 V maximum Vz plus the dynamic drop; I could not read the dynamic-impedance curve), under every absolute maximum on the rail. The part is distributor-listed (AEC-Q101, 90 ohm max Zzt, 5 uA at 1 V) but its onsemi datasheet would not download: confirm leakage at 3.3 V and 85 C (it adds to key-off current) and the 30 mA clamp voltage before ordering. A sustained short at 27 V still burns the 1206 pull-up open, which is the intended failure | fixed (confirm D33's datasheet) |
| G-09 | Medium | gauges | J7 pins 1-2, J8 pins 1-2, J7 pins 3-5, J9 pin 1 | These lines left the board with only a series resistor and a BAV99-Q (or nothing, on the CAN pairs) | D28 to D32: Littelfuse SM24CANB-02HTG (AEC-Q101, SOT-23, 24 V standoff, +-30 kV IEC 61000-4-2, 34 V clamp at 1 A) at the connector pins. Section 3 explains where a TVS is and is not justified | fixed |
| G-10 | Medium | gauges | R84, R85 | LPSPI2_SCK / SOUT run 441 / 428 mm to four modules (round trip about 6 ns on FR4) with a pad that has a 3.2 ns minimum rise time at 25 pF (S32K1xx DS Table 21) and no series resistor; the bus clock is 9.6 MHz (`panel_hal_s32k.c`) | 33 ohm series resistors at the MCU pins | fixed |
| G-11 | Low | gauges | R86 | Q2 gate had no defined level while the MCU pin is high-impedance (reset, boot) | 100 k pull-down | fixed |
| G-12 | Low | gauges | R87, R88 | TJA1043 EN and STB_N have no internal pull-downs (NXP TJA1043 Rev 6, IIL +-1 uA) | 100 k pull-downs, so the transceiver sits in its low-power state until firmware drives them | fixed |
| G-13 | Medium | gauges | VIN_FUSED, VIN_PROT, COMMON, +5V | `layout_checks.py`: those nets were routed at 0.2 mm on 0.5 oz inner layers (0.23 A at 10 K) against 0.30 to 0.45 A; the ladder widened only VIN_PROT | `TRUNK_NETS` now includes VIN_FUSED, COMMON, +5V; see section 8 for the routed result | fixed (check the final widths) |
| G-14 | Medium | gauges | U2, L1, C2, C45 | LMR33630-Q1 SNVSB26C Table 8-2 (B option, 1.4 MHz, 5 V): L = 2.2 uH, COUT 2 x 22 uF of 16 V parts. The board has L1 = 10 uH (LC product about 4 x larger, outside the range the internal compensation was tuned for) and 22 uF **10 V** parts that keep about 10 to 15 uF at 5 V (generic X7R bracket; Murata's curve not retrievable here). The datasheet says use 16 V or higher for 5 V outputs | Do a load-step and Bode check on the first board; if the loop rings, L1 = 3.3 uH and 16 V capacitors | fixed 2026-10-18: L1 = Coilcraft XAL5030-222MEC 2.2 uH (Isat 9.2 A), C2/C45 = 22 uF 16 V X7R 1210 (GCM32ER71C226ME19L); still do the load-step check |
| G-15 | Medium | gauges | U6-U9 | Raystar RFA401280B-AYW-DNF1: operating -20 to +70 C, storage -30 to +80 C. VCI is specified 2.65 to 3.3 V and the 3V3 rail can be 3.35 V (TLV733P +-1.4 % over temperature), 46 mV over the operating maximum (GC9A01A abs max 4.6 V) | Owner decision: this is a commercial-temperature module in a dash. Choose a wider-range module or accept it; the 3.35 V is low risk | open |
| G-16 | Low | gauges | U3, R51/R52 | LM74930 cut-off: UVLO falling threshold 5.1 to 5.7 V; a cold-crank dip below that resets the board. Key-off supply current about 1.4 to 1.8 mA (LM74930 IQ 665 uA typ + divider ladders 0.45 mA + MCU/transceivers), about 35 to 45 mAh per day | Firmware must tolerate a reset on cranking; consider EN from ignition if the battery is not tended | 2026-11-03: the figure left out about 9 mA through the always-on sender pull-ups (G-31, now switched off); brain/ now has an ignition power latch (B-01) |
| G-17 | Low | gauges | C47 | LM74930 pin table says a 100 nF capacitor on VS; TI's example (8.2.2.1) says "a minimum of 1 uF CVS". VS is fed straight from the TVS-clamped fused node here | A 1 uF 50 V part needs a catalogue entry in `tools/passive_catalog.py` (off limits while the other session edits tools/) | fixed 2026-10-18: C47 = 1 uF 50 V X7R 0805 (GCM21BR71H105KA03L) |
| G-18 | Low | gauges | R82, R83 | Arrow LED resistors: 245 mW at a 24 V jump start against 155 mW (1206 derated to 85 C) | Acceptable for a 60 s event; no change | open (accepted) |
| G-21 | Low | gauges | J1, J7-J11 BOM | Harness wording predated docs/harness.md: the BOM named a DTM06-5S (does not exist) for J7 and a DTM06-3S pigtail on J8 | Values and BOM lines now follow docs/harness.md (DTM06-6S with a sealed cavity on J7, J8 a KK 254 cable, 20 AWG power / 22 AWG signal) | fixed |
| G-19 | Low | gauges | board | 447.1 mm long; JLCPCB's multilayer length limit is below 500 mm but check it for the chosen service. The routing is not solid planes (4.2 m of signal on In1, the GND layer) | Ask the fab; see section 7 | open |
| G-20 | Low | gauges | Q2 | Nexperia PMV37ENEA datasheet not retrievable here; pin order (1 G, 2 S, 3 D) matches the PMV55ENEA datasheet of the same package, but one community listing shows 1 G, 2 D, 3 S | Check the PDF before ordering | closed 2026-11-03: the datasheet (21 May 2019) lists 1 G, 2 S, 3 D, as wired |
| X-02 | Medium | both | Q1, Q3, D-series | Nexperia lists PMV55ENEA as not recommended for new designs (as found by a web search; the product page itself would not load here). PESD2CAN is also marked NRND, which is why SM24CANB was chosen | Confirm availability; the front end needs a replacement 60 V, 20 V VGS FET anyway if X-01 fails | fixed 2026-10-18 for the LM74930 pairs (SQJ460AEP, AEC-Q101, Rev. D 2022 datasheet); display/ Q3 (ignition wake) is still a PMV55ENEA |
| X-03 | Medium | both | U3 (gauges), U1 (display) | `surge_sim.py`: a 35 V suppressed load dump for 400 ms keeps the OV clamp cycling; the LM74930's overvoltage circuit-breaker (T = 1.2 V x CTMR / 2.8 uA = 43 ms with 100 nF) then turns the output off for about 2.3 s (22.7 x 10^6 x CTMR). The owner's 24 to 27 V figure never reaches the clamp (it starts at 27.8 V minimum) | Fine for a 27 V requirement; for ISO 16750-2 test B (35 V) raise CTMR (470 nF gives 200 ms) after checking Q3's SOA, or accept a 2 s blackout | open |
| X-04 | Low | both | D1 | A unidirectional TVS conducts forward in a reverse-battery event: -14 V gives 73 A (gauges) / 100 A (display) through the fuse, which opens. The LM74930's reverse blocking is never the protection. TI's reference puts a diode in series or uses a bidirectional TVS | Intent: confirm that "reverse battery blows the 2 A / 5 A fuse" is acceptable (the fuse is a board-mounted holder behind the dash) | fixed 2026-11-03 (F-02): bidirectional TVS and the LM74930 wired so a reversed battery is blocked |
| D-01 | High | display | D1 | BOM and schematic value say SMCJ33A (1500 W, SMC package) but the footprint was `Diode_SMD:D_SMB` (a 600 W SMBJ-class land pattern) | `display/parts.py` footprint changed to `Diode_SMD:D_SMC`; board re-placed and re-routed (section 8) | fixed |
| D-02 | High | display | VBAT_IN, VBAT_F, COMMON, SENSE_OUT | `layout_checks.py` on the committed board (c307bf5): the battery path ahead of and through the LM74930 was 0.2 mm everywhere, including 0.5 oz inner layers (VBAT_F 78 mm, VBAT_IN 12 mm, COMMON 19 mm), against up to 2.6 A (5 A fuse); `TRUNK_NETS` widened only +12V_PROT | VBAT_IN, VBAT_F, SENSE_OUT and COMMON added to `TRUNK_NETS` in `display/build_pcb.py`; re-routed. What could not be widened (inner-layer pieces between vias) is listed in section 8 | fixed (see section 8 for what remains narrow) |
| D-03 | Medium | display | C46, C47 | Schematic value says "22u VPOS out 16V" but `passive_catalog` maps 22 uF 1206 to the 10 V GCM31CR71A226KE02L. At 6.5 V that part keeps 3 to 12 uF (bracket), TPS65131 wants 22 uF at the outputs (Fig 8-1) | Use a 16 V 22 uF part (1210) and add it to the catalogue | fixed 2026-10-18: C46/C47 = 22 uF 16 V X7R 1210 (GCM32ER71C226ME19L) |
| D-04 | Medium | display | U7, L4 | TPS61165-Q1: 2.7 W of LED power at 82 to 90 % efficiency is 0.3 to 0.6 W in a SOT-23-6 with RthJA 210 C/W (JEDEC; about 100 to 150 on this board): 116 to 213 C at 85 C ambient; thermal shutdown 160 C | Estimate only. Plan to reduce the backlight with temperature in software, or a driver with a power package; check on a prototype at 85 C | open (display/) |
| D-05 | Medium | display | Q1, Q2 | Each PMV55ENEA at 1.4 to 2.5 A: 163 to 521 mW, 128 to 222 C junction on the standard footprint (RthJA 262 C/W), against 150 C maximum; ID 3.1 A is only rated with a 6 cm2 drain pad. Verdin power is unpublished (Toradex datasheet Rev 0.7 6.3) | Parallel FETs or a power package; get the module's real current | fixed 2026-10-18: SQJ460AEP, 18.3 mohm at 175 C: 0.12 W each at 2.6 A, about 93 to 99 C junction at 85 C ambient (RthJA 68 to 120 C/W) |
| D-06 | Medium | display | DSI | `dsi_impedance.py`: 0.25 mm over 0.21 mm prepreg gives 102 ohm at a 0.25 mm gap, but the measured gap along the pairs ranges 0.25 to 1.2 mm (mean about 0.6), so the coupled sections are 102 to 120 ohm, and the 2.5 to 3 mm B.Cu swap is two uncoupled 60 ohm legs (about 120 ohm). The boards carry no stackup block, so the fab applies its default | Order with controlled impedance, 100 ohm differential on F.Cu referenced to In1 with the real JLC04161H-7628 stackup, and ask the fab for its calculated width/gap | open (display/) |
| D-07 | Low | display | PG_5V, RT_5V, PANEL_BIAS_EN, PANEL_BL_PWM | `layout_checks.py`: on the committed board PG_5V and PANEL_BIAS_EN ran on In1 directly under switching copper; after the re-route it is PG_5V and RT_5V (the LM61460 frequency-set pin, which is noise-sensitive) under the buck, and PANEL_BL_PWM 0.3 mm from BL_SW. The autorouter places these differently each run | Keep-outs for slow nets under the switch cells in the display autorouter (In1 under the buck cell is supposed to be ground); recheck with `layout_checks.py display` | open |
| D-08 | Low | display | J3, J8, J9, J12, J13, J11 | J3 (private CAN) has no ESD part; bench headers are unprotected by design; J11 dial clamps turn on near 2.5 V, a little above the ADC's 2.1 V maximum (the design's own note) | A SM24CANB-02HTG on J3 if J3 leaves the dash (TCAN1044 itself is rated 8 kV J2962-2 system level) | open (display/) |
| D-09 | Low | display | J4 | The panel (Team Source TST040HDBC-42) datasheet could not be found online, so the 39-pin table, the FH26 connector and the +-6.5 V polarity conflict are not independently verified | Get the PDF from TSD | open |
| D-10 | Low | display | U9-U14, J14-J17, D8 | Reviewed against TI SLASFC2A (TAC5112-Q1), SBVS381A (TLV767-Q1), SLVSC97B (TPS2557-Q1), SLVSCO7C (TPD4E05U06-Q1): all pins agree, codec AVDD 3.3 V and IOVDD 1.8 V inside the 3.9 V absolute maximum, USB current limit 1.61 to 1.98 A with 61.9 k (datasheet table), 22 k Rp advertises 1.5 A. J17 wires only the A9/B4 VBUS pair (documented in docs/audio-and-usb.md: 1.5 A over two 1.25 A contacts, fine for this port) | Tables added to `review/expected.py` | checked |
| D-11 | Medium | display | U12, C76-C79 | The line-out ESD array TPD4E05U06-Q1 is unidirectional: it conducts below -0.6 V (SLVSCO7C 7.4) and sits on the connector side of the 4.7 uF DC-blocking capacitors, where each leg swings about +-1.4 V (2 Vrms differential, 1 Vrms per leg). Into a DC-coupled or resistively biased AUX input the negative half-cycles clip at -0.6 V; into an AC-coupled one the clamp rectifies and shifts the DC level instead | Use a bidirectional ESD part on the line-out legs (or move the array to the codec side of the capacitors, where the legs sit on the codec common mode); listen-test the first board | fixed 2026-10-18: U12 = TI TPD4E02B04-Q1 (bidirectional, VRWM +-3.6 V, same USON-10 pinout); listen-test still advised |
| S-01 | High | manifold-pcb, thermo-pcb, ecu-pcb | J2, Y1 | `manifold-pcb` and `thermo-pcb` use the same `CONN_SWD` symbol (SWDIO on 1, VCC on 2, SWCLK on 3, NC on 4, RST on 5, GND on 6), which is wrong for any Tag-Connect cable. `manifold-pcb` and `ecu-pcb` wire crystal pads 1 and 3 together as OSC_IN and 2 and 4 together as OSC_OUT (ecu-pcb's comment says opposite corners are tied for mechanical stability; for the Abracon ABM8AIG that gauges/ and manifold-pcb name, pads 1 and 3 are the two crystal terminals and 2 and 4 are ground). `thermo-pcb` already wires its crystal correctly (pins 1 and 3 crystal, 2 and 4 ground) | Apply the same fixes to the sibling projects before they are fabricated; not touched here | open |

## 2. Pin-by-pin check (item 1)

`review/review_netlist.py` compares each IC with a table transcribed from its datasheet (revision named in `review/expected.py`):
symbol pin names against datasheet names, and every pin's connection rule (supply, enable strap, unused pin left open,
resistor or capacitor on the pin, MCU alternate function against NXP's signal table). Datasheets read in this review:

| Part | Document and revision | Result |
|---|---|---|
| S32K144 LQFP-64 | NXP S32K1xx Data Sheet Rev 15 (5 Mar 2026) + the IO signal xlsx from the RM 14.2 attachment | 46 connected pins agree with the mux table; 18 package pins float on purpose (all GPIO at reset defaults); SPEED_IN sits on PTA10 whose reset function is JTAG_TDO, firmware must remap it |
| LMR33630BRNXRQ1 | TI SNVSB26C | 12 pins agree; pin 3 (NC) tied to SW as the datasheet asks for the VQFN; EN straight to VIN is allowed; PG left open is allowed |
| LM74930-Q1 (both boards) | TI SNOSDF6 | 25 pins agree; OVCLAMP tied to OV (clamp with timer), ISCP tied to C (20 mV threshold), exposed pad floating as required, IMON/FLT/NC open |
| TLV73333PQDBVRQ1 | TI SBVS283F | 5 pins agree |
| TJA1043T/1J | NXP TJA1043 Rev 6 | 14 pins agree; WAKE to GND is what 7.6 recommends when unused; VIO 2.8 V min against 3.3 V |
| TCAN1044VDRQ1 (both boards) | TI SLLSF17D | 8 pins agree; the V suffix is the one with the VIO pin |
| GC9A01 modules U6-U9 | Raystar RFA401280B-AYW-DNF1 datasheet | 18 pins agree; the datasheet's function column is shifted by one row in the text extraction but follows the order 1..18 |
| LM61460, TLV767, TPS65131, TPS61165, TPS22918 (display) | TI SNVSB70F, SBVS381A, SLVSBB2F, SLVSB73B, SLVSCZ8B | all pins agree with `display/parts.py` and the datasheets |
| PMV55ENEA, BAV99 series, ROHM CSL0902ET1C, SM24CANB | Nexperia 21 Mar 2016, BAV99 Rev 8 (the -Q variant has identical pinning), ROHM Rev 007, Littelfuse 10/09/17 | pinning agrees; Q2 (PMV37ENEA) is unverified (G-20) |
| Verdin iMX95 X1 | Toradex datasheet Rev 0.7 | all non-module-specific pin names agree with `verdin_pinout.py` (checked by regex over the pin tables; the only differences are the module-specific MSP pins, which the extractor renames); VCC 3.135 to 5.5 V, ADC 2.1 V max |

Also checked against package drawings: the custom RNX0012C footprint matches TI's land pattern dimensions (0.65/0.5 mm pad
pitch on the left and right, 1.825 mm SW pad), and the CSL0902 pad spacing matches the part.

Not verifiable here: the panel connector J4, PMV37ENEA, the Amphenol F32Q FPC contact side (the module's FPC contacts must
face the connector's contacts; order a sample and check pin 1 before buying 4), and the Verdin module's current draw.

## 3. Connector protection (item 2)

`review/connector_audit.py gauges` prints the full chain per pin. Summary of what stands between the world and the silicon:

| Connector | Line | Exposure | Protection after this review | Why |
|---|---|---|---|---|
| gauges J1.1 | 12 V | battery, load dump, ISO 7637 | 2 A MINI fuse, SMCJ33A TVS, LM74930 (reverse, 29.9 V clamp, 1.49 A breaker), bulk | see section 4 |
| gauges J1.3 | ignition | 12 V switched wire, spikes | 56 k series, 27 k divider, BAV99-Q to 3.3 V/GND, 10 nF | A pulse of 100 V is 1.8 mA into the clamp (BAV99-Q: 4.5 A for 1 us); high impedance is the protection. No TVS needed |
| gauges J7.1-2 | car CAN | long harness, ISO 7637-3 coupling, ESD | **D28 SM24CANB-02HTG** at the connector, TJA1043T on the bus (+-58 V, +-8 kV IEC 61000-4-2, ISO 7637 pulses 1/2a/3a/3b at 100/75/150/100 V, per its datasheet limits) | The transceiver is already rated; the TVS adds a surge path to ground for the long bus and a place to fit a common-mode choke later |
| gauges J7.3-5 | sender wires | long wires to the tank and engine, shorts to battery | **D29, D30** (24 V standoff, clamp 34 V at 1 A), series 1 k, BAV99-Q at the ADC pin, 1206 pull-ups, **D33** 3.6 V zener on +3V3 | These are low-impedance nodes (1 k pull-up), unlike the 33 k inputs. The TVS covers spikes; a sustained short to battery is carried by the pull-up resistor and the rail clamp D33 (G-08) |
| gauges J8 | private CAN | in-dash, short | **D31** | Cheap, same footprint, TJA1043/TCAN1044 already withstand 8 kV |
| gauges J9.1 | Hall speed | harness from the transmission | **D32**; 33 k series, 15 k, BAV99-Q, 4.7 k pull-up to VIN_PROT | |
| gauges J10 | 6 lamps, dimmer | switch wires | 33 k (22 k) series + 15 k + 10 nF + BAV99-Q each | At 100 V a 33 k series resistor passes 3 mA; the BAV99-Q takes 4.5 A, so no TVS. A 0603 AC resistor's ESD tolerance is the limit for an 8 kV contact discharge directly on the pin; accept |
| gauges J10.1-2 | turn arrows | flasher wire | 1.8 k 1206 to the LED, BAV99-Q reverse clamp | Up to 6.3 mA at 14.4 V; clamp holds the anode at -0.7 V on negative spikes; LED reverse limit 5 V |
| gauges J11 | tach | possibly 300 V coil ring | 2 x 18 k 1206 (200 V each), 15 k, 2.2 nF, BAV99-Q | as designed; coil-negative on points ignition is not validated |
| gauges J2 | SWD | bench only | none | |
| display J2.1 | 12 V | same as above | 5 A fuse, TVS (D-01), LM74930 | |
| display J2.3 | ignition | | 56 k + 33 k + BAV99-Q on the gate node | as gauges |
| display J3 | private CAN | in-dash | none (D-08) | |
| display J11 | dial | in cabin | divider + 1 k + BAV99-Q on both lines | clamp turns on near the ADC maximum, as the design notes |

A TVS was added only where the node is low impedance or is a bus; where the series resistor is 33 k or more it sets the
surge current by itself. Part chosen: Littelfuse SM24CANB-02HTG, AEC-Q101, SOT-23 (pins 1 and 2 to common pin 3), VRWM 24 V,
VBR 26.7 V, VC 34 V at 1 A and 50 V at 10 A (8/20 us), 30 pF per line, +-30 kV IEC 61000-4-2 (datasheet Rev 10/09/17).
A 24 V standoff leaks 0.1 uA at 24 V so it does not load a 14 V wire; PESD2CAN was passed over because Nexperia marks it NRND.
No common-mode choke footprint was added (it needs in-line pads that cannot be bypassed with a script-only change): an open
EMC item for CAN0 after a CISPR 25 measurement.

## 4. 12 V front end (item 3)

Model (`review/surge_sim.py`, lumped time-domain, scipy): source Us(t) with Ri, harness + fuse resistance, the SMCJ33A TVS
(knee at VBR min 36.7 V, slope from Vc 53.3 V at 28.2 A, forward diode for negative pulses), R49/Q3/Q1 path resistance, the input
bulk capacitance (derated for bias) and the buck as a constant-power load. The LM74930 overvoltage clamp is a hysteretic
controller with the datasheet's de-glitch: HGATE turns off 4 to 7 us after OV rises (5.5 us used) and on 9 us after it clears;
OV threshold 0.6 V x (100 k + 2.05 k) / 2.05 k = 29.9 V (28.8 to 31.0 V with the datasheet limits and 1 % resistors).
Pulse amplitudes are the Level IV figures in TCAN1044 DS 6.3 (pulse 1 -100 V, 2a +75 V, 3a -150 V, 3b +100 V); Ri and td
(10 ohm 2 ms, 2 ohm 50 us, 50 ohm 150 ns) are from ISO 7637-2:2011 as I know it: the standard is not in the repository, so check
them before quoting compliance. "Fuse I" is the generator current, which for pulse 2a is the current the FET pair carries into the capacitor.

gauges/ after the fixes (Cin = C1 + C59 + C60, 10.5 uF effective):

| Pulse | VIN_FUSED (min/max) | VIN_PROT peak | TVS | Generator / FET current | Verdict |
|---|---|---|---|---|---|
| Pulse 1, -100 V, 10 ohm, 2 ms | -1.2 V | 13.0 V | 9.7 A forward (about 18 W) | 9.7 A for 2 ms, I2t about 0.2 A2s | TVS forward diode clamps; 2 A fuse sees 9.7 A (fuse datasheet melting I2t not available offline; repeated pulses are a fatigue question) |
| Pulse 2a, +75 V, 2 ohm, 50 us | 33.4 V | **31.5 V** (39.5 V before the fix) | does not conduct | 27 A for a few us | under the buck's 36 V; FET pulse current 2x IDM (X-01) |
| Pulse 3a / 3b, 100 ns, 50 ohm | -0.9 V / 13.2 V | 13 V | 2.9 A | 3 A | inside every rating (package inductance not modelled) |
| 27 V load dump, 400 ms | 26.9 V | 26.8 V | none | 5.5 A | passes; below the 27.8 V clamp |
| 35 V suppressed load dump, 400 ms | 35 V | 27.4 to 30.9 V (clamp cycling) | none | up to 8.5 A while the clamp is off | buck stays under 36 V; the breaker trips at 43 ms (X-03) |
| 24 V jump start, 60 s | 23.8 V | 23.7 V | none | 0.7 A | passes (TVS standoff 33 V, buck 36 V, C1 50 V) |
| Unsuppressed 101 V, 400 ms | 49 V | 41.6 V | 24 A at about 49 V, ~1.2 kW | 32 A | **fails**: the TVS cannot take 400 ms, and the clamp's first microseconds exceed 38 V. Not required (owner specified 24 to 27 V); an unsuppressed system needs TI's 200 V reference (TVS+ SMBJ150A + series FET), not this stage |
| Reverse battery -14 V, 60 s | -3.7 V | 0 V | 73 A forward | 73 A | the fuse opens (X-04) |

Stress on every first-stage part against its absolute maximum, gauges/ (display/ is the same except for 106 uF of bulk
capacitance, which holds pulse 2a at 16 V):

| Part | Worst voltage | Absolute maximum | Margin |
|---|---|---|---|
| LM74930 A, C, VS, CS+, CS-, ISCP | 35 V (load dump), 33.4 V (pulse 2a) at the fused node; TVS Vc up to 53.3 V in a long surge | 70 V (65 V recommended) | 17 to 37 V |
| PMV55ENEA Q1, Q3 | VDS about 14 V reverse (VIN_PROT + 0.8 V) | 60 V | 46 V |
| PMV55ENEA gate | HGATE/DGATE 14.5 V max above source | +-20 V | 5.5 V |
| LMR33630-Q1 VIN, EN | 31.5 V (pulse 2a), 30.9 V (load dump) | 38 V | 6.5 V |
| LM61460-Q1 VIN (display) | 16 V (pulse 2a), 30.0 V (load dump) | 42 V | 12 V |
| TJA1043T VBAT | 31 V | 40 V (58 V transient) | 9 V |
| C1 10 uF 50 V (gauges) | 31 V | 50 V | 19 V |
| C1 100 uF 35 V hybrid (display) | 31 V | 35 V | 4 V (tight: peaks 31.5 V with clamp spread) |
| TVS standoff | 24 V jump start | 33 V | 9 V |

## 5. Thermal and derating (item 4)

`review/thermal_derating.py` prints every table below. Estimates are labelled; module currents without a datasheet number
(GC9A01 10 mA each, Verdin 5 W typical / 10 W peak) are assumptions at the top of that file.

* **gauges/ 5 V rail 299 mA** (3V3 86 mA + two CAN transceivers dominant 140 mA + four 15 mA backlights 72 mA). The LMR33630 loses
  0.12 to 0.37 W (estimate: RDS(on) maxima from the datasheet, 10 ns edges), 94 to 112 C junction at 85 C with the JEDEC 72.5 C/W: fine.
* **TLV733P-Q1**: (5.15 - 3.3) x 86 mA = 0.16 W, 117 C junction with 198 C/W; the limit at 85 C ambient is 177 mA of 3V3 load.
* **display/ 5 V rail**: about 9.5 W typical, 14.5 W peak (backlight 3.2 W, bias 0.8 W, module 5 or 10 W assumed). LM61460 at 1.9 to
  2.9 A: 0.64 to 1.1 W by the 2.1 MHz derating curve (SNVSB70F Fig 10-3), junction 101 to 134 C at 85 C depending on RthJA 25 to 45 C/W: acceptable but tight.
  TPS61165 and the series FETs: D-04, D-05.
* **Capacitor DC bias** (bracketing class-II model, because the Murata curves cannot be downloaded here): C1 10 uF 50 V X7S keeps
  7.9 to 8.9 uF at 13.8 V and 2.3 to 5.8 uF at 31 V; 22 uF 10 V 1206 keeps 9.9 to 15.4 uF at 5 V; 1 uF 16 V 0603 keeps 0.7 to 0.9 uF
  at 5 V (LMR33630 wants 1 uF at VCC, so it is at the edge: fine in practice). Display: C46/C47 (D-03), C52 at 15 V keeps 3.5 to 4.1 uF (0.5 to 2 uF in the 38 V open-LED case).
  The effective values appear in the report only as brackets; confirm with the manufacturer's tool before ordering.
* **Resistor power** (rating derated to 85 C): fine everywhere in normal operation (backlight resistors 40 mW of 62 mW; dividers
  under 15 mW). Faults: R16-R18 123 to 562 mW (G-08, now 1206 with the rail clamp D33); R82/R83 245 mW at a 24 V jump start (G-18); R43 190 mW if the Hall wire is
  grounded while the OV clamp is active (accepted).
* **Copper and fuses**: see G-13 (gauges) and D-02 (display). The 2 A fuse against the 1.49 A breaker setting and a 0.30 A load at 5.8 V
  gives margin x4.9; the 5 A fuse against a 4.96 A breaker does not leave the breaker below the fuse by much: the breaker is meant to act first
  (1.5 ms), the fuse is the last resort.

## 6. Signal integrity sanity (item 5)

* **DSI pairs** (D-06). Stack-up from `fab/README.md` (JLC04161H-7628: 35 um outer copper, 0.2104 mm prepreg, Dk 4.4, In1 = GND). Closed
  form: single track 60.6 ohm (IPC-2141), 60.4 ohm (Hammerstad-Jensen, 6.0 ps/mm); differential 91.8 / 97.8 / 102.5 / 109.3 / 115.2 ohm at gaps of
  0.15 / 0.20 / 0.25 / 0.35 / 0.50 mm. A 2-D field solve (`dsi_impedance.py`, solder mask included) agrees to within 1 ohm: 102.0 ohm at a 0.25 mm gap, 110.7 at 0.35, 115.1 at 0.50, Dk 4.6 about 1.6 ohm lower;
  100 ohm needs 0.26 mm width at a 0.25 mm gap or 0.32 mm at 0.35 mm. The layout's gap (0.25 to 1.2 mm along the pairs) is looser than the quoted
  "0.25 to 0.5 mm", and the swap on B.Cu is a 20 ohm step over about 3 mm. Skew inside a pair is 0.6 mm (about 4 ps). **Ask the fab for: controlled
  impedance 100 ohm +-10 % differential on the DSI pairs with its own stackup and calculated width/gap; the actual dielectric constant and thickness of the
  F.Cu to In1 prepreg; and a coupon.** At the MIPI D-PHY rates in use a +-15 % mismatch over 11 mm is a margin question, not a failure, but it is untested.
* **CAN**. gauges CAN1 and display CAN: split termination, two 60 ohm + 4.7 nF at each end, so the bus is 60 ohm and both ends are terminated;
  both transceivers sit at the ends, so no stub. CAN0 (car bus): R4/R5 are DNP, correct unless this board is an end node; gauges is a stub node on the
  car bus, listen-only. A common-mode choke would help CISPR 25 emissions on a long harness; not added (needs a bypassable footprint).
* **SPI** (G-10). Round trip of a 441 mm run is about 6 ns against a 3.2 ns minimum rise at 25 pF (S32K1xx DS Table 21), so the line is electrically
  long at the fast corner; 33 ohm at the driver damps it. GND on In1 is cut by 4.2 m of other signals: expect poor return paths and radiated noise; it
  was a stated limit of this design and the earlier attempt to forbid signals on In1 left 6 to 122 connections unrouted.
* **Switch nodes**. gauges: no foreign track within 1.5 mm of SW or BOOT on any layer. display (HEAD): PG_5V 0.0 mm (on In1 under a switch
  copper), PANEL_BL_PWM 0.7 mm, USB_ID 1.0 mm, EN_5V 1.4 mm, PANEL_BIAS_EN 1.5 mm (D-07); all slow signals, re-check after the other session's regeneration.

## 7. Sources and what is unverified

Downloaded and read for this review (curl with a browser User-Agent works for ti.com symlink URLs; nxp.com, nexperia.com, mouser.com
block scripted downloads, so the NXP S32K1xx and Nexperia PMV55ENEA documents came through other routes): TI SNVSB26C, SNOSDF6, SBVS283F,
SLLSF17D, SNVSB70F, SBVS381A, SLVSBB2F, SLVSB73B, SLVSCZ8B; NXP S32K1xx Rev 15, TJA1043 Rev 6; Nexperia PMV55ENEA (Mar 2016), BAV99
series Rev 8; ROHM CSL0902ET1(C) Rev 007; Raystar RFA401280B datasheet and GC9A01A datasheet (in `software/refs`); Toradex Verdin iMX95 Rev 0.7;
Abracon ABM8AIG; Tag-Connect TC2030-CTX; Littelfuse SM24CANB (10/09/17); for display/'s audio and USB additions TI SLASFC2A (TAC5112-Q1), SLVSC97B (TPS2557-Q1), SLVSCO7C (TPD4E05U06-Q1).
Not obtained: onsemi SZMMSZ3V6T1G (D33, distributor listing only), PMV37ENEA, PMEG6010ELR, BAV99-Q (the series Rev 8 was used), SMCJ33A (distributor-listed Vc/Ipp used, pulse-rating curve approximated),
Littelfuse 297 fuse (I2t), Murata capacitor bias curves, Amphenol F32Q, Hirose FH26, Keystone 3568, panel TST040HDBC-42, ISO 7637-2 itself.

## 8a. Product review, 2026-10-18

A second pass looked for anything that would stop the boards becoming a product (not only the first power-up). New findings, all fixed in the scripts and regenerated:

| ID | Sev | Board | Finding | Fix |
|---|---|---|---|---|
| P-01 | High | display | No Verdin module standoffs. Toradex's carrier design guide V1.2 section 4.3 recommends screwing the module down in high-vibration use (a car), and 4.4.1 needs two more standoffs for the Verdin Industrial Heatsink. The module was held only by the socket clips, and no heatsink could be mounted | S1/S2 (2.5 mm) and S3/S4 (7.0 mm) M2x0.4 standoff pads, Ø3.00 mm hole, Ø5.30 mm pad on GND, at Toradex's Fig 113 positions relative to the socket pegs (`display/build_pcb.py`, `VERDIN_STANDOFFS`) |
| P-02 | High | display | The module keepout was centred on the socket, but the module is not: it reaches 35 mm from the socket pegs on the latch side (Fig 110/113). The 8 mm under its far edge, where S1/S2 go, was open to carrier parts; C12 had a pad there | `floorplan.py` now places the keepout from the module's real extent (`j1_local_x_hi`); only S1/S2 sit under the module now. The board grew to 178.2 x 105.0 mm |
| P-03 | High | display | CarPlay could not work: LIVI (and any CarPlay receiver) needs Apple's coprocessor on I2C with its power switched from a GPIO; J16 was four bare pads with no supply | J16 is a 1x6 2.54 mm daughterboard header: I2C_1 (1.8 V), MFI_RST_N, GND, MFI_5V (switched by U15, a TPS22918-Q1 on Verdin GPIO_3, held off by R74 in reset) and +1V8. The coprocessor, its regulator and level shifting go on the daughterboard because Apple's pinout and supply are under NDA |
| P-04 | Medium | gauges | The inner small gauges sat at +/-98.5 mm from the centre; the owner's cluster measures about +/-118 mm (photos, 2026-10-08), and at 98.5 mm the inner modules overlapped display/'s width | `INNER_GAUGE_OFFSET_MM = 118` in `gauges/build_pcb.py`; the turn-arrow LEDs now sit midway between each side's two gauges. Replace 118 with a caliper reading |
| P-05 | Medium | display | No heat path for the Verdin module (5 W typical, 10 W peak assumed) in a closed dash | S3/S4 make the Verdin Industrial Heatsink possible; its fin height and thermal resistance, and whether it suffices at 85 C, are asked in `rfq-drafts.md` section 2. See `mechanical-stackup.md` |
| P-07 | Low | gauges | After the re-route for P-04 and the new front-end parts, IGN_RAW (the ignition sense line, 56 k series and 10 nF filtered) crosses under the buck's SW node on In1 (`layout_checks.py gauges`); the 2026-10-17 route had no track near SW. +5V also has more 0.2 mm escape length on In1 (31 mm against 14 mm), VIN_PROT less (10 mm against 41 mm) | Accepted for the prototype (a slow, heavily filtered input); fence In1 under the buck cell for the autorouter, or hand-route IGN_RAW, before production |
| P-06 | Medium | display | Supply: the Verdin iMX95 WB IT is in sample status (Toradex PCN 118589; Mouser no stock, 34-week lead) | Noted in the BOM; question 6 in `rfq-drafts.md` section 2 |

G-15 update (2026-10-18): a search found no 1.28 in round 240x240 module rated beyond -20 to +70 C operating (Raystar, DisplayModule DM-TFTR128-446/466, Winstar WF0128BTYAA4DNN0, GoldenMorning all list -20 to +70, storage -30 to +80). A wider range is a custom-panel question (`rfq-drafts.md` section 6).

Still open from this pass: D-04 (backlight driver thermal; the -Q1 part only comes in SOT-23-6, and a replacement waits for TSD's backlight configuration), G-15 (small-module temperature range), the panel datasheet questions (D-09), and licensing.

## 8b. Six-layer re-route, 2026-10-19

Owner decision: both boards (and display-rgb/) go to six layers, JLC06161H-3313: F.Cu / In1 GND / In2 / In3 with the +5V or +3V3 pour / In4 GND / B.Cu. Measured on the regenerated boards:

* **Planes really solid.** FreeRouting 2.2.4 ignores a DSN `layer_rule ... (active off)` (an early run still had about 1 m of signal on display/'s In1 and 2.8 m on gauges/'). The router input now restricts every net class except GND to F.Cu, In2, In3 and B.Cu (`use_layer`); `review/layout_checks.py` (new plane check, exit 1 on failure) reports no track of any net on In1 or In4 on display/, gauges/ and display-rgb/.
* **Real DRC: 0 unconnected on all three.** display/ and display-rgb/: only the accepted solder_mask_bridge x10 (JP1/JP2) and hole_clearance x4 (J17 pegs), plus warnings. gauges/: warnings only. The board minimum track width is now 0.15 mm (set by `display/build_pcb.py`) for the 0.16 mm DSI pairs.
* **DSI field solve** (`review/dsi_impedance.py`, 2-D, mask included): 0.16 mm tracks over 0.0994 mm prepreg give Z0 51.8 ohm and 96.4 to 103.1 ohm differential across the 0.25 to 1.2 mm gaps (0.34 mm at J1: 99.1 ohm; 0.44 mm at J4: 100.6 ohm). Order with controlled impedance and a coupon.
* **gauges/ current capacity: all [ok] for the first time.** VIN_PROT, VIN_FUSED and +5V are routed at 0.4 mm from the start (a DSN net class) and widened to 0.6 mm where there is room; worst rise 15 K at 0.45 A. The 2026-10-17 board still had 0.2 mm inner-layer pieces on five power nets.
* **gauges/ P-07 resolved:** `layout_checks.py gauges` finds no foreign track within 1.5 mm of the buck's switch node on any layer.
* **display/ and display-rgb/ battery path (D-02 residual), re-routed 2026-10-20.** Until now VBAT_F was 1.5 mm wide for most of its length, but about 60 mm of it ran on 0.5 oz inner copper (In2/In3), which IPC-2221 rates at about 1.3 A for 20 K against 2.6 A; +12V_PROT ran about 12 mm at 0.2 mm hugging C1's GND pad and the buck's input caps, and the path changed layers through single 0.3 mm vias (about 39 K each at 2.6 A with 18 um plating). Now, in `route_board.py` of both boards:
  * VBAT_IN, VBAT_F, SENSE_OUT, COMMON and +12V_PROT are their own router net class, restricted to F.Cu and B.Cu (`use_layer`, as for the planes), routed at 0.3 mm (still escapes the LM74930's 0.5 mm-pitch pins) with a 1.0/0.5 mm via (about 17 K);
  * after widening, each gets an F.Cu pour in a 2 mm band around its own F.Cu tracks (`add_battery_pours()`), so a track that hugs a pad on one side has copper on its free side. F.Cu carried no pour before.
  * Tried and dropped: routing only the current-carrying pins at 0.8 mm and adding the milliamp branches in a second FreeRouting pass. FreeRouting 2.2.4 cannot continue from a board with wiring (a NullPointerException on "to_trace_entries" seconds in, then it spins), protected or not; and the 0.8 mm pass alone left three other connections unrouted. `run_freerouting()` now also has a hard timeout, since a FreeRouting whose routing thread has died never exits.
  * `review/layout_checks.py` now rates these nets along the path the current takes (J2 -> F1 -> R1 -> Q2 -> Q1 -> the buck's VIN pins): the shortest track path between those pads, the copper width across each piece including same-net fill on its layer, and each via barrel. Copper to milliamp pins (LM74930 sense, gate-supply and VS pins, C2/C3, R2, the TVS, the buck's small caps and EN divider) is listed as branch length, not rated at 2.6 A. Before this, a 0.2 mm sense trace to a U1 pin failed the net.
  * Result, no battery copper on any inner layer on either board. **VBAT_IN and VBAT_F [ok]** on both (worst 6 K; VBAT_F's one via 0.5 mm). On the first route the router threaded SENSE_OUT from R1 to Q2 between R2's own 0603 pads at 0.3 mm (20 mW). display/ was then re-placed: `display/cells.py` pulls R2's VBAT_F end to R1's input pad (the Kelvin point RSET wants anyway) and C3's to U1's VS pin 22, beside its CAP pin, and places C3 before R2, so both sit on R1's input side and nothing is left between R1 and Q2. **display/ SENSE_OUT [ok]** after that (worst 2 K). display-rgb/ keeps the first route: it is to be replaced, with display/, by a generic brain board plus per-panel boards (owner decision, 2026-10-20), so it was not re-placed. What is left are short necks where the path meets a pin, each listed by the check with its resistance and dissipation at 2.6 A:

    | Net | display/ (re-placed) | display-rgb/ (first route) |
    |---|---|---|
    | +12V_PROT | 2.3 mm at 0.31 to 0.64 mm, the escapes into the buck's 0.4 mm VIN pins and at C5; 7 mW or less each | 0.4 mm at 0.56 mm; 2 mW |
    | COMMON | 2.0 mm at 0.3 to 0.7 mm, into Q2's source pins and below Q1; 5 mW or less each; no via | 3.6 mm in nine pieces of 0.3 to 0.4 mm length, 0.3 to 0.73 mm wide, below Q1 and into Q2's source pins; 2 to 5 mW each; no via |
    | SENSE_OUT | none [ok] | 2.6 mm at 0.3 to 0.38 mm between R2's pads (1.8 mohm, 12 mW for the longest) |

    The check still marks the nets with necks [FAIL] by IPC-2221's rule, which is for long uniform conductors; these are pinches of a few millimetres between wide copper and pads, on display/ the worst dissipating 7 mW (R1's own 2 mohm sense resistor dissipates 13.5 mW at the same current). Accepted for the prototype; look at them with a thermal camera at 2.5 A on the first board. The necks at the buck's VIN pins and the FETs' source pins are set by the pins' own width. The brain board inherits display/'s cells.py, so it starts from the re-placed front end.
  * Both boards routed with 0 unconnected under real DRC (display/ re-placed, third pipeline attempt; display-rgb/ third), plane check clean, outline unchanged (178.2 x 105.0 mm on display/); DRC only the accepted categories (solder_mask_bridge x10 at JP1/JP2, hole_clearance x4 at J17, plus warnings); `fab/build_fab.py display` passes. The re-route moved display/'s switch-node list (D-07 again): PANEL_BIAS_EN and PANEL_BL_PWM cross switch copper in plan view on In2 (the In1 plane between), +1V8 and EN_5V are clear, and PG_5V, the buck's own power-good pin, runs on F.Cu 0.15 mm from its switch copper beside U2. USB2_DP/DN are 40 and 37 mm with 35 and 29 mm on In3; the bench USB pair (J13) now has both legs on In3 (was In2 and In3).
* **display/ fast nets:** USB-C pair USB2_DP/DN about 39 mm, 30 mm of it on In3 with both legs together; the bench USB pair (J13) has its legs on In2 and In3. In2 and In3 are 0.11 mm apart (2116 prepreg), so broadside coupling between them is the remaining signal-integrity risk; switch-node plan-view crossings on In2/In3 (+1V8, PANEL_BIAS_EN, PG_5V) now have the In1 plane between them and the outer-layer switch copper.
* `review_netlist.py`: gauges 0 FAIL / 0 WARN; display unchanged from the committed board (1 FAIL, 6 WARN, all decoupling distances listed in section 8).
* Panel bias set to +5.98 V / -6.05 V (R38 511k, R40 499k), inside the ICNL9707's 4.5 to 6.5 V operating range with margin to its 6.6 V absolute maximum; `fab/README.md` adds a diode-test polarity check before JP1/JP2 are bridged.

## 8c. Brain board and panel boards, 2026-10-20

Owner decision: one centre-screen board for every car, two screen ports (MIPI DSI and LVDS), display/ and display-rgb/ replaced (`archive/`). display/ was split: `brain/` keeps everything that does not depend on the car or the panel (same designators), `panel-tsd/` carries the TSD panel's own circuits (J4, U6 TPS65131-Q1, U7 TPS61165-Q1, JP1/JP2, unchanged) plus the port input. Port pinouts: `tools/screen_ports.py` and `docs/screen-ports.md`. Measured on the regenerated boards:

* **ERC 0** on brain/ and panel-tsd/. **Real DRC 0 unconnected on both**; brain/ errors only `hole_clearance` x4 (J17 pegs, accepted), panel-tsd/ only `solder_mask_bridge` at JP1/JP2 (accepted). Both fab packages pass `fab/build_fab.py`'s gate. No track of any net on In1 or In4 on either board.
* **Brain fans** (`brain/fan_route.py`): every DSI and LVDS pair straight on F.Cu over In1, 0.16 mm, equal legs (DSI 5.35 mm, LVDS 35.16 mm), GND guards where the socket has a ground pin between pairs, GND stub vias behind the connector pads. Lessons on the way: a rectangular router fence as wide as the J1 end blocked the control contacts beside each fan (12 then 3 unrouted), and stub vias added after routing hit In3 tracks under the connector (1 short, 1 clearance). The fence is now a polygon that follows the fan with 0.15 mm margins, and the stub-via strip is fenced on every layer; `route_board.py` now counts shorts and clearance errors as a failed attempt.
* **Port 5 V**: each port's switched 5 V (TPS2557-Q1, 61.9 k, 1.61 / 1.81 / 1.98 A) routes like the battery path (outer layers, 0.3 mm, F.Cu pour). PORTA_5V 4 K at 1.98 A; PORTB_5V passes except a 0.7 mm neck at 0.45 mm (24 K). At 0.2 mm the first route rated both at 92 K.
* **Panel board DSI**: autorouted on F.Cu / B.Cu at 0.16 mm (the port's N-then-P order against the FPC's P-then-N order makes a crossing unavoidable on one side); skew inside a pair 1.9 to 5.5 mm, under 40 ps.
* `review_netlist.py brain`: 0 FAIL, 5 WARN (display/'s decoupling distances on U1, U2, U9; the U6 INN FAIL left with the panel). `review_netlist.py panel-tsd`: 0 FAIL, 2 WARN: C41 (U6 INN) and C50 (U7 VIN) now 3.4 and 3.3 mm from their pins against the 3.0 mm target, from 8.8 and 3.6 mm on display/ (the panel board has room, so the input caps lead their cells).
* Battery path on brain/ as display/ after D-02: VBAT_IN, VBAT_F, SENSE_OUT pass; short necks at the FET source pins (COMMON 2.1 mm down to 0.34 mm) and the buck's VIN pins (+12V_PROT 1.0 mm down to 0.56 mm).
* Open: whether the Verdin iMX95 runs DSI and LVDS as two independent screens (RFQ section 2 question 9); the FH12's per-contact rating and contact side (cable orientation).

## 8. Fix verification (both boards, final run 2026-10-17)

Full pipeline per board: `build_schematic.py`, `build_pcb.py`, `route_board.py` (FreeRouting, then its own real-DRC check), `run_drc.py`,
`build_bom.py`, then `fab/build_fab.py` (which refuses a board with unconnected nets or an unexpected DRC type) for both packages.

**gauges/** (157 parts + 6 mounting holes, 447.1 x 58.3 mm, unchanged outline):
* ERC: the same four known items (VDDA and buck VIN "not driven", J2 SWCLK input, +5V power flag), nothing new.
* Real `kicad-cli pcb drc`: **0 unconnected items**; 14 warnings, all in the four accepted categories (lib_footprint_mismatch 8, silk_edge_clearance 4,
  silk_overlap 1, silk_over_copper 1). One intermediate route had 6 real clearance errors (+3V3 vs GND on In1) and a later one left the LM74930 corner
  unrouted after D33 enlarged the LDO cell; D33 now sits with the sender pull-ups (6.8 to 13.4 mm from R16-R18) and the final route is clean.
* `review_netlist.py gauges`: FAIL 0, WARN 0, PASS 62 (before the review: 18 FAIL, 8 WARN). Decoupling (pad centre to pad centre): U1 VDD 3.4/3.5 mm,
  VDDA 4.5 mm, U2 3.8 to 4.4 mm, U4 input 3.3 mm, U5/U10 within 5 mm. Connector TVS parts 4.2 to 7.0 mm from the pins they protect.
* `layout_checks.py gauges`: no foreign track within 1.5 mm of SW/BOOT on any layer. Trunks are 0.6 mm; what is still 0.2 mm (VIN_PROT 41 mm,
  +5V 14 mm, VIN_FUSED 2 mm) are pad escapes and branches to milliamp loads (divider, DNP pull-ups, transceiver VBAT).
* BOM: 68 lines, coverage and value-spelling checks pass, 0 lines needing part selection. Harness lines follow docs/harness.md: DTM06-3S (J1), DTM06-6S
  with one sealed cavity (J7; there is no 5-way DTM), DTM06-2S (J9, J11), DTM06-08SA (J10), each with its wedge; J8 is an in-dash KK 254 cable, no DTM;
  20 AWG GXL for power, 22 AWG for signals.

**display/** (160 parts, 169 x 102 mm, from the committed c307bf5 plus D-01 and D-02):
* Real DRC: **0 unconnected items**; findings only in the categories `fab/build_fab.py` accepts: hole_clearance 4 (J17 USB-C pegs, accepted by the
  display session), solder_mask_bridge 11 (all at the intentionally open JP1/JP2 polarity jumpers), lib_footprint_mismatch 18, silk_over_copper 8, silk_overlap 3.
* `review_netlist.py display`: 0 pin FAILs on any IC, including the new TAC5112-Q1, TLV767-Q1 (3.3 V), TPS2557-Q1 and three TPD4E05U06-Q1. Remaining decoupling
  WARN/FAIL lines are placement distances (U6 INN 8.6 mm, U2 VIN 5.1/5.5 mm, U9 IOVDD 5.7 mm), not missing parts: the display session's open item.
* Battery path after D-02: VBAT_IN 1.5 mm for its whole 12 mm; VBAT_F 1.5 mm for 67 of 89 mm (the rest are pad escapes up to 1.2 mm); COMMON and SENSE_OUT
  partly widened (short runs around the LM74930). IPC-2221 is conservative for inner layers (its internal curve halves the external rating);
  the residual risk is the short 0.2 mm escapes, each under 2 mm long, which heat little: re-check on the first board with a thermal camera at 2.5 A.
* Still listed by `layout_checks.py display`: RT_5V and PG_5V on In1 under the buck's switch copper, PANEL_BL_PWM 0.3 mm from BL_SW (D-07).

Open items that need hardware to settle: pulse 2a on the bench (G-07, X-01); the 5 V loop on gauges (G-14); the sender-short test with the car off (G-08:
tie a sender wire to 14 V and measure +3V3); a first-article FPC fit check (U6-U9); the display backlight and series-FET temperatures at 85 C (D-04, D-05);
line-out distortion into the real head unit (D-11).

## 9. Product review for fabrication, 2026-11-03

Scope: gauges/, brain/ and panel-tsd/ as a restomod product for a 1966 Mustang that must work either with an ECU on CAN or with
the car's original analog wiring (stock senders, lamps, dimmer, points ignition, a cable-driven speedometer converted to a Hall
sender). The earlier passes checked each part against its datasheet pin by pin; this one checked how the circuits behave in the
car: at power-up, with the key off for weeks, with a reversed battery, with the grounds of a 60-year-old car, and with the stock
wiring on the inputs. Nothing has been built; every number below is a datasheet figure or a calculation and says which.

### 9.1 Findings and fixes

| ID | Sev | Board | Finding | Fix | Status |
|---|---|---|---|---|---|
| F-01 | High | gauges, brain | **LM74930 sense resistor on the wrong side.** The 5 mohm / 2 mohm sense resistor sat on the INPUT (fuse -> RSENSE -> HGATE FET) while ISCP and C were tied to the OUTPUT. TI SNOSDF6 rates ISCP and CS+ to CS- at +-0.3 V absolute maximum (6.1) and its short-circuit comparator compares ISCP with CS- (7.3.6); TI's own topology (Figure 8-1, 7-7) has RSENSE after the DGATE FET with C, ISCP and RSET on its top. With the old wiring ISCP sat 12 V below CS- at every power-up (output still at 0 V), throughout every OV-clamp cycle and on any output short, the short-circuit comparator could never trip on a forward overload, and an input dip below the held-up output would trip it falsely. Earlier reviews read "ISCP connected to C = 20 mV threshold" from the pin table without checking where the resistor was | Rewired to TI's topology on both boards: VIN -> HGATE FET -> COMMON -> DGATE FET -> SENSE_HI -> RSENSE -> output; C, ISCP and RSET on SENSE_HI, CS- on the output. `review/expected.py` now checks it pad by pad on the sense resistor as well as on the IC | fixed |
| F-02 | High | gauges, brain | **Reverse battery and negative pulses reached pins rated -1 V.** With RSENSE on the input, CS+, CS-, ISCP and VS (tied straight to the fused input) all saw the input. The unidirectional SMCJ33A conducted forward on a reversed battery (73 A on gauges, about 100 A on brain, until the fuse opened) and held the input at -1.2 V (ISO 7637-2 pulse 1) to -3.7 V (reverse battery): beyond the -1 V rating of those pins, with only the IC's ESD structures to carry the difference. So a reversed battery blew the board fuse (X-04) and likely the LM74930 too, although the LM74930 is there to block exactly that | Sense pins now sit on the output side. VS comes through a series diode (D34 gauges, D9 brain: one BAV99-Q section) with its 1 uF CVS; EN and MODE are tied to VS (gauges) or to the power latch (brain), never to the raw input. D1 is now an SMCJ33CA (bidirectional, same SMC footprint). `surge_sim.py`: reverse battery -14 V now draws 0 A and blows nothing; pulse 1 (-100 V, 10 ohm) holds the input at -39.8 V, inside the A pin's -65 V; the DGATE FET then blocks 13 + 39.8 = 52.8 V (SQJ460AEP 60 V). Positive pulses unchanged | fixed (bench-test pulse 1 and a reversed battery on the first board) |
| F-03 | High | gauges, brain | **No inrush limit on HGATE.** TI 7.3.2.1: "The CdVdT capacitor is required for slowing down the HGATE voltage ramp during power up for inrush current limiting" (Figure 8-1: RG 100 ohm + 10 nF with 100 uF out). Without it the output ramp is set by the HGATE FET's own gate charge (55 uA into tens to hundreds of pF), which into the 30 uF (gauges) and 110 uF (brain) of input capacitance is amps to tens of amps, above the 4 A / 10 A short-circuit thresholds: a board that might never start, or retry 32 times and latch off | RG 100 ohm + CdVdT 4.7 nF (gauges, R89/C61: 0.35 A, 0.48 A at the 75 uA maximum drive, 1 ms ramp) and 10 nF (brain, R87/C85: 0.6 A, 0.8 A maximum, 2 ms), plus the 100 nF input capacitor TI asks for (C62, C86) | fixed |
| F-04 | High | gauges, brain | **The breaker read the routing copper as well as the sense resistor.** TI 8.5.1: "Follow kelvin connection for connecting CS+ and CS- pin to external current sense resistor." With CS- on the output net the autorouter tapped it wherever was convenient. Measured on the first routes (`layout_checks.py`, track resistance including fill width): gauges CS- shared 6.0 mm of inner-layer VIN_PROT (10.2 mohm) and CS+ 1.8 mm (1.5 mohm) with the power path, in series with the 5 mohm resistor, so the 1.49 A breaker would trip near 0.45 A against a 0.40 A worst-case load: a board that shuts down during cranking. brain shared 0.43 mohm with its 2 mohm resistor (4.96 A down to 4.08 A) | The taps are now nets of their own (SENSE_TAP, CS_MINUS), joined to the terminals only inside the resistor's footprint: `tools/make_kelvin_footprint.py` writes a 1206 land pattern with two small copper pads bridged to the terminals and declared as a net tie, so no route can share power-path copper. Same two-terminal part. `layout_checks.py` checks the pad and pin nets. ISCP and RSET sit on SENSE_TAP, CS- on CS_MINUS; C stays on the FET drain | fixed |
| B-01 | High | brain | **The centre screen could not be restarted with the key, and never switched off.** The LM74930's EN was tied to the battery, so the 5 V buck ran whenever the battery was connected. The Verdin starts by itself only when VCC appears; once software powered it off (a deliberate shutdown, a low-battery policy, a crash that ends in power-off) only the bench button J9 or disconnecting the battery would start it again, and the key did nothing. And it could only suspend with the car parked: tens of mA (the module's suspend current is not published), a flat battery within weeks for a car that sits | **Ignition power latch**: EN = ignition (100 k / 33 k, R88/R89, filtered by C87) OR the module's CTRL_PWR_EN_MOCI, through one BAV99-Q section each (D10, D11), 100 k pull-down (R90). Ignition switches the board on and the module boots; the module holds the board on while it is on or suspended; when software powers it off with the key off the board falls to the LM74930's 2.5 uA shutdown current. Software decides how long to stay suspended (9.3). Datasheet: EN rising 0.8-1.05 V, falling 0.41-0.7 V, rated 0-65 V; 1.8 V minus a diode is 1.2-1.3 V, 12 V ignition gives 3.0 V, 6 V gives 1.5 V, a 100 V spike 25 V. The Verdin Carrier Board Design Guide confirms the module side: CTRL_PWR_EN_MOCI "remains high during sleep modes" (table 41), is low with no VCC, and every module boots when VCC is applied (3.2). The guide's own kill signal, CTRL_FORCE_OFF_MOCI#, was passed over: it is open-drain and undefined as VCC collapses, so its pull-up could re-enable EN and restart the module in a loop; the guide's own use of it needs a latching button IC. A software reboot with the key off drops CTRL_PWR_EN_MOCI during the cold reset, so it may end in power-off instead: run updates with the key on | fixed (measure sleep current on the first module) |
| B-03 | High | brain | **The module might never have started.** R44-R46 were 10 k "pull-ups" on CTRL_PWR_BTN_MICO#, CTRL_RECOVERY_MICO# and CTRL_RESET_MICO# to +1V8, which U3 only turns on after the module raises CTRL_PWR_EN_MOCI. Verdin Carrier Board Design Guide table 41: these are open-drain inputs with 100 k, 10 k and 100 k pull-ups on the module's own 1.8 V RTC rail; 2.20.3: "No external pull-up resistor is allowed on the carrier board" (recovery). With +1V8 still off the 10 k resistors overpower those pull-ups and hold all three low: reset is asserted, and a module in cold reset holds CTRL_PWR_EN_MOCI low (3.2, 3.3.3), so +1V8 never comes up: a possible deadlock at every power-on. In the off state they would also read as a held power button (over 5 s forces the module off, 3.2) | R44-R46 removed; the J8/J9 bench headers still short the lines to ground. R47 on CTRL_RESET_MOCI# stays (an output the guide says may be pulled up). Earlier checks compared these pins' names with the datasheet, not what the module expects on them | fixed |
| B-02 | Medium | brain | CVS was 100 nF; TI 8.2.2.1: "a minimum of 1-uF CVS capacitance is required" (fixed on gauges as G-17 on 2026-10-18, never carried over) | C2 = 1 uF 50 V 0805 on the new LM_VS node | fixed |
| G-30 | High | gauges | **Sender readings ruined by ground offset.** The senders return through the engine block (oil, coolant) and the tank and body (fuel); this board's ground is wherever J1's ground wire lands. The body-to-engine strap carries every body load's return current, so the two grounds commonly sit 10-500 mV apart (15-25 A of lights and blower through a few to tens of milliohms of strap and joints). The front end put 3.3 mA through the sender (1 k from 3.3 V), so a 10 ohm sender was only 33 mV: with the engine block 50 mV below the board's ground a hot engine, a full tank or high oil pressure read about -17 mV, which the firmware called a shorted sender (dashes on the gauge exactly when overheating matters). The stock gauges did not suffer this: their 5 V regulator drove the sender and gauge coil at 60-220 mA | Each sender's 1 k pull-up now hangs off SENDER_EXC, switched by U11 (TPS22918-Q1, the same part as brain U8/U15), and each ADC pin gets a 6.8 k bias resistor to SENDER_BIAS (MCU output PTE6). Firmware reads all three channels with the excitation on, then off: both readings carry the same ground offset, which cancels; the bias lifts the ADC pin 0.42 V so an offset down to about -0.48 V stays readable (a larger one is reported, not misread). The model, its algebra and the test: `software/gauges-fw/inc/senders.h`, `src/senders.c`, `test/test_inputs.c` (10 ohm read to 0.4 ohm with -50 mV; 40/73/300 ohm read to 0.6/0.6/2.5 ohm with offsets of +120, -300 and -420 mV) | fixed (firmware host-tested; first board: compare against a decade box with an offset supply) |
| G-31 | Medium | gauges | **Key-off drain through the senders.** The pull-ups were tied to +3V3, which stays up in VLPS: about 3 mA through each sender to ground with the car parked, about 9 mA on the 3.3 V rail, roughly 5 mA from the battery (3.5 Ah a month), three times the rest of the board. G-16's 1.4-1.8 mA key-off figure left it out | U11 and SENDER_BIAS are off in VLPS (`power_hw_s32k.c`) | fixed |
| G-32 | High (if fitted) | gauges | **Pull-ups fed from the always-on battery rail.** The Hall sender pull-up R43 (fitted) and the DNP pull-ups for ground-switched lamps (R60-R75) and an open-collector tach (R79) went to VIN_PROT: R43 drew 0.27 mA through R44/R45 forever and back-fed an unpowered sender; an oil-pressure switch is closed whenever the engine is stopped, so a fitted pull-up drew 3 mA per lamp channel with the car parked; and on a charge-lamp channel the pull-up would feed the alternator regulator's I terminal with the key off (a Ford 3G then energises its field from the battery: a flat battery overnight) | **VPULL**: U12, a TPS1H000-Q1 smart high-side switch (40 V, 1 ohm, 148 mA current limit set by R91 3.24 k, auto-retry, 0.5 uA off) from VIN_PROT, switched by the MCU (PTE2) and off in VLPS. R43, R60-R75 and R79 now pull up to VPULL, and VPULL also powers the Hall sender on J9's new pin 3 (J9 is now 3-way, DTM06-3S), so the sender no longer needs its own ignition tap. New footprint for U12: KiCad's HVSSOP-8 pads (0.5 mm at 0.65 mm pitch) broke the 0.2 mm clearance; `gauges/footprints/TI_DGN0008K.pretty` uses TI's 0.45 mm land pattern | fixed |
| G-33 | Medium | gauges | Car-CAN termination was two DNP 0603 resistors: an installer with a two-node ECU + cluster bus (the usual case) had to solder 0603 parts onto a finished board | R4/R5 fitted, switched in by the open solder jumpers JP1/JP2 (bridge both); `fab/build_fab.py` already accepts JP1/JP2 mask bridges by name | fixed |
| G-34 | Medium | gauges firmware | Dimmer: "lights on" needed 1.5 V on the ADC pin, a 6.4 V feed, above the 4 V bottom of the dimming range, so turning the knob down past about half read as "lights off" and put every screen back to daytime brightness at night | `IM_DIM_LIGHTS_ON_MV` 470 (a 2.0 V feed); test updated | fixed |
| G-35 | Medium | gauges, firmware | Tach from a points coil's negative terminal: the primary rings at roughly 3-4 kHz for a millisecond after each spark, and the 2.2 nF filter (6.8 kHz corner) and a fixed 100 us glitch filter let those edges through: two or three counts per spark | C56 10 nF (1.5 kHz corner, 106 us; 9000 rpm on 8 cylinders is 600 Hz) and adaptive blanking in `capture.c` (an edge sooner than half the last period is ignored, which a real engine or wheel cannot produce); host test with ringing at +3 and +6 ms after each spark | fixed (check against a timing-light tach on the first car) |

| G-38 | High | gauges, firmware | **The dash-light knob could not work with no bulbs on its circuit, and not with the engine running on any circuit.** A rheostat drops voltage only while current flows, and the cluster's input draws almost none. The review's answer, a resistor on the circuit, was wrong twice: 30 ohm 5 W overheats (6.9 W at 14.4 V), and even at 47 ohm the feed only falls to 76-90 % of battery, about 86-100 % on the firmware's 4-12 V bulb scale. Worse, the 22 k / 6.8 k divider read 14 V at full scale, so at the alternator's 14.4 V the ADC sat at full scale at every knob position | Owner's decision: a pulsed load on the board, nothing under the dash. D37 (BAV99-Q, both sections in series, 200 V), R105 (330 ohm 2512 1 W), Q4 (MMBT5551Q, 160 V NPN, AEC-Q101), R106 1 k and R107 47 k, driven from PTB2 (pin 32). R81 is now 4.7 k (18.75 V full scale) and C57 220 nF. Firmware switches the load on for one 10 ms poll every 250 ms while the lights are on, and reads the rheostat from the sag: source resistance = sag / load current, divided by feed / battery so that bulbs left on the circuit cancel. The two readings are 10 ms apart, so battery voltage does not enter into it. No learning and no flash. 20 mW on average; stuck on through a fault 0.48 W at 14.4 V, inside the part's rating, so nothing has to be fast enough to save it. Off in VLPS, in reset, and if the inputs task is quarantined. `test_inputs.c` tests it against a model of the circuit, which is what found the divider | fixed (first board: 9.5 step 6b; `IM_DIM_RHEO_FULL_OHM` = 12 ohm is an estimate until a real switch is measured) |
| G-37 | Owner request | gauges, firmware | **Two-wire VR speed sensors** (4R70W, AOD-E, some T56) needed a converter box. Owner's decision 2026-11-04: support them directly | New input: J12 (2-way KK 254, DTM06-2S pigtail), 47 k 200 V in each wire (R99, R100), 4.7 nF to ground on each (C68, C69), BAV99-Q to the rails (D35, D36), TLV7031-Q1 comparator (U13, AEC-Q100 Grade 1) with 680 k feedback through a 10 k isolator (R102, R101) and a 2 M + 2 M bias on IN- (R103, R104), output on PTA12 / FTM1_CH6 (pin 56). `review/vr_input_sim.py`: threshold about 106 mV peak (120 mV worst corner), one rising edge per tooth up to 120 V peak (onsemi AND8149's figure for what VR sensors can reach), no edges unplugged, 2.5 mA at most into the clamps. Differential and ungrounded, so it can share a sensor with a PCM; 1.1 uA from +3V3, so no switched rail and nothing added to the key-off budget. MAX9924 (differential, adaptive) was passed over: 5 V at 2.6 mA would need a switched rail, and ADI's datasheet could not be read from here. NCV1124 (fixed +-160 mV) is ground-referenced. Firmware: third capture channel; whichever input reports is used, faster reading wins | fixed (a signal generator on the first board, then the real sensor: the sim is not a measurement) |
| G-36 | Medium | gauges firmware | With the key off the four GC9A01 controllers stayed awake: VLPS entry switched off only the backlights ("the screens keep their last picture, dark"), so each kept its DC/DC converter, oscillator and panel scanning running on the always-on 3V3 rail. The datasheet gives no current, so this was never in a budget (`thermal_derating.py` assumes 10 mA each when running) | `gc9a01_sleep()` (Display Off, Enter Sleep Mode, datasheet 6.2.3) on all four before VLPS; the wake is a full reset, which re-inits them; host test added | fixed (measure on the first board) |

### 9.2 What changed on the boards

* **gauges/** 447.1 x 65.9 mm (was 65.6 mm tall; the FRONT cell is held to a flat 44 x 14 mm keep-in and the POWER zone may use 50 mm of width, so the new front-end parts add 0.3 mm). New parts: U11, U12, D34, R89-R98, C61-C67, JP1, JP2; R49 on the Kelvin land pattern. MCU pins PTD2 (SENDER_EXC_EN), PTE6 (SENDER_BIAS), PTE2 (VPULL_EN); PTD3 was passed over because it carries NMI_b. 2026-11-04: the VR input (G-37) adds J12, U13, R99-R104, C68-C70, D35, D36 and pin 56 (PTA12), in the SPEED+IGN zone. The dimmer's test load (G-38) adds Q4, R105-R107, D37 and pin 32 (PTB2) in the LAMPS+TACH zone, with R81 4.7 k and C57 220 nF. The outline did not change.
* **brain/** 184.8 x 104.9 mm (was 188.9 x 103.2; still inside the 105.54 mm inner opening). The input TVS D1 and the 100 uF hold-up capacitor C1 moved into the INPUT cell beside the fuse, which kept the bottom row's height after the front end gained seven parts. New parts: D9-D11, R87-R90, C85-C87; C2 is now 1 uF; R1 on the Kelvin land pattern.
* **panel-tsd/** unchanged: it is fed from brain's current-limited port switch and touches nothing in the car.
* Firmware: `software/gauges-fw` (senders, capture, dimmer threshold, the three new pins, VLPS entry); `make test` and the ARM build pass.

* **The dV/dt capacitors and the OV clamp.** While clamping, HGATE re-enables at 55 uA into CdVdT + Cgs, about 0.33 ms on gauges and 0.62 ms on brain, during which the output droops about 3 V: TI's Eq. 9 with the 0.10 V gap between V(OVF) and V(OVCLAMPF) asks for at least 6.7 uF (10.5 uF effective is fitted) and 62 uF (106 uF is fitted); at the worst-case 0.058 V gap 11.5 and 107 uF, about what is fitted. Should it fall short, the timer resets and the clamp rides through the load dump instead of breaking the circuit after 43 ms, which is not a hazard: Q2/Q3 stay within SOA at about 1 A and 8 V. Turn-off, which sets the surge peaks in `surge_sim.py`, is not slowed because RG isolates the capacitor.

* **Key-off drain, calculated (measure on the first board).** brain/ latched off: 2.5 uA typ (LM74930 shutdown, datasheet 5 uA max). brain/ suspended: unknown until the module is measured; the module datasheet gives no sleep figure. gauges/ in VLPS at 12.6 V: LM74930 0.67-0.78 mA, its OV/UV dividers 0.24 mA, the battery divider R19/R20 0.21 mA, about 0.5 mA more through the buck (its 12.5 k feedback divider, the LDO, the MCU, the sleeping screens, the transceivers, D33's leakage at 3.3 V): about 1.7 mA, or 1.2 Ah a month. Before this review the sender pull-ups and awake screens added at least 5 mA. If that matters for a stored car, the same ignition latch can go on gauges/ in a later revision, but its inputs then need protecting against the lamp wires that stay live with the key off (hazards, headlights), which would back-feed an unpowered 3V3 rail through their clamps.

### 9.3 The owner's decisions, 2026-11-04

* **Dimmer knob with no bulbs left on the instrument-lamp circuit: a pulsed load on the board, so nothing has to go under the dash.** Done: G-38. The owner first chose a resistor over a leftover bulb, on the review's word that either would work; it would not have dimmed usefully, and once that was clear the owner chose this. Still to do: measure a real switch's rheostat, because the 12 ohm full scale is an estimate (`docs/harness.md`).
* **ALT gauge: a voltmeter.** The stock gauge is a shunt ammeter (two small wires across a section of the charging wire). The cluster shows battery volts, and the owner expects that in every one of these cars; the ammeter wires are capped. Reading amps would need a differential shunt input on a later revision.
* **Variable-reluctance speed sensors (4R70W, AOD-E, some T56): supported directly.** Done: G-37.
* **Unsuppressed load dump (ISO 16750-2 test A, 101 V for 400 ms: a classic alternator whose battery terminal comes loose while charging): accepted.** Unchanged from section 4: the SMC TVS cannot absorb 400 ms; it fails short, the fuse opens and the board survives with the TVS replaced. TI's 200 V reference (SMBJ150A + SMBJ33A anti-series, VS behind 10 k and a 60 V zener) is there if that ever changes.
* **Brain power policy in software.** With the latch, Linux or Android decides: suspend at key-off, and after N hours (24-72 is a sensible default) wake on the RTC and power off, so a stored car draws microamps. Written for the Linux option on 2026-11-03 (48 h by default, `parked_poweroff_hours`; `software/linux/README.md`, "The parked car"), tested on a PC only: RTC wake, the power-off and the latch have never run on a module. Not done for the Android option. USB_1 goes client-only in the device tree, because USB_1_ID is not pulled up (guide 2.x, it is a bench port): noted for the image in the same README, as there is no device-tree source yet. **If the RTC alarm cannot be armed the owner asked for what car makers do**, so it does not sleep: three tries, then a power-off, as Android Automotive does after failed suspends (same README).
* **KK 254 friction-lock headers on the harness pigtails: accepted as they are.** The owner sees no issue with the friction lock in a dash, so no RTV, tie or latching connector is called for. Worth a look at the first car's connectors after some driving.

### 9.4 Fabrication readiness

| Board | Verdict | What remains |
|---|---|---|
| gauges/ | Ready for a first prototype run | First-article checks of the Amphenol FPC contact side against the Raystar tail (buy one set first); a sample order for the screens, which are rated -20 to +70 C (G-15); the VR input (G-37) has only been simulated, so step 6a of 9.5 |
| brain/ | Ready for a first prototype run, once a Verdin iMX95 module can be bought | The module is in sample status with a long lead time (P-06); its sleep current, the wake and the latch can only be proven on a real module. USB-C J17's peg clearance needs the board house's DFM check; screen-port FFC contact side (`fab/README.md`) |
| panel-tsd/ | **Hold until TSD answers** | The 39-pin FPC connector is inferred, not named by the panel datasheet: if it is wrong the board cannot take the panel. The +/-6 V polarity is covered by JP1/JP2. Backlight driver temperature (D-04) is untested. The RFQ in `docs/rfq-drafts.md` has not been sent |

Nothing has been built, so "ready" means every check that can be done without hardware passes. Live stock and pricing have not been checked for any board (`fab/combined_bom.csv`; the brain BOM also lists the dial's click switch and the optional MFi parts as still to choose).

### 9.5 First power-up, in this order

Use a current-limited bench supply (1 A at first), no Verdin module, no screens, no panel.

1. **Reversed supply:** -14 V on the battery pin for a few seconds. Expect about 0 A and an unblown fuse on both boards.
2. **gauges/ with the key off:** 12.6 V on J1 pin 1, ignition open. Program the firmware over SWD, then measure the key-off current after the countdown: about 1.7 mA expected (9.3 budget).
3. **brain/ with the key off:** 12.6 V on J2 pin 1, ignition open. Expect under 10 uA and no +12V_PROT or +5V.
4. **Key on, both boards:** watch the input current as the rails come up: no spike past about 1 A, no fuse or breaker trip. Check +5V, +3V3, +1V8 (brain: +1V8 only once a module raises CTRL_PWR_EN_MOCI) and, on gauges/, VPULL and J9 pin 3 at battery voltage.
5. **Breaker:** with an electronic load, confirm the trip near 1.5 A (gauges) and 5 A (brain).
6. **Senders:** decade box on J7 pins 3-5, 10 to 300 ohm, then with a bench supply lifting the box's ground -0.3 V and +0.1 V from the board's: `senders: ...` must read the same.
6a. **VR speed input (G-37):** signal generator on J12 through two 100 ohm resistors, floating: 20 Hz and 500 Hz sine. No speed reading at 60 mV peak, a steady reading from about 150 mV peak (the sim's 106-120 mV plus margin), and the same reading at 20 V peak. Unplugged it must read as no sensor. Then the real sensor, spun by hand, and against GPS on the first car.
6b. **Dash dimmer (G-38):** key on, 14.4 V bench supply through 0, 3, 6 and 12 ohm (at least 1 W) to J10 pin 8: `DashDimmerPct` about 100, 78, 52 and 0, and the same at 12.6 V. On a scope at pin 8, 40 mA-sized dips of 10 ms, four a second; with the supply off, none. Then the real switch, and read its ohms for `IM_DIM_RHEO_FULL_OHM`.
7. **Fit the module (brain):** confirm it boots at key-on, that CTRL_PWR_EN_MOCI stays high in suspend, that a falling edge on CTRL_WAKE1_MICO# wakes it, that the RTC alarm wakes it, and that software power-off with the key off drops the board to the step 3 figure (`software/linux/README.md`, L6). Measure suspend current.
8. **Screens one at a time**, then the surge tests from section 8 (pulse 1 and 2a) and the sender-short test (G-08). In the car: compare the tach against a timing light.

### 9.5a Second USB-C port on brain/, 2026-11-06

The owner asked for it for add-ons, on both cars. Design, sums and what's unverified: `audio-and-usb.md` section 2a. J19 on USB_1, 14 new parts (J19, U16, U17, D12, C88-C91, R91-R96), same outline, none of the 179 existing parts moved. Added to first power-up, after step 7: with the module fitted and USB_1 set to host, plug a USB 2.0 stick into J19 and read it, then flash once through J19 with a USB-A to USB-C cable and once through J13, and look at both on a USB eye test if one is to hand.

Found on the way, fixed: J17's VBUS had never been rated by `layout_checks.py`, and at 0.2 mm near the receptacle came out at 92 K for U11's 1.98 A limit. Both ports' VBUS now route like the screen ports' 5 V, and they're on the list: 7 K and 4 K.

Verification: ERC 0. Real `kicad-cli` DRC 0 unconnected, findings only in `fab/build_fab.py`'s accepted categories (hole_clearance x8, now J17 and J19). `review_netlist.py brain` 49 PASS, 0 FAIL, the same 5 WARN as before. `layout_checks.py brain`: under-width power copper 3.4 mm in all, against 5.5 mm on the last board, best of four full routes; COMMON's 1.1 mm neck at 0.3 mm (88 K) is unchanged, and the other necks are at 28 K or less. `usb1_topology.py`: both legs 43.6 mm to J19's first contact. `mech/build_assembly.py`: 0 clashes. `fab/build_fab.py brain` passes its gate.

### 9.6 Verification run for this section

ERC (gauges: the 4 known items; brain: 0); real `kicad-cli` DRC after routing; `review/review_netlist.py`, `review/layout_checks.py`,
`review/connector_audit.py`, `review/surge_sim.py`; `software/gauges-fw` `make test` (WSL) and `make arm-check`; `mech/build_assembly.py`
clash check with the new outlines. The Verdin module requirements were read from Toradex's Verdin Carrier Board Design Guide (docs.toradex.com/108140),
the LM74930 requirements from TI SNOSDF6 sections 6.1, 6.5, 7.3, 8.2 and 8.5.

**2026-11-04, after G-37, gauges/ only:** ERC (the same 4 items); real `kicad-cli` DRC, 0 unconnected; `review_netlist.py gauges` 72 PASS, 0 FAIL, with U13, D35 and D36 in it; `layout_checks.py gauges`, no FAIL; `connector_audit.py`; `thermal_derating.py` (R99 154 mW against 155 mW at 85 C, at 120 V peak with its other wire tied down, the worst case there is); `vr_input_sim.py`; `fab/build_fab.py gauges`; `mech/build_assembly.py`, 0 clashes, same outline. `software/gauges-fw`: `make test`, the ARM image with FTM1_CH6_7_IRQHandler linked, and nine deliberate mistakes in a copy of the VR logic, all caught. The TLV7031-Q1 requirements were read from TI SNOSDA5D. The first routes left COMMON at 0.2 mm on 0.5 oz inner copper, 37 K at 0.40 A, which only `layout_checks.py` noticed, so `gauges/route_board.py` changed twice: trunk nets now widen in rounds from the narrowest width up, so neighbours share the room, and a layout FAIL now counts as a failed attempt, like an unconnected net (this board took 4 attempts). brain/ and panel-tsd/ keep the old widening until they are next routed. Nothing has been built, so the VR input is still a calculation.

**2026-11-04, after G-38, gauges/ only:** ERC (the same 4 items); real `kicad-cli` DRC, 0 unconnected; `review_netlist.py gauges` 74 PASS, 0 FAIL, with Q4 and D37 in it; `layout_checks.py gauges`, no FAIL; `thermal_derating.py` (R105 481 mW stuck on at 14.4 V, 611 mW at 16 V, against 620 mW at 85 C); `fab/build_fab.py gauges`; `mech/build_assembly.py`, 0 clashes, same outline. `software/gauges-fw`: `make test`, `make arm-check`, `tools/check_pins.py`, and 26 deliberate mistakes in a copy of the dimmer logic, all caught in the end; the first pass let 6 through, which exposed a redundant line (removed) and tests too loose to notice the filter, the ceiling and the dead band. MMBT5551Q requirements read from Diodes Inc. DS42560 Rev 1-2, its pin-out from the drawing. Nothing has been built, so this too is a calculation and a model until step 6b.
