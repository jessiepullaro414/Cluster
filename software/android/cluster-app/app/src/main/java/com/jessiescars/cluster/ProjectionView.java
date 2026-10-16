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
 * PLACEHOLDER: there is no projection yet (PLAN.md B5, and the licensing route
 * is open). What is real is the geometry: the rectangular projection window is
 * the largest rectangle of the chosen aspect inside the safe circle, and the
 * two caps above and below it carry the lamps that used to be on the gauge.
 * The "map" inside the window is a drawing to show scale and shape, nothing more.
 * Speed is not shown here: it is on the small gauges.
 */
public class ProjectionView extends View {
    static final float C = 360f, SAFE_DIAMETER = 680f;

    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF win = new RectF();
    private final Path path = new Path();
    private final Lamps lamps = new Lamps();

    private VehicleState state = new VehicleState();
    private CenterLogic.Aspect aspect = CenterLogic.Aspect.FOUR_THREE;

    public ProjectionView(Context context) {
        super(context);
        setBackgroundColor(0xFF000000);
        t.setTextAlign(Paint.Align.CENTER);
    }

    public void setState(VehicleState s) { state = s; invalidate(); }

    public void setAspect(CenterLogic.Aspect a) { aspect = a; invalidate(); }

    /** The projection window in design-space pixels, for the platform code that places the real surface. */
    public static RectF windowFor(CenterLogic.Aspect a) {
        float[] wh = CenterLogic.inscribed(SAFE_DIAMETER, a);
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

        // the panel's edge, so the shape reads in screenshots
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(2f);
        p.setColor(pal.track);
        c.drawCircle(C, C, 358f, p);

        win.set(windowFor(aspect));
        drawFakeMap(c, pal);

        // lamps in the caps above and below the window
        float topY = (C - SAFE_DIAMETER / 2f + win.top) / 2f;
        float botY = (C + SAFE_DIAMETER / 2f + win.bottom) / 2f;
        lamps.drawTop(c, pal, state, C, topY, 70f);
        lamps.drawWarnings(c, pal, state, C, botY);
        c.restore();
    }

    private void drawFakeMap(Canvas c, Palette pal) {
        float lv = pal.level;
        c.save();
        path.reset();
        path.addRoundRect(win, 18f, 18f, Path.Direction.CW);
        c.clipPath(path);
        c.drawColor(Palette.scale(0xFF1B2A38, lv));                    // map ground

        p.setStyle(Paint.Style.STROKE);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setColor(Palette.scale(0xFF3A4D60, lv));                      // streets
        p.setStrokeWidth(14f);
        float w = win.width(), h = win.height();
        for (int i = 1; i <= 3; i++) {
            c.drawLine(win.left + w * i / 4f, win.top, win.left + w * i / 4f, win.bottom, p);
            c.drawLine(win.left, win.top + h * i / 4f, win.right, win.top + h * i / 4f, p);
        }
        p.setColor(Palette.scale(0xFF2F8CFF, lv));                      // route
        p.setStrokeWidth(12f);
        path.reset();
        path.moveTo(win.left + w * 0.25f, win.bottom);
        path.lineTo(win.left + w * 0.25f, win.top + h * 0.5f);
        path.lineTo(win.left + w * 0.75f, win.top + h * 0.5f);
        path.lineTo(win.left + w * 0.75f, win.top + h * 0.25f);
        c.drawPath(path, p);

        p.setStyle(Paint.Style.FILL);
        p.setColor(Palette.scale(0xFFFFFFFF, lv));                      // own position
        float px = win.left + w * 0.25f, py = win.top + h * 0.62f;
        path.reset();
        path.moveTo(px, py - 22f);
        path.lineTo(px + 15f, py + 14f);
        path.lineTo(px, py + 6f);
        path.lineTo(px - 15f, py + 14f);
        path.close();
        c.drawPath(path, p);

        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setTextSize(22f);
        t.setColor(Palette.scale(0xFFFFFFFF, lv));
        c.drawText("CARPLAY / ANDROID AUTO", C, win.top + 34f, t);
        t.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        t.setTextSize(18f);
        t.setColor(Palette.scale(0xFFFFC857, lv));
        c.drawText("placeholder - " + aspect.w + ":" + aspect.h + " window, "
                + Math.round(win.width()) + " x " + Math.round(win.height()) + " px", C, win.bottom - 14f, t);
        c.restore();
    }
}
