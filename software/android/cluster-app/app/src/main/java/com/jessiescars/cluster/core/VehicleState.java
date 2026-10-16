package com.jessiescars.cluster.core;

/**
 * Everything the cluster shows, as the VHAL bridge reports it (see
 * ../vhal-bridge/src/bridge.h for the property list). Speed is metres per
 * second because that is what Android's PERF_VEHICLE_SPEED uses.
 */
public final class VehicleState {
    public Reading speedMps = Reading.UNAVAILABLE;
    public Reading rpm = Reading.UNAVAILABLE;
    public Reading batteryV = Reading.UNAVAILABLE;
    public Reading fuelPct = Reading.UNAVAILABLE;
    public Reading coolantC = Reading.UNAVAILABLE;
    public Reading oilKpa = Reading.UNAVAILABLE;

    public Reading turnLeft = Reading.UNAVAILABLE;
    public Reading turnRight = Reading.UNAVAILABLE;
    public Reading highBeam = Reading.UNAVAILABLE;
    public Reading brakeWarning = Reading.UNAVAILABLE;
    public Reading alternatorWarning = Reading.UNAVAILABLE;
    public Reading oilWarning = Reading.UNAVAILABLE;

    public Reading dashLightsOn = Reading.UNAVAILABLE;
    public Reading dashDimmerPct = Reading.UNAVAILABLE;

    /** False when the private CAN link has produced nothing recently. */
    public boolean linkAlive;
}
