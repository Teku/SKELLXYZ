import sys
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from camera_test import Target, deduplicate, load_face_detector
from camera_source import open_source, validate_rtsp, redact_diagnostic
from unittest.mock import patch
import os


class TrackingTests(unittest.TestCase):
    def test_rtsp_backend_timeouts_and_no_url_in_failure(self):
        calls = []
        secret_url = "rtsp://test:dummy-password@192.0.2.1/live"
        class Capture:
            def open(self, *args):
                calls.append(args)
                return True
            def release(self):
                calls.append("release")
        cv = SimpleNamespace(VideoCapture=Capture, CAP_FFMPEG=1900,
                             CAP_PROP_OPEN_TIMEOUT_MSEC=53, CAP_PROP_READ_TIMEOUT_MSEC=54)
        with patch.dict(os.environ, OPENCV_FFMPEG_CAPTURE_OPTIONS="original"):
            open_source(cv, "/dev/video0", secret_url)
            self.assertEqual(os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"], "original")
        self.assertEqual(calls[0], (secret_url, 1900, [53, 10000, 54, 5000]))
        with patch.object(Capture, "open", side_effect=RuntimeError(secret_url)):
            with self.assertRaises(RuntimeError) as caught:
                open_source(cv, "0", secret_url)
        self.assertNotIn("dummy-password", str(caught.exception))
        self.assertEqual(calls[-1], "release")
        with self.assertRaises(ValueError):
            validate_rtsp("https://example.com")

    def test_rtsp_failure_reports_redacted_backend_error(self):
        url = "rtsp://viewer:secret-value@camera/live"
        class Capture:
            def open(self, *args):
                os.write(2, ("SETUP failed: 461 Unsupported Transport " + url).encode())
                return False
            def release(self):
                pass
        cv = SimpleNamespace(VideoCapture=Capture, CAP_FFMPEG=1900)
        with self.assertRaises(RuntimeError) as caught:
            open_source(cv, "0", url)
        message = str(caught.exception)
        with self.assertRaises(RuntimeError) as raw:
            open_source(cv, "0", url, debug=True)
        self.assertIn(url, str(raw.exception))
        self.assertIn("461 Unsupported Transport", message)
        self.assertNotIn("secret-value", message)
        self.assertNotIn("viewer", message)
        self.assertNotIn("s3cret", redact_diagnostic("password s3cret", "rtsp://viewer:s3cret@camera/live"))

    def test_gif_preview_encodes_timing_and_bounds_memory(self):
        from PIL import Image
        from camera_gif import GifPreview
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.gif"
            gif = GifPreview(path)
            for now, color in ((0, "red"), (0.1, "green"), (0.7, "blue")):
                with patch.object(Image, "fromarray", return_value=Image.new("RGB", (480, 360), color)):
                    gif.add(None, now)
            self.assertEqual(len(gif.frames), 2)
            self.assertTrue(gif.save())
            with Image.open(path) as saved:
                self.assertEqual(saved.n_frames, 2)
                self.assertEqual(saved.size, (320, 240))
                self.assertEqual(saved.info["duration"], 700)
                self.assertEqual(saved.info["loop"], 0)
            with patch.object(Image, "fromarray", return_value=Image.new("RGB", (480, 360))):
                for i in range(100):
                    gif.add(None, i + 1)
            self.assertEqual(len(gif.frames), 60)

    def test_head_follow_limits_stale_target_and_direction(self):
        from head_follow import target_pose
        from servo_config import get_servo_configs
        configs = get_servo_configs()
        rest = {n: configs[n]["rest"] for n in ("Base", "Pitch", "Tilt")}
        for data in ({}, {"time": 1, "x": 0, "y": 0}, {"time": 10, "x": None, "y": None}, {"time": 10, "x": float("nan"), "y": 0}):
            self.assertEqual(target_pose(configs, data, 10), (rest, False))
        data = {"time": 10, "x": 100, "y": -100}
        pose, valid = target_pose(configs, data, 10)
        self.assertTrue(valid)
        for name in rest:
            low, high = configs[name]["range"]
            self.assertGreaterEqual(pose[name], rest[name] + (low - rest[name]) * .35)
            self.assertLessEqual(pose[name], rest[name] + (high - rest[name]) * .35)
        self.assertEqual(pose["Tilt"], rest["Tilt"])
        reversed_pose, _ = target_pose(configs, data, 10, True, True)
        self.assertLess(reversed_pose["Base"], rest["Base"])
        self.assertLess(reversed_pose["Pitch"], rest["Pitch"])

    def test_legacy_rtsp_uses_two_argument_open(self):
        calls = []
        class Capture:
            def open(self, *args):
                calls.append((args, os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]))
                return True
        cv = SimpleNamespace(VideoCapture=Capture, CAP_FFMPEG=1900)
        with patch.dict(os.environ, OPENCV_FFMPEG_CAPTURE_OPTIONS="original"):
            open_source(cv, "0", "rtsp://camera/live")
            self.assertEqual(os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"], "original")
        self.assertEqual(calls, [(("rtsp://camera/live", 1900), "rtsp_transport;tcp|stimeout;5000000")])

    def test_face_cascade_loading_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "face.xml"
            fake = SimpleNamespace(CascadeClassifier=lambda p: SimpleNamespace(empty=lambda: False))
            with self.assertRaisesRegex(RuntimeError, "Face cascade missing"):
                load_face_detector(fake, path)
            path.write_text("placeholder")
            self.assertFalse(load_face_detector(fake, path).empty())
            fake.CascadeClassifier = lambda p: SimpleNamespace(empty=lambda: True)
            with self.assertRaisesRegex(RuntimeError, "Invalid face cascade"):
                load_face_detector(fake, path)

    def test_lock_smoothing_and_missing_observations(self):
        tracker = Target()
        self.assertEqual(tracker.update([(10, 10, 60, 120)], 0), (40, 70))
        self.assertIsNone(tracker.update([], 0.5))
        point = tracker.update([(20, 10, 60, 120), (300, 10, 60, 120)], 1)
        self.assertAlmostEqual(point[0], 43.5)
        self.assertIsNone(tracker.update([], 3))
        self.assertIsNone(tracker.box)

    def test_crowd_does_not_acquire_arbitrary_target(self):
        tracker = Target()
        self.assertIsNone(tracker.update([(0, 0, 60, 120), (200, 0, 60, 120)], 0))
        self.assertIsNone(tracker.box)

    def test_overlapping_detections_are_deduplicated(self):
        self.assertEqual(deduplicate([(0, 0, 60, 120), (2, 2, 60, 120), (200, 0, 60, 120)]),
                         [(0, 0, 60, 120), (200, 0, 60, 120)])
