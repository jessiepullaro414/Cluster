"""Small helpers for driving the cluster app in the emulator from Python (used by the demo-video scripts)."""
import os
import subprocess
import time

def _find_adb():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    # the Claude desktop app is a packaged (MSIX) app and keeps the Android SDK it installed under its package cache; a plain
    # Python process only sees it at that real location
    for base in (os.path.join(local, "Packages", "Claude_pzs8sxrjxfjjc", "LocalCache", "Local"), local):
        p = os.path.join(base, "Android", "Sdk", "platform-tools", "adb.exe")
        if os.path.exists(p):
            return p
    return "adb"


ADB = _find_adb()
ACTION = "com.jessiescars.cluster.SET"


def adb(*args, check=True, timeout=30):
    r = subprocess.run([ADB, *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def _extra_args(extras):
    out = []
    for k, v in extras.items():
        if isinstance(v, bool):
            out += ["--ez", k, "true" if v else "false"]
        elif isinstance(v, (int, float)):
            out += ["--ef", k, str(float(v))]
        else:
            out += ["--es", k, str(v)]
    return out


def set_app(**extras):
    """send the app's debug broadcast (see RUNNING.md): theme=, units=, speed_kph=, flip=, phone=, ..."""
    return adb("shell", "am", "broadcast", "-a", ACTION, *_extra_args(extras), check=False)


def clear_app():
    return adb("shell", "am", "broadcast", "-a", "com.jessiescars.cluster.CLEAR", check=False)


def screenshot(path):
    r = subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=30)
    data = r.stdout
    i = data.find(b"\x89PNG")                  # with two displays screencap prints a warning line first
    if i < 0:
        return False
    with open(path, "wb") as f:
        f.write(data[i:])
    return True


def key(code):
    adb("shell", "input", "keyevent", str(code), check=False)


def wsl_ip(distro="Ubuntu-22.04"):
    out = subprocess.run(["wsl.exe", "-d", distro, "--", "hostname", "-I"], capture_output=True, text=True).stdout
    return out.split()[0]


if __name__ == "__main__":
    print(adb("devices"))


def clear_then_set(**extras):
    """CLEAR (drops the speed/rpm/lamp overrides) and SET in one adb call, so the screen does not flicker between the two"""
    import shlex
    one = "am broadcast -a com.jessiescars.cluster.CLEAR >/dev/null; am broadcast -a " + ACTION + " " + " ".join(shlex.quote(a) for a in _extra_args(extras))
    return adb("shell", one, check=False)
