package com.jessiescars.cluster;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;

import com.jessiescars.cluster.core.Palette;
import com.jessiescars.cluster.core.VehicleState;

/** Turn arrows, high beam and warning lamps, shared by the gauge and the maps screen. All coordinates are in the 720 px design space. */
final class Lamps {
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final Path path = new Path();

    Lamps() {
        fill.setStyle(Paint.Style.FILL);
        text.setTextAlign(Paint.Align.CENTER);
        text.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        text.setTextSize(22f);
    }

    /** Turn arrows at (cx - spread, y) and (cx + spread, y), high beam at (cx, y). */
    void drawTop(Canvas c, Palette p, VehicleState v, float cx, float y, float spread) {
        if (v.turnLeft.on()) arrow(c, cx - spread, y, -1, p.good);
        if (v.turnRight.on()) arrow(c, cx + spread, y, +1, p.good);
        if (v.highBeam.on()) pill(c, cx, y, "HI", p.blue, 56f);
    }

    /** Brake, alternator and oil warnings in a row centred on cx. */
    void drawWarnings(Canvas c, Palette p, VehicleState v, float cx, float y) {
        if (v.brakeWarning.on()) pill(c, cx - 92f, y, "BRAKE", p.redline, 92f);
        if (v.alternatorWarning.on()) pill(c, cx, y, "ALT", p.redline, 74f);
        if (v.oilWarning.on()) pill(c, cx + 92f, y, "OIL", p.redline, 74f);
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
        rect.set(x - w / 2f, y - 18f, x + w / 2f, y + 18f);
        c.drawRoundRect(rect, 10f, 10f, fill);
        text.setColor(0xFF000000);
        c.drawText(label, x, y + 8f, text);
    }
}
