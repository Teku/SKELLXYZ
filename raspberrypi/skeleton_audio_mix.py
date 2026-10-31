"""Continuous stereo show output: looping music ducked beneath recorded voice."""
from array import array
import sys
import threading
import wave
from skeleton_speech import Speech, check_clip, process_chunk


class ShowAudio(Speech):
    RATE = 44100

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = threading.RLock()
        self.background = None
        self.background_path = None
        self.music_volume = 25
        self.duck = 1.

    def _open_clip(self, path):
        check_clip(path)
        source = wave.open(str(path), 'rb')
        if not self.dry_run and source.getframerate() != self.RATE:
            source.close()
            raise ValueError('Show audio requires 44100 Hz PCM WAV: ' + str(path))
        return source

    def _ensure_stream(self):
        if self.dry_run or self.stream is not None:
            return
        def callback(in_data, frame_count, time_info, status):
            try:
                return self.render(frame_count), self.api.paContinue
            except Exception as exc:
                self.error = exc
                return b'', self.api.paAbort
        self.stream = self.audio.open(format=self.api.paInt16, channels=2, rate=self.RATE,
                                      output=True, frames_per_buffer=self.RATE // 50,
                                      stream_callback=callback)

    def set_background(self, path, volume):
        if self.error:
            raise RuntimeError('Audio mixer callback failed') from self.error
        if self.stream is not None and not self.stream.is_active():
            raise RuntimeError('Show audio output stopped unexpectedly')
        path = str(path) if path else None
        with self.lock:
            self.music_volume = volume
            if path == self.background_path:
                return
            source = self._open_clip(path) if path else None
            if self.background is not None:
                self.background.close()
            self.background, self.background_path = source, path
        if path:
            self._ensure_stream()

    def start(self, path, now):
        source = self._open_clip(path)
        with self.lock:
            if self.source is not None:
                self.source.close()
            self.source = source
            self.ends = now + source.getnframes() / source.getframerate()
            self.error = None
        self._ensure_stream()

    @staticmethod
    def _stereo(data, channels, frames):
        samples = array('h')
        samples.frombytes(data)
        if sys.byteorder != 'little':
            samples.byteswap()
        if channels == 1:
            samples = array('h', (v for sample in samples for v in (sample, sample)))
        samples.extend([0] * (frames * 2 - len(samples)))
        return samples

    def render(self, frames):
        with self.lock:
            voice = array('h', [0]) * (frames * 2)
            speaking = False
            if self.source is not None:
                channels = self.source.getnchannels()
                data = self.source.readframes(frames)
                speaking = bool(data)
                if data:
                    data, self.jaw = process_chunk(data, channels, self.options, self.mouth['range'])
                    voice = self._stereo(data, channels, frames)
                else:
                    self.source.close()
                    self.source = None
                    self.jaw = self.mouth['rest']
            music = array('h', [0]) * (frames * 2)
            if self.background is not None:
                channels = self.background.getnchannels()
                chunks, remaining = [], frames
                while remaining:
                    data = self.background.readframes(remaining)
                    if not data:
                        self.background.rewind()
                        data = self.background.readframes(remaining)
                        if not data:
                            raise ValueError('Background recording contains no audio')
                    chunks.append(data)
                    remaining -= len(data) // (2 * channels)
                music = self._stereo(b''.join(chunks), channels, frames)
            # Fade the music gain, never the source position: ~50 ms attack,
            # ~400 ms release. Voice gain is independent of mouth thresholds.
            target = .2 if speaking else 1.
            seconds = frames / self.RATE
            change = max(-seconds / .05, min(seconds / .4, target - self.duck))
            start = self.duck
            self.duck += change
            vg, mg = self.volume / 100, self.music_volume / 100
            for i in range(frames * 2):
                gain = start + change * ((i // 2 + 1) / frames)
                voice[i] = max(-32768, min(32767, round(voice[i]*vg + music[i]*mg*gain)))
            if sys.byteorder != 'little':
                voice.byteswap()
            return voice.tobytes()

    def active(self, now):
        if self.error:
            raise RuntimeError('Audio mixer callback failed') from self.error
        if self.dry_run:
            with self.lock:
                if self.source is None:
                    return False
                data = self.source.readframes(max(1, self.source.getframerate() // 50))
                _, self.jaw = process_chunk(data, self.source.getnchannels(), self.options, self.mouth['range'])
                return now < self.ends
        with self.lock:
            active = self.source is not None
        if self.stream is not None and not self.stream.is_active():
            raise RuntimeError('Show audio output stopped unexpectedly')
        return active

    def stop(self):
        # End voice only. The output stream and background cursor keep running.
        with self.lock:
            if self.source is not None:
                self.source.close()
                self.source = None
            self.jaw = self.mouth['rest']

    def close(self):
        try:
            if self.stream is not None:
                try:
                    self.stream.stop_stream()
                finally:
                    self.stream.close()
        finally:
            self.stream = None
            try:
                self.stop()
                with self.lock:
                    if self.background is not None:
                        self.background.close()
                        self.background = None
            finally:
                if self.audio is not None:
                    self.audio.terminate()
