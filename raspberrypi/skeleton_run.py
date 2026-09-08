#!/usr/bin/env python3
"""Unified recorded speech and smooth head gestures; manual trial runner."""
import argparse
from contextlib import ExitStack
import math
from pathlib import Path
import random
import signal
import time

from servo_config import get_servo_configs
from skeleton_motion import HEAD, Motion, validate_configs
from skeleton_gestures import NAMES, sequence
from skeleton_speech import CHATTER, Speech, check_clip, settings


class Outputs:
    def __init__(self, configs, jaw_enabled, dry_run):
        self.configs = configs
        self.resources = ExitStack()
        self.servos = {}
        self.closed = False
        if dry_run:
            return
        try:
            from gpiozero import Servo
            from gpiozero.pins.pigpio import PiGPIOFactory
            factory = PiGPIOFactory()
            self.resources.callback(factory.close)
            for name, config in configs.items():
                if name == "Mouth" and not jaw_enabled:
                    continue
                servo = Servo(config["pin"], initial_value=None, min_pulse_width=0.0005,
                              max_pulse_width=0.0025, pin_factory=factory)
                self.resources.callback(servo.close)
                self.servos[name] = servo
        except BaseException:
            self.close()
            raise

    def write(self, pose):
        for name, angle in pose.items():
            cfg = self.configs[name]
            if angle is None:
                if name in self.servos:
                    self.servos[name].value = None
                continue
            if not math.isfinite(angle):
                raise ValueError("Non-finite servo angle")
            low, high = cfg["range"]
            if name in self.servos:
                self.servos[name].value = max(low, min(high, angle)) / (cfg["travel"] / 2)

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Explicitly stop PWM on every owned servo before closing any device
        # or the pigpio connection. ExitStack attempts all releases even if
        # one pin fails, and still closes the underlying resources afterward.
        with ExitStack() as cleanup:
            cleanup.callback(self.resources.close)
            for servo in self.servos.values():
                cleanup.callback(servo.detach)


def gesture(configs, rng):
    # Start conservatively: use the inner 35% of each side of the tuned range.
    return {n: rng.uniform(configs[n]["rest"] + (configs[n]["range"][0] - configs[n]["rest"]) * 0.35,
                           configs[n]["rest"] + (configs[n]["range"][1] - configs[n]["rest"]) * 0.35)
            for n in HEAD}


