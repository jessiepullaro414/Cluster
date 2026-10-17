# Electrical design review of display/ and gauges/ (2026-10-17)

Scope: both boards before anything is fabricated. Nothing here has been built, powered or measured; every number is
a datasheet figure or a calculation, and each is labelled with how sure it is. gauges/ was reviewed and fixed. display/
was reviewed **read-only** (another session is editing it), against the committed version (git `HEAD`); its findings
are open items for that session or the owner.

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

**The three open items I would not ship the first board without deciding on (all need an owner decision):**

* **G-01** A sender wire shorted to battery while the car is off can pump the 3.3 V rail up to the wire voltage (the LDO cannot
  sink current and the 1 k pull-ups are tied to the rail). Everything on +3V3, the MCU and four displays, would see up to ~12 V.
* **D-01 / D-02** display/ battery path: the 5 A fuse feeds `VBAT_IN`/`VBAT_F` routed as 0.2 mm tracks on 0.5 oz inner layers
  (a 0.2 mm inner track carries about 0.23 A for a 10 K rise), and the TVS footprint is a 600 W SMB while the BOM orders an SMC part.
* **G-02** The GC9A01 modules (and the display panel) are rated -20 to +70 C / -30 to +80 C; the Verdin 85 C; a dash in the sun is hotter.

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
| X-01 | Medium | both | Q1, Q3 / Q1, Q2 | Same simulation: during pulse 2a the FET pair carries about 27 A for a few us while the input capacitance charges; PMV55ENEA IDM is 12.6 A (tp <= 10 us, 25 C, Nexperia 21 Mar 2016). It is a transient but twice the pulse rating | Bench-test ISO 7637-2 pulse 2a at Level III and IV; if it fails use FETs with 100 A+ pulse ratings (PowerPAK/DPAK, 60 V, VGS 20 V) | open |
| G-08 | High | gauges | R16-R18, D12-D14 | A wire shorted to the 14.4 V rail puts (14.4-3.3)/1k = 11 mA through each 1 k pull-up into +3V3: 123 mW in a 0603 (rated 62 mW at 85 C derated). With the car off the 3V3 load is a few hundred uA, the LDO cannot sink, so +3V3 rises toward the wire voltage and the MCU, four displays and the clamps (all fed from it) see up to ~12 V | R16-R18 are now 1206 (fixed the resistor). **The rail pump is not fixed**: options are a 3.6 V zener/TVS on +3V3 (needs an AEC-Q101 part with a retrievable datasheet), or moving the sender pull-ups to a rail that is fed through a series diode (costs ratiometric accuracy) | resistors fixed, pump **open** |
| G-09 | Medium | gauges | J7 pins 1-2, J8 pins 1-2, J7 pins 3-5, J9 pin 1 | These lines left the board with only a series resistor and a BAV99-Q (or nothing, on the CAN pairs) | D28 to D32: Littelfuse SM24CANB-02HTG (AEC-Q101, SOT-23, 24 V standoff, +-30 kV IEC 61000-4-2, 34 V clamp at 1 A) at the connector pins. Section 3 explains where a TVS is and is not justified | fixed |
| G-10 | Medium | gauges | R84, R85 | LPSPI2_SCK / SOUT run 441 / 428 mm to four modules (round trip about 6 ns on FR4) with a pad that has a 3.2 ns minimum rise time at 25 pF (S32K1xx DS Table 21) and no series resistor; the bus clock is 9.6 MHz (`panel_hal_s32k.c`) | 33 ohm series resistors at the MCU pins | fixed |
| G-11 | Low | gauges | R86 | Q2 gate had no defined level while the MCU pin is high-impedance (reset, boot) | 100 k pull-down | fixed |
| G-12 | Low | gauges | R87, R88 | TJA1043 EN and STB_N have no internal pull-downs (NXP TJA1043 Rev 6, IIL +-1 uA) | 100 k pull-downs, so the transceiver sits in its low-power state until firmware drives them | fixed |
| G-13 | Medium | gauges | VIN_FUSED, VIN_PROT, COMMON, +5V | `layout_checks.py`: those nets were routed at 0.2 mm on 0.5 oz inner layers (0.23 A at 10 K) against 0.30 to 0.45 A; the ladder widened only VIN_PROT | `TRUNK_NETS` now includes VIN_FUSED, COMMON, +5V; see section 8 for the routed result | fixed (check the final widths) |
| G-14 | Medium | gauges | U2, L1, C2, C45 | LMR33630-Q1 SNVSB26C Table 8-2 (B option, 1.4 MHz, 5 V): L = 2.2 uH, COUT 2 x 22 uF of 16 V parts. The board has L1 = 10 uH (LC product about 4 x larger, outside the range the internal compensation was tuned for) and 22 uF **10 V** parts that keep about 10 to 15 uF at 5 V (generic X7R bracket; Murata's curve not retrievable here). The datasheet says use 16 V or higher for 5 V outputs | Do a load-step and Bode check on the first board; if the loop rings, L1 = 3.3 uH and 16 V capacitors | open |
| G-15 | Medium | gauges | U6-U9 | Raystar RFA401280B-AYW-DNF1: operating -20 to +70 C, storage -30 to +80 C. VCI is specified 2.65 to 3.3 V and the 3V3 rail can be 3.35 V (TLV733P +-1.4 % over temperature), 46 mV over the operating maximum (GC9A01A abs max 4.6 V) | Owner decision: this is a commercial-temperature module in a dash. Choose a wider-range module or accept it; the 3.35 V is low risk | open |
| G-16 | Low | gauges | U3, R51/R52 | LM74930 cut-off: UVLO falling threshold 5.1 to 5.7 V; a cold-crank dip below that resets the board. Key-off supply current about 1.4 to 1.8 mA (LM74930 IQ 665 uA typ + divider ladders 0.45 mA + MCU/transceivers), about 35 to 45 mAh per day | Firmware must tolerate a reset on cranking; consider EN from ignition if the battery is not tended | open |
| G-17 | Low | gauges | C47 | LM74930 pin table says a 100 nF capacitor on VS; TI's example (8.2.2.1) says "a minimum of 1 uF CVS". VS is fed straight from the TVS-clamped fused node here | A 1 uF 50 V part needs a catalogue entry in `tools/passive_catalog.py` (off limits while the other session edits tools/) | open |
| G-18 | Low | gauges | R82, R83 | Arrow LED resistors: 245 mW at a 24 V jump start against 155 mW (1206 derated to 85 C) | Acceptable for a 60 s event; no change | open (accepted) |
| G-19 | Low | gauges | board | 447.1 mm long; JLCPCB's multilayer length limit is below 500 mm but check it for the chosen service. The routing is not solid planes (4.2 m of signal on In1, the GND layer) | Ask the fab; see section 7 | open |
| G-20 | Low | gauges | Q2 | Nexperia PMV37ENEA datasheet not retrievable here; pin order (1 G, 2 S, 3 D) matches the PMV55ENEA datasheet of the same package, but one community listing shows 1 G, 2 D, 3 S | Check the PDF before ordering | open |
| X-02 | Medium | both | Q1, Q3, D-series | Nexperia lists PMV55ENEA as not recommended for new designs (as found by a web search; the product page itself would not load here). PESD2CAN is also marked NRND, which is why SM24CANB was chosen | Confirm availability; the front end needs a replacement 60 V, 20 V VGS FET anyway if X-01 fails | open |
| X-03 | Medium | both | U3 (gauges), U1 (display) | `surge_sim.py`: a 35 V suppressed load dump for 400 ms keeps the OV clamp cycling; the LM74930's overvoltage circuit-breaker (T = 1.2 V x CTMR / 2.8 uA = 43 ms with 100 nF) then turns the output off for about 2.3 s (22.7 x 10^6 x CTMR). The owner's 24 to 27 V figure never reaches the clamp (it starts at 27.8 V minimum) | Fine for a 27 V requirement; for ISO 16750-2 test B (35 V) raise CTMR (470 nF gives 200 ms) after checking Q3's SOA, or accept a 2 s blackout | open |
| X-04 | Low | both | D1 | A unidirectional TVS conducts forward in a reverse-battery event: -14 V gives 73 A (gauges) / 100 A (display) through the fuse, which opens. The LM74930's reverse blocking is never the protection. TI's reference puts a diode in series or uses a bidirectional TVS | Intent: confirm that "reverse battery blows the 2 A / 5 A fuse" is acceptable (the fuse is a board-mounted holder behind the dash) | open |
| D-01 | High | display | D1 | BOM and schematic value say SMCJ33A (1500 W, SMC package) but the footprint is `Diode_SMD:D_SMB` (a 600 W SMBJ class part); the simulation used the SMCJ rating | Change the footprint to `D_SMC` or the part to SMBJ33A and rerun the surge simulation (SMBJ33A: 11.3 A at 53.3 V) | open (display/) |
| D-02 | High | display | VBAT_IN, VBAT_F, +12V_PROT | `layout_checks.py` on HEAD: the battery path before the LM74930 (`VBAT_IN`, `VBAT_F`, `COMMON`, `SENSE_OUT`) is 0.2 mm on In1/In2 (0.5 oz); `TRUNK_NETS` does not list VBAT_F or VBAT_IN. It carries up to 2.6 A (5 A fuse) | Add VBAT_IN, VBAT_F, COMMON, SENSE_OUT to `TRUNK_NETS` (or route as inner-layer planes); re-run `layout_checks.py display` on the regenerated board. The working tree was mid-regeneration (no zones, unrouted) so I could not check it | open (display/) |
| D-03 | Medium | display | C46, C47 | Schematic value says "22u VPOS out 16V" but `passive_catalog` maps 22 uF 1206 to the 10 V GCM31CR71A226KE02L. At 6.5 V that part keeps 3 to 12 uF (bracket), TPS65131 wants 22 uF at the outputs (Fig 8-1) | Use a 16 V 22 uF part (1210) and add it to the catalogue | open (display/) |
| D-04 | Medium | display | U7, L4 | TPS61165-Q1: 2.7 W of LED power at 82 to 90 % efficiency is 0.3 to 0.6 W in a SOT-23-6 with RthJA 210 C/W (JEDEC; about 100 to 150 on this board): 116 to 213 C at 85 C ambient; thermal shutdown 160 C | Estimate only. Plan to reduce the backlight with temperature in software, or a driver with a power package; check on a prototype at 85 C | open (display/) |
| D-05 | Medium | display | Q1, Q2 | Each PMV55ENEA at 1.4 to 2.5 A: 163 to 521 mW, 128 to 222 C junction on the standard footprint (RthJA 262 C/W), against 150 C maximum; ID 3.1 A is only rated with a 6 cm2 drain pad. Verdin power is unpublished (Toradex datasheet Rev 0.7 6.3) | Parallel FETs or a power package; get the module's real current | open (display/) |
| D-06 | Medium | display | DSI | `dsi_impedance.py`: 0.25 mm over 0.21 mm prepreg gives 102 ohm at a 0.25 mm gap, but the measured gap along the pairs ranges 0.25 to 1.2 mm (mean about 0.6), so the coupled sections are 102 to 120 ohm, and the 2.5 to 3 mm B.Cu swap is two uncoupled 60 ohm legs (about 120 ohm). The boards carry no stackup block, so the fab applies its default | Order with controlled impedance, 100 ohm differential on F.Cu referenced to In1 with the real JLC04161H-7628 stackup, and ask the fab for its calculated width/gap | open (display/) |
| D-07 | Low | display | PG_5V, PANEL_BL_PWM, USB_ID, EN_5V | `layout_checks.py`: signal tracks within 1.5 mm of switching nodes (PG_5V on In1 directly under one) | Re-check on the regenerated board; none is fast | open (display/) |
| D-08 | Low | display | J3, J8, J9, J12, J13, J11 | J3 (private CAN) has no ESD part; bench headers are unprotected by design; J11 dial clamps turn on near 2.5 V, a little above the ADC's 2.1 V maximum (the design's own note) | A SM24CANB-02HTG on J3 if J3 leaves the dash (TCAN1044 itself is rated 8 kV J2962-2 system level) | open (display/) |
| D-09 | Low | display | J4 | The panel (Team Source TST040HDBC-42) datasheet could not be found online, so the 39-pin table, the FH26 connector and the +-6.5 V polarity conflict are not independently verified | Get the PDF from TSD | open |
| D-10 | Low | display | U9-U14, J14-J17 | The audio codec, USB host and other additions in the working tree were not reviewed | Extend `review/expected.py` for them after that session commits; the existing display tables pass on the working-tree netlist | open |
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
| gauges J7.3-5 | sender wires | long wires to the tank and engine, shorts to battery | **D29, D30** (24 V standoff, clamp 34 V at 1 A), series 1 k, BAV99-Q at the ADC pin, 1206 pull-ups | These are low-impedance nodes (1 k pull-up), unlike the 33 k inputs. The TVS covers spikes, not a sustained short (G-08) |
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
  under 15 mW). Faults: R16-R18 123 to 562 mW (G-08, now 1206); R82/R83 245 mW at a 24 V jump start (G-18); R43 190 mW if the Hall wire is
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
Abracon ABM8AIG; Tag-Connect TC2030-CTX; Littelfuse SM24CANB (10/09/17).
Not obtained: PMV37ENEA, PMEG6010ELR, BAV99-Q (the series Rev 8 was used), SMCJ33A (distributor-listed Vc/Ipp used, pulse-rating curve approximated),
Littelfuse 297 fuse (I2t), Murata capacitor bias curves, Amphenol F32Q, Hirose FH26, Keystone 3568, panel TST040HDBC-42, ISO 7637-2 itself.

