# The car on a PC: a control panel for the cluster bench

**Start:** double-click `start_car_sim.cmd` (or run `start_car_sim.sh` as root in the Ubuntu-24.04 WSL distro). It starts:
- LIVI, the round centre screen, if it isn't already running
- the four small gauges (gauges-fw's harness)
- `clusterd`
- this panel.

Close the panel to stop `clusterd` and the harness. LIVI keeps running.

| On the panel | Reaches the cluster as | Where it is in the car |
|---|---|---|
| The **dial**: drag the rim or scroll to turn; press the centre (or hold Space) | **Simulated GPIO**: `/tmp/carsim/adc` (12-bit angle) and `/tmp/carsim/click` (0/1), read by `clusterd --sim-gpio` | Piher PSC-360 on Verdin ADC_1, push button on a gpio-keys pin |
| Speed, RPM, fuel, coolant, oil, battery | **Simulated CAN**: VehicleMotion and VehicleFluids from the DBC (rolling counter, CRC-8), sent to `clusterd --can-udp 5101` | gauges/ sending on the private CAN link |
| Lamps: turns (flashing 1.5 Hz), hazards, high beam, brake, alternator, oil; headlights + dash dimmer | Simulated CAN: Indicators | gauges/'s 12 V lamp inputs and dimmer divider |
| Ignition (or key I) | Simulated CAN: PowerState. Key off: SuspendRequest with a 5 s countdown | gauges/'s ignition input |
| "Gauges board connected" | Unticked: frames stop, so the centre shows NO DATA | a broken private link |
| **Connect Android Auto** / Disconnect | `phone.py` on Windows: starts the aa_phone emulator if needed, a fresh head unit server, one relay into LIVI | a phone plugged into the USB-C port or on Wi-Fi |

The panel's status box reads `clusterd`'s `/state`: what the centre shows, the small gauges' look, units, and the link.

What happens on the centre (clusterd's dial flows, `../clusterd/src/shell.h`):
- **No phone.** Turn or click flips between our speedometer and LIVI's home. Hold 0.6 s for Settings.
- **In Settings.** Turn to choose a row, click to edit it (turn changes the value, click keeps it), hold to go back.
- **With a phone on the map.** The dial goes to the phone: turn moves its highlight, click selects, a 0.6 s hold is Back. Keep holding to 1.5 s for our speedometer; from there a turn or click goes back to the map and a 0.6 s hold opens Settings.

On a PC there's no real suspend. Key off only shows the countdown in the panel and logs "would suspend" (`clusterd-sim.conf`).
