package com.jessiescars.cluster.core;

/**
 * Colours for day and night. Night is selected by the headlight switch (the
 * Indicators message's DashLightsOn) and its brightness follows the dash dimmer
 * (DashDimmerPct). This scales what the app draws; the panel backlight itself
 * is a separate Android display-brightness setting handled in the platform.
 */
public final class Palette {
    public final boolean night;
    public final int background, track, accent, text, textDim, redline, warning, good, blue;

    private Palette(boolean night, int accent, int text, int textDim, int track, float level) {
        this.night = night;
        this.background = 0xFF000000;
        this.accent = scale(accent, level);
        this.text = scale(text, level);
        this.textDim = scale(textDim, level);
        this.track = scale(track, level);
        this.redline = scale(0xFFE5484D, level);
        this.warning = scale(0xFFFFB000, level);
        this.good = scale(0xFF3DDC84, level);
        this.blue = scale(0xFF3D8BFF, level);
    }

    public static final float MIN_NIGHT_LEVEL = 0.20f;

    /**
     * @param dashLightsOn  headlights on: use the night palette
     * @param dimmerPct     0..100 from the rheostat, ignored by day
     */
    public static Palette forLights(boolean dashLightsOn, float dimmerPct) {
        if (!dashLightsOn) {
            return new Palette(false, 0xFF35C6F4, 0xFFFFFFFF, 0xFF8A95A3, 0xFF262B33, 1f);
        }
        float pct = Float.isNaN(dimmerPct) ? 100f : Math.max(0f, Math.min(100f, dimmerPct));
        float level = MIN_NIGHT_LEVEL + (1f - MIN_NIGHT_LEVEL) * (pct / 100f);
        return new Palette(true, 0xFFFFA000, 0xFFFFC857, 0xFFB07A1F, 0xFF2A2013, level);
    }

    /** Multiplies the RGB of an ARGB colour by level (0..1). */
    public static int scale(int argb, float level) {
        int a = argb >>> 24;
        int r = Math.round(((argb >> 16) & 0xFF) * level);
        int g = Math.round(((argb >> 8) & 0xFF) * level);
        int b = Math.round((argb & 0xFF) * level);
        return (a << 24) | (r << 16) | (g << 8) | b;
    }
}
