#!/usr/bin/env python3
"""End-to-end bench of clusterd's parked-car power-off, on a PC (WSL is fine): no module, no CAN, no real sleep.

    python3 software/linux/aa-bench/bench_park.py

The host tests (clusterd/test, test_park) cover the decisions. This covers what they cannot reach, main_linux.cpp's
wiring: the RTC file, the two commands, noticing a resume, forgetting what was heard before the sleep. It runs the real
daemon and plays everything around it:

  gauges/         PowerState frames to --can-udp, packed from protocol/can_protocol.py's table
  the wake pin    the file DIR/ign (--sim-gpio DIR)
  a sleep         suspend_cmd blocks until the scenario wakes it, as a command that really suspends would, and the
                  file DIR/slept_s then adds the time asleep to CLOCK_BOOTTIME
  the RTC         rtc_wakealarm points at a plain file, which ends up holding the last thing written to it

It says nothing about a real RTC, real suspend, evdev or the board: those need a module (README.md, L6).
"""
import concurrent.futures
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CLUSTERD = os.path.normpath(os.path.join(HERE, "..", "clusterd"))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "protocol")))
import can_protocol as proto  # noqa: E402

POWER = next(m for m in proto.PRIVATE if m["name"] == "PowerState")
CARS = []                     # every daemon started, so a scenario that dies cannot leave one holding its port
LIMIT_S = 48 * 3600
GRACE_S = 5.0                 # ParkPolicy::kGraceMs
SLOP_S = 2.0                  # room for a busy PC


def power_frame(counter, ign, req, secs):
    """A 13-byte --can-udp datagram (parse_udp_can) holding one PowerState."""
    vals = {"IgnitionOn": int(ign), "SuspendRequest": int(req), "SuspendInSeconds": secs, "Counter": counter}
    raw = 0
    for s in POWER["signals"]:
        raw |= vals.get(s["name"], 0) << s["start"]
    data = bytearray(raw.to_bytes(8, "little"))
    data[7] = proto.crc8(bytes(data[:7]))
    return struct.pack("<IB", POWER["id"], 8) + bytes(data)


class Car:
    """One clusterd and everything around it. Each scenario gets its own directory and ports."""

    def __init__(self, port, pin="1", conf="", args=()):
        self.dir = tempfile.mkdtemp(prefix="bench_park_")
        self.port = port
        self.counter = 0
        self.slept = 0
        self.results = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.log_path = self.path("clusterd.log")
        if pin is not None:
            self.pin(pin)
        with open(self.path("wakealarm"), "w") as f:
            f.write("never written")
        # blocks like a real suspend until wake() removes the file
        with open(self.path("suspend.sh"), "w") as f:
            f.write(f'echo "suspend $(cat {self.dir}/wakealarm)" >> {self.dir}/commands\n'
                    f'[ -f {self.dir}/suspend_fails ] && exit 1\n'
                    f'[ -f {self.dir}/no_sleep ] && exit 0\n'
                    f'touch {self.dir}/asleep\n'
                    f'while [ -f {self.dir}/asleep ]; do sleep 0.02; done\n')
        with open(self.path("poweroff.sh"), "w") as f:
            f.write(f'echo "poweroff $(cat {self.dir}/wakealarm)" >> {self.dir}/commands\n')
        with open(self.path("clusterd.conf"), "w") as f:
            f.write(f"can_if = none\nlivi_port = {port + 1000}\npage_port = {port + 2000}\n"
                    f"suspend_cmd = sh {self.dir}/suspend.sh\npoweroff_cmd = sh {self.dir}/poweroff.sh\n"
                    f"rtc_wakealarm = {self.dir}/wakealarm\n{conf}")
        self.log = open(self.log_path, "w")
        CARS.append(self)
        self.proc = subprocess.Popen(
            [os.path.join(CLUSTERD, "build", "clusterd"), "--can", "none", "--can-udp", str(port),
             "--sim-gpio", self.dir, "--config", self.path("clusterd.conf"), "--settings", self.path("settings.conf"),
             "--web", os.path.join(CLUSTERD, "web"), "--livi-status", self.path("status.json"), *args],
            stdout=self.log, stderr=subprocess.STDOUT)
        time.sleep(0.2)

    def path(self, name):
        return os.path.join(self.dir, name)

    def write(self, name, text):
        tmp = self.path(name + ".tmp")
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, self.path(name))

    def pin(self, value):
        self.write("ign", value + "\n")

    def touch(self, name):
        self.write(name, "")

    def frame(self, ign, req=False, secs=0):
        self.sock.sendto(power_frame(self.counter, ign, req, secs), ("127.0.0.1", self.port))
        self.counter = (self.counter + 1) & 0xF

    def frames(self, seconds, ign, req=False, secs=0):
        end = time.time() + seconds
        while time.time() < end:
            self.frame(ign, req, secs)
            time.sleep(0.1)

    def driving(self):
        self.pin("1")
        self.frames(0.5, True)

    def key_off(self):
        """gauges/ counts down from 1 s until the module has gone to sleep. Then it sleeps too: the link falls silent."""
        self.pin("0")
        end = time.time() + 5
        while not os.path.exists(self.path("asleep")) and time.time() < end:
            self.frame(False, True, 1)
            time.sleep(0.1)
        self.check(os.path.exists(self.path("asleep")), "key off: it suspends after gauges/ counts down")

    def wake(self, seconds):
        if not self.asleep():
            raise RuntimeError("the scenario wanted to wake it, but it never went to sleep")
        self.slept += seconds
        self.write("slept_s", f"{self.slept}\n")
        os.remove(self.path("asleep"))

    def asleep(self):
        return os.path.exists(self.path("asleep"))

    def wait_asleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end and not self.asleep():
            time.sleep(0.02)
        return self.asleep()

    def commands(self):
        try:
            with open(self.path("commands")) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def wait_command(self, count, seconds):
        """Waits for the command list to reach count lines. Returns how long it took, or None."""
        start = time.time()
        while time.time() - start < seconds:
            if len(self.commands()) >= count:
                return time.time() - start
            time.sleep(0.02)
        return None

    def alarm(self):
        with open(self.path("wakealarm")) as f:
            return f.read().strip()

    def logged(self):
        self.log.flush()
        with open(self.log_path) as f:
            return f.read()

    def check(self, ok, what):
        self.results.append((bool(ok), what))

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait()
        self.log.close()
        self.sock.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def finish(self):
        self.check(self.proc.poll() is None, "clusterd is still running at the end")
        if any(not ok for ok, _ in self.results):
            self.results.append((True, "--- clusterd log\n" + self.logged() + "--- commands\n" + "\n".join(self.commands())))
        return self.results


