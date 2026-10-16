package com.jessiescars.cluster.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.DialUi.Event;
import com.jessiescars.cluster.core.DialUi.Mode;
import com.jessiescars.cluster.core.Settings.Row;

public class DialUiTest {
    private static final class Rec implements DialUi.Host {
        int changed, closed;
        @Override public void onChanged(Settings s) { changed++; }
        @Override public void onClose() { closed++; }
    }

    @Test public void turnMovesAndWrapsThroughBack() {
        Settings s = new Settings();
        Rec h = new Rec();
        DialUi d = new DialUi(s, h);
        d.open();
        assertEquals(0, d.selected());
        d.handle(Event.LEFT);
        assertTrue(d.backSelected());                    // wraps to Back
        d.handle(Event.RIGHT);
        assertEquals(0, d.selected());
        for (int i = 0; i < Settings.ROWS.length; i++) d.handle(Event.RIGHT);
        assertTrue(d.backSelected());
        d.handle(Event.CLICK);
        assertEquals(1, h.closed);                       // click on Back closes
    }

    @Test public void editChangesLiveClickKeepsHoldCancels() {
        Settings s = new Settings();
        s.theme = 1;
        Rec h = new Rec();
        DialUi d = new DialUi(s, h);
        d.open();
        d.handle(Event.CLICK);
        assertEquals(Mode.EDIT, d.mode());
        d.handle(Event.RIGHT);
        assertEquals(2, s.theme);                        // live
        d.handle(Event.RIGHT);
        assertEquals(3, s.theme);
        d.handle(Event.LEFT);
        assertEquals(2, s.theme);                        // both directions
        assertEquals(3, h.changed);
        d.handle(Event.LONG);                            // cancel
        assertEquals(1, s.theme);                        // restored
        assertEquals(Mode.LIST, d.mode());
        assertEquals(0, h.closed);                       // the list stays open
        d.handle(Event.CLICK);
        d.handle(Event.RIGHT);
        d.handle(Event.CLICK);                           // keep
        assertEquals(2, s.theme);
        assertEquals(Mode.LIST, d.mode());
        d.handle(Event.LONG);                            // hold in the list closes it
        assertEquals(1, h.closed);
    }

    @Test public void editsEveryRowAndKeepsOtherValues() {
        Settings s = new Settings();
        Rec h = new Rec();
        DialUi d = new DialUi(s, h);
        d.open();
        d.handle(Event.RIGHT);                           // With CarPlay
        d.handle(Event.CLICK);
        d.handle(Event.RIGHT);
        assertFalse(s.matchCarPlay);
        d.handle(Event.CLICK);
        d.handle(Event.RIGHT);                           // Units
        d.handle(Event.CLICK);
        d.handle(Event.LEFT);
        assertFalse(s.imperial);
        d.handle(Event.CLICK);
        d.handle(Event.RIGHT);                           // No phone shows
        d.handle(Event.RIGHT);                           // Map shape
        d.handle(Event.CLICK);
        d.handle(Event.LEFT);                            // round -> 16:9 (wraps backwards)
        assertEquals(Aspect.SIXTEEN_NINE, s.aspect);
        d.handle(Event.CLICK);
        assertEquals(1, s.theme);                        // untouched
        assertFalse(s.matchCarPlay);
    }

    @Test public void tapStepsARowAndBackCloses() {
        Settings s = new Settings();
        Rec h = new Rec();
        DialUi d = new DialUi(s, h);
        d.tap(Settings.ROWS.length > 2 ? 2 : 0);         // Units
        assertFalse(s.imperial);
        assertEquals(1, h.changed);
        d.tap(Settings.ROWS.length);
        assertEquals(1, h.closed);
    }

    @Test public void stepWrapsBothWays() {
        Settings s = new Settings();
        s.theme = 0;
        s.step(Row.THEME, -1);
        assertEquals(3, s.theme);
        s.step(Row.THEME, +1);
        assertEquals(0, s.theme);
        Settings o = new Settings();
        o.theme = 2;
        o.imperial = false;
        s.copyFrom(o);
        assertEquals(2, s.theme);
        assertFalse(s.imperial);
    }
}
