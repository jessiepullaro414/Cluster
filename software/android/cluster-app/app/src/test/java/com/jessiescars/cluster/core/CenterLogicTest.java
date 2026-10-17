package com.jessiescars.cluster.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.CenterLogic.Content;
import com.jessiescars.cluster.core.CenterLogic.NoPhone;

public class CenterLogicTest {
    @Test public void phoneProjectingShowsMapsUnlessFlipped() {
        for (NoPhone n : NoPhone.values()) {
            assertEquals(Content.PROJECTION, CenterLogic.choose(true, false, n));
            assertEquals(Content.GAUGE, CenterLogic.choose(true, true, n));
        }
    }

    @Test public void carPlayIsOpenOnlyWhileItsScreenIsShown() {
        assertTrue(CenterLogic.carPlayOpen(Content.PROJECTION, true));
        assertTrue(!CenterLogic.carPlayOpen(Content.PROJECTION, false));      // Android Auto
        assertTrue(!CenterLogic.carPlayOpen(Content.GAUGE, true));            // phone connected, but the centre shows the speedometer
        assertTrue(!CenterLogic.carPlayOpen(Content.HOME, true));
        assertTrue(!CenterLogic.carPlayOpen(Content.GAUGE, false));
    }

    @Test public void noPhoneFollowsTheUsersChoiceAndIgnoresFlip() {
        assertEquals(Content.GAUGE, CenterLogic.choose(false, false, NoPhone.GAUGE));
        assertEquals(Content.HOME, CenterLogic.choose(false, false, NoPhone.HOME));
        assertEquals(Content.GAUGE, CenterLogic.choose(false, true, NoPhone.GAUGE));
        assertEquals(Content.HOME, CenterLogic.choose(false, true, NoPhone.HOME));   // flipping is a projection-time action
    }

    @Test public void inscribedRectanglesMatchTheMechanicalNote() {
        // 101.5 mm circle: 16:9 is 88.5 x 49.8 mm (docs/mechanical-fit.md)
        float[] r = CenterLogic.inscribed(101.5f, Aspect.SIXTEEN_NINE);
        assertEquals(88.5f, r[0], 0.1f);
        assertEquals(49.8f, r[1], 0.1f);
        float[] sq = CenterLogic.inscribed(101.5f, Aspect.SQUARE);
        assertEquals(71.8f, sq[0], 0.1f);
        assertEquals(sq[0], sq[1], 1e-4f);
        float[] f = CenterLogic.inscribed(680f, Aspect.FOUR_THREE);
        assertEquals(544f, f[0], 0.01f);
        assertEquals(408f, f[1], 0.01f);
    }

    @Test public void roundFillsTheCircle() {
        float[] r = CenterLogic.inscribed(716f, Aspect.ROUND);
        assertEquals(716f, r[0], 0.01f);
        assertEquals(716f, r[1], 0.01f);
        assertEquals(Aspect.ROUND, Aspect.parse("round", Aspect.SQUARE));
        assertEquals(Aspect.ROUND, Aspect.parse("Circle", Aspect.SQUARE));
    }

    @Test public void everyShapeFitsTheCircle() {
        for (Aspect a : Aspect.values()) {
            if (a == Aspect.ROUND) continue;                        // fills the circle by design
            float[] r = CenterLogic.inscribed(680f, a);
            double corner = Math.hypot(r[0] / 2.0, r[1] / 2.0);
            assertTrue(corner <= 340.0 + 1e-3);                      // corners touch, never pass, the circle
        }
    }

    @Test public void squareGivesTheMostMapAreaThenFourThree() {
        float sq = area(Aspect.SQUARE), f = area(Aspect.FOUR_THREE), w = area(Aspect.SIXTEEN_NINE);
        assertTrue(sq > f && f > w);
    }

    @Test public void parsingIsForgivingButFallsBack() {
        assertEquals(Aspect.FOUR_THREE, Aspect.parse(" 4:3 ", Aspect.SQUARE));
        assertEquals(Aspect.SQUARE, Aspect.parse("1:1", Aspect.FOUR_THREE));
        assertEquals(Aspect.SQUARE, Aspect.parse("nonsense", Aspect.SQUARE));
        assertEquals(Aspect.SQUARE, Aspect.parse(null, Aspect.SQUARE));
        assertEquals(NoPhone.HOME, NoPhone.parse("HOME", NoPhone.GAUGE));
        assertEquals(NoPhone.GAUGE, NoPhone.parse("x", NoPhone.GAUGE));
    }

    private static float area(Aspect a) {
        float[] r = CenterLogic.inscribed(680f, a);
        return r[0] * r[1];
    }
}