def alarm_wake_key_off(port):
    c = Car(port)
    c.driving()
    c.key_off()
    c.check(c.commands() == [f"suspend +{LIMIT_S}"], f"the RTC is armed for 48 h before suspend_cmd: {c.commands()}")
    c.wake(LIMIT_S)
    took = c.wait_command(2, GRACE_S + SLOP_S)
    c.check(took is not None and took >= GRACE_S - 0.5, f"powers off after the grace (took {took})")
    c.check(c.commands()[1:] == ["poweroff 0"], f"the alarm is cleared before poweroff_cmd: {c.commands()}")
    c.check(f"resumed after {LIMIT_S} s" in c.logged(), "the resume is noticed on CLOCK_BOOTTIME")
    time.sleep(1)
    c.check(len(c.commands()) == 2, "asked for once")
    return c


def key_on_wake(port):
    """Frames from just before the sleep and frames queued during it must not put a key-on wake straight back down."""
    c = Car(port)
    c.driving()
    c.key_off()
    c.frame(False, True, 1)     # queued in the socket while "asleep"
    c.frame(False, True, 1)
    c.pin("1")
    c.wake(3600)                # inside the old frames' 1.5 s of freshness
    time.sleep(1.6)             # gauges/ is slow to come up: longer than the old 1 s countdown
    c.frames(GRACE_S, True)
    c.check(len(c.commands()) == 1, f"no second suspend, no power-off: {c.commands()}")
    c.check(c.alarm() == "0", "the alarm is cleared")
    c.check("key on, carrying on" in c.logged(), "carries on")
    return c


def key_on_during_alarm_wake(port):
    c = Car(port)
    c.driving()
    c.key_off()
    c.wake(LIMIT_S)
    time.sleep(GRACE_S - 2)
    c.pin("1")
    time.sleep(GRACE_S)
    c.check(len(c.commands()) == 1, f"no power-off: {c.commands()}")
    c.check(c.alarm() == "0", "the alarm is cleared")
    return c


def quiet_link_pin_on(port):
    """gauges/ never comes back and the pin says the key is on: the screen stays up."""
    c = Car(port)
    c.driving()
    c.key_off()
    c.pin("1")
    c.wake(LIMIT_S)
    time.sleep(GRACE_S + SLOP_S)
    c.check(len(c.commands()) == 1, f"nothing but the first suspend: {c.commands()}")
    return c


def no_pin_link_decides(port):
    """No usable pin (--ign on something that is not an input device): the link alone decides, and it gets its chance."""
    c = Car(port, pin=None, args=("--ign", "/dev/null"))
    c.frames(0.5, True)
    c.frames(1.5, False, True, 1)
    c.check(c.wait_asleep(2), "key off: it suspends")
    c.wake(LIMIT_S)
    time.sleep(GRACE_S - 2.5)
    c.frames(GRACE_S, True)
    c.check(len(c.commands()) == 1, f"a PowerState saying On in the grace saves it: {c.commands()}")
    c.frames(1.5, False, True, 1)
    c.check(c.wait_asleep(2), "key off again: it suspends")
    c.wake(LIMIT_S)
    took = c.wait_command(3, GRACE_S + SLOP_S)
    c.check(took is not None and took >= GRACE_S - 0.5, f"silence for the whole grace reads as key off (took {took})")
    c.check(c.commands()[2:] == ["poweroff 0"], f"powers off: {c.commands()}")
    return c


