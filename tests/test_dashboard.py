from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from skeleton_preferences import validate, read, save
from skeleton_speech import gain_pcm
from skeleton_dashboard import Controller, Camera, main
from skeleton_dashboard import handler_for
from http.server import ThreadingHTTPServer
import threading
import urllib.request
import urllib.error
import json
import base64
from types import SimpleNamespace
import io
from contextlib import redirect_stdout
from skeleton_run import run


class DashboardTests(unittest.TestCase):
    def test_camera_stop_kills_only_stalled_worker(self):
        import subprocess
        process = MagicMock()
        Camera._finish_stop(process)
        process.kill.assert_not_called()
        process.wait.side_effect = subprocess.TimeoutExpired("camera", 10)
        Camera._finish_stop(process)
        process.kill.assert_called_once()

    def test_camera_countdown_starts_and_cancels_on_server(self):
        camera = Camera()
        camera.url_path = Path(camera.directory.name) / "source.json"
        try:
            with patch("skeleton_dashboard.threading.Timer") as timer, patch("skeleton_dashboard.subprocess.Popen") as spawn:
                camera.start({"url": "rtsp://camera/live"})
                self.assertTrue(camera.status()["scheduled"])
                self.assertEqual(timer.call_args.args[0], 90)
                spawn.assert_not_called()
                callback = timer.call_args.args[1]
                camera.stop()
                callback()
                spawn.assert_not_called()
                self.assertFalse(camera.status()["scheduled"])
                camera.start({"url": "rtsp://camera/live"})
                callback = timer.call_args.args[1]
                with patch.object(camera, "start") as start:
                    callback()
                    self.assertEqual(start.call_args.args[0]["delay"], 0)
                    self.assertFalse(camera.status()["scheduled"])
        finally:
            camera.close()

    def test_camera_worker_validation_and_private_url(self):
        camera = Camera()
        camera.url_path = Path(camera.directory.name) / "source.json"
        try:
            with self.assertRaises(ValueError):
                camera.start({"url": "http://camera/live"})
            process = MagicMock()
            process.poll.return_value = None
            with patch("skeleton_dashboard.subprocess.Popen", return_value=process) as spawn, patch("skeleton_dashboard.threading.Thread"):
                url = "rtsp://user:secret@camera/live"
                camera.start({"url": url, "detector": "face", "seconds": 30, "delay": 0})
                self.assertNotIn(url, " ".join(spawn.call_args.args[0]))
                self.assertEqual(spawn.call_args.kwargs["env"]["SKELL_RTSP_URL"], url)
                self.assertNotIn(url, json.dumps(camera.status()))
                restored = Camera(camera.url_path)
                try:
                    self.assertEqual(restored.saved_url(), url)
                    self.assertTrue(restored.status()["configured"])
                    restored.save_url("rtsp://replacement/live")
                    self.assertEqual(camera.saved_url(), "rtsp://replacement/live")
                finally:
                    restored.close()
                with self.assertRaises(ValueError):
                    camera.start({"url": url})
                camera.stop()
                process.terminate.assert_called_once()
        finally:
            camera.close()

    def test_startup_runs_show_unless_start_stopped(self):
        for flags, should_start in (([], True), (["--start-stopped"], False)):
            with self.subTest(flags=flags), patch("sys.argv", ["dashboard", *flags]), patch.dict("os.environ", {"SKELL_DASHBOARD_PASSWORD": "test-password"}), patch("skeleton_dashboard.Controller") as factory, patch("skeleton_dashboard.ThreadingHTTPServer") as server, patch("skeleton_dashboard.signal.signal"), redirect_stdout(io.StringIO()):
                factory.return_value.process = None
                main()
                if should_start:
                    factory.return_value.start.assert_called_once_with("show")
                else:
                    factory.return_value.start.assert_not_called()
                factory.return_value.stop.assert_called_once()
                server.return_value.server_close.assert_called_once()

    def test_http_requires_password_and_validates_settings(self):
        class Connection:
            def __init__(self, request):
                self.input = io.BytesIO(request)
                self.output = bytearray()
            def makefile(self, *args):
                return self.input
            def sendall(self, data):
                self.output.extend(data)
        with tempfile.TemporaryDirectory() as directory:
            controller = Controller(True, Path(directory) / "settings.json")
            snapshot = Path(directory) / "frame.jpg"
            snapshot.write_bytes(b"test-jpeg")
            camera = SimpleNamespace(snapshot=snapshot, status=lambda: {"running": True})
            handler = handler_for(controller, "test-password", camera)
            def request(method, path, data=None, authorized=False, username="admin", password="test-password", cookie=None):
                body = json.dumps(data).encode() if data is not None else b""
                headers = f"{method} {path} HTTP/1.0\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                if authorized:
                    token = base64.b64encode(f"{username}:{password}".encode()).decode()
                    headers += f"Authorization: Basic {token}\r\n"
                if cookie:
                    headers += f"Cookie: {cookie}\r\n"
                connection = Connection(headers.encode() + b"\r\n" + body)
                handler(connection, ("127.0.0.1", 1), None)
                return bytes(connection.output)
            login = request("POST", "/api/login", {}, authorized=True)
            cookie_header = next(line for line in login.split(b"\r\n") if line.startswith(b"Set-Cookie:"))
            cookie = cookie_header.decode().split(": ", 1)[1].split(";", 1)[0]
            self.assertIn(b"HttpOnly", cookie_header)
            self.assertIn(b"SameSite=Strict", cookie_header)
            handler = handler_for(controller, "test-password", camera)  # Simulate restart.
            self.assertIn(b"200", request("GET", "/api/status", cookie=cookie))
            self.assertIn(b"200", request("GET", "/api/camera/preview", cookie=cookie))
            self.assertIn(b"401", request("GET", "/api/status", cookie=cookie + "bad"))
            with patch("skeleton_dashboard.time.time", return_value=9999999999):
                self.assertIn(b"401", request("GET", "/api/status", cookie=cookie))
            self.assertIn(b"Max-Age=0", request("POST", "/api/logout", {}, cookie=cookie))
            handler = handler_for(controller, "changed-password", camera)
            self.assertIn(b"401", request("GET", "/api/status", cookie=cookie))
            handler = handler_for(controller, "test-password", camera)
            self.assertIn(b"401", request("GET", "/api/status"))
            self.assertIn(b"Camera debug", request("GET", "/camera"))
            for endpoint in ("/api/camera/status", "/api/camera/preview"):
                self.assertIn(b"401", request("GET", endpoint))
                self.assertIn(b"200", request("GET", endpoint, authorized=True))
            self.assertIn(b"test-jpeg", request("GET", "/api/camera/preview", authorized=True))
            self.assertIn(b"401", request("GET", "/api/status", authorized=True, username="other"))
            self.assertIn(b"401", request("GET", "/api/status", authorized=True, password="wrong"))
            self.assertIn(b"200", request("POST", "/api/settings", {"volume": 32}, True))
            self.assertEqual(read(controller.preferences)["volume"], 32)
            self.assertIn(b"<h1>Skeleton</h1>", request("GET", "/"))
            self.assertIn(b"400", request("POST", "/api/settings", {"speed": 999}, True))

    def test_background_yields_to_speech_without_jaw_motion(self):
        clock, events, poses = [0.0], [], []
        class Player:
            jaw = -9
            volume = 100
            def __init__(self, *args, **kwargs):
                self.end = 0
            def start(self, path, now):
                self.stop()
                events.append(path.parent.name)
                self.end = now + 0.1
            def active(self, now):
                return now < self.end
            def stop(self):
                events.append("stop")
            def close(self):
                pass
        preferences = validate({"music": "a01.wav", "silent_chance": 0, "pause": 0.5})
        args = SimpleNamespace(preferences="unused", clip=None, action=None, no_voice=False, dry_run=True,
                               speed=10, seed=1, once=False, seconds=8, pause=0.5)
        with patch("skeleton_preferences.read", return_value=preferences), patch("skeleton_run.Speech", Player), patch("skeleton_run.time.monotonic", side_effect=lambda: clock[0]), patch("skeleton_run.time.sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), patch("skeleton_run.Outputs.write", side_effect=lambda pose: poses.append((clock[0], pose))), redirect_stdout(io.StringIO()):
            run(args)
        self.assertIn("ambient", events)
        self.assertIn("vocals", events)
        self.assertTrue(all(events[i-1] == "stop" for i, value in enumerate(events) if value in ("ambient", "vocals")))
        self.assertTrue(all(p["Mouth"] is None for t, p in poses if t < 0.5))

    def test_preferences_reject_unsafe_and_out_of_range_inputs(self):
        for value in ({"speed": 900}, {"volume": float("nan")}, {"clips": ["../other.wav"]},
                      {"music": "../../secret"}, {"hold_idle": "false"}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                validate(value)

    def test_preferences_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(read(path)["volume"], 75)
            save({"volume": 40, "pause": 20}, path)
            self.assertEqual(read(path)["volume"], 40)
            self.assertEqual(read(path)["pause"], 20)

    def test_pcm_volume(self):
        data = struct.pack("<hhh", -32768, 1000, 32767)
        self.assertEqual(gain_pcm(data, 100), data)
        self.assertEqual(struct.unpack("<hhh", gain_pcm(data, 50)), (-16384, 500, 16384))
        self.assertEqual(gain_pcm(data, 0), b"\0" * 6)

    def test_single_process_start_and_graceful_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = Controller(True, Path(directory) / "settings.json")
            process = MagicMock()
            process.poll.return_value = None
            with patch("skeleton_dashboard.subprocess.Popen", return_value=process) as spawn, patch("skeleton_dashboard.threading.Thread"):
                controller.start("yes")
                command = spawn.call_args.args[0]
                self.assertIn("--dry-run", command)
                self.assertIn("--action", command)
                with self.assertRaises(ValueError):
                    controller.start("show")
                controller.stop()
                controller.stop()
                self.assertEqual(process.send_signal.call_count, 1)
                self.assertTrue(controller.stopping)
            with self.assertRaises(ValueError):
                Controller(True).start("arbitrary-command")
