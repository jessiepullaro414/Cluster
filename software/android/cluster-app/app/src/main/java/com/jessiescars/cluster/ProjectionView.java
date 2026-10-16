package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.View;

import com.jessiescars.cluster.core.CenterLogic;
import com.jessiescars.cluster.core.Palette;
import com.jessiescars.cluster.core.VehicleState;

/**
 * Centre display while a phone is projecting CarPlay / Android Auto.
 *
 * PLACEHOLDER: there is no projection yet (PLAN.md B5, and the licensing route is open). What is real
 * is the geometry. By default the picture is ROUND: it fills the whole circle and the panel's edge
 * crops it, as the Android Auto screen does in the owner's reference picture. The other shapes put a
 * rectangle (4:3, square, 16:9) in the middle of the circle. The "map" is a drawing to show scale and
 * shape, nothing more.
 *
 * There are no turn indicators (the dash has physical ones) and speed is not shown here (it is on the
 * small gauges). Only the lamps that are lit (high beam, brake, alternator, oil) appear, in a row along
 * the lower edge.
 */
public class ProjectionView extends View {
    static final float C = 360f, SAFE_DIAMETER = 680f, PANEL_RADIUS = 358f;

    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF win = new RectF();
    private final Path path = new Path();
    private final Path circle = new Path();
    private final Lamps lamps = new Lamps();

    private VehicleState state = new VehicleState();
    private CenterLogic.Aspect aspect = CenterLogic.Aspect.ROUND;

    public ProjectionView(Context context) {
        super(context);
        setBackgroundColor(0xFF000000);
        t.setTextAlign(Paint.Align.CENTER);
        circle.addCircle(C, C, PANEL_RADIUS, Path.Direction.CW);
    }

    public void setState(VehicleState s) { state = s; invalidate(); }

    public void setAspect(CenterLogic.Aspect a) { aspect = a; invalidate(); }

    /** The projection window in design-space pixels, for the platform code that places the real surface. */
    public static RectF windowFor(CenterLogic.Aspect a) {
        float[] wh = CenterLogic.inscribed(a == CenterLogic.Aspect.ROUND ? 2f * PANEL_RADIUS : SAFE_DIAMETER, a);
        return new RectF(C - wh[0] / 2f, C - wh[1] / 2f, C + wh[0] / 2f, C + wh[1] / 2f);
    }

    @Override
    protected void onDraw(Canvas c) {
        float s = Math.min(getWidth(), getHeight()) / 720f;
        c.save();
        c.translate((getWidth() - 720f * s) / 2f, (getHeight() - 720f * s) / 2f);
        c.scale(s, s);

        Palette pal = Palette.forLights(state.dashLightsOn.on(),
                state.dashDimmerPct.available ? state.dashDimmerPct.value : Float.NaN);
        c.drawColor(pal.background);

        win.set(windowFor(aspect));
        boolean round = aspect == CenterLogic.Aspect.ROUND;
        c.save();
        if (round) c.clipPath(circle);
        drawFakeMap(c, pal, round);
        c.restore();

        if (!round) {                                           // show the shape of the panel around the window
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(2f);
            p.setColor(pal.track);
            c.drawCircle(C, C, PANEL_RADIUS, p);
        }
        // lit lamps only, along the lower edge of the circle (clear of the map's own controls)
        lamps.drawRow(c, pal, state, C, round ? 652f : (win.bottom + (C + SAFE_DIAMETER / 2f)) / 2f);
        c.restore();
    }

    private void drawFakeMap(Canvas c, Palette pal, boolean round) {
        float lv = pal.level;
        c.save();
        if (!round) {
            path.reset();
            path.addRoundRect(win, 18f, 18f, Path.Direction.CW);
            c.clipPath(path);
        }
        c.drawColor(Palette.scale(0xFF1B2A38, lv));                    // map ground

        // streets, turned 30 degrees about the centre so the round shape reads as a map and not a grid
        c.save();
        c.rotate(-30f, C, C);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setColor(Palette.scale(0xFF3A4D60, lv));
        p.setStrokeWidth(round ? 22f : 14f);
        for (int i = -4; i <= 4; i++) {
            float o = i * (round ? 130f : 95f);
            c.drawLine(C + o, win.top - 200f, C + o, win.bottom + 200f, p);
            c.drawLine(win.left - 200f, C + o, win.right + 200f, C + o, p);
        }
        p.setStrokeWidth(round ? 12f : 8f);
        p.setColor(Palette.scale(0xFF2C3E50, lv));
        for (int i = -8; i <= 8; i++) {
            float o = i * (round ? 65f : 47f) + (round ? 32f : 23f);
            c.drawLine(C + o, win.top - 200f, C + o, win.bottom + 200f, p);
        }
        c.restore();

        // a park and a river, for some variety
        p.setStyle(Paint.Style.FILL);
        p.setColor(Palette.scale(0xFF1F4A3A, lv));
        c.drawCircle(C - 190f, C - 150f, round ? 90f : 60f, p);
        p.setColor(Palette.scale(0xFF1D3F63, lv));
        path.reset();
        path.moveTo(C + 120f, win.top);
        path.cubicTo(C + 230f, C - 120f, C + 20f, C + 60f, C + 160f, win.bottom);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(round ? 40f : 24f);
        c.drawPath(path, p);

        // the route and our position
        p.setColor(Palette.scale(0xFF2F8CFF, lv));
        p.setStrokeWidth(round ? 18f : 12f);
        path.reset();
        path.moveTo(C - 60f, win.bottom);
        path.lineTo(C - 60f, C - 10f);
        path.lineTo(C + 150f, C - 10f);
        path.lineTo(C + 150f, win.top + (round ? 40f : 20f));
        c.drawPath(path, p);

        p.setStyle(Paint.Style.FILL);
        p.setColor(Palette.scale(0xFFFFFFFF, lv));
        float px = C - 60f, py = C + (round ? 150f : 120f);
        path.reset();
        path.moveTo(px, py - 30f);
        path.lineTo(px + 20f, py + 20f);
        path.lineTo(px, py + 8f);
        path.lineTo(px - 20f, py + 20f);
        path.close();
        c.drawPath(path, p);

        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setTextSize(24f);
        t.setColor(Palette.scale(0xFFFFFFFF, lv));
        c.drawText("CARPLAY / ANDROID AUTO", C, round ? 118f : win.top + 36f, t);
        t.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        t.setTextSize(19f);
        t.setColor(Palette.scale(0xFFFFC857, lv));
        c.drawText("placeholder - " + (round ? "round, fills the panel" : aspect.w + ":" + aspect.h + " window, "
                + Math.round(win.width()) + " x " + Math.round(win.height()) + " px"), C, round ? 150f : win.bottom - 16f, t);
        c.restore();
    }
}
