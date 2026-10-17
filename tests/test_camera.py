import sys
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from camera_test import Target, deduplicate, load_face_detector
from camera_source import open_source, validate_rtsp
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