def stray_wake(port):
    c = Car(port)
    c.driving()
    c.key_off()
    c.wake(3600)
    c.check(c.wait_asleep(GRACE_S + SLOP_S), "key off with time left: back to sleep")
    left = int(c.alarm().lstrip("+"))
    c.check(LIMIT_S - 3600 - 15 <= left <= LIMIT_S - 3600, f"with the alarm set to what is left: {left} s")
    c.wake(left)
    took = c.wait_command(3, GRACE_S + SLOP_S)
    c.check(took is not None and c.commands()[2:] == ["poweroff 0"], f"then powers off on time: {c.commands()}")
    return c


def disabled(port):
    c = Car(port, conf="parked_poweroff_hours = 0\n")
    c.driving()
    c.key_off()
    c.check(c.alarm() == "never written", "no alarm")
    c.wake(10 * LIMIT_S)
    c.check(c.wait_asleep(GRACE_S + SLOP_S), "a key-off wake goes back to sleep")
    c.check(all(l.startswith("suspend") for l in c.commands()), f"never a power-off: {c.commands()}")
    c.pin("1")
    c.wake(10)
    c.frames(1, True)
    c.check("key on, carrying on" in c.logged(), "a key-on wake carries on")
    c.touch("suspend_fails")
    c.pin("0")
    c.frames(1.5, False, True, 1)
    c.check("suspend command failed" in c.logged(), "a failed suspend is logged")
    c.check(c.alarm() == "never written", "the RTC is left alone throughout: key on and a failed suspend too")
    return c


def boots_with_key_off(port):
    """The key went off during boot: gauges/ is asleep before clusterd starts, so no SuspendRequest will ever come."""
    c = Car(port, pin="0")
    c.check(c.wait_asleep(GRACE_S + SLOP_S), "the pin says off and nobody speaks: it suspends")
    c.check(c.alarm() == f"+{LIMIT_S}", "with the alarm armed")
    return c


def suspend_fails(port):
    c = Car(port)
    c.touch("suspend_fails")
    c.driving()
    c.pin("0")
    c.frames(1.5, False, True, 1)
    c.check(c.alarm() == "0" and "suspend command failed" in c.logged(), "a failed suspend clears the alarm and says so")
    took = c.wait_command(4, 3 * GRACE_S + SLOP_S)
    tries = c.commands()[:3]
    c.check(took is not None and all(t.startswith("suspend +") for t in tries) and c.commands()[3:] == ["poweroff 0"],
            f"three tries, then a power-off rather than a flat battery: {c.commands()}")
    return c


def pc_bench(port):
    """No pin, no gauges, and the PC suspends for reasons of its own: nothing, ever."""
    c = Car(port, pin=None)
    c.write("slept_s", f"{LIMIT_S * 2}\n")
    time.sleep(GRACE_S + SLOP_S)
    c.check(c.commands() == [], f"no command runs: {c.commands()}")
    c.check(c.alarm() == "never written", "the RTC is left alone")
    c.check(f"resumed after {LIMIT_S * 2} s" in c.logged(), "the resume was noticed")
    return c


def rtc_unwritable(port):
    c = Car(port, conf="rtc_wakealarm = /nonexistent/wakealarm\n")
    c.driving()
    c.key_off()
    log = c.logged()
    c.check("cannot write /nonexistent/wakealarm" in log, "the problem is logged at start, not after a flat battery")
    c.check("could not arm the RTC alarm" in log, "and again at the suspend, which still happens")
    return c


SCENARIOS = [alarm_wake_key_off, key_on_wake, key_on_during_alarm_wake, quiet_link_pin_on, no_pin_link_decides,
             stray_wake, disabled, boots_with_key_off, suspend_fails, pc_bench, rtc_unwritable]


def run(scenario, port):
    try:
        return scenario(port).finish()
    except Exception as e:      # a bench bug must fail the bench, not vanish in the pool
        return [(False, f"{type(e).__name__}: {e}")]


def main():
    subprocess.run(["make", "-s", "build/clusterd"], cwd=CLUSTERD, check=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(len(SCENARIOS)) as pool:
            jobs = [(s, pool.submit(run, s, 5200 + i * 3)) for i, s in enumerate(SCENARIOS)]
    finally:
        for car in CARS:
            car.stop()
    failed = 0
    for scenario, job in jobs:
        print(f"--- {scenario.__name__}")
        for ok, what in job.result():
            print(("ok    " if ok else "FAIL  ") + what)
            failed += not ok
    print("all scenarios pass" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
