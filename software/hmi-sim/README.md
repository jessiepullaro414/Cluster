# Dial HMI simulator (proof of concept)

A desktop window to try the dial interface for the centre (Android) screen before it exists in Android. It shows
the round centre screen next to the four small gauge screens; the small ones are the **real firmware screen code**
on a mock GC9A01 panel, so a theme or unit change made with the dial shows up on them exactly as it would in the car.

Decisions behind it (2026-10-16): every setting is changed through the Android screen; Bluetooth is for Android
Auto / CarPlay later, not for settings; the dial is a Piher PSC-360 variant with a push-button, feel not critical.
In the car the dial arrives as an analog angle (ADC) and a click switch (GPIO) and becomes the same four inputs:
turn left, turn right, click, long press. The menu flows here are a **proposal to try**, not a decision.

| Where | Click | Hold (0.6 s) | Turn |
|---|---|---|---|
| Home | maps / gauge | open Settings | maps / gauge |
| Settings list | edit the row (Back leaves) | back to Home | move the selection |
| Editing a row | keep the value | cancel, restore | change the value (small screens follow live) |

Rows: gauge theme, units, no-phone screen, map shape, brightness, back.

```
wsl -d Ubuntu-22.04 -- make -C /mnt/c/Users/root/Project/cluster-pcb/software/hmi-sim test   # build + self test
powershell -File software\hmi-sim\run.ps1                                                        # open the window
build/hmi_sim --script "H,R,R,C,shot=a.png"    # headless: R/L turn, C click, H hold, shot=file.png
```

Window: mouse wheel = turn, left button or Space/Enter = click (hold for long press), arrows or A/D = turn,
Esc = long press, Q = quit. Saved settings go to `hmi_settings.txt` (`--fresh` ignores them).

Not here: real Android, the GPIO/ADC code, the Bluetooth link to a phone, the real map. The centre screen is drawn
on a 480 px canvas (the panel is 720 px) with the same gfx renderer as the small screens.
