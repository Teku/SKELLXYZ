import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from camera_test import Target, deduplicate


class TrackingTests(unittest.TestCase):
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
