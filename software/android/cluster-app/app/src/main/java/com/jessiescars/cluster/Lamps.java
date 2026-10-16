package com.jessiescars.cluster;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;

import com.jessiescars.cluster.core.Palette;
import com.jessiescars.cluster.core.VehicleState;

/** High beam and warning lamps, shared by the gauge and the maps screen. All coordinates are in the 720 px design space. */
final class Lamps {
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();

    Lamps() {
        fill.setStyle(Paint.Style.FILL);
        text.setTextAlign(Paint.Align.CENTER);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        text.setTextSize(22f);
    }

    /** High beam at (cx, y). There are no turn arrows: the dash has physical turn indicators. */
    void drawTop(Canvas c, Palette p, VehicleState v, float cx, float y, float spread) {
        if (v.highBeam.on()) pill(c, cx, y, "HI", p.blue, 56f);
    }

    /** The lit lamps (high beam, brake, alternator, oil) in one row centred on cx; nothing when none is lit. */
    void drawRow(Canvas c, Palette p, VehicleState v, float cx, float y) {
        String[] label = { "HI", "BRAKE", "ALT", "OIL" };
        float[] width = { 56f, 92f, 74f, 74f };
        boolean[] lit = { v.highBeam.on(), v.brakeWarning.on(), v.alternatorWarning.on(), v.oilWarning.on() };
        int[] color = { p.blue, p.redline, p.redline, p.redline };
        float total = 0f;
        int n = 0;
        for (int i = 0; i < 4; i++) if (lit[i]) { total += width[i]; n++; }
        if (n == 0) return;
        total += 12f * (n - 1);
        float x = cx - total / 2f;
        for (int i = 0; i < 4; i++) {
            if (!lit[i]) continue;
            pill(c, x + width[i] / 2f, y, label[i], color[i], width[i]);
            x += width[i] + 12f;
        }
    }

    /** Brake, alternator and oil warnings in a row centred on cx. */
    void drawWarnings(Canvas c, Palette p, VehicleState v, float cx, float y) {
        if (v.brakeWarning.on()) pill(c, cx - 92f, y, "BRAKE", p.redline, 92f);
        if (v.alternatorWarning.on()) pill(c, cx, y, "ALT", p.redline, 74f);
        if (v.oilWarning.on()) pill(c, cx + 92f, y, "OIL", p.redline, 74f);
    }

    /** Lit warning lamp: solid rounded plate with dark lettering. */
    private void pill(Canvas c, float x, float y, String label, int color, float w) {
        fill.setColor(color);
        rect.set(x - w / 2f, y - 18f, x + w / 2f, y + 18f);
        c.drawRoundRect(rect, 10f, 10f, fill);
        text.setColor(0xFF000000);
        c.drawText(label, x, y + 8f, text);
    }
}
