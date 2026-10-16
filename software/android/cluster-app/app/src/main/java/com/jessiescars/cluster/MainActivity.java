package com.jessiescars.cluster;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.ViewConfiguration;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;

import com.jessiescars.cluster.core.CenterLogic;
import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.CenterLogic.Content;
import com.jessiescars.cluster.core.CenterLogic.NoPhone;
import com.jessiescars.cluster.core.DialUi;
import com.jessiescars.cluster.core.DriveScenario;
import com.jessiescars.cluster.core.Settings;
import com.jessiescars.cluster.core.Telemetry;
import com.jessiescars.cluster.core.VehicleState;

/**
 * The round centre display. What it shows is decided by CenterLogic: CarPlay / Android Auto maps while a
 * phone is projecting, otherwise the user's choice (the gauge or home). The dial click flips between maps
 * and the gauge. A long press (or the MENU key) opens the settings list: gauge theme for the four small
 * screens, units, what to show with no phone, and the shape of the map.
 *
 * Data comes from a fake source (core/DriveScenario) that adb can override:
 *
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --ef speed_kph 120 --ez night true --ef dimmer 30
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --ez phone false --es no_phone home
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --es aspect round --ez flip true
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --es theme modern --es units kph
 *   adb shell am broadcast -a com.jessiescars.cluster.SET --ez settings true
 *   adb shell am broadcast -a com.jessiescars.cluster.CLEAR
 *
 * float extras: speed_kph, rpm, dimmer. boolean extras: night, link_dead, high_beam, brake, alt, oil,
 * phone (a phone is projecting), match_carplay (saved: the small screens take the CarPlay look while it is open), flip (show the gauge instead of maps), settings (open/close the list).
 * string extras: phone_kind (carplay|androidauto: what the projecting phone is); (saved): no_phone (gauge|home), aspect (round|square|4:3|16:9), theme (classic|modern|carplay|factory|0..3),
 * units (mph|kph); telemetry (off | host | host:port: where the development feed for the small screens goes;
 * default 10.0.2.2:5005, the PC the emulator runs on). The real source (the VHAL bridge) replaces only the fake
 * one; the views only ever see a VehicleState. There are no turn indicators: the dash has physical ones.
 */
public class MainActivity extends Activity implements DialUi.Host {
    static final String ACTION_SET = "com.jessiescars.cluster.SET";
    static final String ACTION_CLEAR = "com.jessiescars.cluster.CLEAR";
    private static final long TICK_MS = 50;            // 20 updates per second
    private static final String PREFS = "cluster";

    private ClusterView gauge;
    private ProjectionView maps;
    private HomeView home;
    private SettingsView settingsView;
    private SharedPreferences prefs;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final DriveScenario.Override override = new DriveScenario.Override();
    private long t0;