def run(args):
    configs = get_servo_configs()
    validate_configs(configs)
    options = settings()
    clips = [Path(args.clip).resolve()] if args.clip else sorted((CHATTER / "vocals").glob("v[0-9][0-9].wav"))
    if not clips:
        raise ValueError("No vocal recordings found")
    for clip in clips:
        check_clip(clip)
    motion = Motion(configs, args.speed)
    rest = {n: configs[n]["rest"] for n in HEAD}
    rng = random.Random(args.seed)
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    with ExitStack() as resources:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous = signal.signal(sig, stop)
            resources.callback(signal.signal, sig, previous)
        outputs = Outputs(configs, options["jaw_enabled"], args.dry_run)
        resources.callback(outputs.close)
        speech = Speech(options, configs["Mouth"], args.dry_run, audio_debug=getattr(args, "audio_debug", False))
        resources.callback(speech.close)
        outputs.write(dict(rest, Mouth=None))
        started = time.monotonic()
        next_clip = started + 0.5
        speaking = False
        position = 0
        completed = 0
        resting_since = None
        silent_steps = []
        silent_active = False
        last_was_silent = False
        try:
            while not stopping:
                now = time.monotonic()
                if args.seconds and now - started >= args.seconds:
                    break
                if speaking and not speech.active(now):
                    speech.stop()
                    speaking = False
                    completed += 1
                    print("Speech finished; returning to rest", flush=True)
                    # Complete the current gesture before returning, preserving smooth endpoints.
                    next_clip = max(now, motion.started + motion.duration) + 2.0 + args.pause
                if not speaking and motion.finished(now):
                    if silent_active:
                        if silent_steps:
                            target, duration = silent_steps.pop(0)
                            motion.move(target, now, duration)
                        else:
                            silent_active = False
                            next_clip = now + args.pause
                            print("Silent gesture finished; resting", flush=True)
                    elif motion.target != rest:
                        motion.move(rest, now, 2.0)
                        next_clip = max(next_clip, now + motion.duration + args.pause)
                    elif args.once and completed:
                        break
                    elif now >= next_clip:
                        if not args.once and not last_was_silent and rng.random() < getattr(args, "silent_chance", 0.35):
                            name = rng.choice(NAMES)
                            silent_steps = sequence(name, configs, rng.choice((-1, 1)))
                            silent_active = last_was_silent = True
                            target, duration = silent_steps.pop(0)
                            motion.move(target, now, duration)
                            print("Silent gesture: " + name, flush=True)
                        else:
                            clip = clips[position % len(clips)]
                            print("Speaking: " + clip.name, flush=True)
                            speech.start(clip, now)
                            position += 1
                            speaking = True
                            last_was_silent = False
                if speaking and motion.finished(now):
                    target = gesture(configs, rng)
                    motion.move(target, now, rng.uniform(1.5, 3.0))
                    print("Head gesture: " + str({n: round(v, 1) for n, v in target.items()}), flush=True)
                pose = motion.sample(now)
                at_rest = not speaking and not silent_active and motion.finished(now) and motion.target == rest
                if at_rest:
                    if resting_since is None:
                        resting_since = now
                    if not getattr(args, "hold_idle", False) and now - resting_since >= 0.5:
                        pose = {n: None for n in HEAD}
                else:
                    resting_since = None
                # Match legacy ChatterPi: release the jaw after playback, rather
                # than treating Mouth_rest as a calibrated closed-mouth angle.
                outputs.write(dict(pose, Mouth=speech.jaw if speaking else None))
                time.sleep(0.02)
        finally:
            print("Stopping: finishing motion and returning to rest before releasing PWM...", flush=True)
            speech.stop()
            # Finish any in-flight gesture, then ease home; all outputs close even on failure.
            now = time.monotonic()
            while not motion.finished(now):
                outputs.write(dict(motion.sample(now), Mouth=None))
                time.sleep(0.02)
                now = time.monotonic()
            motion.move(rest, now, 1.5)
            while not motion.finished(time.monotonic()):
                outputs.write(dict(motion.sample(time.monotonic()), Mouth=None))
                time.sleep(0.02)
            outputs.write(dict(rest, Mouth=None))
    print("Stopped; servo outputs released", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Simulate speech and poses without GPIO or audio devices")
    parser.add_argument("--audio-debug", action="store_true", help="Show full ALSA startup diagnostics")
    parser.add_argument("--clip", help="Play a particular 16-bit PCM WAV instead of cycling existing vocals")
    parser.add_argument("--once", action="store_true", help="Play one clip, return to rest, and exit")
    parser.add_argument("--seconds", type=float, default=0, help="Stop trial after this many seconds (0: unlimited)")
    parser.add_argument("--speed", type=float, default=18, help="Maximum head speed in degrees/second")
    parser.add_argument("--pause", type=float, default=5, help="Pause between recordings in seconds")
    parser.add_argument("--silent-chance", type=float, default=0.35, help="Chance of a silent expression instead of the next recording (0..1); never two in a row")
    parser.add_argument("--hold-idle", action="store_true", help="Keep head servos holding rest during pauses instead of releasing PWM")
    parser.add_argument("--seed", type=int, help="Reproducible gesture seed")
    args = parser.parse_args()
    if not math.isfinite(args.silent_chance) or not 0 <= args.silent_chance <= 1:
        parser.error("silent-chance must be between 0 and 1")
    for name in ("seconds", "pause", "speed"):
        value = getattr(args, name)
        if not math.isfinite(value) or value < 0 or (name == "speed" and value == 0):
            parser.error(name + " must be finite and " + ("positive" if name == "speed" else "nonnegative"))
    run(args)


if __name__ == "__main__":
    main()
