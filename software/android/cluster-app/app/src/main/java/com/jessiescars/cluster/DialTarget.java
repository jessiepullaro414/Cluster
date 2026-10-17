package com.jessiescars.cluster;

import android.content.Context;
import android.view.MotionEvent;
import android.view.View;

/**
 * A see-through, window-sized view that the dial can focus on the main screen (maps, gauge or home). It is the thing the dial
 * "presses": a click on it flips maps and gauge, a long press opens the settings. It takes no touches (those go to the views
 * underneath, for example the phone's projected screen) and draws nothing.
 *
 * The AAOS rotary controller injects the dial button as DPAD_CENTER into the focused view, and Android turns a short press into
 * onClick and a held press into onLongClick, so this works the same with the controller and with keys sent straight to the app.
 */
final class DialTarget extends View {
    DialTarget(Context context) {
        super(context);
        setFocusable(true);
        setClickable(true);
        setLongClickable(true);
        setDefaultFocusHighlightEnabled(false);
        setWillNotDraw(true);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        return false;
    }
}
