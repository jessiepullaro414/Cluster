# RFQ drafts (not sent)

Drafts for the two vendor questions that block hardware ordering. Edit the sender details and send them yourself; nothing here has been sent.

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
