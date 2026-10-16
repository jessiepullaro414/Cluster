package com.jessiescars.cluster.core;

/**
 * The dial's menu logic for the settings list, with no Android classes so it can be unit tested. It is the same flow as the
 * desktop simulator (software/hmi-sim/hmi.h), which the owner tried and liked:
 *
 *   list   turn: move the selection (wraps, the last entry is Back)   click: edit the row (Back closes)   hold: close
 *   edit   turn: change the value (it applies at once, the small screens follow)   click: keep   hold: cancel and restore
 *
 * Home (maps / gauge) belongs to MainActivity: turn or click flips between them, hold opens this list.
 */
public final class DialUi {
    public enum Event { LEFT, RIGHT, CLICK, LONG }
    public enum Mode { LIST, EDIT }

    /** What the owner of the screen does with the result. */
    public interface Host {
        void onChanged(Settings s);      // a value changed (or was restored): apply and save
        void onClose();
    }

    private final Settings settings;
    private final Host host;
    private final Settings before = new Settings();
    private int selected;
    private Mode mode = Mode.LIST;

    public DialUi(Settings settings, Host host) {
        this.settings = settings;
        this.host = host;
    }

    /** Number of entries: every setting plus Back. */
    public int count() { return Settings.ROWS.length + 1; }
    public int selected() { return selected; }
    public Mode mode() { return mode; }
    public boolean backSelected() { return selected == Settings.ROWS.length; }

    /** A fresh opening starts at the first row in the list. */
    public void open() {
        selected = 0;
        mode = Mode.LIST;
    }

    /** Returns true if the event was used. */
    public boolean handle(Event e) {
        if (mode == Mode.LIST) {
            switch (e) {
                case LEFT: selected = (selected + count() - 1) % count(); return true;
                case RIGHT: selected = (selected + 1) % count(); return true;
                case CLICK:
                    if (backSelected()) { host.onClose(); return true; }
                    before.copyFrom(settings);
                    mode = Mode.EDIT;
                    return true;
                default: host.onClose(); return true;
            }
        }
        switch (e) {
            case LEFT: settings.step(Settings.ROWS[selected], -1); host.onChanged(settings); return true;
            case RIGHT: settings.step(Settings.ROWS[selected], +1); host.onChanged(settings); return true;
            case CLICK: mode = Mode.LIST; return true;
            default:
                settings.copyFrom(before);
                host.onChanged(settings);
                mode = Mode.LIST;
                return true;
        }
    }

    /** Touch: tap a row to step it forward, or Back to close (no edit mode with a finger). */
    public void tap(int row) {
        selected = row;
        if (backSelected()) { host.onClose(); return; }
        settings.cycle(Settings.ROWS[row]);
        host.onChanged(settings);
    }
}
