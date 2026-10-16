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
import com.jessiescars.cluster.core.Settings;
import com.jessiescars.cluster.core.Units;
import com.jessiescars.cluster.core.VehicleState;

/**
 * The speedometer on the round centre display, drawn in the style of the gauge theme the owner chose, so it matches the
 * four small screens (gauges-fw/src/dial*.c). While it is up, the small screens do not repeat speed (see
 * DisplaySettings.CenterShowsSpeed and screens_layout_for in gauges-fw): the screen that had it shows another gauge.
 *
 * Everything is drawn in a 720 x 720 design space (the TSD TST040HDBC-42 panel) and scaled to the view. The panel is round,
 * so nothing that matters sits outside a circle of radius 340 around (360, 360). There are no turn indicators: the dash has
 * physical ones. Styling is a first pass to tune together with the owner.
 *
 *   classic   needle on a 270 degree scale, seven-segment style number below
 *   modern    navy face, blue progress arc, big number
 *   carplay   black, thin ring with a white knob, light number (Apple-inspired)
 *   factory   the 1966 Mustang speedometer: printed numerals radiating out, chrome hub, odometer window, red-orange needle
 */
public class ClusterView extends View {
    private static final float C = 360f;

    private final Paint arc = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();
    private final Path path = new Path();
    private final Lamps lamps = new Lamps();

    private VehicleState state = new VehicleState();
    private Units units = Units.MPH;
    private int theme = 1;

    public ClusterView(Context context) {
        super(context);
        arc.setStyle(Paint.Style.STROKE);
        line.setStyle(Paint.Style.STROKE);
        line.setStrokeCap(Paint.Cap.BUTT);
        fill.setStyle(Paint.Style.FILL);
        text.setTextAlign(Paint.Align.CENTER);
        setBackgroundColor(0xFF000000);
    }

    public void setState(VehicleState s) {
        state = s;
        invalidate();
    }

    /** The look: Settings theme number (0 classic, 1 modern, 2 CarPlay, 3 factory). */
    public void setTheme(int t) {
        theme = Settings.clampTheme(t);
        invalidate();
    }

    public void setImperial(boolean imperial) {
        units = imperial ? Units.MPH : Units.KPH;
        invalidate();
    }

    public Units units() { return units; }
    public int theme() { return theme; }

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
        final float spd = v.speedMps.available ? units.fromMps(Math.max(0f, v.speedMps.value)) : Float.NaN;