    // centre-display state
    private boolean phoneProjecting = true;            // fake: a phone is connected
    private boolean projectingCarPlay = true;          // fake: it is an iPhone (CarPlay), not Android Auto
    private boolean flippedToGauge;
    private Content shown;
    private boolean settingsOpen;
    private final Settings settings = new Settings();
    private final DialUi dial = new DialUi(settings, this);
    private long dialDownAt = -1;                      // when the dial button went down, -1 when it is up
    private final TelemetryPublisher telemetry = new TelemetryPublisher();

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            float t = (SystemClock.elapsedRealtime() - t0) / 1000f;
            VehicleState s = DriveScenario.at(t, override);
            final int look = settings.effectiveTheme(phoneProjecting && projectingCarPlay);
            gauge.setTheme(look);                  // the centre speedometer matches the small screens
            gauge.setImperial(settings.imperial);
            gauge.setState(s);
            maps.setState(s);
            // development feed for the small screens; while the centre shows the speedometer they do not repeat speed
            telemetry.publish(Telemetry.encode(s, settings.imperial, look, shown == Content.GAUGE && !settingsOpen));
            if (dialDownAt >= 0 && settingsOpen) {
                settingsView.setHoldProgress(Math.min(1f, (SystemClock.elapsedRealtime() - dialDownAt) / (float) ViewConfiguration.getLongPressTimeout()));
            }
            handler.postDelayed(this, TICK_MS);
        }
    };

    private final BroadcastReceiver debug = new BroadcastReceiver() {
        @Override public void onReceive(Context ctx, Intent i) {
            if (ACTION_CLEAR.equals(i.getAction())) {
                override.speedKph = override.rpm = override.dimmerPct = null;
                override.night = override.linkDead = override.turnLeft = override.highBeam = null;
                override.brake = override.alternator = override.oil = null;
                phoneProjecting = true;
                projectingCarPlay = true;
                flippedToGauge = false;
                setSettingsOpen(false);
                refreshContent();
                return;
            }
            if (i.hasExtra("speed_kph")) override.speedKph = i.getFloatExtra("speed_kph", 0f);
            if (i.hasExtra("rpm")) override.rpm = i.getFloatExtra("rpm", 0f);
            if (i.hasExtra("dimmer")) override.dimmerPct = i.getFloatExtra("dimmer", 100f);
            if (i.hasExtra("night")) override.night = i.getBooleanExtra("night", false);
            if (i.hasExtra("link_dead")) override.linkDead = i.getBooleanExtra("link_dead", false);
            if (i.hasExtra("high_beam")) override.highBeam = i.getBooleanExtra("high_beam", false);
            if (i.hasExtra("brake")) override.brake = i.getBooleanExtra("brake", false);
            if (i.hasExtra("alt")) override.alternator = i.getBooleanExtra("alt", false);
            if (i.hasExtra("oil")) override.oil = i.getBooleanExtra("oil", false);
            if (i.hasExtra("phone")) phoneProjecting = i.getBooleanExtra("phone", true);
            if (i.hasExtra("phone_kind")) projectingCarPlay = !"androidauto".equalsIgnoreCase(String.valueOf(i.getStringExtra("phone_kind")).trim());
            if (i.hasExtra("flip")) flippedToGauge = i.getBooleanExtra("flip", false);
            if (i.hasExtra("settings")) setSettingsOpen(i.getBooleanExtra("settings", false));
            if (i.hasExtra("telemetry")) telemetry.configure(i.getStringExtra("telemetry"));
            boolean changed = false;
            if (i.hasExtra("units")) {
                String u = i.getStringExtra("units");
                String n = u == null ? "" : u.trim().toLowerCase(java.util.Locale.ROOT);
                settings.imperial = !(n.equals("kph") || n.equals("metric") || n.equals("km/h"));
                changed = true;
            }
            if (i.hasExtra("match_carplay")) { settings.matchCarPlay = i.getBooleanExtra("match_carplay", true); changed = true; }
            if (i.hasExtra("theme")) {
                Integer th = Settings.parseTheme(i.getStringExtra("theme"));
                if (th != null) { settings.theme = th; changed = true; }
            }
            if (i.hasExtra("no_phone")) { settings.noPhone = NoPhone.parse(i.getStringExtra("no_phone"), settings.noPhone); changed = true; }
            if (i.hasExtra("aspect")) {
                Aspect a = Aspect.parse(i.getStringExtra("aspect"), null);
                if (a != null) { settings.aspect = a; changed = true; }
            }
            if (changed) applySettings(true);
            refreshContent();
        }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        loadSettings();

        gauge = new ClusterView(this);
        maps = new ProjectionView(this);
        home = new HomeView(this);
        settingsView = new SettingsView(this, settings, dial);

        FrameLayout root = new FrameLayout(this);
        root.addView(gauge);
        root.addView(maps);
        root.addView(home);
        root.addView(settingsView);
        root.setOnLongClickListener(v -> { setSettingsOpen(true); return true; });
        gauge.setOnLongClickListener(v -> { setSettingsOpen(true); return true; });
        maps.setOnLongClickListener(v -> { setSettingsOpen(true); return true; });
        home.setOnLongClickListener(v -> { setSettingsOpen(true); return true; });
        setContentView(root);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        applySettings(false);
        refreshContent();
    }

    // ---- settings ----

    private void loadSettings() {
        settings.theme = Settings.clampTheme(prefs.getInt("theme", 1));
        settings.matchCarPlay = prefs.getBoolean("match_carplay", true);
        settings.imperial = prefs.getBoolean("imperial", true);
        settings.noPhone = parseEnum(NoPhone.class, prefs.getString("no_phone", null), NoPhone.GAUGE);
        settings.aspect = parseEnum(Aspect.class, prefs.getString("aspect", null), Aspect.ROUND);
    }

    private void saveSettings() {
        prefs.edit().putInt("theme", settings.theme).putBoolean("match_carplay", settings.matchCarPlay).putBoolean("imperial", settings.imperial)
                .putString("no_phone", settings.noPhone.name()).putString("aspect", settings.aspect.name()).apply();
    }

    private void applySettings(boolean save) {
        maps.setAspect(settings.aspect);
        if (save) saveSettings();
    }

    @Override public void onChanged(Settings s) {
        applySettings(true);
        refreshContent();
    }

    @Override public void onClose() { setSettingsOpen(false); }

    private void setSettingsOpen(boolean open) {
        if (open && !settingsOpen) dial.open();
        settingsOpen = open;
        settingsView.setVisibility(open ? View.VISIBLE : View.GONE);
        if (open) settingsView.invalidate();
    }

    private static <E extends Enum<E>> E parseEnum(Class<E> type, String name, E fallback) {
        try {
            return name == null ? fallback : Enum.valueOf(type, name);
        } catch (IllegalArgumentException e) {
            return fallback;
        }
    }

    private void refreshContent() {
        Content c = CenterLogic.choose(phoneProjecting, flippedToGauge, settings.noPhone);
        if (c != shown) {
            shown = c;
            gauge.setVisibility(c == Content.GAUGE ? View.VISIBLE : View.GONE);
            maps.setVisibility(c == Content.PROJECTION ? View.VISIBLE : View.GONE);
            home.setVisibility(c == Content.HOME ? View.VISIBLE : View.GONE);
        }
        settingsView.setVisibility(settingsOpen ? View.VISIBLE : View.GONE);
        settingsView.invalidate();
    }

    /** Development: every key and rotary event that reaches the app is logged (adb logcat -s ClusterInput). */
    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        Log.i("ClusterInput", "key " + KeyEvent.keyCodeToString(e.getKeyCode()) + " action=" + e.getAction() + " repeat=" + e.getRepeatCount()
                + " source=0x" + Integer.toHexString(e.getSource()) + " device=" + e.getDeviceId());
        return super.dispatchKeyEvent(e);
    }

    @Override public boolean dispatchGenericMotionEvent(MotionEvent e) {
        Log.i("ClusterInput", "motion action=" + e.getActionMasked() + " source=0x" + Integer.toHexString(e.getSource())
                + " scroll=" + e.getAxisValue(MotionEvent.AXIS_SCROLL) + " vscroll=" + e.getAxisValue(MotionEvent.AXIS_VSCROLL));
        return super.dispatchGenericMotionEvent(e);
    }

    // ---- the dial -----------------------------------------------------------------------------------------
    // The AAOS rotary controller delivers: rotation as KEYCODE_NAVIGATE_NEXT / PREVIOUS (or as scroll events from a
    // rotary encoder), nudges as DPAD keys, and the button as DPAD_CENTER (a long press arrives as a repeating key).
    // Flow (same as the desktop simulator, hmi-sim): Home: turn or click flips maps / gauge, hold opens the settings;
    // settings: see core/DialUi.

    /** +1 clockwise, -1 counter-clockwise, 0 not a turn. Nudges count as turns: one dial, two directions. */
    private static int turnOf(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_NAVIGATE_NEXT:
            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                return +1;
            case KeyEvent.KEYCODE_NAVIGATE_PREVIOUS:
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_DPAD_LEFT:
                return -1;
            default:
                return 0;
        }
    }

    private static boolean isClick(int keyCode) {
        return keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER || keyCode == KeyEvent.KEYCODE_NUMPAD_ENTER;
    }

    private void turn(int dir) {
        if (settingsOpen) {
            dial.handle(dir > 0 ? DialUi.Event.RIGHT : DialUi.Event.LEFT);
            settingsView.invalidate();
        } else if (phoneProjecting) {
            flippedToGauge = !flippedToGauge;               // turning on Home flips between the maps and the speedometer
            refreshContent();
        }
    }

    private void click() {
        if (settingsOpen) {
            dial.handle(DialUi.Event.CLICK);
            settingsView.invalidate();
        } else if (phoneProjecting) {
            flippedToGauge = !flippedToGauge;
            refreshContent();
        }
    }

    private void longPress() {
        if (settingsOpen) {
            dial.handle(DialUi.Event.LONG);                 // cancels an edit, or closes the list
            settingsView.invalidate();
        } else {
            setSettingsOpen(true);
        }
    }

    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (isClick(keyCode)) {
            if (event.getRepeatCount() == 0) {
                event.startTracking();                      // a long press then arrives in onKeyLongPress
                dialDownAt = SystemClock.elapsedRealtime();
            }
            return true;
        }
        int d = turnOf(keyCode);
        if (d != 0) {
            turn(d);
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override public boolean onKeyLongPress(int keyCode, KeyEvent event) {
        if (isClick(keyCode)) {
            dialDownAt = -1;
            settingsView.setHoldProgress(0f);
            longPress();
            return true;
        }
        return super.onKeyLongPress(keyCode, event);
    }

    @Override public boolean onKeyUp(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_MENU) { setSettingsOpen(!settingsOpen); return true; }
        if (keyCode == KeyEvent.KEYCODE_BACK && settingsOpen) { longPress(); return true; }       // back = hold: cancel, then close
        if (isClick(keyCode)) {
            dialDownAt = -1;
            settingsView.setHoldProgress(0f);
            if (event.isTracking() && !event.isCanceled()) click();                                 // not a long press
            return true;
        }
        if (turnOf(keyCode) != 0) return true;
        return super.onKeyUp(keyCode, event);
    }

    /** Rotation from a rotary encoder device. Which sign is clockwise is the encoder's convention: ROTARY_CLOCKWISE_SIGN. */
    private static final float ROTARY_CLOCKWISE_SIGN = 1f;      // UNVERIFIED on hardware: the emulator sends keys, not scroll events

    @Override public boolean onGenericMotionEvent(MotionEvent e) {
        if ((e.getSource() & InputDevice.SOURCE_ROTARY_ENCODER) != 0 && e.getActionMasked() == MotionEvent.ACTION_SCROLL) {
            float v = e.getAxisValue(MotionEvent.AXIS_SCROLL) * ROTARY_CLOCKWISE_SIGN;
            int n = Math.max(1, Math.round(Math.abs(v)));
            for (int i = 0; i < n; i++) turn(v >= 0f ? +1 : -1);
            return true;
        }
        return super.onGenericMotionEvent(e);
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

    @Override protected void onDestroy() {
        telemetry.close();
        super.onDestroy();
    }

    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) c.hide(WindowInsets.Type.systemBars());
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }
}
