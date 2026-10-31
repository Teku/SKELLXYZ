import sys
import struct
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'raspberrypi'))
from skeleton_audio_mix import ShowAudio
from skeleton_speech import settings
from servo_config import get_servo_configs


class MixerTests(unittest.TestCase):
    def test_one_output_stream_survives_multiple_voice_clips_and_closes_cleanly(self):
        streams = []
        class Stream:
            running = True
            closed = False
            def is_active(self): return self.running
            def stop_stream(self): self.running = False
            def close(self): self.closed = True
        class Audio:
            terminated = False
            def open(self, **kwargs):
                stream = Stream()
                stream.callback = kwargs['stream_callback']
                streams.append(stream)
                return stream
            def terminate(self): self.terminated = True
        audio = Audio()
        api = SimpleNamespace(PyAudio=lambda: audio, paInt16=8, paContinue=0, paAbort=2)
        with tempfile.TemporaryDirectory() as folder:
            music = self.clip(folder, 'music.wav', [1000]*10000)
            voice = self.clip(folder, 'voice.wav', [5000]*1000)
            with patch.dict(sys.modules, pyaudio=api), patch('skeleton_speech.initialize', return_value=audio):
                player = ShowAudio(settings(), get_servo_configs()['Mouth'])
                try:
                    player.set_background(music, 25)
                    for now in (0, 1):
                        player.start(voice, now)
                        _, status = streams[0].callback(None, 1000, None, 0)
                        self.assertEqual(status, api.paContinue)
                        player.stop()
                    self.assertEqual(len(streams), 1)
                    self.assertEqual(player.background.tell(), 2000)
                    self.assertFalse(streams[0].closed)
                    player.background.close()  # Callback failures must surface.
                    _, status = streams[0].callback(None, 1000, None, 0)
                    self.assertEqual(status, api.paAbort)
                    with self.assertRaisesRegex(RuntimeError, 'callback failed'):
                        player.set_background(music, 25)
                finally:
                    player.close()
                self.assertTrue(streams[0].closed)
                self.assertTrue(audio.terminated)

    def clip(self, folder, name, samples, channels=1):
        path = Path(folder) / name
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(channels)
            out.setsampwidth(2)
            out.setframerate(44100)
            out.writeframes(struct.pack('<'+'h'*len(samples), *samples))
        return path

    def samples(self, data):
        result = array('h'); result.frombytes(data)
        if sys.byteorder != 'little': result.byteswap()
        return result

    def test_music_cursor_continues_through_voice_duck_stop_and_loop(self):
        with tempfile.TemporaryDirectory() as folder:
            music = self.clip(folder, 'music.wav', [1000]*10000)
            voice = self.clip(folder, 'voice.wav', [5000]*8820)
            player = ShowAudio(settings(), get_servo_configs()['Mouth'], dry_run=True)
            try:
                player.set_background(music, 100)
                self.assertEqual(self.samples(player.render(4410))[-1], 1000)
                source = player.background
                self.assertEqual(source.tell(), 4410)
                player.start(voice, 0)
                mixed = self.samples(player.render(4410))
                self.assertEqual(mixed[-1], 5200)  # Voice + music at 20%.
                self.assertEqual(player.jaw, -9)
                self.assertEqual(source.tell(), 8820)
                player.set_background(music, 100)  # Polling must not restart it.
                self.assertIs(player.background, source)
                self.assertEqual(source.tell(), 8820)
                player.stop()  # Voice ends, music continues through its EOF.
                quiet = self.samples(player.render(4410))
                self.assertEqual(source.tell(), 3230)
                self.assertEqual(quiet[-1], 450)  # Gradual recovery, not a jump.
                self.assertEqual(player.jaw, get_servo_configs()['Mouth']['rest'])
                player.render(4410*4)
                self.assertEqual(player.duck, 1.)
                self.assertEqual(self.samples(player.render(20))[-1], 1000)
                player.set_background(None, 100)
                self.assertIsNone(player.background)
                self.assertEqual(set(self.samples(player.render(100))), {0})
            finally:
                player.close()

    def test_voice_eof_does_not_stop_music_and_mix_saturates(self):
        with tempfile.TemporaryDirectory() as folder:
            music = self.clip(folder, 'music.wav', [30000,30000]*100, 2)
            voice = self.clip(folder, 'voice.wav', [30000]*10)
            player = ShowAudio(settings(), get_servo_configs()['Mouth'], dry_run=True)
            try:
                player.set_background(music, 100)
                player.start(voice, 0)
                mixed = self.samples(player.render(20))
                self.assertEqual(mixed[0], 32767)
                player.render(20)
                self.assertIsNone(player.source)
                self.assertIsNotNone(player.background)
                self.assertEqual(player.jaw, player.mouth['rest'])
            finally:
                player.close()
