import sys
from pathlib import Path
import unittest
import math
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from motion_tracking import StableTarget, MotionDetector
from tracking_settings import DEFAULTS, validate
from head_follow import geometry_pose, FollowMotion
from servo_config import get_servo_configs


class TrackingPipelineTests(unittest.TestCase):
    def test_confirmation_hold_expiry_and_no_jump_to_distant_object(self):
        tracker = StableTarget()
        box = (50, 50, 35, 90)
        self.assertIsNone(tracker.update([box], 0))
        self.assertIsNone(tracker.update([box], .2))
        point = tracker.update([box], .4)
        self.assertIsNotNone(point)
        self.assertEqual(tracker.update([], .8), point)
        self.assertEqual(tracker.state, "HOLDING")
        self.assertEqual(tracker.update([(350, 50, 35, 90)], 1), point)
        self.assertIsNone(tracker.update([], 1.3))
        self.assertIsNone(tracker.update([box, (350,50,35,90)], 1.4))

    def test_tracker_smoothed_target_remains_between_measurements(self):
        tracker = StableTarget()
        for t in (0,.2,.4):
            tracker.update([(50,50,35,90)], t)
        old = tracker.point
        new = tracker.update([(70,50,35,90)], .6)
        self.assertGreater(new[0], old[0])
        self.assertLess(new[0], 87.5)

    def test_geometry_height_and_calibrated_rest(self):
        configs = get_servo_configs()
        s = dict(DEFAULTS, range_fraction=1)
        pose = geometry_pose(configs, 0, 0, 16/9, s)
        self.assertEqual(pose["Base"], configs["Base"]["rest"])
        self.assertEqual(pose["Pitch"], configs["Pitch"]["range"][0])  # 26.565 degrees exceeds default downward travel.
        s["rest_pitch"] = math.degrees(math.atan2(-7,14))
        pose = geometry_pose(configs, 0, 0, 16/9, s)
        self.assertAlmostEqual(pose["Pitch"], configs["Pitch"]["rest"])
        left = geometry_pose(configs, -.3, 0, 16/9, s)
        right = geometry_pose(configs, .3, 0, 16/9, s)
        self.assertAlmostEqual(left["Base"], -right["Base"])
        self.assertAlmostEqual(left["Pitch"], right["Pitch"])

    def test_continuous_motion_bounds_speed_acceleration_and_returns_home(self):
        configs = get_servo_configs()
        motion = FollowMotion(configs)
        rest = {n:configs[n]["rest"] for n in motion.pose}
        previous = dict(motion.velocity)
        for i in range(500):
            target = dict(rest, Base=20 if i < 250 else -20)
            pose = motion.step(target, .02)
            for n in pose:
                self.assertLessEqual(abs(motion.velocity[n]), 10)
                self.assertLessEqual(abs(motion.velocity[n]-previous[n]), .400001)
                self.assertGreaterEqual(pose[n], configs[n]["range"][0])
                self.assertLessEqual(pose[n], configs[n]["range"][1])
            previous = dict(motion.velocity)
        for _ in range(1000):
            motion.step(rest, .02)
        self.assertTrue(motion.settled(rest))

    def test_invalid_tracking_settings_rejected(self):
        for values in ({"hfov":float("nan")}, {"speed":1000}, {"roi_left":80,"roi_right":20}, {"geometry":"true"}):
            with self.assertRaises(ValueError):
                validate(values)

    def test_motion_detects_blob_rejects_scene_flash_and_respects_roi(self):
        import cv2
        import numpy as np
        detector = MotionDetector(cv2, dict(DEFAULTS, roi_left=20, roi_right=80))
        background = np.full((360,480,3), 60, dtype=np.uint8)
        for i in range(21):
            boxes = detector.detect(background, i*.2)
        self.assertEqual(boxes, [])
        frame = background.copy()
        frame[100:210, 180:220] = 230
        boxes = detector.detect(frame, 4.3)
        self.assertTrue(boxes)
        self.assertTrue(all(96 <= box[0] < 384 for box in boxes))
        outside = background.copy()
        outside[100:210, 10:40] = 230
        self.assertEqual(detector.detect(outside, 4.5), [])
        flash = np.full_like(background, 250)
        self.assertEqual(detector.detect(flash, 4.7), [])
        self.assertEqual(detector.state, "LIGHT/SCENE CHANGE")
