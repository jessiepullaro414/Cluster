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

Not orderable directly: the 4 in 720 x 720 ICNL9707 round panels from Shenzhen factories (Yousee,
Microtech MTF040HD22A-V1, which claims 1000 nits) look like the same glass as the TSD panel and have
the same small-quantity problem.

Small gauges: 1.28 in GC9A01 round modules are stocked everywhere (Elecrow, AZ-Delivery,
DisplayModule DM-TFTR128-446 at 400 cd/m2), but every one found is rated -20 to +70 C operating;
none wider was found (same as review item G-15).

## Suggested order

1. **DisplayModule DMKTT0340F2NA sample** (the car candidate) and ask for its datasheet: FPC pinout,
   supply voltages, backlight current, init code.
2. **Waveshare 4-DSI-TOUCH-C** for the bench: works today with almost no adapter, and runs the
   software on a real round screen while the car panel is chosen.

Each needs its own panel board (like `panel-tsd/`) and a panel-ID resistor (`tools/screen_ports.py`).
