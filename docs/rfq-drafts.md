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
