package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.MotionEvent;
import android.view.View;

import com.jessiescars.cluster.core.DialUi;
import com.jessiescars.cluster.core.Settings;

/**
 * The settings list on the round display, driven by the dial (core/DialUi): turn to move, click to edit a row (its value then
 * shows between chevrons and turning changes it at once), click to keep, hold to cancel. A finger works too: tap a row to step
 * its value. Drawn in the 720 px design space, rows kept inside the circle.
 */
public class SettingsView extends View {
    private static final float ROW_H = 62f, ROW_W = 500f, TOP = 154f, GAP = 8f;

    private final Settings settings;
    private final DialUi dial;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF r = new RectF();
    private float holdProgress;                        // 0..1 while the dial button is held towards a long press

    public SettingsView(Context context, Settings settings, DialUi dial) {
        super(context);
        this.settings = settings;
        this.dial = dial;
        setBackgroundColor(0xFF000000);
        // The AAOS rotary controller moves focus between focusable views; this screen takes the dial itself.
        setFocusable(false);
    }

    private RectF rowRect(int i) {
        float y = TOP + i * (ROW_H + GAP);
        r.set(360f - ROW_W / 2f, y, 360f + ROW_W / 2f, y + ROW_H);
        return r;
    }

    /** Shows how far the held dial button is towards a long press. */
    public void setHoldProgress(float f) {
        holdProgress = f;
        invalidate();
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getActionMasked() != MotionEvent.ACTION_UP) return true;
        float s = Math.min(getWidth(), getHeight()) / 720f;
        float x = (e.getX() - (getWidth() - 720f * s) / 2f) / s, y = (e.getY() - (getHeight() - 720f * s) / 2f) / s;
        for (int i = 0; i < dial.count(); i++) {
            RectF rr = rowRect(i);
            if (x >= rr.left && x <= rr.right && y >= rr.top && y <= rr.bottom) {
                dial.tap(i);
                invalidate();
                return true;
            }
        }
        return true;
    }

    @Override
    protected void onDraw(Canvas c) {
        float s = Math.min(getWidth(), getHeight()) / 720f;
        c.save();
        c.translate((getWidth() - 720f * s) / 2f, (getHeight() - 720f * s) / 2f);
        c.scale(s, s);
        c.drawColor(0xFF0B1626);

        t.setTextAlign(Paint.Align.CENTER);
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setTextSize(40f);
        t.setColor(0xFFF4F7FF);
        c.drawText("Settings", 360f, 120f, t);

        final boolean editing = dial.mode() == DialUi.Mode.EDIT;
        for (int i = 0; i < dial.count(); i++) {
            RectF rr = rowRect(i);
            boolean sel = i == dial.selected();
            p.setStyle(Paint.Style.FILL);
            p.setColor(sel ? (editing ? 0xFF1F4A86 : 0xFF1A3560) : 0xFF132238);
            c.drawRoundRect(rr, 18f, 18f, p);
            if (sel) {
                p.setStyle(Paint.Style.STROKE);
                p.setStrokeWidth(editing ? 5f : 3f);
                p.setColor(editing ? 0xFFFFFFFF : 0xFF3DB6FF);
                c.drawRoundRect(rr, 18f, 18f, p);
            }
            t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            t.setTextSize(30f);
            float base = rr.centerY() + 11f;
            if (i == Settings.ROWS.length) {
                t.setTextAlign(Paint.Align.CENTER);
                t.setColor(0xFFF4F7FF);
                c.drawText("Back", 360f, base, t);
            } else {
                t.setTextAlign(Paint.Align.LEFT);
                t.setColor(0xFFC9D6EE);
                c.drawText(Settings.label(Settings.ROWS[i]), rr.left + 26f, base, t);
                t.setTextAlign(Paint.Align.RIGHT);
                t.setColor(0xFFFFFFFF);
                String v = settings.value(Settings.ROWS[i]);
                c.drawText(sel && editing ? "‹  " + v + "  ›" : v, rr.right - 26f, base, t);
            }
        }

        t.setTextAlign(Paint.Align.CENTER);
        t.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        t.setTextSize(24f);
        t.setColor(0xFF8A95A3);
        c.drawText(editing ? "turn: change    click: keep    hold: cancel" : "turn: move    click: edit    hold: close", 360f, 652f, t);

        if (holdProgress > 0.02f) {                      // a ring fills while the button is held
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(10f);
            p.setStrokeCap(Paint.Cap.ROUND);
            p.setColor(0xFF3DB6FF);
            c.drawArc(new RectF(24f, 24f, 696f, 696f), -90f, 360f * holdProgress, false, p);
            p.setStrokeCap(Paint.Cap.BUTT);
        }
        c.restore();
    }
}