        switch (theme) {
            case 0: drawClassic(c, p, spd); lamps.drawRow(c, p, v, C, 644f); break;
            case 2: drawCarPlay(c, p, spd); lamps.drawRow(c, p, v, C, 644f); break;
            case 3: drawFactory(c, p, v, spd); lamps.drawWarnings(c, p, v, C, 644f); break;
            default: drawModern(c, p, spd); lamps.drawRow(c, p, v, C, 644f); break;
        }
        if (!v.linkAlive) {
            text.setColor(p.warning);
            text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
            text.setTextScaleX(1f);
            text.setTextSize(46f);
            c.drawText("NO DATA", C, 300f, text);
        }
        c.restore();
    }

    // ---- helpers ---------------------------------------------------------

    private void ring(Canvas c, float r, float w, float from, float to, int color) {
        oval.set(C - r, C - r, C + r, C + r);
        arc.setStrokeWidth(w);
        arc.setColor(color);
        arc.setStrokeCap(Paint.Cap.BUTT);
        c.drawArc(oval, Gauge.angle(from), Gauge.SWEEP_DEG * (to - from), false, arc);
    }

    /** A progress arc whose colour runs c0 -> c1 along the whole scale (drawn in small steps). */
    private void gradientRing(Canvas c, float r, float w, float shown, int c0, int c1) {
        oval.set(C - r, C - r, C + r, C + r);
        arc.setStrokeWidth(w);
        arc.setStrokeCap(Paint.Cap.BUTT);
        int steps = Math.max(1, Math.round(shown * 135f));
        for (int i = 0; i < steps; i++) {
            float f0 = (float) i / 135f;
            arc.setColor(mix(c0, c1, f0));
            c.drawArc(oval, Gauge.angle(f0), Gauge.SWEEP_DEG / 135f * 1.4f, false, arc);
        }
    }

    private static int mix(int a, int b, float t) {
        int r = Math.round(((a >> 16) & 0xFF) * (1 - t) + ((b >> 16) & 0xFF) * t);
        int g = Math.round(((a >> 8) & 0xFF) * (1 - t) + ((b >> 8) & 0xFF) * t);
        int bl = Math.round((a & 0xFF) * (1 - t) + (b & 0xFF) * t);
        return 0xFF000000 | (r << 16) | (g << 8) | bl;
    }

    private void disc(Canvas c, float x, float y, float r, int color) {
        fill.setColor(color);
        c.drawCircle(x, y, r, fill);
    }

    private float[] polar(float cx, float cy, float r, float deg) {
        double a = Math.toRadians(deg);
        return new float[] { cx + (float) Math.cos(a) * r, cy + (float) Math.sin(a) * r };
    }

    private void tick(Canvas c, float cx, float cy, float deg, float r0, float r1, float w, int color) {
        float[] a = polar(cx, cy, r0, deg), b = polar(cx, cy, r1, deg);
        line.setColor(color);
        line.setStrokeWidth(w);
        c.drawLine(a[0], a[1], b[0], b[1], line);
    }

    private String speedText(float spd) {
        return Float.isNaN(spd) ? "--" : Integer.toString(Math.round(spd));
    }

    // ---- classic: needle -------------------------------------------------

    private void drawClassic(Canvas c, Palette p, float spd) {
        final float max = units == Units.MPH ? 120f : 200f;
        ring(c, 318f, 22f, 0f, 1f, p.track);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextScaleX(1f);
        text.setTextSize(40f);
        for (int val = 0; val <= (int) max; val += 10) {
            boolean major = val % 20 == 0;
            float ang = Gauge.angle(Gauge.fraction(val, 0f, max));
            tick(c, C, C, ang, 296f - (major ? 40f : 18f), 296f, major ? 5f : 3f, p.text);
            if (major) {
                float[] q = polar(C, C, 218f, ang);
                text.setColor(p.textDim);
                c.drawText(Integer.toString(val), q[0], q[1] + 14f, text);
            }
        }
        int needle = Palette.scale(0xFFFF9500, p.level);
        if (!Float.isNaN(spd)) {
            float ang = Gauge.angle(Gauge.fraction(spd, 0f, max));
            float[] tip = polar(C, C, 272f, ang), tail = polar(C, C, -34f, ang);
            line.setColor(needle);
            line.setStrokeWidth(13f);
            line.setStrokeCap(Paint.Cap.ROUND);
            c.drawLine(tail[0], tail[1], tip[0], tip[1], line);
            line.setStrokeCap(Paint.Cap.BUTT);
        }
        disc(c, C, C, 30f, Palette.scale(0xFF70747C, p.level));
        text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
        text.setTextSize(150f);
        text.setColor(Float.isNaN(spd) ? p.textDim : p.text);
        c.drawText(speedText(spd), C, 560f, text);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(34f);
        text.setColor(p.textDim);
        c.drawText(units.label, C, 610f, text);
    }

    // ---- modern: navy face, blue arc ------------------------------------------

    private void drawModern(Canvas c, Palette p, float spd) {
        final float max = units == Units.MPH ? 160f : 260f;
        c.drawColor(Palette.scale(0xFF0B1626, p.level));
        ring(c, 297f, 33f, 0f, 1f, Palette.scale(0xFF15233A, p.level));
        float f = Float.isNaN(spd) ? 0f : Gauge.fraction(spd, 0f, max);
        if (f > 0f) gradientRing(c, 297f, 33f, f, Palette.scale(0xFF1A4FD8, p.level), Palette.scale(0xFF3DB6FF, p.level));
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextScaleX(1f);
        text.setTextSize(34f);
        float step = units == Units.MPH ? 20f : 40f;
        for (float val = 0f; val <= max + 0.1f; val += step / 2f) {
            boolean major = Math.abs(val % step) < 0.01f;
            float ang = Gauge.angle(Gauge.fraction(val, 0f, max));
            tick(c, C, C, ang, 322f, major ? 338f : 330f, major ? 6f : 3f, major ? p.text : p.textDim);
            if (major) {
                float[] q = polar(C, C, 232f, ang);
                text.setColor(Palette.scale(0xFFC9D6EE, p.level));
                c.drawText(Integer.toString(Math.round(val)), q[0], q[1] + 12f, text);
            }
        }
        text.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        text.setTextSize(210f);
        text.setColor(Float.isNaN(spd) ? p.textDim : p.text);
        c.drawText(speedText(spd), C, 420f, text);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(38f);
        text.setColor(Palette.scale(0xFFC9D6EE, p.level));
        c.drawText(units.label, C, 486f, text);
    }

    // ---- carplay: Apple-inspired -----------------------------------------------

    private void drawCarPlay(Canvas c, Palette p, float spd) {
        final float max = units == Units.MPH ? 160f : 260f;
        final float r = 324f, w = 24f;
        final int track = Palette.scale(0xFF1F1F23, p.level);
        ring(c, r, w, 0f, 1f, track);
        float f = Float.isNaN(spd) ? 0f : Gauge.fraction(spd, 0f, max);
        int c0 = Palette.scale(0xFF0A84FF, p.level), c1 = Palette.scale(0xFF64D2FF, p.level);
        if (!Float.isNaN(spd)) {
            if (f > 0f) gradientRing(c, r, w, f, c0, c1);
            float[] s0 = polar(C, C, r, Gauge.angle(0f)), s1 = polar(C, C, r, Gauge.angle(f));
            if (f > 0f) disc(c, s0[0], s0[1], w / 2f, c0);
            disc(c, s1[0], s1[1], w / 2f + 12f, p.background);          // a black gap, then the white knob
            disc(c, s1[0], s1[1], w / 2f + 1.5f, 0xFF000000 | Palette.scale(0xFFFFFFFF, p.level));
        }
        text.setTextScaleX(1f);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(36f);
        text.setColor(Palette.scale(0xFF8E8E93, p.level));
        c.drawText("SPEED", C, 222f, text);
        text.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        text.setTextSize(250f);
        text.setColor(Float.isNaN(spd) ? p.textDim : p.text);
        c.drawText(speedText(spd), C, 436f, text);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        text.setTextSize(38f);
        text.setColor(Palette.scale(0xFF8E8E93, p.level));
        c.drawText(units.label, C, 506f, text);
    }

    // ---- factory: the 1966 Mustang speedometer ----------------------------------

    private static final float F_START = 151f, F_SWEEP = 238.5f;       // measured on the owner's photo (see gauges-fw/tools/gen_faces.py)
    private static final float F_PX = 360f, F_PY = 378f;

    private void drawFactory(Canvas c, Palette p, VehicleState v, float spd) {
        final float L = p.level;
        final boolean mph = units == Units.MPH;
        final float vmax = mph ? 140f : 220f;
        final int minor = mph ? 5 : 10, label = mph ? 10 : 20;
        final int face = Palette.scale(0xFF080808, L), print = Palette.scale(0xFFF2EFE6, L);
        c.drawColor(face);
        c.save();
        c.translate(0f, 28f);                                  // the face is drawn high in its own space

        // ticks, then the numerals with their tops pointing outwards
        for (int val = 0; val <= (int) vmax; val += minor) {
            boolean tens = val % label == 0;
            float ang = F_START + F_SWEEP * val / vmax;
            tick(c, F_PX, F_PY, ang, (tens ? 47f : 52f) * 3f, (tens ? 61f : 60f) * 3f, tens ? 6.6f : 4.8f, print);
        }
        text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.NORMAL));      // regular weight: thin strokes, like the printed numerals
        text.setColor(print);
        text.setTextSize(54f);
        for (int val = 0; val <= (int) vmax; val += label) {                             // including the 0
            float ang = F_START + F_SWEEP * val / vmax;
            float[] q = polar(F_PX, F_PY, 77f * 3f, ang);
            text.setTextScaleX(val >= 100 ? 0.64f : 0.82f);
            c.save();
            c.translate(q[0], q[1]);
            c.rotate(ang + 90f);
            c.drawText(Integer.toString(val), 0f, 19f, text);
            c.restore();
        }
        text.setTextScaleX(0.9f);
        text.setTextSize(38f);
        c.drawText(mph ? "MILES" : "KM/H", C, 78f, text);
        text.setTextScaleX(1f);

        // the high-beam lens: blue, brighter when lit
        disc(c, 357f, 261f, 17f, Palette.scale(v.highBeam.on() ? 0xFF3C8CFF : 0xFF1457D8, L));

        // an odometer window with six empty cells (no odometer data exists yet)
        final float x0 = 246f, y0 = 441f, x1 = 474f, y1 = 486f;
        fill.setColor(0xFF000000);
        c.drawRoundRect(x0, y0, x1, y1, 5f, 5f, fill);
        line.setColor(Palette.scale(0xFF969696, L));
        line.setStrokeWidth(4f);
        c.drawRoundRect(x0, y0, x1, y1, 5f, 5f, line);
        line.setColor(Palette.scale(0xFF5A5A5A, L));
        line.setStrokeWidth(2.5f);
        for (int i = 1; i < 6; i++) {
            float x = x0 + (x1 - x0) * i / 6f;
            c.drawLine(x, y0 + 5f, x, y1 - 5f, line);
        }

        // the needle: wide root, fine tip, red-orange
        if (!Float.isNaN(spd)) {
            float ang = F_START + F_SWEEP * Math.min(1f, spd / vmax);
            double a = Math.toRadians(ang), ca = Math.cos(a), sa = Math.sin(a);
            float len = 67f * 3f, root = 7f, tip = 1.4f;
            path.reset();
            path.moveTo((float) (F_PX - sa * root), (float) (F_PY + ca * root));
            path.lineTo((float) (F_PX + ca * len - sa * tip), (float) (F_PY + sa * len + ca * tip));
            path.lineTo((float) (F_PX + ca * len + sa * tip), (float) (F_PY + sa * len - ca * tip));
            path.lineTo((float) (F_PX + sa * root), (float) (F_PY - ca * root));
            path.close();
            fill.setColor(Palette.scale(0xFFFF4A1A, L));
            c.drawPath(path, fill);
        }
        // the chrome hub
        disc(c, F_PX, F_PY, 51f, Palette.scale(0xFFE6E8EB, L));
        disc(c, F_PX, F_PY, 45f, Palette.scale(0xFFB9BDC3, L));
        disc(c, F_PX, F_PY, 31f, Palette.scale(0xFF1A1A1A, L));
        disc(c, F_PX, F_PY, 21f, Palette.scale(0xFF3A3C40, L));
        c.restore();
    }
}
