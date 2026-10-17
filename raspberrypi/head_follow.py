#!/usr/bin/env python3
"""Follow a fresh camera target with calibrated, speed-limited head motion."""
import argparse
import json
import math
from pathlib import Path
import signal
import time
from servo_config import get_servo_configs
from skeleton_motion import HEAD, Motion
from skeleton_run import Outputs
from skeleton_lock import hardware_lock


def target_pose(configs, data, now, reverse_x=False, reverse_y=False):
    rest = {n: configs[n]["rest"] for n in HEAD}
    try:
        age = now - float(data["time"])
        x, y = float(data["x"]), float(data["y"])
        if not all(math.isfinite(v) for v in (age, x, y)) or not 0 <= age <= 2:
            return rest, False
    except (KeyError, TypeError, ValueError):
        return rest, False
    for name, value in (("Base", -x if reverse_x else x), ("Pitch", y if reverse_y else -y)):
        value = max(-1, min(1, value))
        if abs(value) < 0.08:
            value = 0
        low, high = configs[name]["range"]
        # Same conservative inner 35% envelope as the existing show gestures.
        rest[name] += value * 0.35 * ((high - rest[name]) if value >= 0 else (rest[name] - low))
    return rest, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--reverse-x", action="store_true")
    parser.add_argument("--reverse-y", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configs = get_servo_configs()
    motion = Motion(configs, speed=10)
    rest = {n: configs[n]["rest"] for n in HEAD}
    stopping = False
    def stop(*unused):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with hardware_lock(args.dry_run):
        outputs = Outputs(configs, False, args.dry_run)
        idle_since = None
        try:
            while not stopping:
                now = time.monotonic()
                try:
                    data = json.loads(args.target.read_text())
                except (OSError, ValueError):
                    data = {}
                target, tracking = target_pose(configs, data, time.time(), args.reverse_x, args.reverse_y)
                if motion.finished(now) and any(abs(target[n] - motion.pose[n]) > 0.3 for n in HEAD):
                    motion.move(target, now, duration=0.7)
                pose = motion.sample(now)
                if not tracking and motion.finished(now) and all(abs(pose[n] - rest[n]) <= 0.3 for n in HEAD):
                    idle_since = now if idle_since is None else idle_since
                    if now - idle_since > 0.5:
                        pose = {n: None for n in HEAD}
                else:
                    idle_since = None
                outputs.write(pose)
                time.sleep(0.02)
        finally:
            try:
                # Finish the current smooth trajectory, then return home and detach.
                while not motion.finished(time.monotonic()):
                    outputs.write(motion.sample(time.monotonic()))
                    time.sleep(0.02)
                motion.move(rest, time.monotonic(), duration=1.5)
                while not motion.finished(time.monotonic()):
                    outputs.write(motion.sample(time.monotonic()))
                    time.sleep(0.02)
                outputs.write(rest)
                time.sleep(0.5)
            finally:
                outputs.close()


if __name__ == "__main__":
    main()
