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
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;

import com.jessiescars.cluster.core.CenterLogic;
import com.jessiescars.cluster.core.CenterLogic.Aspect;
import com.jessiescars.cluster.core.CenterLogic.Content;
import com.jessiescars.cluster.core.CenterLogic.NoPhone;
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
 * phone (a phone is projecting), flip (show the gauge instead of maps), settings (open/close the list).
 * string extras (saved): no_phone (gauge|home), aspect (round|square|4:3|16:9), theme (classic|modern|0|1),
 * units (mph|kph); telemetry (off | host | host:port: where the development feed for the small screens goes;
 * default 10.0.2.2:5005, the PC the emulator runs on). The real source (the VHAL bridge) replaces only the fake
 * one; the views only ever see a VehicleState. There are no turn indicators: the dash has physical ones.
 */
public class MainActivity extends Activity implements SettingsView.Listener {
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
    private boolean flippedToGauge;
    private Content shown;
    private boolean settingsOpen;
    private final Settings settings = new Settings();
    private final TelemetryPublisher telemetry = new TelemetryPublisher();

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            float t = (SystemClock.elapsedRealtime() - t0) / 1000f;
            VehicleState s = DriveScenario.at(t, override);
            gauge.setState(s);
            maps.setState(s);
            telemetry.publish(Telemetry.encode(s, settings.imperial, settings.theme));   // development feed for the small screens
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
        settingsView = new SettingsView(this, settings, this);

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
        settings.imperial = prefs.getBoolean("imperial", true);
        settings.noPhone = parseEnum(NoPhone.class, prefs.getString("no_phone", null), NoPhone.GAUGE);
        settings.aspect = parseEnum(Aspect.class, prefs.getString("aspect", null), Aspect.ROUND);
    }

    private void saveSettings() {
        prefs.edit().putInt("theme", settings.theme).putBoolean("imperial", settings.imperial)
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

    /** The rotary dial arrives as DPAD keys. In the settings list it moves and changes; otherwise a click flips maps and gauge. */
    @Override public boolean onKeyUp(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_MENU) { setSettingsOpen(!settingsOpen); return true; }
        if (settingsOpen) {
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_UP: settingsView.move(-1); return true;
                case KeyEvent.KEYCODE_DPAD_DOWN: settingsView.move(+1); return true;
                case KeyEvent.KEYCODE_DPAD_CENTER:
                case KeyEvent.KEYCODE_ENTER: settingsView.activate(); return true;
                case KeyEvent.KEYCODE_BACK: setSettingsOpen(false); return true;
                default: break;
            }
            return super.onKeyUp(keyCode, event);
        }
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (phoneProjecting) {
                flippedToGauge = !flippedToGauge;
                refreshContent();
            }
            return true;
        }
        return super.onKeyUp(keyCode, event);
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
