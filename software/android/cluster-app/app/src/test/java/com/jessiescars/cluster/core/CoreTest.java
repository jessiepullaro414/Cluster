package com.jessiescars.cluster.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class CoreTest {
    @Test public void fractionClampsAndHandlesNaN() {
        assertEquals(0f, Gauge.fraction(-5f, 0f, 120f), 0f);
        assertEquals(1f, Gauge.fraction(500f, 0f, 120f), 0f);
        assertEquals(0.5f, Gauge.fraction(60f, 0f, 120f), 1e-6f);
        assertEquals(0f, Gauge.fraction(Float.NaN, 0f, 120f), 0f);
        assertEquals(0f, Gauge.fraction(10f, 5f, 5f), 0f);          // degenerate scale
    }

    @Test public void sweepEndpoints() {
        assertEquals(135f, Gauge.angle(0f), 1e-4f);
        assertEquals(405f, Gauge.angle(1f), 1e-4f);                 // 45 degrees past 360
        assertEquals(270f, Gauge.angle(0.5f), 1e-4f);               // straight up
    }

    @Test public void speedConversionAndText() {
        float mps = 90f / 3.6f;                                     // 90 km/h
        assertEquals("56", Units.MPH.speedText(Reading.of(mps)));   // 55.9 mph
        assertEquals("90", Units.KPH.speedText(Reading.of(mps)));
        assertEquals("0", Units.KPH.speedText(Reading.of(-1f)));    // never negative
        assertEquals("--", Units.KPH.speedText(Reading.UNAVAILABLE));
        assertEquals("--", Units.MPH.speedText(new Reading(50f, false)));   // stale value must not show
    }

    @Test public void otherText() {
        assertEquals("2350", Units.rpmText(Reading.of(2350.4f)));
        assertEquals("----", Units.rpmText(Reading.UNAVAILABLE));
        assertEquals("13.8 V", Units.voltsText(Reading.of(13.84f)));
        assertEquals("--.- V", Units.voltsText(Reading.UNAVAILABLE));
    }

    @Test public void dayPaletteIgnoresDimmer() {
        Palette a = Palette.forLights(false, 0f), b = Palette.forLights(false, 100f);
        assertFalse(a.night);
        assertEquals(a.accent, b.accent);
        assertEquals(0xFFFFFFFF, a.text);
    }

    @Test public void nightPaletteFollowsDimmer() {
        Palette dim = Palette.forLights(true, 0f), bright = Palette.forLights(true, 100f);
        assertTrue(dim.night && bright.night);
        assertEquals(0xFFFFA000, bright.accent);                    // full level keeps the colour
        int dimRed = (dim.accent >> 16) & 0xFF, brightRed = (bright.accent >> 16) & 0xFF;
        assertEquals(Math.round(255 * Palette.MIN_NIGHT_LEVEL), dimRed);
        assertTrue(dimRed < brightRed);
        assertEquals(bright.accent, Palette.forLights(true, Float.NaN).accent);   // unknown dimmer: full
        assertEquals(bright.accent, Palette.forLights(true, 250f).accent);        // clamped
    }

    @Test public void scaleKeepsAlpha() {
        assertEquals(0x80000000, Palette.scale(0x80FFFFFF, 0f));
        assertEquals(0xFF808080, Palette.scale(0xFFFFFFFF, 0.5f));
    }

    @Test public void scenarioPhases() {
        VehicleState idle = DriveScenario.at(1f, null);
        assertEquals(0f, idle.speedMps.value, 1e-6f);
        VehicleState cruise = DriveScenario.at(15f, null);
        assertEquals(90f / 3.6f, cruise.speedMps.value, 1e-4f);
        VehicleState wrapped = DriveScenario.at(45f, null);         // 45 s is 15 s into the second loop
        assertEquals(cruise.speedMps.value, wrapped.speedMps.value, 1e-4f);
        assertTrue(DriveScenario.at(26f, null).speedMps.value < cruise.speedMps.value);
    }

    @Test public void linkDeadMakesEverythingUnavailable() {
        DriveScenario.Override o = new DriveScenario.Override();
        o.linkDead = true;
        VehicleState s = DriveScenario.at(15f, o);
        assertFalse(s.linkAlive);
        assertFalse(s.speedMps.available || s.rpm.available || s.turnLeft.available || s.dashLightsOn.available);
    }

    @Test public void overridesWin() {
        DriveScenario.Override o = new DriveScenario.Override();
        o.speedKph = 130f; o.night = true; o.dimmerPct = 30f; o.alternator = true;
        VehicleState s = DriveScenario.at(1f, o);
        assertEquals(130f / 3.6f, s.speedMps.value, 1e-4f);
        assertTrue(s.dashLightsOn.on() && s.alternatorWarning.on());
        assertEquals(30f, s.dashDimmerPct.value, 0f);
    }
}