## 8. Fix verification (gauges/)

Pipeline run after the changes: `build_schematic.py`, `build_pcb.py`, `route_board.py`, `run_drc.py`, `build_bom.py`, in that order.

* ERC: the same four categories as before (VDDA undriven, J2 SWCLK pin, buck VIN undriven, +5V power flag), no new ones.
* Placement self-checks: no overlapping footprints, every net's pin count matches between schematic and PCB (91 nets).
* Routing: FreeRouting then `route_board.py`'s own check: **0 unconnected items**, and `run_drc.py` (real `kicad-cli pcb drc`) reports 0 unconnected
  items and 14 warnings in the four accepted categories only (lib_footprint_mismatch 8, silk_edge_clearance 4, silk_over_copper 1, silk_overlap 1), the same set as before.
* Board size unchanged: 447.1 x 58.3 mm. 156 parts plus 6 mounting holes (was 143 parts).
* `review_netlist.py gauges`: FAIL 0, WARN 0, PASS 61 (before the fixes: 18 FAIL, 8 WARN).
* Decoupling now measured from the routed board (pad centre to pad centre): U1 VDD 3.4 and 3.5 mm, VDDA 4.5 mm, U2 3.8 to 4.4 mm,
  U5 and U10 supply capacitors within 5 mm, U4 input 3.3 mm. Connector TVS parts sit 4.2 to 7.0 mm from the pins they protect.
* Trunk widening: VIN_FUSED, COMMON and most of VIN_PROT and +5V are now 0.6 mm. `layout_checks.py gauges` still lists some 0.2 mm
  pieces (VIN_PROT 81 mm on In1 and +5V 24 mm, both branches to low-current loads such as the DNP pull-ups, the divider and the transceiver VBAT pin);
  the 0.40 A trunk itself is 0.6 mm (6 K rise on 0.5 oz inner copper).
* BOM: 64 order lines for 154 placements, coverage and value-spelling self-checks pass; new line SM24CANB-02HTG; R16-R18 now 1206 (AC1206FR-071KL, pattern entry).

Open items that need hardware to settle: pulse 2a on the bench (G-07, X-01), the 5 V loop (G-14), the sender short test (G-08), a first-article FPC fit check (U6-U9), and the display items D-01 to D-10 once the other session commits.
