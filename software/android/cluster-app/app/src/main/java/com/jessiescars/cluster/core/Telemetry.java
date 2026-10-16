package com.jessiescars.cluster.core;

import java.util.Locale;

/**
 * One line of text describing the vehicle state, sent over UDP from the app to the PC so the
 * small gauge screens can be driven from Android during development (tools/live_screens.py in
 * gauges-fw). This is a DEVELOPMENT feed: in the car the data flows the other way, from the
 * gauges board to Android over the private CAN link.
 *
 * Format: "CL1 imperial=1 speed=96.56 rpm=3500 batt=13.8 fuel=68 cool=90 oil=350 tl=0 tr=0 hb=0
 * br=0 alt=0 oilw=0 dash=0 dim=70", values in the units of gauges-fw (km/h, rpm, V, %, degC,
 * kPa); a reading that is not available is "-". Always '.' as the decimal point.
 */
public final class Telemetry {
    private Telemetry() {}

    public static final String MAGIC = "CL1";

    public static String encode(VehicleState s, boolean imperial) {
        StringBuilder b = new StringBuilder(160);
        b.append(MAGIC).append(" imperial=").append(imperial ? 1 : 0);
        num(b, "speed", s.speedMps, 3.6f, 2);
        num(b, "rpm", s.rpm, 1f, 0);
        num(b, "batt", s.batteryV, 1f, 2);
        num(b, "fuel", s.fuelPct, 1f, 1);
        num(b, "cool", s.coolantC, 1f, 1);
        num(b, "oil", s.oilKpa, 1f, 1);
        flag(b, "tl", s.turnLeft);
        flag(b, "tr", s.turnRight);
        flag(b, "hb", s.highBeam);
        flag(b, "br", s.brakeWarning);
        flag(b, "alt", s.alternatorWarning);
        flag(b, "oilw", s.oilWarning);
        flag(b, "dash", s.dashLightsOn);
        num(b, "dim", s.dashDimmerPct, 1f, 0);
        return b.toString();
    }

    private static void num(StringBuilder b, String key, Reading r, float scale, int decimals) {
        b.append(' ').append(key).append('=');
        if (!r.available) b.append('-');
        else b.append(String.format(Locale.US, "%." + decimals + "f", r.value * scale));
    }

    private static void flag(StringBuilder b, String key, Reading r) {
        b.append(' ').append(key).append('=').append(r.available ? (r.on() ? '1' : '0') : '-');
    }
}
