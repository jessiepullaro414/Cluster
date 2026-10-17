package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.FrameLayout;

import com.jessiescars.cluster.core.Settings;

/**
 * The settings list on the round display, built the way the Android Automotive rotary controller expects, so its dial works
 * without special cases:
 *
 *  - every row is a real focusable view. Turning the dial moves focus from row to row (the controller does that), and the
 *    focused row is drawn highlighted. The last row, Back, is an ordinary button.
 *  - a setting row says it supports "direct manipulation" (its content description is the marker the controller looks for,
 *    DirectManipulationHelper in car-ui-lib). Pressing the dial on it makes the controller select the row: that is the edit
 *    mode. The row shows its value between chevrons, turning the dial now changes the value (the controller sends scroll
 *    actions, which the row handles), and the BACK key leaves edit mode, keeping the value.
 *  - without the controller (the dial wired to the app directly, as in the car): DPAD_CENTER clicks the focused row, which
 *    toggles the same edit mode, the turn keys call turn(), and holding the button cancels an edit (restores the old value)
 *    or closes the list.
 *
 * A finger works too: tap a row to step its value. Drawn in the 720 px design space, rows kept inside the circle.
 */
public class SettingsView extends FrameLayout {
    public interface Listener {
        void onChanged(Settings s);
        void onClose();
    }

    /** What the AAOS rotary controller looks for in a view's content description (car-ui-lib DirectManipulationHelper). */
    static final String DIRECT_MANIPULATION = "com.android.car.ui.utils.DIRECT_MANIPULATION";

    private static final float ROW_H = 62f, ROW_W = 500f, TOP = 154f, GAP = 8f;

