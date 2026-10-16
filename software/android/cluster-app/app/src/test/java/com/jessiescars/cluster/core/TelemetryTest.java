package com.jessiescars.cluster.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

import org.junit.Test;

public class TelemetryTest {
    private static Map<String, String> parse(String line) {
        String[] parts = line.split(" ");
        assertEquals(Telemetry.MAGIC, parts[0]);
        Map<String, String> m = new HashMap<>();
        for (int i = 1; i < parts.length; i++) {
            int eq = parts[i].indexOf('=');
            m.put(parts[i].substring(0, eq), parts[i].substring(eq + 1));
        }
        return m;
    }

    @Test public void encodesValuesInTheUnitsTheGaugesUse() {
        VehicleState s = new VehicleState();
        s.speedMps = Reading.of(90f / 3.6f);
        s.rpm = Reading.of(3500.4f);
        s.batteryV = Reading.of(13.84f);
        s.fuelPct = Reading.of(68.04f);
        s.coolantC = Reading.of(90f);
        s.oilKpa = Reading.of(350f);
        s.turnLeft = Reading.of(1f);
        s.highBeam = Reading.of(0f);
        s.dashDimmerPct = Reading.of(70f);
        Map<String, String> m = parse(Telemetry.encode(s, true));
        assertEquals("1", m.get("imperial"));
        assertEquals("90.00", m.get("speed"));               // km/h, not m/s
        assertEquals("3500", m.get("rpm"));
        assertEquals("13.84", m.get("batt"));
        assertEquals("68.0", m.get("fuel"));
        assertEquals("1", m.get("tl"));
        assertEquals("0", m.get("hb"));
        assertEquals("70", m.get("dim"));
    }

    @Test public void unavailableReadingsAreDashesNeverStaleNumbers() {
        VehicleState s = new VehicleState();                 // everything unavailable
        s.speedMps = new Reading(25f, false);                // a number with the flag off must not leak
        Map<String, String> m = parse(Telemetry.encode(s, false));
        assertEquals("0", m.get("imperial"));
        for (String k : new String[] { "speed", "rpm", "batt", "fuel", "cool", "oil", "tl", "tr", "hb", "br", "alt", "oilw", "dash", "dim" })
            assertEquals(k, "-", m.get(k));
    }

    @Test public void decimalPointIsADotWhateverTheDeviceLocale() {
        Locale old = Locale.getDefault();
        try {
            Locale.setDefault(Locale.GERMANY);               // would print "13,84"
            VehicleState s = new VehicleState();
            s.batteryV = Reading.of(13.84f);
            String line = Telemetry.encode(s, true);
            assertTrue(line, line.contains("batt=13.84"));
            assertFalse(line.contains(","));
        } finally {
            Locale.setDefault(old);
        }
    }

    @Test public void lineIsShortEnoughForOneDatagram() {
        VehicleState s = DriveScenario.at(15f, null);
        assertTrue(Telemetry.encode(s, true).length() < 200);
    }
}
