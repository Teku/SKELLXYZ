#!/usr/bin/env python3
"""LAN dashboard for one managed skeleton runner. No third-party web packages."""
import argparse
import base64
from collections import deque
import getpass
import hmac
import hashlib
import secrets
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import tempfile
import time

from skeleton_preferences import PATH, catalog, read, save
from skeleton_gestures import NAMES
from camera_source import validate_rtsp

ROOT = Path(__file__).resolve().parent


class Camera:
    def __init__(self, url_path=ROOT / "camera-source.json"):
        self.url_path = Path(url_path)
        self.lock = threading.RLock()
        self.process = None
        self.logs = deque(maxlen=60)
        self.directory = tempfile.TemporaryDirectory(prefix="skell-camera-")
        self.snapshot = Path(self.directory.name) / "preview.jpg"

    def status(self):
        with self.lock:
            return dict(running=self.process is not None and self.process.poll() is None,
                        logs=list(self.logs), preview=self.snapshot.exists(),
                        configured=self.url_path.exists() or bool(os.environ.get("SKELL_RTSP_URL")))

    def saved_url(self):
        try:
            value = json.loads(self.url_path.read_text(encoding="utf-8"))["url"]
            if not isinstance(value, str):
                raise ValueError()
            return validate_rtsp(value)
        except FileNotFoundError:
            return os.environ.get("SKELL_RTSP_URL", "")
        except (ValueError, KeyError, TypeError):
            raise ValueError("Saved camera URL is invalid; enter a replacement URL") from None

    def save_url(self, url):
        # mkstemp creates an owner-only file; replace keeps the update atomic.
        fd, temporary = tempfile.mkstemp(prefix="camera-source.", suffix=".tmp", dir=self.url_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"url": url}, stream)
            os.replace(temporary, self.url_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def start(self, data):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError("Stop the current camera test first")
            mode = data.get("detector", "capture")
            if mode not in ("capture", "person", "face"):
                raise ValueError("Choose capture, person or face")
            seconds = data.get("seconds", 60)
            if type(seconds) is not int or not 5 <= seconds <= 3600:
                raise ValueError("Camera duration must be 5–3600 seconds")
            url = data.get("url") or self.saved_url()
            if not isinstance(url, str) or not url:
                raise ValueError("Enter the RTSP URL once to save it on the Pi")
            validate_rtsp(url)
            self.save_url(url)
            command = [sys.executable, "-u", str(ROOT / "camera_test.py"), "--rtsp",
                       "--seconds", str(seconds), "--snapshot-hz", "5", "--snapshot", str(self.snapshot)]
            command += ["--capture-only"] if mode == "capture" else ["--detector", mode]
            env = dict(os.environ, SKELL_RTSP_URL=url)
            if self.snapshot.exists():
                self.snapshot.unlink()
            self.logs.clear()
            self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1)
            threading.Thread(target=self._collect, args=(self.process, url), daemon=True).start()
            threading.Thread(target=self._watch, args=(self.process, seconds), daemon=True).start()

    def _watch(self, process, seconds):
        started = last_frame = time.monotonic()
        stamp = None
        while True:
            try:
                process.wait(timeout=2)
                return
            except subprocess.TimeoutExpired:
                pass
            try:
                current = self.snapshot.stat().st_mtime_ns
                if current != stamp:
                    stamp, last_frame = current, time.monotonic()
            except FileNotFoundError:
                pass
            now = time.monotonic()
            if now - last_frame > 30 or now - started > seconds + 30:
                with self.lock:
                    self.logs.append("Camera timed out; check the stream and network connection")
                process.kill()
                return

    @staticmethod
    def _finish_stop(process):
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    def _collect(self, process, url):
        for line in process.stdout:
            with self.lock:
                self.logs.append(line.rstrip().replace(url, "[RTSP source]"))
        process.stdout.close()
        code = process.wait()
        with self.lock:
            self.logs.append("Camera test exited with code " + str(code))

    def stop(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                threading.Thread(target=self._finish_stop, args=(self.process,), daemon=True).start()

    def close(self):
        self.stop()
        if self.process is not None:
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()  # Camera worker has no servo ownership.
                self.process.wait()
        self.directory.cleanup()


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


def handler_for(controller, password, camera=None):
    session_key = hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), b"skell-dashboard-session-v1", 200000)
    lifetime = 30 * 24 * 60 * 60

    def sign(payload):
        return hmac.new(session_key, payload.encode("ascii"), "sha256").hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, content_type="application/json", cookie=None):
            body = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            supplied = self.headers.get("Authorization", "")
            expected = b"Basic " + base64.b64encode(("admin:" + password).encode("ascii"))
            if supplied:
                return hmac.compare_digest(supplied.encode(), expected)
            try:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
                token = cookies["skell_session"].value
                expires, nonce, signature = token.split(".")
                payload = expires + "." + nonce
                return (time.time() < int(expires) <= time.time() + lifetime
                        and hmac.compare_digest(signature, sign(payload)))
            except (CookieError, KeyError, ValueError, UnicodeError):
                return False

        def do_GET(self):
            if self.path == "/":
                self.send(200, (ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/camera":
                self.send(200, (ROOT / "camera.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/camera/status" and camera is not None:
                if not self.authorized():
                    self.send(401, {"error": "Sign in first"})
                    return
                self.send(200, camera.status())
            elif self.path == "/api/status":
                if not self.authorized():
                    self.send(401, {"error": "Enter username admin and the dashboard password"})
                    return
                try:
                    status = controller.status()
                    if camera is not None:
                        status["camera"] = camera.status()
                    self.send(200, status)
                except (ValueError, OSError) as exc:
                    self.send(500, {"error": str(exc)})
            elif self.path == "/api/camera/preview" and camera is not None:
                if not self.authorized():
                    self.send(401, {"error": "Sign in first"})
                    return
                try:
                    self.send(200, camera.snapshot.read_bytes(), "image/jpeg")
                except FileNotFoundError:
                    self.send(404, {"error": "Waiting for a camera frame"})
            else:
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                self.send(401, {"error": "Enter username admin and the dashboard password"})
                return
            # No CORS support; cross-origin form requests cannot supply the Authorization header.
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
                if self.path == "/api/login":
                    payload = str(int(time.time()) + lifetime) + "." + secrets.token_hex(16)
                    cookie = "skell_session=" + payload + "." + sign(payload) + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" + str(lifetime)
                    self.send(200, {"ok": True}, cookie=cookie)
                    return
                elif self.path == "/api/logout":
                    self.send(200, {"ok": True}, cookie="skell_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
                    return
                elif self.path == "/api/camera/start" and camera is not None:
                    camera.start(data)
                elif self.path == "/api/camera/stop" and camera is not None:
                    camera.stop()
                elif self.path == "/api/settings":
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
    parser.add_argument("--start-stopped", action="store_true", help="Open the dashboard without starting the show")
    args = parser.parse_args()
    password = os.environ.get("SKELL_DASHBOARD_PASSWORD") or getpass.getpass("Dashboard password (8+ characters): ")
    if len(password) < 8 or not password.isascii():
        parser.error("Use a password of at least 8 ASCII characters")
    controller = Controller(args.dry_run)
    camera = Camera()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(controller, password, camera))
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    print("Dashboard listening on http://%s:%d (%s)" % (args.host, args.port, "simulation" if args.dry_run else "hardware"), flush=True)
    try:
        if not args.start_stopped:
            try:
                controller.start("show")
            except (ValueError, OSError) as exc:
                controller.logs.append("Automatic show startup failed: " + str(exc))
                print("Automatic show startup failed:", exc, flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        camera.close()
        if controller.process is not None:
            controller.process.wait()  # Do not kill the runner before GPIO cleanup.
        server.server_close()


if __name__ == "__main__":
    main()
