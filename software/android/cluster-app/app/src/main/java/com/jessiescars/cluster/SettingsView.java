package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.MotionEvent;
import android.view.View;

import com.jessiescars.cluster.core.Settings;

/**
 * The settings list on the round display: one row per setting, a "Done" row at the bottom. Touch a row
 * to change it; with the rotary dial (up/down moves, click changes). Opened by a long press or the
 * MENU key, closed by Done or BACK. Drawn in the 720 px design space, rows kept inside the circle.
 */
public class SettingsView extends View {
    public interface Listener {
        void onChanged(Settings s);
        void onClose();
    }

    private static final float ROW_H = 76f, ROW_W = 500f, TOP = 178f, GAP = 10f;

    private final Settings settings;
    private final Listener listener;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF r = new RectF();
    private int selected;                              // 0..rows-1 are settings, rows is "Done"

    public SettingsView(Context context, Settings settings, Listener listener) {
        super(context);
        this.settings = settings;
        this.listener = listener;
        setBackgroundColor(0xFF000000);
        setFocusable(true);
    }

    private int rows() { return Settings.ROWS.length; }

    private RectF rowRect(int i) {
        float y = TOP + i * (ROW_H + GAP);
        r.set(360f - ROW_W / 2f, y, 360f + ROW_W / 2f, y + ROW_H);
        return r;
    }

    /** Dial or key: move the selection (delta +1 / -1), wrapping. */
    public void move(int delta) {
        int n = rows() + 1;
        selected = ((selected + delta) % n + n) % n;
        invalidate();
    }

    /** Dial click or tap on the selected row. */
    public void activate() {
        if (selected == rows()) { listener.onClose(); return; }
        settings.cycle(Settings.ROWS[selected]);
        listener.onChanged(settings);
        invalidate();
    }

    public int selectedRow() { return selected; }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getActionMasked() != MotionEvent.ACTION_UP) return true;
        float s = Math.min(getWidth(), getHeight()) / 720f;
        float x = (e.getX() - (getWidth() - 720f * s) / 2f) / s, y = (e.getY() - (getHeight() - 720f * s) / 2f) / s;
        for (int i = 0; i <= rows(); i++) {
            RectF rr = rowRect(i);
            if (x >= rr.left && x <= rr.right && y >= rr.top && y <= rr.bottom) {
                selected = i;
                activate();
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

        for (int i = 0; i <= rows(); i++) {
            RectF rr = rowRect(i);
            boolean sel = i == selected;
            p.setStyle(Paint.Style.FILL);
            p.setColor(sel ? 0xFF1A3560 : 0xFF132238);
            c.drawRoundRect(rr, 18f, 18f, p);
            if (sel) {
                p.setStyle(Paint.Style.STROKE);
                p.setStrokeWidth(3f);
                p.setColor(0xFF3DB6FF);
                c.drawRoundRect(rr, 18f, 18f, p);
            }
            t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            t.setTextSize(30f);
            float base = rr.centerY() + 11f;
            if (i == rows()) {
                t.setTextAlign(Paint.Align.CENTER);
                t.setColor(0xFFF4F7FF);
                c.drawText("Done", 360f, base, t);
            } else {
                t.setTextAlign(Paint.Align.LEFT);
                t.setColor(0xFFC9D6EE);
                c.drawText(Settings.label(Settings.ROWS[i]), rr.left + 26f, base, t);
                t.setTextAlign(Paint.Align.RIGHT);
                t.setColor(0xFFFFFFFF);
                c.drawText(settings.value(Settings.ROWS[i]), rr.right - 26f, base, t);
            }
        }
        c.restore();
    }
}
