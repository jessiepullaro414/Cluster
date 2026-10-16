package com.jessiescars.cluster;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.view.View;

/**
 * "No phone, show home" choice. PLACEHOLDER: the production image decides what
 * home is (Android's launcher, its own maps app, a clock); until then this only
 * marks that the choice works.
 */
public class HomeView extends View {
    private final Paint t = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);

    public HomeView(Context context) {
        super(context);
        setBackgroundColor(0xFF000000);
        t.setTextAlign(Paint.Align.CENTER);
        ring.setStyle(Paint.Style.STROKE);
        ring.setStrokeWidth(2f);
        ring.setColor(0xFF262B33);
    }

    @Override
    protected void onDraw(Canvas c) {
        float s = Math.min(getWidth(), getHeight()) / 720f;
        c.save();
        c.translate((getWidth() - 720f * s) / 2f, (getHeight() - 720f * s) / 2f);
        c.scale(s, s);
        c.drawCircle(360f, 360f, 358f, ring);
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setColor(0xFFFFFFFF);
        t.setTextSize(64f);
        c.drawText("HOME", 360f, 370f, t);
        t.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        t.setTextSize(24f);
        t.setColor(0xFF8A95A3);
        c.drawText("placeholder: no phone connected", 360f, 420f, t);
        c.restore();
    }
}
