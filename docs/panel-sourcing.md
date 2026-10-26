# Centre-screen panels you can order directly (searched 2026-10-25)

TSD (TST040HDBC-42) and Anders (part 12575) have not answered the RFQs in `rfq-drafts.md`,
probably because the quantities are small. These round panels are sold online or through
distributors in ones and twos. Specs are from the sellers' pages; nothing here has been measured.
All of them speak MIPI DSI, so each fits the brain board's port A (`docs/screen-ports.md`) with its
own small panel board.

| Panel | Size, active area | Resolution, interface | Brightness | Temperature | Where, price | Notes |
|---|---|---|---|---|---|---|
| **DisplayModule DMKTT0340F2NA** | 3.4 in round, 87.6 mm | 800 x 800, MIPI DSI, ILI9881C, I2C touch | **850 cd/m2** (seller page) | **-30 to +80 C** | [displaymodule.com](https://www.displaymodule.com/products/3-4-inch-round-tft-lcd-800x800-mipi-dsi-capacitive-touch), $79, samples in stock, 3-week bulk | Brightest round panel with a temperature range for a car. 87.6 mm fits a stock ~89 mm speedometer hole uncropped (the 4 in panels need the custom faceplate). The 850 figure is only on the seller's page: ask for the datasheet with the sample. |
| **Waveshare 4-DSI-TOUCH-C** | 4 in round | 720 x 720, 2-lane MIPI DSI, JD9365, GT928 touch | 550 cd/m2 | 0 to +60 C (storage -10 to +70) | [waveshare.com](https://www.waveshare.com/product/luckfox/4-dsi-touch-c.htm), about $60-70, in stock | A finished module: it makes its own panel supplies, takes 5 V (0.3 A minimum) and a Raspberry Pi 22-pin DSI ribbon, and dims over I2C (device 0x45). Its panel board would be a simple adapter. Consumer temperature range: bench and first prototype, not the car. Linux has a JD9365 panel driver. [Wiki](https://www.waveshare.com/wiki/4-DSI-TOUCH-C) |
| Midas MDT0340AIS-MIPI | 3.4 in round | 800 x 800, MIPI | 380 cd/m2 | see datasheet | Farnell (order code 4248104), RS | A real datasheet and distributor stock, but dim. |
| Allshore ASI-T-400R72A3MPN/X | 4 in round, 101.52 mm | 720 x 720, 4-lane MIPI, FL7703 | 350 cd/m2 | see [datasheet](https://www.allshore.com/portals/0/PDFs/ASIT400R72A3MPNX.pdf) | allshore.com (US), cart or quote | Same size as the TSD panel, dim. |
| Newhaven NHD-2.1-480480AF-ASXP | 2.1 in round | 480 x 480, 1-lane MIPI or RGB, ST7701S | 1000 cd/m2 | -20 to +70 C | Newhaven, Mouser, about $20 | Too small for the centre. |

Not sold off the shelf: the 4 in 720 x 720 round panels from Shenzhen factories (Yousee, Microtech,
LCD Mall), which look like the same class of glass as the TSD panel. Their trade-platform listings
do take sample orders, though: see the 4 in section below.

Small gauges: 1.28 in GC9A01 round modules are stocked everywhere (Elecrow, AZ-Delivery,
DisplayModule DM-TFTR128-446 at 400 cd/m2), but every one found is rated -20 to +70 C operating;
none wider was found (same as review item G-15).

## 4 in round options (2026-10-25, after "3.4 is too small")

The dash opening is 105.5 mm tall, so a 4 in round (101.5 mm active circle) is about the largest
that fits. No 4 in round at 800 nits is sold off the shelf; the 800-nit ones come from factories
that sell through trade platforms, where sample orders of 1-5 pieces are normal.

| Panel | Brightness | Temperature | How to buy | Notes |
|---|---|---|---|---|
| Waveshare 4-DSI-TOUCH-C | 550 cd/m2 | 0 to +60 C | In stock: waveshare.com, Robotshop | Complete module, 5 V + Pi 22-pin DSI ribbon; brightest 4 in round in stock |
| Microtech MTF040HD22A-V1 | 800 cd/m2 typ (listing title says 1000) | not stated | Factory, via its [HKTDC listing](https://www.hktdc.com/event/electronicasia/en/product/1Z03L0778) (or Alibaba); production lead time 25-45 days | 720 x 720, MIPI; same class as the TSD panel, likely the same glass |
| LCD Mall LMT040SV001U | 800 nits (listing) | not stated | Factory, via [Global Sources](https://www.globalsources.com/Dot-matrix/LCD-display-1219087130p.htm); 7-30 days | 720 x 720, MIPI, FL7707 driver; supplier not verified by the platform |
| Allshore ASI-T-400R72A3MPN/X | 350 cd/m2 | see datasheet | allshore.com (US distributor) | FL7703 driver |
| FanyiTek 4 in round (Newegg) | 300 nits | not stated | Newegg, about $150 | Needs its own 5 V |
| Shenzhen Yousee YX40023A | 300 cd/m2 | not stated | Factory | ICNL9707AC-03 driver |
| Adafruit 5793 (round RGB) | not stated | not stated | adafruit.com, $54.95 | Parallel RGB, would go on port B through an LVDS-to-RGB receiver |

### Sample request for the 800-nit factories (send through the platform's message or RFQ form)

> We are building a small batch of automotive instrument clusters and would like to buy 2 samples
> of your 4.0 in round 720 x 720 MIPI TFT (MTF040HD22A-V1 / LMT040SV001U), with a production
> quantity of about 20-50 a year. Please send: the full datasheet (FPC pinout, supply voltages and
> currents, backlight LED configuration and current), the driver IC's initialisation code, the
> measured brightness and operating temperature range, the sample price with shipping to the USA,
> and the lead time. We can pay through the platform.

## Suggested order (revised 2026-10-25: 3.4 in is too small)

1. **Waveshare 4-DSI-TOUCH-C** now: right size, 550 nits, in stock, almost no adapter. Bench first,
   and a real-car brightness check under the dash hood.
2. **Samples from Microtech and LCD Mall** (800 nits) through their platforms with the message above,
   as the car candidates; one of them may be the TSD panel's glass, which `panel-tsd/` already fits
   if the FPC pinout matches.

Each needs its own panel board (like `panel-tsd/`) and a panel-ID resistor (`tools/screen_ports.py`).
