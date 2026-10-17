#!/usr/bin/env python3
"""Join an Android phone's "head unit server" to LIVI's Android Auto port, so a phone on a USB cable or
an Android emulator can drive LIVI with no Bluetooth or Wi-Fi bootstrap.

    adb forward tcp:5277 tcp:5277                        # the phone's head unit server, on this machine
    python relay.py --phone 127.0.0.1:5277 --livi 127.0.0.1:5278
    python relay.py --selftest

Why this works: in Android Auto the head unit is always the TLS client and the phone the TLS server
(LIVI livi-aa tls.rs), whichever side opened the TCP connection. Google's Desktop Head Unit connects TO
the phone's head unit server (developer settings, port 5277); in wireless Android Auto the phone connects
TO the head unit (LIVI listens on LIVI_PORT, default 5277). Both ends here are listeners, so the relay
connects to both and copies bytes. It does not look inside the stream beyond logging the first frame
header (channel, flags, length) so a failed handshake can be told apart from a dead socket.

Run LIVI with LIVI_PORT=5278 when it shares localhost with the adb forward. Stdlib only.
"""
import argparse
import socket
import sys
import threading
import time


def addr(s):
    host, _, port = s.rpartition(":")
    return host or "127.0.0.1", int(port)


def describe(first):
    # Android Auto frame: byte 0 channel, byte 1 flags, bytes 2-3 big-endian length, then a 2-byte message id.
    if len(first) < 6:
        return f"{len(first)} bytes"
    ch, flags, ln, msg = first[0], first[1], int.from_bytes(first[2:4], "big"), int.from_bytes(first[4:6], "big")
    kind = {1: "version request", 2: "version response", 3: "TLS handshake"}.get(msg, f"message 0x{msg:04x}")
    return f"channel {ch} flags 0x{flags:02x} length {ln}: {kind}"


def pump(src, dst, name, stats, stop):
    first = True
    try:
        while not stop.is_set():
            data = src.recv(65536)
            if not data:
                break
            if first:
                print(f"[relay] first {name} frame: {describe(data)}", flush=True)
                first = False
            dst.sendall(data)
            stats[name] += len(data)
    except OSError as e:
        if not stop.is_set():
            print(f"[relay] {name}: {e}", flush=True)
    finally:
        stop.set()
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def session(phone, livi):
    p = socket.create_connection(phone, timeout=5)
    try:
        h = socket.create_connection(livi, timeout=5)
    except OSError:
        p.close()
        raise
    for s in (p, h):
        s.settimeout(None)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    stats = {"phone->livi": 0, "livi->phone": 0}
    stop = threading.Event()
    t = [threading.Thread(target=pump, args=(p, h, "phone->livi", stats, stop), daemon=True),
         threading.Thread(target=pump, args=(h, p, "livi->phone", stats, stop), daemon=True)]
    for x in t:
        x.start()
    t0 = time.time()
    while not stop.wait(5):
        print(f"[relay] {time.time() - t0:5.0f} s  phone->livi {stats['phone->livi'] / 1e6:7.2f} MB  "
              f"livi->phone {stats['livi->phone'] / 1e3:7.1f} kB", flush=True)
    for x in t:
        x.join(2)
    p.close()
    h.close()
    return stats


def selftest():
    """Two fake listeners: the head unit (LIVI) opens with a version request, as Android Auto's head unit does,
    and the 'phone' answers with a version response; both must see the other's bytes."""
    got = {}

    def listener(name, send):
        ls = socket.socket()
        ls.bind(("127.0.0.1", 0))
        ls.listen(1)

        def run():
            c, _ = ls.accept()
            if send:
                c.sendall(send)
            got[name] = c.recv(100)
            time.sleep(0.2)
            c.close()
            ls.close()
        threading.Thread(target=run, daemon=True).start()
        return ls.getsockname()

    version_request = bytes([0, 3, 0, 6, 0, 1, 0, 1, 0, 7])   # channel 0, flags 3, len 6, msg 1, v1.7
    version_response = bytes([0, 3, 0, 8, 0, 2, 0, 1, 0, 7, 0, 0])
    livi = listener("livi", version_request)
    phone = listener("phone", version_response)
    stats = session(phone, livi)
    assert got.get("phone") == version_request, got
    assert got.get("livi") == version_response, got
    assert stats["livi->phone"] == len(version_request) and stats["phone->livi"] == len(version_response), stats
    assert describe(version_request).endswith("version request") and describe(version_response).endswith("version response")
    print("relay selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phone", default="127.0.0.1:5277", help="the phone's head unit server (after adb forward)")
    ap.add_argument("--livi", default="127.0.0.1:5278", help="LIVI's Android Auto port (LIVI_PORT)")
    ap.add_argument("--once", action="store_true", help="stop after one session instead of reconnecting")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    while True:
        try:
            print(f"[relay] connecting phone {a.phone} <-> LIVI {a.livi}", flush=True)
            session(addr(a.phone), addr(a.livi))
            print("[relay] session ended", flush=True)
        except OSError as e:
            print(f"[relay] {e}; retrying in 3 s", flush=True)
        if a.once:
            return 0
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