    private final Settings settings;
    private final Listener listener;
    private final Settings before = new Settings();              // the values when an edit began, to cancel back to
    private final RowView[] rows = new RowView[Settings.ROWS.length + 1];
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);

    public SettingsView(Context context, Settings settings, Listener listener) {
        super(context);
        this.settings = settings;
        this.listener = listener;
        setBackgroundColor(0xFF0B1626);
        setWillNotDraw(false);
        for (int i = 0; i < rows.length; i++) {
            rows[i] = new RowView(context, i);
            addView(rows[i]);
        }
    }

    // ---- what the owner calls ------------------------------------------------------------------------------

    /** Put the dial on the first row. */
    public void focusFirst() {
        for (RowView r : rows) r.setSelected(false);
        rows[0].requestFocus();
    }

    /** True while a row is in edit mode. */
    public boolean editing() { return editingIndex() >= 0; }

    private int editingIndex() {
        for (int i = 0; i < rows.length; i++) if (rows[i].isSelected()) return i;
        return -1;
    }

    /** A turn from keys or a rotary encoder: change the value being edited, or move to the next / previous row. */
    public void turn(int dir) {
        int e = editingIndex();
        if (e >= 0) {
            step(e, dir);
            return;
        }
        int at = 0;
        for (int i = 0; i < rows.length; i++) if (rows[i].hasFocus()) at = i;
        rows[((at + dir) % rows.length + rows.length) % rows.length].requestFocus();
    }

    /** BACK: leave edit mode and keep the value. Returns false if no row was being edited (then the list should close). */
    public boolean back() {
        int e = editingIndex();
        if (e < 0) return false;
        rows[e].setSelected(false);
        return true;
    }

    // ---- editing ----------------------------------------------------------------------------------------------

    private void step(int index, int dir) {
        settings.step(Settings.ROWS[index], dir);
        listener.onChanged(settings);
        invalidateRows();
    }

    private void cancelEdit(int index) {
        settings.copyFrom(before);
        listener.onChanged(settings);
        rows[index].setSelected(false);
    }

    private void invalidateRows() {
        invalidate();
        for (RowView r : rows) r.invalidate();
    }

    // ---- layout and drawing ---------------------------------------------------------------------------------

    @Override
    protected void onLayout(boolean changed, int l, int tp, int r, int b) {
        float s = Math.min(r - l, b - tp) / 720f;
        float ox = ((r - l) - 720f * s) / 2f, oy = ((b - tp) - 720f * s) / 2f;
        for (int i = 0; i < rows.length; i++) {
            int x0 = Math.round(ox + (360f - ROW_W / 2f) * s), x1 = Math.round(ox + (360f + ROW_W / 2f) * s);
            int y0 = Math.round(oy + (TOP + i * (ROW_H + GAP)) * s), y1 = Math.round(oy + (TOP + i * (ROW_H + GAP) + ROW_H) * s);
            rows[i].measure(MeasureSpec.makeMeasureSpec(x1 - x0, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(y1 - y0, MeasureSpec.EXACTLY));
            rows[i].layout(x0, y0, x1, y1);
        }
    }

    @Override
    protected void onDraw(Canvas c) {
        float s = Math.min(getWidth(), getHeight()) / 720f;
        c.save();
        c.translate((getWidth() - 720f * s) / 2f, (getHeight() - 720f * s) / 2f);
        c.scale(s, s);
        t.setTextAlign(Paint.Align.CENTER);
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setTextSize(40f);
        t.setColor(0xFFF4F7FF);
        c.drawText("Settings", 360f, 120f, t);
        t.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        t.setTextSize(24f);
        t.setColor(0xFF8A95A3);
        c.drawText(editing() ? "turn: change    back: done" : "turn: move    click: edit    back: close", 360f, 652f, t);
        c.restore();
    }

    // ---- one row ----------------------------------------------------------------------------------------------

    private final class RowView extends View {
        private final int index;
        private final boolean backRow;
        private final Paint rp = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint rt = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF rect = new RectF();

        RowView(Context context, int index) {
            super(context);
            this.index = index;
            this.backRow = index == Settings.ROWS.length;
            setFocusable(true);
            setClickable(true);
            setDefaultFocusHighlightEnabled(false);
            if (!backRow) setContentDescription(DIRECT_MANIPULATION);       // pressing the dial on it enters edit mode
            setOnClickListener(v -> {
                if (backRow) listener.onClose();
                else setSelected(!isSelected());                              // (the controller selects it itself when it enters direct manipulation)
            });
            setOnLongClickListener(v -> {
                if (isSelected()) cancelEdit(index);
                else listener.onClose();
                return true;
            });
        }

        /** Selected = being edited. The rotary controller sets this when the dial is pressed on the row, and clears it on BACK. */
        @Override
        public void setSelected(boolean sel) {
            boolean was = isSelected();
            super.setSelected(sel);
            if (sel && !was) before.copyFrom(settings);
            invalidateRows();
        }

        @Override
        public boolean onTouchEvent(MotionEvent e) {
            if (e.getActionMasked() == MotionEvent.ACTION_UP) {
                if (backRow) listener.onClose();
                else {
                    settings.cycle(Settings.ROWS[index]);
                    listener.onChanged(settings);
                    invalidateRows();
                }
            }
            return true;
        }

        @Override
        public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
            super.onInitializeAccessibilityNodeInfo(info);
            if (!backRow) {
                info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD);      // the controller turns the dial into these
                info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD);
            }
        }

        @Override
        public boolean performAccessibilityAction(int action, Bundle args) {
            if (!backRow && isSelected()) {
                if (action == AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD.getId()) { step(index, +1); return true; }
                if (action == AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD.getId()) { step(index, -1); return true; }
            }
            return super.performAccessibilityAction(action, args);
        }

        @Override
        protected void onDraw(Canvas c) {
            float s = getHeight() / ROW_H;
            c.save();
            c.scale(s, s);
            boolean focus = hasFocus() || isFocused(), edit = isSelected();
            rect.set(0f, 0f, ROW_W, ROW_H);
            rp.setStyle(Paint.Style.FILL);
            rp.setColor(edit ? 0xFF1F4A86 : (focus ? 0xFF1A3560 : 0xFF132238));
            c.drawRoundRect(rect, 18f, 18f, rp);
            if (focus || edit) {
                rect.inset(1.5f, 1.5f);
                rp.setStyle(Paint.Style.STROKE);
                rp.setStrokeWidth(edit ? 5f : 3f);
                rp.setColor(edit ? 0xFFFFFFFF : 0xFF3DB6FF);
                c.drawRoundRect(rect, 17f, 17f, rp);
            }
            rt.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            rt.setTextSize(30f);
            float base = ROW_H / 2f + 11f;
            if (backRow) {
                rt.setTextAlign(Paint.Align.CENTER);
                rt.setColor(0xFFF4F7FF);
                c.drawText("Back", ROW_W / 2f, base, rt);
            } else {
                rt.setTextAlign(Paint.Align.LEFT);
                rt.setColor(0xFFC9D6EE);
                c.drawText(Settings.label(Settings.ROWS[index]), 26f, base, rt);
                rt.setTextAlign(Paint.Align.RIGHT);
                rt.setColor(0xFFFFFFFF);
                String v = settings.value(Settings.ROWS[index]);
                c.drawText(edit ? "‹  " + v + "  ›" : v, ROW_W - 26f, base, rt);
            }
            c.restore();
        }
    }
}
