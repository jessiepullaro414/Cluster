package com.jessiescars.cluster.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.CenterLogic.NoPhone;
import com.jessiescars.cluster.core.Settings.Row;

public class SettingsTest {
    @Test public void defaultsMatchTheReferencePicture() {
        Settings s = new Settings();
        assertEquals(1, s.theme);                       // modern
        assertTrue(s.imperial);
        assertEquals(Aspect.ROUND, s.aspect);
        assertEquals(NoPhone.GAUGE, s.noPhone);
    }

    @Test public void everyRowCyclesAndWraps() {
        Settings s = new Settings();
        s.cycle(Row.THEME);
        assertEquals(2, s.theme);                       // modern -> CarPlay
        s.cycle(Row.THEME);
        assertEquals(3, s.theme);                       // -> factory
        s.cycle(Row.THEME);
        assertEquals(0, s.theme);                       // wraps to classic
        s.cycle(Row.THEME);
        assertEquals(1, s.theme);
        s.cycle(Row.MATCH_CARPLAY);
        assertEquals(false, s.matchCarPlay);
        s.cycle(Row.MATCH_CARPLAY);
        assertEquals(true, s.matchCarPlay);
        s.cycle(Row.UNITS);
        assertEquals(false, s.imperial);
        s.cycle(Row.NO_PHONE);
        assertEquals(NoPhone.HOME, s.noPhone);
        s.cycle(Row.NO_PHONE);
        assertEquals(NoPhone.GAUGE, s.noPhone);
        Aspect first = s.aspect;
        for (int i = 0; i < Aspect.values().length; i++) s.cycle(Row.MAP_SHAPE);
        assertEquals(first, s.aspect);                  // a full lap returns to the start
    }

    @Test public void labelsAndValuesReadWell() {
        Settings s = new Settings();
        assertEquals("Gauge theme", Settings.label(Row.THEME));
        assertEquals("Modern", s.value(Row.THEME));
        s.theme = 0;
        assertEquals("Classic", s.value(Row.THEME));
        assertEquals("Round", s.value(Row.MAP_SHAPE));
        s.imperial = false;
        assertTrue(s.value(Row.UNITS).contains("km/h"));
        assertEquals(5, Settings.ROWS.length);
    }

    @Test public void carPlayLookFollowsTheProjectionUnlessTheUserOptsOut() {
        Settings s = new Settings();
        s.theme = 0;                                    // the user's own pick: classic
        assertEquals(0, s.effectiveTheme(false));       // nothing projecting
        assertEquals(Settings.THEME_CARPLAY, s.effectiveTheme(true));   // CarPlay open: Apple look
        s.matchCarPlay = false;
        assertEquals(0, s.effectiveTheme(true));        // opted out: keeps classic
        assertEquals("My theme", s.value(Row.MATCH_CARPLAY));
        s.matchCarPlay = true;
        assertEquals("Apple look", s.value(Row.MATCH_CARPLAY));
        assertEquals("With CarPlay", Settings.label(Row.MATCH_CARPLAY));
    }

    @Test public void themeNumbersAreClampedAndParsed() {
        assertEquals(0, Settings.clampTheme(-1));
        assertEquals(0, Settings.clampTheme(7));
        assertEquals(3, Settings.clampTheme(3));
        assertEquals(0, Settings.clampTheme(4));
        assertEquals(1, Settings.clampTheme(1));
        assertEquals(Integer.valueOf(0), Settings.parseTheme("classic"));
        assertEquals(Integer.valueOf(1), Settings.parseTheme(" Modern "));
        assertEquals(Integer.valueOf(1), Settings.parseTheme("1"));
        assertEquals(Integer.valueOf(2), Settings.parseTheme("carplay"));
        assertEquals(Integer.valueOf(2), Settings.parseTheme("2"));
        assertEquals(Integer.valueOf(3), Settings.parseTheme("factory"));
        assertNull(Settings.parseTheme("4"));
        assertNull(Settings.parseTheme("nonsense"));
        assertNull(Settings.parseTheme(null));
    }

    @Test public void stepGoesBothWaysAndWraps() {
        Settings s = new Settings();
        s.theme = 0;
        s.step(Row.THEME, -1);
        assertEquals(3, s.theme);
        s.step(Row.THEME, +1);
        assertEquals(0, s.theme);
        s.aspect = Aspect.ROUND;
        s.step(Row.MAP_SHAPE, -1);
        assertEquals(Aspect.SIXTEEN_NINE, s.aspect);        // backwards past the first value wraps to the last
        s.step(Row.UNITS, +1);
        assertEquals(false, s.imperial);
        s.step(Row.UNITS, -1);
        assertEquals(true, s.imperial);                     // two-value rows flip in either direction
    }

    @Test public void copyFromRestoresEverything() {
        Settings a = new Settings(), b = new Settings();
        b.theme = 2;
        b.matchCarPlay = false;
        b.imperial = false;
        b.noPhone = NoPhone.HOME;
        b.aspect = Aspect.FOUR_THREE;
        a.copyFrom(b);
        assertEquals(2, a.theme);
        assertEquals(false, a.matchCarPlay);
        assertEquals(false, a.imperial);
        assertEquals(NoPhone.HOME, a.noPhone);
        assertEquals(Aspect.FOUR_THREE, a.aspect);
    }
}