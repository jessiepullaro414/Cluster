package com.jessiescars.cluster.core;

/**
 * What the round centre display shows.
 *
 * Decision 2026-10-15: the centre is CarPlay / Android Auto maps; speed, rpm and
 * the fluids are on the four small screens (gauges-fw/inc/screens.h). So the
 * gauge built in B1 is no longer the default, only a choice:
 *  - a phone is projecting: PROJECTION, unless the driver flipped to the gauge
 *    (dial click) for the moment;
 *  - no phone: whatever the user chose to see then, GAUGE or HOME.
 */
public final class CenterLogic {
    private CenterLogic() {}

    public enum Content { PROJECTION, GAUGE, HOME }

    /** The user's setting for "no phone connected". */
    public enum NoPhone {
        GAUGE, HOME;

        public static NoPhone parse(String s, NoPhone fallback) {
            if (s == null) return fallback;
            switch (s.trim().toLowerCase(java.util.Locale.ROOT)) {
                case "gauge": return GAUGE;
                case "home": return HOME;
                default: return fallback;
            }
        }
    }

    public static Content choose(boolean phoneProjecting, boolean flippedToGauge, NoPhone noPhone) {
        if (phoneProjecting) return flippedToGauge ? Content.GAUGE : Content.PROJECTION;
        return noPhone == NoPhone.HOME ? Content.HOME : Content.GAUGE;
    }

    /** Shape of the rectangular CarPlay / Android Auto window inside the circle. */
    public enum Aspect {
        SQUARE(1, 1), FOUR_THREE(4, 3), SIXTEEN_NINE(16, 9);

        public final int w, h;
        Aspect(int w, int h) { this.w = w; this.h = h; }

        public static Aspect parse(String s, Aspect fallback) {
            if (s == null) return fallback;
            switch (s.trim().toLowerCase(java.util.Locale.ROOT)) {
                case "square": case "1:1": return SQUARE;
                case "4:3": return FOUR_THREE;
                case "16:9": return SIXTEEN_NINE;
                default: return fallback;
            }
        }
    }

    /**
     * Largest rectangle of the given aspect that fits inside a circle of the
     * given diameter: its diagonal is the diameter. Returns {width, height}.
     * 16:9 in a 101.5 mm circle is 88.5 x 49.8 mm (docs/mechanical-fit.md).
     */
    public static float[] inscribed(float diameter, Aspect a) {
        double diag = Math.hypot(a.w, a.h);
        return new float[] { (float) (diameter * a.w / diag), (float) (diameter * a.h / diag) };
    }
}
