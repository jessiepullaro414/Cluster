package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.View;

import com.jessiescars.cluster.core.Gauge;
import com.jessiescars.cluster.core.Palette;
import com.jessiescars.cluster.core.Reading;
import com.jessiescars.cluster.core.Units;
import com.jessiescars.cluster.core.VehicleState;

/**
 * The centre gauge. Everything is drawn in a 720 x 720 design space (the TSD
 * TST040HDBC-42 panel) and scaled to the view. The panel is round, so nothing
 * that matters sits outside a circle of radius 340 around (360, 360); the four
 * corners are never drawn.
 *
 *   outer ring   speed, 270 degree sweep open at the bottom, with a number scale
 *   inner ring   engine speed to 7000 rpm, red from 6000
 *   centre       speed number, unit, digital rpm, battery volts
 *   top          turn arrows and high beam
 *   bottom       brake, alternator and oil lamps
 */
public class ClusterView extends View {
    private static final float C = 360f;
    private static final float R_SPEED = 316f, W_SPEED = 24f;
    private static final float R_RPM = 222f, W_RPM = 13f;
    static final float RPM_MAX = 7000f, RPM_REDLINE = 6000f;

    private final Paint arc = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private final Path path = new Path();

    private VehicleState state = new VehicleState();
    private Units units = Units.MPH;

    public ClusterView(Context context) {
        super(context);
        arc.setStyle(Paint.Style.STROKE);
        line.setStyle(Paint.Style.STROKE);
        line.setStrokeCap(Paint.Cap.BUTT);
        text.setTextAlign(Paint.Align.CENTER);
        fill.setStyle(Paint.Style.FILL);
        setBackgroundColor(0xFF000000);
        setOnClickListener(v -> {                       // tap toggles the units
            units = units == Units.MPH ? Units.KPH : Units.MPH;
            invalidate();
        });
    }

    public void setState(VehicleState s) {
        state = s;
        invalidate();
    }

    public Units units() { return units; }

    @Override
    protected void onDraw(Canvas c) {
        float s = Math.min(getWidth(), getHeight()) / 720f;
        c.save();
        c.translate((getWidth() - 720f * s) / 2f, (getHeight() - 720f * s) / 2f);
        c.scale(s, s);

        final VehicleState v = state;
        final Palette p = Palette.forLights(v.dashLightsOn.on(),
                v.dashDimmerPct.available ? v.dashDimmerPct.value : Float.NaN);
        c.drawColor(p.background);

        drawSpeedRing(c, p, v);
        drawRpmRing(c, p, v);
        drawCentre(c, p, v);
        drawTop(c, p, v);
        drawLamps(c, p, v);
        if (!v.linkAlive) {
            text.setColor(p.warning);
            text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
            text.setTextSize(46f);
            c.drawText("NO DATA", C, 300f, text);
        }
        c.restore();
    }

    // ---- rings ---------------------------------------------------------

    private void ring(Canvas c, float r, float w, float from, float to, int color) {
        oval.set(C - r, C - r, C + r, C + r);
        arc.setStrokeWidth(w);
        arc.setColor(color);
        arc.setStrokeCap(Paint.Cap.BUTT);
        c.drawArc(oval, Gauge.angle(from), Gauge.SWEEP_DEG * (to - from), false, arc);
    }

    private void drawSpeedRing(Canvas c, Palette p, VehicleState v) {
        final float max = units == Units.MPH ? 120f : 200f;
        ring(c, R_SPEED, W_SPEED, 0f, 1f, p.track);
        if (v.speedMps.available) {
            float f = Gauge.fraction(units.fromMps(v.speedMps.value), 0f, max);
            ring(c, R_SPEED, W_SPEED, 0f, f, p.accent);
        }
        line.setColor(p.textDim);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(24f);
        for (int val = 0; val <= (int) max; val += 10) {
            boolean major = val % 20 == 0;
            double a = Math.toRadians(Gauge.angle(Gauge.fraction(val, 0f, max)));
            float r0 = R_SPEED - W_SPEED / 2f - 4f, r1 = r0 - (major ? 18f : 9f);
            line.setStrokeWidth(major ? 3f : 2f);
            c.drawLine(C + (float) Math.cos(a) * r0, C + (float) Math.sin(a) * r0,
                       C + (float) Math.cos(a) * r1, C + (float) Math.sin(a) * r1, line);
            if (major) {
                float rt = r1 - 20f;
                text.setColor(p.textDim);
                c.drawText(Integer.toString(val), C + (float) Math.cos(a) * rt,
                           C + (float) Math.sin(a) * rt + 8f, text);
            }
        }
    }

