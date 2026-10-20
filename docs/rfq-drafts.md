# RFQ drafts (not sent)

Drafts for the vendor questions that block hardware ordering. Edit the sender details and send them yourself; nothing here has been sent.

## 1. Team Source Display: TST040HDBC-42 (4.0in round, 720x720, MIPI)

Subject: TST040HDBC-42 (V1.0, 2023-06-29): questions before a prototype order

Hello,

We are designing a carrier board around your TST040HDBC-42 for an automotive instrument cluster (one unit per board, prototype quantity first). Your datasheet V1.0 leaves a few points open, and one point is contradictory. Could you confirm:

1. **Analog supply pins.** The interface table (section 3) lists pins 7-8 as VSP (+6.5 V) and pins 10-11 as VSN (-6.5 V). The mechanical drawing's pin header row shows pins 7-8 as VDD(-6.3 V) and pins 10-11 as VDD(+6.3 V). Which is correct, and what are the exact voltage tolerances? Please also give the supply currents (input current is listed as TBD).
2. **FPC.** What connector mates with the 39-pin FPC (we assume 0.3 mm pitch from the 12 mm tail width)? Which side are the contact fingers on, and can the FPC be built with the fingers facing either direction?
3. **Initialisation.** Please send the ICNL9707 initialisation command sequence (DCS) and the recommended DSI timings: lane count (we plan 3 lanes), clock rate, porches, refresh rate.
4. **Power sequencing.** The required order and timing for IOVCC, VSP/VSN, reset and the backlight.
5. **Backlight.** The backlight is listed as 20 LEDs, 180 mA, Vf 15 V. Is that 5 series x 4 parallel? What is the maximum current at 80 C ambient, and what PWM dimming frequency range do you recommend if we dim with PWM?
6. **Commercial.** Price at 5 and 50 pieces, minimum order quantity, lead time, and whether the module is in current production.
7. **Environment.** Is the -30 to +80 C operating rating at full brightness, and is there a derating curve for backlight current versus temperature?
8. **(added 2026-10-19) VSP/VSN level.** The ICNL9707 data sheet (Chipone V0.03, section 4.2) gives VSP 4.5 to 6.5 V (typical 5.5 V) and VSN -6.5 to -4.5 V, with absolute maxima of +6.6 V and -6.6 V. Your sheet gives 6.5 V typical, at the top of that range. We have set our supplies to +5.98 V and -6.05 V for margin. Is that inside what this module needs (the charge pumps for VGH/VGL), or do you require 6.5 V, and with what tolerance?

Thank you,
(name)

## 2. Toradex: Verdin iMX95 in an Android Automotive instrument cluster

Subject: Verdin iMX95 (PN 0089): Android Automotive support and suspend behaviour

Hello,

We are building a custom carrier for the Verdin iMX95 Hexa 8GB WB IT (0089, V1.1B) as an Android Automotive instrument cluster. Could you tell us:

1. Is there a Toradex-supported or planned path for Android or Android Automotive on the production Verdin iMX95? NXP's automotive-16.0.0_1.3.0 lists only the NXP i.MX 95 19x19 EVK, and the Verdin EVK is end of life.
2. Which development carrier should we use with the iMX95 module (the Verdin EVK replacement, PN 05241104, or a Verdin Development Board)?
3. Does the module support suspend-to-RAM with wake on CTRL_WAKE1_MICO# (X1 pin 252)? What is the typical suspend current of the module, and what is the resume time to first frame? Is the wake input active-low and level or edge triggered?
4. Where can we find the System Manager board configuration for the production module, since NXP's tree builds the System Manager with the EVK regulator configuration?
5. Is a power consumption table (typical and maximum VCC current) available yet?
6. (added 2026-10-18) Ordering: your PCN for 00891000 says V1.0A is end of life, V1.0B (00891001) had limited samples from February 2026 and V1.0C (00891002) samples from Q2 2026. Which revision should a new design order, what is the current lead time for 5 and for 50 pieces, and when is the WB IT variant planned to leave the sample phase? Distributors show no stock and up to 34 weeks.
7. (added 2026-10-18) Thermal: we follow your carrier design guide V1.2 sections 4.3 to 4.5 (S1/S2 2.5 mm M2 standoffs, S3/S4 7.0 mm for the Verdin Industrial Heatsink). Our module sits in a closed dashboard at up to 85 C ambient. Please send the Verdin Industrial Heatsink Type 1 datasheet (outline, height above the carrier, thermal resistance) and say whether the iMX95 at about 5 W typical can run there without throttling, or what heat path you recommend instead (a heat spreader to a metal housing, for example).
8. (added 2026-10-18) The Linux alternative: we are also evaluating Linux (your BSP / Torizon) with an open-source CarPlay and Android Auto receiver on this module. Does your BSP support the Verdin iMX95's hardware video decoder through V4L2 (for GStreamer's v4l2h264dec / v4l2h265dec), the MAYA-W260 Wi-Fi access-point mode together with Bluetooth, and suspend-to-RAM?

