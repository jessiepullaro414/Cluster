"""
screen_ports.py - the two screen ports of the brain board, as data.

Single source of truth for the pin order of both ribbon-cable ports: the
brain board's schematic builder and every panel board's builder import this
module, so the two ends of a cable cannot drift apart. docs/screen-ports.md
explains the choices.

Port A: MIPI DSI (the Verdin's DSI_1, 4 data lanes + clock), Hirose
        FH12-40S-0.5SH, 40 contacts. For panels with a native MIPI input
        (the TSD TST040HDBC-42). DSI is meant for short runs: keep the cable
        at or under about 15 cm.
Port B: LVDS (the Verdin's LVDS0 and LVDS1, 4 data pairs + clock each),
        Hirose FH12-50S-0.5SH, 50 contacts. One single-link panel on LVDS0,
        or one dual-link panel on both. RGB panels use an LVDS-to-RGB
        receiver on their panel board.

The pin counts differ on purpose, so a cable cannot go into the wrong port.

Conventions:
  * Every differential pair is P/N in the Verdin's own order (N first, as
    X1 lists them), with a GND contact on each side.
  * +5V comes through a per-port current-limited switch on the brain board
    (PORTx_5V, a TPS2557-Q1 with the same 61.9 k limit resistor as the USB-C
    port: 1.61 / 1.81 / 1.98 A min / typ / max); a panel board makes its own
    bias, backlight and any 3.3 V rail from it. FH12 contacts are rated
    0.5 A each (Hirose catalogue; confirm against the current datasheet), so
    port A's 4 contacts carry 2.0 A and port B's 5 carry 2.5 A, both above
    the switch's 1.98 A maximum.
  * +1V8 is the Verdin's I/O level: the panel's IOVCC where it needs 1.8 V,
    and the reference for every control line. It is a reference, not a
    power feed (at most 50 mA).
  * Control lines are 1.8 V logic. A panel that needs 3.3 V logic shifts
    levels on its own board.
  * IDx is an analog panel-identification pin: the brain board pulls it up
    to +1V8 through 10 k and reads it on an ADC; each panel board puts its
    own resistor to GND (table PANEL_ID_OHMS), so software knows which
    panel is plugged in. Open = no panel.
"""

# signal names used on the brain board's nets, per contact
PORT_A = {
    1: "GND",
    2: "PORTA_5V", 3: "PORTA_5V", 4: "PORTA_5V", 5: "PORTA_5V",
    6: "GND",
    7: "+1V8",
    8: "GND",
    9: "DSI_D3_N", 10: "DSI_D3_P",
    11: "GND",
    12: "DSI_D2_N", 13: "DSI_D2_P",
    14: "GND",
    15: "DSI_CLK_N", 16: "DSI_CLK_P",
    17: "GND",
    18: "DSI_D1_N", 19: "DSI_D1_P",
    20: "GND",
    21: "DSI_D0_N", 22: "DSI_D0_P",
    23: "GND",
    24: "PORTA_RESET",      # Verdin GPIO_9_DSI: panel reset, active low
    25: "PORTA_EN",         # Verdin GPIO_10_DSI: panel power/bias enable
    26: "PORTA_BL_PWM",     # Verdin PWM_3_DSI: backlight enable + dimming
    27: "PORTA_TE",         # panel tearing-effect output -> Verdin GPIO_IO33
    28: "GND",
    29: "PORTA_SDA",        # Verdin I2C_2_DSI (touch controller, if any)
    30: "PORTA_SCL",
    31: "PORTA_INT",        # touch interrupt -> Verdin GPIO_IO34
    32: "PORTA_ID",         # analog panel ID -> Verdin ADC_2
    33: "GND",
    34: "RESERVED", 35: "RESERVED", 36: "RESERVED", 37: "RESERVED",
    38: "GND", 39: "GND", 40: "GND",
}

