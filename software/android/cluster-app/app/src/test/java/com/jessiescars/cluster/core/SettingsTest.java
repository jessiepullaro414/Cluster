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
        assertEquals(0, s.theme);                       // 1 wraps to 0
        s.cycle(Row.THEME);
        assertEquals(1, s.theme);
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
        assertEquals(4, Settings.ROWS.length);
    }

    @Test public void themeNumbersAreClampedAndParsed() {
        assertEquals(0, Settings.clampTheme(-1));
        assertEquals(0, Settings.clampTheme(7));
        assertEquals(1, Settings.clampTheme(1));
        assertEquals(Integer.valueOf(0), Settings.parseTheme("classic"));
        assertEquals(Integer.valueOf(1), Settings.parseTheme(" Modern "));
        assertEquals(Integer.valueOf(1), Settings.parseTheme("1"));
        assertNull(Settings.parseTheme("2"));
        assertNull(Settings.parseTheme("nonsense"));
        assertNull(Settings.parseTheme(null));
    }
}
