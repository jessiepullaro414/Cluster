package com.jessiescars.cluster.core;

import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.CenterLogic.NoPhone;

/**
 * What the user can change from the on-screen settings list (SettingsView). Pure logic: the rows, their
 * values and how a row cycles, so it can be unit tested and shared with the dial's rotary navigation.
 *
 * theme: the look of the four small gauge screens; the number is the one the gauges board understands
 * (DisplaySettings.GaugeTheme in protocol/cluster_can.h: 0 classic needles, 1 modern arcs, 2 CarPlay-inspired rings, 3 factory 1966 Mustang look).
 *
 * matchCarPlay: while a phone is projecting CarPlay, the small screens switch to the CarPlay-inspired theme whatever
 * the user's own choice is, and go back afterwards. Android Auto and "no phone" use the user's theme.
 */
public final class Settings {
    public enum Row { THEME, MATCH_CARPLAY, UNITS, NO_PHONE, MAP_SHAPE }

    public static final String[] THEME_NAMES = { "Classic", "Modern", "CarPlay", "Factory" };
    public static final int THEME_CARPLAY = 2;

    public int theme = 1;                       // modern, like the reference picture
    public boolean matchCarPlay = true;
    public boolean imperial = true;
    public NoPhone noPhone = NoPhone.GAUGE;
    public Aspect aspect = Aspect.ROUND;

    public static final Row[] ROWS = Row.values();

    public static String label(Row r) {
        switch (r) {
            case THEME: return "Gauge theme";
            case MATCH_CARPLAY: return "With CarPlay";
            case UNITS: return "Units";
            case NO_PHONE: return "No phone shows";
            default: return "Map shape";
        }
    }

    public String value(Row r) {
        switch (r) {
            case THEME: return THEME_NAMES[clampTheme(theme)];
            case MATCH_CARPLAY: return matchCarPlay ? "Apple look" : "My theme";
            case UNITS: return imperial ? "mph, °F, psi" : "km/h, °C, kPa";
            case NO_PHONE: return noPhone == NoPhone.HOME ? "Home" : "Gauge";
            default:
                switch (aspect) {
                    case ROUND: return "Round";
                    case SQUARE: return "Square";
                    case FOUR_THREE: return "4:3";
                    default: return "16:9";
                }
        }
    }

    /** Next value of a row, wrapping around. */
    public void cycle(Row r) {
        switch (r) {
            case THEME: theme = (clampTheme(theme) + 1) % THEME_NAMES.length; break;
            case MATCH_CARPLAY: matchCarPlay = !matchCarPlay; break;
            case UNITS: imperial = !imperial; break;
            case NO_PHONE: noPhone = noPhone == NoPhone.GAUGE ? NoPhone.HOME : NoPhone.GAUGE; break;
            default: {
                Aspect[] all = Aspect.values();
                aspect = all[(aspect.ordinal() + 1) % all.length];
            }
        }
    }

    /** The theme the small screens should show now (what goes into DisplaySettings.GaugeTheme). */
    public int effectiveTheme(boolean carPlayOpen) {
        return carPlayOpen && matchCarPlay ? THEME_CARPLAY : clampTheme(theme);
    }

    /** One step of a row in either direction (the dial turns both ways). Two-value rows flip. */
    public void step(Row r, int dir) {
        switch (r) {
            case THEME: theme = ((clampTheme(theme) + dir) % THEME_NAMES.length + THEME_NAMES.length) % THEME_NAMES.length; break;
            case MAP_SHAPE: {
                Aspect[] all = Aspect.values();
                aspect = all[((aspect.ordinal() + dir) % all.length + all.length) % all.length];
                break;
            }
            default: cycle(r);
        }
    }

    public void copyFrom(Settings o) {
        theme = o.theme;
        matchCarPlay = o.matchCarPlay;
        imperial = o.imperial;
        noPhone = o.noPhone;
        aspect = o.aspect;
    }

    public static int clampTheme(int t) {
        return t >= 0 && t < THEME_NAMES.length ? t : 0;
    }

    /** Parses "classic", "modern" or a number; null if it means nothing. */
    public static Integer parseTheme(String s) {
        if (s == null) return null;
        String t = s.trim().toLowerCase(java.util.Locale.ROOT);
        for (int i = 0; i < THEME_NAMES.length; i++)
            if (THEME_NAMES[i].toLowerCase(java.util.Locale.ROOT).equals(t)) return i;
        try {
            int n = Integer.parseInt(t);
            return n >= 0 && n < THEME_NAMES.length ? n : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