Thank you,
(name)

## 3. 5 in round panel at 800 nits or more (drafted 2026-10-08, not sent)

Findings behind this draft (web checks on 2026-10-08): every standard 5 in round MIPI panel listed by [Kingtech PV05003SYS50B](https://www.kingtechdisplay.com/products/ips-5-0-inch-1080-1080-mipi-interface-round-tft-display.html), [Tailor Pixels TTG050BRT-01](https://tailorpixels.com/product/5-inch-ips-tft-round-display-1080-1080/), [DisplayModule DM-TFTR50-413](https://www.displaymodule.com/products/5-0-inch-1080x1080-tft-display-mipi-hx8399-dm-tftr50-413), IFANTEK and YOURITECH (ET050CIR01) appears to be the same panel: 1080x1080, HX8399C, 4-lane MIPI, 50-pin board connector, 136.53 x 132.2 x 1.98 mm, 127.0 mm active circle, **350-400 nits, -20 to +60 C**. None lists 800 nits. The vendors look like resellers of one panel, so the first task is to find who makes it.

To: Kingtech, Tailor Pixels, Panox, IFANTEK, YOURITECH (any that answer), and TSD (maker of the 4 in automotive round panel we already use).

Subject: 5 in round 1080x1080 MIPI panel, 800+ nit, automotive temperature, custom backlight

We are building a classic-car instrument cluster product and need a 5 in round panel (127 mm active circle, 1080x1080, MIPI DSI) that is readable in direct sunlight. The standard HX8399C 5 in round modules we found are 350-400 nits and -20 to +60 C. Could you tell us:

1. Is your panel the HX8399C, 136.53 x 132.2 x 1.98 mm module, and who is the panel maker?
2. Can you build it with a backlight of at least 800 cd/m2 (1000 preferred), typical, measured at the module? What would change (LED count, current, forward voltage, brightness-enhancement films)?
3. Can the operating range be -30 to +85 C (storage -40 to +90 C), and what is the backlight life at 800 nits and 85 C?
4. Optional sunlight options: anti-reflective or anti-glare, optical bonding to a cover glass, PCAP touch (we may not use touch).
5. The 50-pin board connector: manufacturer part number, mating part, pinout, power-supply voltages and currents, DSI lane count and timing, the initialisation sequence, and whether TE and reset are available.
6. Quality: automotive grade or IATF 16949 production, PPAP capability, and long-term supply (10 years or more).
7. Commercial: price at 5, 50 and 500 pieces, NRE for the custom backlight, minimum order quantity, sample lead time and production lead time.

Our own side: the panel will sit in a housing about 140 mm across; we need the connector/FPC tab position drawing (the 136.53 mm dimension is along the tab).

## 4. Anders: 4.2 in circular high-bright display, part 12575 (drafted 2026-10-08, not sent)

Found on [Anders' product page](https://www.andersdx.com/4.2inch-circular-high-bright-ipstft-display/?tab=specifications) (specification tab, read 2026-10-08): 4.2 in IPS, 720 x 720, active area 105.84 x 105.84 mm, **1300 cd/m2**, contrast 1000, **RGB interface**, module 114.85 x 118.37 x 16.83 mm, **-30 to +85 C**. Not on the page: driver IC, connector and pin count, touch options, backlight current and voltage, timing, storage temperature, lifecycle, MOQ, price. The page offers a datasheet by email form.

To: info@andersdx.com

Subject: Part 12575, 4.2 in circular high-bright display: datasheet, sample, and larger sizes

We are building a classic-car instrument cluster product and are evaluating your 4.2 in circular high-bright display (part 12575). Could you send:

1. The full datasheet and a 2D/3D drawing: connector manufacturer part number and mating part, pinout, driver IC, the SPI/I2C initialisation sequence, RGB timing (pixel clock, porches), supply voltages and currents, backlight LED string (current, forward voltage) and how brightness is dimmed (PWM frequency range).
2. Storage temperature, expected backlight life at 1300 nits and 85 C, and whether the display is built to an automotive quality standard (IATF 16949 / PPAP).
3. Is the 16.83 mm module thickness the display plus backlight only, and does it include any bonded cover glass or touch layer? Are optical bonding, anti-glare and PCAP touch available?
4. Price at 5, 50 and 500 pieces, sample lead time, minimum order quantity, and expected long-term availability.
5. You list circular displays from 1 to 7 in. Do you have a high-bright circular display larger than 4.2 in (4.5 to 5 in) at 800 nits or more, with RGB, LVDS or MIPI?

Our side: we will drive it from an NXP i.MX 95 module through an LVDS-to-RGB receiver, 720 x 720 at 60 Hz.

## 5. Raystar: RFA401280B-AYW-DNF1 (1.28 in round GC9A01 module), firmware questions (drafted 2026-10-15, not sent)

To: salescontact@raystar-optronics.com (the same contact as the order; see `gauges/build_bom.py`).

We are driving four RFA401280B-AYW-DNF1 modules over 4-line SPI from an NXP S32K144. The datasheet gives the pinout and electrical limits but no initialisation sequence. Could you send:

1. **The recommended GC9A01 initialisation code for this exact module**, including the undocumented registers (the 84h to 8Fh, 90h, 62h to 67h, 70h, 74h, 98h group and the EBh, BCh, BDh, BEh, DFh, E1h, EDh values), the gamma tables (F0h to F3h), the power controls (C3h, C4h, C9h) and the frame rate (E8h). We are using the values from the open-source Zephyr driver as a stand-in.
2. **Whether the module needs display inversion (21h)** and which **MADCTL (36h)** value gives the upright, RGB-correct image with the FPC tail at the bottom.
3. **The maximum SPI clock** you qualify (the controller allows a 10 ns write cycle; our MCU limits us to 10 MHz, but we want to know if you restrict it) and whether SDA can be driven at 3.3 V logic with VCI = 3.3 V as planned.
4. **Reset and power-up timing**: how long RESET must be held low, and how long to wait after it and after Sleep Out (11h) before the next command and before Display On (29h). We currently use 10 ms, 120 ms and 150 ms.
5. **Backlight**: the VLED+ and VLED- current limits and whether PWM dimming is allowed (frequency range). We switch it with a transistor and may add PWM.
6. Whether the **TE** pin is useful for tear-free updates when writing small windows, and whether the **touch controller** (CST816D) can be left unpowered.

## 6. Small round gauge displays for a dashboard (drafted 2026-10-18, not sent)

To: Raystar (maker of the RFA401280B-AYW-DNF1 we designed around), Winstar, DisplayModule.

Subject: 1.28 in round 240x240 GC9A01 TFT, operating range -30 to +85 C

We use four 1.28 in round 240x240 TFTs (GC9A01, 4-wire SPI, 18-pin 0.5 mm FPC) in a classic-car instrument cluster. Behind a windscreen in the sun the dashboard runs hotter than the -20 to +70 C operating range every standard module we found lists. Could you tell us:

1. Can the module be built for -30 to +85 C operation (storage -40 to +90 C)? Which part limits it today (the LC fluid, the polarizer, the backlight)?
2. Brightness: the standard modules are about 400 cd/m2; what is the highest backlight option, and its forward voltage and current?
3. Can the FPC keep the RFA401280B-AYW-DNF1 pinout and outline (50.20 x 50.20 x 3.99 mm, 32.40 mm active)? If not, please send the drawing.
4. Price at 20 and 200 pieces, NRE, minimum order quantity, sample lead time, and expected product life.