# Written in the Verdin's order; the contact numbers are mirrored below.
_PORT_B_VERDIN_ORDER = {
    1: "GND",
    2: "PORTB_5V", 3: "PORTB_5V", 4: "PORTB_5V", 5: "PORTB_5V", 6: "PORTB_5V",
    7: "GND", 8: "GND",
    9: "+1V8",
    10: "GND",
    11: "LVDS0_CLK_N", 12: "LVDS0_CLK_P",
    13: "GND",
    14: "LVDS0_D0_N", 15: "LVDS0_D0_P",
    16: "GND",
    17: "LVDS0_D1_N", 18: "LVDS0_D1_P",
    19: "GND",
    20: "LVDS0_D2_N", 21: "LVDS0_D2_P",
    22: "GND",
    23: "LVDS0_D3_N", 24: "LVDS0_D3_P",
    25: "GND",
    26: "LVDS1_CLK_N", 27: "LVDS1_CLK_P",
    28: "GND",
    29: "LVDS1_D0_N", 30: "LVDS1_D0_P",
    31: "GND",
    32: "LVDS1_D1_N", 33: "LVDS1_D1_P",
    34: "GND",
    35: "LVDS1_D2_N", 36: "LVDS1_D2_P",
    37: "GND",
    38: "LVDS1_D3_N", 39: "LVDS1_D3_P",
    40: "GND",
    41: "PORTB_RESET",      # Verdin GPIO_4: panel reset, active low
    42: "PORTB_EN",         # Verdin GPIO_5_CSI: panel power enable
    43: "PORTB_BL_PWM",     # Verdin PWM_1: backlight enable + dimming
    44: "PORTB_SDA",        # Verdin I2C_3_HDMI (touch, panel set-up)
    45: "PORTB_SCL",
    46: "PORTB_SPI_CLK",    # Verdin SPI_1: panel set-up for RGB panels
    47: "PORTB_SPI_MOSI",
    48: "PORTB_SPI_CS",
    49: "PORTB_ID",         # analog panel ID -> Verdin ADC_3
    50: "GND",
}
# Port B's connector sits above the module and faces the socket, so it is
# turned 180 degrees and its contact numbers run against the Verdin's pin
# order there. Mirroring the numbering keeps every pair in order across the
# fan from J1 to the connector (no crossings): contact c carries what the
# Verdin-order list has at 51 - c, so LVDS0_CLK_N is contact 40 and the 5 V
# contacts are 45-49.
PORT_B = dict(sorted((51 - c, net) for c, net in _PORT_B_VERDIN_ORDER.items()))

# Verdin X1 signal -> brain-board net, for the port control lines
VERDIN_PORT_NETS = {
    "GPIO_9_DSI": "PORTA_RESET",
    "GPIO_10_DSI": "PORTA_EN",
    "PWM_3_DSI": "PORTA_BL_PWM",
    "GPIO_IO33": "PORTA_TE",
    "I2C_2_DSI_SDA": "PORTA_SDA", "I2C_2_DSI_SCL": "PORTA_SCL",
    "GPIO_IO34": "PORTA_INT",
    "ADC_2": "PORTA_ID",
    "GPIO_4": "PORTB_RESET",
    "GPIO_5_CSI": "PORTB_EN",
    "PWM_1": "PORTB_BL_PWM",
    "I2C_3_HDMI_SDA": "PORTB_SDA", "I2C_3_HDMI_SCL": "PORTB_SCL",
    "SPI_1_CLK": "PORTB_SPI_CLK", "SPI_1_MOSI": "PORTB_SPI_MOSI",
    "SPI_1_CS": "PORTB_SPI_CS",
    "ADC_3": "PORTB_ID",
    # per-port 5 V switch enables and fault flags (brain board only)
    "GPIO_IO04": "PORTA_PWR_EN",
    "GPIO_IO07": "PORTB_PWR_EN",
    "GPIO_7_CSI": "PORTA_FLT_N",
    "GPIO_8_CSI": "PORTB_FLT_N",
}

# panel boards: resistor from IDx to GND; the brain board pulls IDx up to
# +1V8 through 10 k. Spaced so 1 % parts and the ADC never confuse two codes.
PANEL_ID_PULLUP_OHMS = 10_000
PANEL_ID_OHMS = {
    "TSD TST040HDBC-42 (4.0 in round, MIPI)": 2_000,
    "Anders 12575 (4.2 in round, RGB via LVDS receiver)": 4_990,
    "reserved 3": 10_000,
    "reserved 4": 20_000,
    "reserved 5": 49_900,
}


def id_volts(r_id, vref=1.8):
    return vref * r_id / (r_id + PANEL_ID_PULLUP_OHMS)


def _check():
    for name, port, n in (("A", PORT_A, 40), ("B", PORT_B, 50)):
        assert sorted(port) == list(range(1, n + 1)), f"port {name} must use contacts 1..{n}"
        # every pair sits between GND contacts and its two legs are adjacent
        step = 1 if name == "A" else -1      # port B's numbering is mirrored
        for c, net in port.items():
            if net.endswith("_N") and ("DSI" in net or "LVDS" in net):
                assert port[c + step] == net[:-2] + "_P", (name, c, net)
                assert port[c - step] == "GND" and port[c + 2 * step] == "GND", (name, c, net)
    a5 = sum(1 for v in PORT_A.values() if v == "PORTA_5V")
    b5 = sum(1 for v in PORT_B.values() if v == "PORTB_5V")
    assert (a5, b5) == (4, 5)
    vs = sorted(id_volts(r) for r in PANEL_ID_OHMS.values())
    assert all(b - a > 0.1 for a, b in zip(vs, vs[1:])), vs


_check()


if __name__ == "__main__":
    for name, port in (("A (DSI, FH12-40S)", PORT_A), ("B (LVDS, FH12-50S)", PORT_B)):
        print(f"Port {name}")
        for c, net in port.items():
            print(f"  {c:2d}  {net}")
    print("Panel IDs:")
    for k, r in PANEL_ID_OHMS.items():
        print(f"  {r:>6} ohm -> {id_volts(r):.3f} V  {k}")
