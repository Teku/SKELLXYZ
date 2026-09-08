import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
import wave
import io
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberrypi"))
from servo_config import get_servo_configs
from skeleton_motion import HEAD, Motion, validate_configs
from skeleton_speech import Speech, process_chunk, settings, check_clip, CHATTER
from skeleton_run import Outputs, run
from skeleton_gestures import NAMES, sequence
from skeleton_audio_init import initialize, report
from contextlib import redirect_stderr


class MotionTests(unittest.TestCase):
    def test_expressions_are_bounded_and_return_to_rest(self):
        cfg = get_servo_configs()
        for name in NAMES:
            for direction in (-1, 1):
                steps = sequence(name, cfg, direction)
                self.assertEqual(steps[-1][0], {n: cfg[n]["rest"] for n in HEAD})
                for pose, duration in steps:
                    self.assertGreater(duration, 0)
                    for n in HEAD:
                        low, high = cfg[n]["range"]
                        rest = cfg[n]["rest"]
                        self.assertTrue(rest + 0.35 * (low - rest) - 1e-9 <= pose[n] <= rest + 0.35 * (high - rest) + 1e-9)
                        if name in ("yes", "no", "happy") and n != {"yes": "Pitch", "no": "Base", "happy": "Tilt"}[name]:
                            self.assertEqual(pose[n], rest)

    def test_simultaneous_endpoints_speed_and_limits(self):
        cfg = get_servo_configs()
        motion = Motion(cfg, speed=10)
        rest = dict(motion.pose)
        motion.move({n: 1000 for n in HEAD}, 0, 0.1)
        middle = motion.sample(motion.duration / 2)
        for n in HEAD:
            self.assertAlmostEqual(middle[n], (rest[n] + cfg[n]["range"][1]) / 2)
        previous = motion.sample(0)
        dt = motion.duration / 1000
        for i in range(1, 1001):
            pose = motion.sample(i * dt)
            for n in HEAD:
                self.assertLessEqual(abs(pose[n] - previous[n]) / dt, 10.0001)
                self.assertTrue(cfg[n]["range"][0] <= pose[n] <= cfg[n]["range"][1])
            previous = pose
        self.assertEqual(motion.sample(motion.duration + 1), motion.target)

    def test_retarget_preserves_position(self):
        motion = Motion(get_servo_configs())
        motion.move({n: 10 for n in HEAD}, 0)
        pose = motion.sample(0.5)
        motion.move({n: -10 for n in HEAD}, 0.5)
        self.assertEqual(pose, motion.sample(0.5))

    def test_invalid_limits_rejected(self):
        for value in (float("nan"), 999):
            cfg = get_servo_configs()
            cfg["Base"]["rest"] = value
            with self.assertRaises(ValueError):
                validate_configs(cfg)


