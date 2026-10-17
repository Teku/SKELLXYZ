#!/usr/bin/env python3
"""LAN dashboard for one managed skeleton runner. No third-party web packages."""
import argparse
from collections import deque
import getpass
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from skeleton_preferences import PATH, catalog, read, save
from skeleton_gestures import NAMES

ROOT = Path(__file__).resolve().parent


class Controller:
    def __init__(self, dry_run=False, preferences=PATH):
        self.dry_run, self.preferences = dry_run, Path(preferences)
        self.lock = threading.RLock()
        self.process = None
        self.logs = deque(maxlen=150)
        self.mode = "Stopped"
        self.activity = "Idle"
        self.stopping = False

    def status(self):
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            code = self.process.poll() if self.process else None
            return dict(running=running, stopping=self.stopping and running,
                        mode=self.mode if running else "Stopped", activity=self.activity if running else "Idle",
                        pid=self.process.pid if running else None, exit_code=code,
                        simulation=self.dry_run, logs=list(self.logs),
                        settings=read(self.preferences), catalog=catalog())

    def start(self, mode="show", clip=None):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError("Stop the current run and wait for it to finish first")
            if mode not in ("show", "head", "say", *NAMES):
                raise ValueError("Unknown run mode")
            if mode == "say" and clip not in catalog()["clips"]:
                raise ValueError("Choose a recording")
            read(self.preferences)
            command = [sys.executable, "-u", str(ROOT / "skeleton_run.py"), "--preferences", str(self.preferences)]
            if self.dry_run:
                command += ["--dry-run"]
            if mode == "head":
                command += ["--no-voice"]
            elif mode in NAMES:
                command += ["--action", mode]
            elif mode == "say":
                command += ["--clip", str(ROOT / "vendor/ChatterPi/src/vocals" / clip), "--once"]
            self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.mode, self.activity, self.stopping = mode, "Starting", False
            process = self.process
            threading.Thread(target=self._collect, args=(process,), daemon=True).start()

    def _collect(self, process):
        for line in process.stdout:
            line = line.rstrip()
            with self.lock:
                self.logs.append(time.strftime("%H:%M:%S ") + line)
                if process is self.process:
                    if line.startswith(("Speaking:", "Silent gesture:", "Background music:", "Stopping:")):
                        self.activity = line
                    elif "returning to rest" in line or "finished; resting" in line:
                        self.activity = "Returning to rest"
        process.stdout.close()
        code = process.wait()
        with self.lock:
            self.logs.append("Runner exited with code " + str(code))
            if process is self.process:
                self.stopping = False

    def stop(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None and not self.stopping:
                self.process.send_signal(signal.SIGTERM)
                self.stopping = True
                self.activity = "Stopping; waiting for servo release"


def handler_for(controller, password):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, content_type="application/json"):
            body = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied.encode(), ("Bearer " + password).encode())

        def do_GET(self):
            if self.path == "/":
                self.send(200, (ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/status":
                if not self.authorized():
                    self.send(401, {"error": "Enter the dashboard password"})
                    return
                try:
                    self.send(200, controller.status())
                except (ValueError, OSError) as exc:
                    self.send(500, {"error": str(exc)})
            else:
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                self.send(401, {"error": "Enter the dashboard password"})
                return
            # No CORS support; cross-origin form requests cannot supply bearer auth.
            if self.headers.get("Content-Type") != "application/json":
                self.send(415, {"error": "JSON required"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                if self.path == "/api/settings":
                    with controller.lock:
                        save(data, controller.preferences)
                elif self.path == "/api/start":
                    controller.start(data.get("mode", "show"), data.get("clip"))
                elif self.path == "/api/stop":
                    controller.stop()
                else:
                    self.send(404, {"error": "Not found"})
                    return
                self.send(200, {"ok": True})
            except (ValueError, OSError, TypeError) as exc:
                self.send(400, {"error": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dry-run", action="store_true", help="Run simulated gestures/audio only")
    args = parser.parse_args()
    password = os.environ.get("SKELL_DASHBOARD_PASSWORD") or getpass.getpass("Dashboard password (8+ characters): ")
    if len(password) < 8 or not password.isascii():
        parser.error("Use a password of at least 8 ASCII characters")
    controller = Controller(args.dry_run)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(controller, password))
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    print("Dashboard listening on http://%s:%d (%s)" % (args.host, args.port, "simulation" if args.dry_run else "hardware"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        if controller.process is not None:
            controller.process.wait()  # Do not kill the runner before GPIO cleanup.
        server.server_close()


if __name__ == "__main__":
    main()
