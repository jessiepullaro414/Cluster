#!/usr/bin/env python3
"""A stand-in for LIVI's two interfaces clusterd uses, to test clusterd on a PC without LIVI:

  * HTTP POST /telemetry on port 4000: prints every field that changed (and the page changes);
  * state/status.json: written with the projecting phone, from a script line or stdin
    ("cp", "aa" or "none").

    python3 fake_livi.py --status /tmp/livi/status.json [--phone-script "2:cp,6:none"] [--log out.jsonl]
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

snap = {}
log_file = None


def write_status(path, phone):
    active = {"cp": "cp", "aa": "aa"}.get(phone)
    kind = {"cp": "CarPlay", "aa": "AndroidAuto"}.get(phone)
    doc = {"ui": {"path": snap.get("path", "/")},
           "projection": {"active": active, "streaming": active is not None, "phoneType": kind},
           "audio": {"media": {"playing": False}, "speech": {"playing": False}, "system": {"playing": False}},
           "phone": {"active": False}, "voiceAssistant": {"active": False}, "nav": {"announcing": False}}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, path)
    print(f"[fake-livi] phone: {phone}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/telemetry":
            self.send_response(404)
            self.end_headers()
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            patch = json.loads(body)
            assert isinstance(patch, dict)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        changed = {k: v for k, v in patch.items() if snap.get(k, object()) != v}
        snap.update(patch)
        if changed:
            print(f"[fake-livi] {json.dumps(changed)}", flush=True)
            if log_file:
                log_file.write(json.dumps({"t": time.time(), "changed": changed}) + "\n")
                log_file.flush()
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    global log_file
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4000)
    ap.add_argument("--status", required=True)
    ap.add_argument("--phone-script", default="", help="seconds:phone pairs, e.g. 2:cp,6:none")
    ap.add_argument("--log")
    a = ap.parse_args()
    if a.log:
        log_file = open(a.log, "w")
    write_status(a.status, "none")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[fake-livi] listening on {a.port}", flush=True)
    t0 = time.time()
    for item in filter(None, a.phone_script.split(",")):
        sec, phone = item.split(":")
        time.sleep(max(0.0, t0 + float(sec) - time.time()))
        write_status(a.status, phone)
    if not a.phone_script:
        for line in sys.stdin:
            write_status(a.status, line.strip() or "none")
    else:
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