class SpeechTests(unittest.TestCase):
    def test_head_only_modes_never_initialize_audio(self):
        for action in (*NAMES, None):
            clock = [0.0]
            def sleep(seconds):
                clock[0] += seconds
                if clock[0] > 45:
                    raise AssertionError("Head-only mode failed to stop")
            args = SimpleNamespace(action=action, no_voice=True, clip=None,
                                   dry_run=True, speed=10, seed=1, once=False,
                                   seconds=0 if action else 20, pause=0.6)
            output = io.StringIO()
            poses = []
            with patch("skeleton_run.settings", side_effect=AssertionError("Audio config accessed")), patch("skeleton_run.Speech", side_effect=AssertionError("Audio initialized")), patch("skeleton_run.check_clip", side_effect=AssertionError("Clip accessed")), patch("skeleton_run.time.monotonic", side_effect=lambda: clock[0]), patch("skeleton_run.time.sleep", side_effect=sleep), patch("skeleton_run.Outputs.write", side_effect=lambda pose: poses.append(pose)), redirect_stdout(output):
                run(args)
            events = [line for line in output.getvalue().splitlines() if line.startswith("Silent gesture:")]
            if action:
                self.assertEqual(events, ["Silent gesture: " + action])
            else:
                self.assertGreaterEqual(len(events), 2)
                self.assertGreaterEqual(clock[0], 20)
            self.assertNotIn("Speaking:", output.getvalue())
            self.assertTrue(all(pose["Mouth"] is None for pose in poses))
            self.assertIn("Stopped; servo outputs released", output.getvalue())

    def test_startup_diagnostics_keep_errors_and_support_debug(self):
        diagnostics = b"ALSA lib pcm.c: Unknown PCM surround51\nOther warning\n"
        output = io.StringIO()
        with redirect_stderr(output):
            report(diagnostics, True)
        self.assertNotIn("Unknown PCM", output.getvalue())
        self.assertIn("Other warning", output.getvalue())
        self.assertIn("1 ALSA", output.getvalue())
        output = io.StringIO()
        with redirect_stderr(output):
            report(diagnostics, False)
        self.assertEqual(output.getvalue(), diagnostics.decode())
        token = object()
        self.assertIs(initialize(lambda: token, debug=True), token)
        def fail():
            raise RuntimeError("No audio device")
        with self.assertRaises(RuntimeError):
            initialize(fail, debug=True)

    def test_shutdown_detaches_all_before_closing_connection(self):
        for fail in (False, True):
            outputs = Outputs(get_servo_configs(), True, True)
            events = []
            def detach(name):
                events.append("detach " + name)
                if fail and name == "Tilt":
                    raise RuntimeError("pin unavailable")
            for name in (*HEAD, "Mouth"):
                outputs.servos[name] = SimpleNamespace(detach=lambda n=name: detach(n))
            outputs.resources.callback(lambda: events.append("close connection"))
            if fail:
                with self.assertRaises(RuntimeError):
                    outputs.close()
            else:
                outputs.close()
            self.assertEqual(set(events[:-1]), {"detach " + n for n in (*HEAD, "Mouth")})
            self.assertEqual(events[-1], "close connection")
            outputs.close()
            self.assertEqual(len(events), 5)

    def test_output_release_and_reactivation(self):
        outputs = Outputs(get_servo_configs(), True, True)
        servo = SimpleNamespace(value=0.5)
        outputs.servos["Mouth"] = servo
        outputs.write({"Mouth": None})
        self.assertIsNone(servo.value)
        outputs.write({"Mouth": -9})
        self.assertAlmostEqual(servo.value, -0.1)

    def test_one_clip_full_controller_lifecycle(self):
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
            if clock[0] > 30:
                raise AssertionError("Controller failed to finish one clip")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "short.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(struct.pack("<h", 5000) * 800)
            args = SimpleNamespace(clip=str(path), dry_run=True, speed=18, seed=1,
                                   once=True, seconds=0, pause=0, silent_chance=0)
            output = io.StringIO()
            with patch("skeleton_run.time.monotonic", side_effect=lambda: clock[0]), patch("skeleton_run.time.sleep", side_effect=sleep), redirect_stdout(output):
                run(args)
            self.assertEqual(output.getvalue().count("Speaking:"), 1)
            self.assertIn("Head gesture:", output.getvalue())
            self.assertIn("Speech finished; returning to rest", output.getvalue())
            self.assertIn("Stopped; servo outputs released", output.getvalue())
            # Observe actual controller output policy through an entire idle pause.
            for hold in (False, True):
                clock[0] = 0
                args.once, args.seconds, args.pause, args.hold_idle = False, 12, 20, hold
                writes = []
                def record(pose):
                    writes.append((clock[0], dict(pose)))
                with patch("skeleton_run.time.monotonic", side_effect=lambda: clock[0]), patch("skeleton_run.time.sleep", side_effect=sleep), patch("skeleton_run.Outputs.write", side_effect=record), redirect_stdout(io.StringIO()):
                    run(args)
                self.assertTrue(any(p["Mouth"] is not None for _, p in writes))
                self.assertTrue(all(p["Mouth"] is None for t, p in writes if t > 0.8))
                idle = [p for t, p in writes if 9 < t < 11]
                self.assertTrue(idle)
                for pose in idle:
                    for name in HEAD:
                        if hold:
                            self.assertAlmostEqual(pose[name], get_servo_configs()[name]["rest"])
                        else:
                            self.assertIsNone(pose[name])
            # Force a silent expression, then verify the next event is speech.
            clock[0] = 0
            args.once, args.seconds, args.pause = False, 24, 1
            args.silent_chance, args.hold_idle = 1, False
            writes = []
            output = io.StringIO()
            with patch("skeleton_run.time.monotonic", side_effect=lambda: clock[0]), patch("skeleton_run.time.sleep", side_effect=sleep), patch("skeleton_run.Outputs.write", side_effect=record), redirect_stdout(output):
                run(args)
            events = [line for line in output.getvalue().splitlines() if line.startswith(("Silent gesture:", "Speaking:"))]
            self.assertTrue(events[0].startswith("Silent gesture:"))
            self.assertTrue(events[1].startswith("Speaking:"))
            self.assertIn("Silent gesture finished; resting", output.getvalue())
            # All servo frames before the first speech keep the jaw released.
            first_jaw = next(i for i, (_, p) in enumerate(writes) if p["Mouth"] is not None)
            self.assertGreater(first_jaw, 50)
            self.assertTrue(any(p["Base"] is None for _, p in writes[:first_jaw]))

    def test_callback_completion_and_cleanup(self):
        streams = []
        class Stream:
            closed = False
            running = True
            def __init__(self, callback):
                self.callback = callback
            def is_active(self):
                return self.running
            def stop_stream(self):
                self.running = False
            def close(self):
                self.closed = True
        class Audio:
            terminated = False
            def open(self, **kwargs):
                stream = Stream(kwargs["stream_callback"])
                streams.append(stream)
                return stream
            def terminate(self):
                self.terminated = True
        audio = Audio()
        api = SimpleNamespace(PyAudio=lambda: audio, paInt16=8, paComplete=1, paContinue=0, paAbort=2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "short.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(struct.pack("<hh", 5000, 5000))
            with patch.dict(sys.modules, pyaudio=api):
                speech = Speech(settings(), get_servo_configs()["Mouth"])
                try:
                    speech.start(path, 0)
                    self.assertTrue(speech.active(0))
                    data, status = streams[0].callback(None, 160, None, 0)
                    self.assertEqual(status, api.paComplete)
                    self.assertEqual(len(data), 4)
                    self.assertEqual(speech.jaw, -9)
                    speech.start(path, 1)
                    self.assertTrue(streams[0].closed)
                    speech.source.close()
                    _, status = streams[1].callback(None, 160, None, 0)
                    self.assertEqual(status, api.paAbort)
                    with self.assertRaises(RuntimeError):
                        speech.active(1)
                finally:
                    speech.close()
                self.assertTrue(streams[1].closed)
                self.assertTrue(audio.terminated)
                self.assertEqual(speech.jaw, get_servo_configs()["Mouth"]["rest"])

    def test_threshold_direction_and_full_scale(self):
        options = settings()
        for sample, expected in ((0, 72), (2000, 45), (3000, 18), (-32768, -9)):
            _, jaw = process_chunk(struct.pack("<h", sample), 1, options, (-9, 72))
            self.assertAlmostEqual(jaw, expected)
        _, jaw = process_chunk(b"", 1, options, (-9, 72))
        self.assertEqual(jaw, 72)

    def test_stereo_envelope_uses_right_before_left_output_copy(self):
        options = dict(settings(), output="LEFT")
        result, jaw = process_chunk(struct.pack("<hh", 100, 5000), 2, options, (-9, 72))
        self.assertEqual(jaw, -9)
        self.assertEqual(struct.unpack("<hh", result), (100, 100))

    def test_existing_vocals_supported(self):
        clips = list((CHATTER / "vocals").glob("v[0-9][0-9].wav"))
        self.assertTrue(clips)
        for clip in clips:
            check_clip(clip)


if __name__ == "__main__":
    unittest.main()