    private void drawRpmRing(Canvas c, Palette p, VehicleState v) {
        float red = Gauge.fraction(RPM_REDLINE, 0f, RPM_MAX);
        ring(c, R_RPM, W_RPM, 0f, red, p.track);
        ring(c, R_RPM, W_RPM, red, 1f, Palette.scale(p.redline, 0.35f));
        if (v.rpm.available) {
            float f = Gauge.fraction(v.rpm.value, 0f, RPM_MAX);
            ring(c, R_RPM, W_RPM, 0f, Math.min(f, red), p.text);
            if (f > red) ring(c, R_RPM, W_RPM, red, f, p.redline);
        }
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(18f);
        text.setColor(p.textDim);
        for (int k = 1; k <= 7; k++) {
            double a = Math.toRadians(Gauge.angle(Gauge.fraction(k * 1000f, 0f, RPM_MAX)));
            float rt = R_RPM - W_RPM / 2f - 16f;
            c.drawText(Integer.toString(k), C + (float) Math.cos(a) * rt,
                       C + (float) Math.sin(a) * rt + 6f, text);
        }
    }

    // ---- centre --------------------------------------------------------

    private void drawCentre(Canvas c, Palette p, VehicleState v) {
        text.setColor(v.speedMps.available ? p.text : p.textDim);
        text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
        text.setTextSize(176f);
        c.drawText(units.speedText(v.speedMps), C, 402f, text);

        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(30f);
        text.setColor(p.textDim);
        c.drawText(units.label, C, 444f, text);

        text.setTextSize(36f);
        text.setColor(v.rpm.available ? p.text : p.textDim);
        c.drawText(Units.rpmText(v.rpm) + " RPM", C, 506f, text);

        text.setTextSize(28f);
        text.setColor(v.batteryV.available && v.batteryV.value < 11.5f ? p.warning : p.textDim);
        c.drawText(Units.voltsText(v.batteryV), C, 552f, text);
    }

    // ---- indicators ----------------------------------------------------

    private void drawTop(Canvas c, Palette p, VehicleState v) {
        // Kept inside the rpm ring (inner edge at radius about 215 from the centre).
        if (v.turnLeft.on()) arrow(c, 296f, 214f, -1, p.good);
        if (v.turnRight.on()) arrow(c, 424f, 214f, +1, p.good);
        if (v.highBeam.on()) pill(c, 360f, 214f, "HI", p.blue, 56f);
    }

    private void drawLamps(Canvas c, Palette p, VehicleState v) {
        if (v.brakeWarning.on()) pill(c, 268f, 628f, "BRAKE", p.redline, 92f);
        if (v.alternatorWarning.on()) pill(c, 360f, 628f, "ALT", p.redline, 74f);
        if (v.oilWarning.on()) pill(c, 452f, 628f, "OIL", p.redline, 74f);
    }

    /** Solid arrow centred on (x, y) pointing left (dir -1) or right (+1). */
    private void arrow(Canvas c, float x, float y, int dir, int color) {
        fill.setColor(color);
        path.reset();
        path.moveTo(x + dir * 26f, y);
        path.lineTo(x - dir * 4f, y - 26f);
        path.lineTo(x - dir * 4f, y - 10f);
        path.lineTo(x - dir * 26f, y - 10f);
        path.lineTo(x - dir * 26f, y + 10f);
        path.lineTo(x - dir * 4f, y + 10f);
        path.lineTo(x - dir * 4f, y + 26f);
        path.close();
        c.drawPath(path, fill);
    }

    /** Lit warning lamp: solid rounded plate with dark lettering. */
    private void pill(Canvas c, float x, float y, String label, int color, float w) {
        fill.setColor(color);
        oval.set(x - w / 2f, y - 18f, x + w / 2f, y + 18f);
        c.drawRoundRect(oval, 10f, 10f, fill);
        text.setColor(0xFF000000);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        text.setTextSize(22f);
        c.drawText(label, x, y + 8f, text);
    }
}
