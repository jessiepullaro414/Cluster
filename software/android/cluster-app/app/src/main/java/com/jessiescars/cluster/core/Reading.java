package com.jessiescars.cluster.core;

/** One vehicle property: a value and whether it may be shown. Mirrors vhal::PropValue in ../vhal-bridge. */
public final class Reading {
    public static final Reading UNAVAILABLE = new Reading(0f, false);

    public final float value;
    public final boolean available;

    public Reading(float value, boolean available) {
        this.value = value;
        this.available = available;
    }

    public static Reading of(float value) { return new Reading(value, true); }

    public boolean on() { return available && value >= 0.5f; }
}
