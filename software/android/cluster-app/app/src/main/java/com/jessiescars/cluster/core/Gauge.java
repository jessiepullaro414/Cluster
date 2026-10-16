package com.jessiescars.cluster.core;

/** Scale arithmetic for the dial arcs. */
public final class Gauge {
    private Gauge() {}

    /** Both dials sweep 270 degrees, open at the bottom, starting bottom-left (Canvas angles: 0 = 3 o'clock, clockwise). */
    public static final float START_DEG = 135f;
    public static final float SWEEP_DEG = 270f;

    /** Position of value on the scale as 0..1. NaN and values below min give 0, above max give 1. */
    public static float fraction(float value, float min, float max) {
        if (Float.isNaN(value) || max <= min) return 0f;
        float f = (value - min) / (max - min);
        return f < 0f ? 0f : (f > 1f ? 1f : f);
    }

    /** Canvas angle of a scale position. */
    public static float angle(float fraction) {
        return START_DEG + SWEEP_DEG * fraction;
    }
}
