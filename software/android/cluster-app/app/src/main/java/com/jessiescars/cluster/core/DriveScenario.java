package com.jessiescars.cluster.core;

/**
 * The scripted drive for the fake property source: the same curve as
 * ../../tools/can_replay.py drive(), so the app and the CAN replay tell the same
 * story. 30 s loop: 0-3 idle, 3-13 accelerate to 90 km/h, 13-23 cruise,
 * 23-30 brake to a stop. Plausible, not measured.
 */
public final class DriveScenario {
    private DriveScenario() {}

    public static final float LOOP_S = 30f;

    /** Manual overrides (from the debug broadcast); null fields keep the script. */
    public static final class Override {
        public Float speedKph, rpm, dimmerPct;
        public Boolean night, linkDead, turnLeft, highBeam, brake, alternator, oil;
    }

    public static VehicleState at(float tSeconds, Override o) {
        float t = ((tSeconds % LOOP_S) + LOOP_S) % LOOP_S;
        float kph;
        if (t < 3f) kph = 0f;
        else if (t < 13f) kph = 90f * (t - 3f) / 10f;
        else if (t < 23f) kph = 90f;
        else kph = 90f * (LOOP_S - t) / 7f;
        float rpm = 800f + kph * 28f + 40f * (float) Math.sin(t * 6f);

        VehicleState s = new VehicleState();
        s.linkAlive = o == null || o.linkDead == null || !o.linkDead;
        if (!s.linkAlive) return s;               // every reading stays unavailable

        if (o != null && o.speedKph != null) kph = o.speedKph;
        if (o != null && o.rpm != null) rpm = o.rpm;

        s.speedMps = Reading.of(kph / 3.6f);
        s.rpm = Reading.of(rpm);
        s.batteryV = Reading.of(t > 1f ? 13.8f : 12.4f);
        s.fuelPct = Reading.of(68f - 0.02f * t);
        s.coolantC = Reading.of(Math.min(92f, 40f + 2f * t));
        s.oilKpa = Reading.of(Math.min(380f, 150f + rpm * 0.08f));

        // no turn indicators in the app: the dash has physical ones (the properties stay for the VHAL map)
        s.turnLeft = Reading.of(flag(o != null ? o.turnLeft : null, false));
        s.turnRight = Reading.of(0f);
        s.highBeam = Reading.of(flag(o != null ? o.highBeam : null, false));
        s.brakeWarning = Reading.of(flag(o != null ? o.brake : null, false));
        s.alternatorWarning = Reading.of(flag(o != null ? o.alternator : null, false));
        s.oilWarning = Reading.of(flag(o != null ? o.oil : null, false));

        boolean night = o != null && o.night != null && o.night;
        s.dashLightsOn = Reading.of(night ? 1f : 0f);
        s.dashDimmerPct = Reading.of(o != null && o.dimmerPct != null ? o.dimmerPct : 70f);
        return s;
    }

    private static float flag(Boolean override, boolean scripted) {
        return (override != null ? override : scripted) ? 1f : 0f;
    }
}
