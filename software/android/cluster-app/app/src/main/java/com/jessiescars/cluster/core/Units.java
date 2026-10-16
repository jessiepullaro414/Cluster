package com.jessiescars.cluster.core;

import java.util.Locale;

/** Display units and number formatting. */
public enum Units {
    MPH("MPH", 2.2369363f),      // m/s to mph
    KPH("KM/H", 3.6f);           // m/s to km/h

    public final String label;
    private final float perMps;

    Units(String label, float perMps) {
        this.label = label;
        this.perMps = perMps;
    }

    public float fromMps(float mps) { return mps * perMps; }

    /** Whole-number speed, or "--" when the reading is not available (never a stale number). */
    public String speedText(Reading speedMps) {
        if (!speedMps.available) return "--";
        return String.format(Locale.US, "%d", Math.round(fromMps(Math.max(0f, speedMps.value))));
    }

    public static String rpmText(Reading rpm) {
        if (!rpm.available) return "----";
        return String.format(Locale.US, "%d", Math.round(Math.max(0f, rpm.value)));
    }

    public static String voltsText(Reading volts) {
        if (!volts.available) return "--.- V";
        return String.format(Locale.US, "%.1f V", volts.value);
    }
}
