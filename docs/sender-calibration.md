# Measuring the sender curves in the car

The fuel, oil-pressure and coolant senders are resistors whose value follows the level, pressure or temperature. Every
sender (and every reproduction sender) follows its own curve, so the gauges show dashes for a sender until its curve is
measured. The cluster measures the resistance itself, so no multimeter is needed once the boards are in the car.

## What you need

- The cluster installed and powered, ignition on.
- The centre screen's **Settings** page: hold the dial 0.6 s. Under the list it shows
  `senders: fuel 41.5 Ω · oil 10.1 Ω · temp 302.0 Ω` (a dash means no reading: wire open or shorted). It updates once a
  second (CAN message SenderOhms, 0x305, `protocol/can_protocol.py`).
- A way to know the true value at each reading (below), and a text file for the readings.

## Taking the readings

Write one line per reading into `software/gauges-fw/sender_readings.csv`:

```
sender,ohms,value
fuel,73.2,0
fuel,41.5,50
fuel,10.4,100
```

**Fuel (percent).** Start with the tank as empty as is safe (or with the sender out of the tank, arm hanging free). Add a
known amount of fuel at a time (a 5 L or 5 gal can) and note the reading after each, letting the float settle for a
minute. Convert to percent of the tank capacity set on the display. Five to eight readings give a good curve; the level
is not linear in a 1966 Mustang tank.

**Coolant (deg C).** The easiest accurate way is on the bench: the sender in a pot of water with a kitchen thermometer,
heated from cold to near boiling, a reading every 10 deg C. Wire it to the cluster's sender input with the sender's body
to ground. In the car, compare against an infrared thermometer on the thermostat housing (less accurate).

**Oil pressure (kPa).** Tee a mechanical gauge into the sender port and note readings at idle, at a few steady engine
speeds and with the engine off (0 kPa). 1 psi = 6.895 kPa.

## Turning readings into the firmware table

```
python software/gauges-fw/tools/make_sender_curves.py software/gauges-fw/sender_readings.csv
```

This writes `software/gauges-fw/src/sender_curves.c`. It refuses readings that cannot be right (two at the same
resistance, a value outside the sender's range, a curve that rises and then falls) so a typo is caught there and not on
the dash. Rebuild the firmware (`make image`) and send it over the private CAN link (`tools/can_flash.py`, see
`software/gauges-fw/README.md`): no programmer, no opening the dash.

Between the readings the firmware interpolates in straight lines and holds the end values beyond them.
