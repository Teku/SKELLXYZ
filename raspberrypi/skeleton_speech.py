"""Recorded speech with the existing ChatterPi style 0/1 jaw thresholds.

No GPIO or audio devices are opened during import. The audio callback only
publishes a jaw target; the controller owns all servo writes.
"""
from array import array
from configparser import ConfigParser
from pathlib import Path
import sys
import wave

CHATTER = Path(__file__).resolve().parent / "vendor" / "ChatterPi" / "src"


def settings(path=CHATTER / "config.ini"):
    cfg = ConfigParser()
    if not cfg.read(path):
        raise ValueError("Missing audio settings: " + str(path))
    if cfg.get("AUDIO", "source").upper() != "FILES":
        raise ValueError("Unified runner currently supports recorded FILES only")
    style = cfg.getint("CONTROLLER", "style")
    if style not in (0, 1):
        raise ValueError("Unified runner supports ChatterPi styles 0 and 1 only")
    levels = tuple(cfg.getint("CONTROLLER", "level" + str(i)) for i in (1, 2, 3))
    if not 0 <= levels[0] <= levels[1] <= levels[2]:
        raise ValueError("Jaw thresholds must be nonnegative and ordered")
    output = cfg.get("AUDIO", "output_channels").upper()
    if output not in ("LEFT", "BOTH"):
        raise ValueError("Unsupported output_channels: " + output)
    return dict(style=style, levels=levels, threshold=cfg.getint("CONTROLLER", "threshold"),
                output=output, jaw_enabled=cfg.get("PROP", "jaw_enabled").upper() == "ON")


def process_chunk(data, channels, options, limits):
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    signal = samples[1::2] if channels == 2 else samples
    volume = sum(abs(int(v)) for v in signal) / len(signal) if signal else 0
    if options["style"] == 0:
        amount = float(volume > options["threshold"])
    else:
        amount = sum(volume > level for level in options["levels"]) / 3.0
    # Preserve ChatterPi's existing direction: quiet=max, loud=min.
    low, high = limits
    angle = high + (low - high) * amount
    if channels == 2 and options["output"] == "LEFT":
        samples[1::2] = samples[::2]
        if sys.byteorder != "little":
            samples.byteswap()
        data = samples.tobytes()
    return data, angle


def check_clip(path):
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() not in (1, 2) or source.getcomptype() != "NONE":
            raise ValueError("Expected mono/stereo 16-bit PCM WAV: " + str(path))
        if not source.getnframes():
            raise ValueError("Empty recording: " + str(path))


class Speech:
    def __init__(self, options, mouth, dry_run=False):
        self.options, self.mouth, self.dry_run = options, mouth, dry_run
        self.jaw = mouth["rest"]
        self.stream = self.source = self.audio = None
        self.error = None
        self.ends = 0.0
        if not dry_run:
            import pyaudio
            self.api = pyaudio
            self.audio = pyaudio.PyAudio()

    def start(self, path, now):
        self.stop()
        check_clip(path)
        self.error = None
        self.source = wave.open(str(path), "rb")
        rate, channels = self.source.getframerate(), self.source.getnchannels()
        self.ends = now + self.source.getnframes() / rate
        if self.dry_run:
            return

        def callback(in_data, frame_count, time_info, status):
            try:
                data = self.source.readframes(frame_count)
                data, self.jaw = process_chunk(data, channels, self.options, self.mouth["range"])
                complete = len(data) < frame_count * channels * 2
                return data, self.api.paComplete if complete else self.api.paContinue
            except Exception as exc:
                self.error = exc
                return b"", self.api.paAbort

        self.stream = self.audio.open(format=self.api.paInt16, channels=channels, rate=rate,
                                      output=True, frames_per_buffer=max(1, rate // 50),
                                      stream_callback=callback)

    def active(self, now):
        if self.error:
            raise RuntimeError("Audio callback failed") from self.error
        if self.source is None:
            return False
        if self.dry_run:
            # Exercise the same envelope calculation without audio/GPIO dependencies.
            data = self.source.readframes(max(1, self.source.getframerate() // 50))
            _, self.jaw = process_chunk(data, self.source.getnchannels(), self.options, self.mouth["range"])
            return now < self.ends
        return self.stream is not None and self.stream.is_active()

    def stop(self):
        try:
            if self.stream is not None:
                try:
                    self.stream.stop_stream()
                finally:
                    self.stream.close()
        finally:
            self.stream = None
            if self.source is not None:
                self.source.close()
                self.source = None
            self.jaw = self.mouth["rest"]

    def close(self):
        try:
            self.stop()
        finally:
            if self.audio is not None:
                self.audio.terminate()
