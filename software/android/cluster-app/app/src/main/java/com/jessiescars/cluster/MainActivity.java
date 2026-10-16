package com.jessiescars.cluster;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;

import com.jessiescars.cluster.core.DriveScenario;

/**
 * Full-screen cluster. The data comes from a fake source: the scripted drive in
 * core/DriveScenario, optionally overridden from adb for testing:
 *
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --ef speed_kph 120 --ez night true --ef dimmer 30
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --ez link_dead true
 *   adb shell am broadcast -a com.jessiescars.cluster.CLEAR
 *
 * extras: speed_kph, rpm, dimmer (float); night, link_dead, turn_left,
 * high_beam, brake, alt, oil (boolean). The real source (the VHAL bridge) replaces
 * only FakeTick; ClusterView only ever sees a VehicleState.
 */
public class MainActivity extends Activity {
    static final String ACTION_SET = "com.jessiescars.cluster.SET";
    static final String ACTION_CLEAR = "com.jessiescars.cluster.CLEAR";
    private static final long TICK_MS = 50;            // 20 updates per second

    private ClusterView view;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final DriveScenario.Override override = new DriveScenario.Override();
    private long t0;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            float t = (SystemClock.elapsedRealtime() - t0) / 1000f;
            view.setState(DriveScenario.at(t, override));
            handler.postDelayed(this, TICK_MS);
        }
    };

    private final BroadcastReceiver debug = new BroadcastReceiver() {
        @Override public void onReceive(Context ctx, Intent i) {
            if (ACTION_CLEAR.equals(i.getAction())) {
                override.speedKph = override.rpm = override.dimmerPct = null;
                override.night = override.linkDead = override.turnLeft = override.highBeam = null;
                override.brake = override.alternator = override.oil = null;
                return;
            }
            if (i.hasExtra("speed_kph")) override.speedKph = i.getFloatExtra("speed_kph", 0f);
            if (i.hasExtra("rpm")) override.rpm = i.getFloatExtra("rpm", 0f);
            if (i.hasExtra("dimmer")) override.dimmerPct = i.getFloatExtra("dimmer", 100f);
            if (i.hasExtra("night")) override.night = i.getBooleanExtra("night", false);
            if (i.hasExtra("link_dead")) override.linkDead = i.getBooleanExtra("link_dead", false);
            if (i.hasExtra("turn_left")) override.turnLeft = i.getBooleanExtra("turn_left", false);
            if (i.hasExtra("high_beam")) override.highBeam = i.getBooleanExtra("high_beam", false);
            if (i.hasExtra("brake")) override.brake = i.getBooleanExtra("brake", false);
            if (i.hasExtra("alt")) override.alternator = i.getBooleanExtra("alt", false);
            if (i.hasExtra("oil")) override.oil = i.getBooleanExtra("oil", false);
        }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        view = new ClusterView(this);
        setContentView(view);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override protected void onResume() {
        super.onResume();
        hideSystemBars();
        IntentFilter f = new IntentFilter();
        f.addAction(ACTION_SET);
        f.addAction(ACTION_CLEAR);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(debug, f, Context.RECEIVER_EXPORTED);
        else registerReceiver(debug, f);
        t0 = SystemClock.elapsedRealtime();
        handler.post(tick);
    }

    @Override protected void onPause() {
        handler.removeCallbacks(tick);
        unregisterReceiver(debug);
        super.onPause();
    }

    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            var c = getWindow().getInsetsController();
            if (c != null) c.hide(WindowInsets.Type.systemBars());
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }
}
