#!/usr/bin/env python3
"""Follow a fresh camera target with calibrated, speed-limited head motion."""
import argparse
import json
import math
from pathlib import Path
import signal
import time
from servo_config import get_servo_configs
from skeleton_motion import HEAD
from tracking_settings import read as read_tracking
from skeleton_run import Outputs
from skeleton_lock import hardware_lock


def target_pose(configs, data, now, reverse_x=False, reverse_y=False, settings=None):
    rest = {n: configs[n]["rest"] for n in HEAD}
    try:
        age = now - float(data["time"])
        x, y = float(data["x"]), float(data["y"])
        if not all(math.isfinite(v) for v in (age, x, y)) or not 0 <= age <= 2:
            return rest, False
    except (KeyError, TypeError, ValueError):
        return rest, False
    if settings is not None and settings["geometry"]:
        return geometry_pose(configs, x, y, data.get("aspect", 4/3), settings, reverse_x, reverse_y), True
    for name, value in (("Base", -x if reverse_x else x), ("Pitch", y if reverse_y else -y)):
        value = max(-1, min(1, value))
        if abs(value) < 0.08:
            value = 0
        low, high = configs[name]["range"]
        # Respect the selected fraction within the existing calibrated limits.
        fraction = settings["range_fraction"] if settings else 1.
        rest[name] += value * fraction * ((high - rest[name]) if value >= 0 else (rest[name] - low))
    return rest, True


def geometry_pose(configs, x, y, aspect, s, reverse_x=False, reverse_y=False):
    rest = {n: configs[n]["rest"] for n in HEAD}
    if not isinstance(aspect, (float, int)) or not math.isfinite(aspect) or not .2 <= aspect <= 5:
        return rest
    dx = max(-1, min(1, x)) * math.tan(math.radians(s["hfov"])/2)
    dy = -max(-1, min(1, y)) * math.tan(math.radians(s["hfov"])/2) / aspect
    pitch = math.radians(s["camera_pitch"])
    forward = math.cos(pitch) - dy*math.sin(pitch)
    azimuth = math.atan2(dx, forward) + math.radians(s["camera_yaw"])
    if abs(azimuth) >= math.radians(80):
        return rest
    lateral = s["sidewalk_distance"] * math.tan(azimuth)
    distance = math.hypot(lateral, s["sidewalk_distance"])
    elevation = math.degrees(math.atan2(s["aim_height"]-s["head_height"], distance))
    yaw = math.degrees(azimuth) - s["rest_yaw"]
    pitch_delta = elevation - s["rest_pitch"]
    for name, delta in (("Base", -yaw if reverse_x else yaw), ("Pitch", -pitch_delta if reverse_y else pitch_delta)):
        low, high = configs[name]["range"]
        fraction = s["range_fraction"]
        rest[name] = max(rest[name]+(low-rest[name])*fraction,
                         min(rest[name]+(high-rest[name])*fraction, rest[name]+delta))
    return rest


class TargetLinger:
    """Keep the last aim through brief detection gaps, then return to rest."""
    def __init__(self, rest, seconds=5):
        self.rest = dict(rest)
        self.seconds = seconds
        self.last_target = None
        self.lost_at = None

    def update(self, target, tracking, now):
        if tracking:
            self.last_target = dict(target)
            self.lost_at = None
            return target, True
        if self.last_target is not None:
            if self.lost_at is None:
                self.lost_at = now
            if now - self.lost_at < self.seconds:
                return dict(self.last_target), True
        return dict(self.rest), False


class FollowMotion:
    """Continuously retargetable damped motion with bounded speed/acceleration."""
    def __init__(self, configs, speed=10, acceleration=20):
        from skeleton_motion import validate_configs
        validate_configs(configs)
        self.configs, self.speed, self.acceleration = configs, speed, acceleration
        self.pose = {n: configs[n]["rest"] for n in HEAD}
        self.velocity = {n: 0. for n in HEAD}

    def step(self, target, dt):
        dt = min(.1, max(0, dt))
        for n in HEAD:
            low, high = self.configs[n]["range"]
            desired = max(low, min(high, target[n]))
            error = desired - self.pose[n]
            if abs(error) < .1:
                error = 0
            acceleration = max(-self.acceleration, min(self.acceleration, 9*error - 6*self.velocity[n]))
            self.velocity[n] = max(-self.speed, min(self.speed, self.velocity[n]+acceleration*dt))
            self.pose[n] += self.velocity[n]*dt
            if self.pose[n] < low or self.pose[n] > high:
                self.pose[n] = max(low, min(high, self.pose[n]))
                self.velocity[n] = 0
        return dict(self.pose)

    def settled(self, target):
        return all(abs(self.pose[n]-target[n]) < .15 and abs(self.velocity[n]) < .15 for n in HEAD)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--reverse-x", action="store_true")
    parser.add_argument("--reverse-y", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tracking-config", type=Path)
    args = parser.parse_args()
    settings = read_tracking(args.tracking_config) if args.tracking_config else None
    configs = get_servo_configs()
    motion = FollowMotion(configs, speed=settings["speed"] if settings else 10, acceleration=settings["acceleration"] if settings else 20)
    rest = {n: configs[n]["rest"] for n in HEAD}
    linger = TargetLinger(rest)
    stopping = False
    def stop(*unused):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with hardware_lock(args.dry_run):
        outputs = Outputs(configs, False, args.dry_run)
        idle_since = None
        previous_tick = time.monotonic()
        try:
            while not stopping:
                now = time.monotonic()
                try:
                    data = json.loads(args.target.read_text())
                except (OSError, ValueError):
                    data = {}
                target, tracking = target_pose(configs, data, time.time(), args.reverse_x, args.reverse_y, settings)
                target, tracking = linger.update(target, tracking, now)
                pose = motion.step(target, now-previous_tick)
                previous_tick = now
                if not tracking and motion.settled(rest):
                    idle_since = now if idle_since is None else idle_since
                    if now - idle_since > 0.5:
                        pose = {n: None for n in HEAD}
                else:
                    idle_since = None
                outputs.write(pose)
                time.sleep(0.02)
        finally:
            try:
                while not motion.settled(rest):
                    now = time.monotonic()
                    outputs.write(motion.step(rest, now-previous_tick))
                    previous_tick = now
                    time.sleep(0.02)
                outputs.write(rest)
                time.sleep(0.5)
            finally:
                outputs.close()


if __name__ == "__main__":
    main()
