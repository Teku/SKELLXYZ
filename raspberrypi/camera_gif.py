"""Bounded animated preview for camera diagnostics."""
from collections import deque
from pathlib import Path
import os


class GifPreview:
    def __init__(self, path):
        from PIL import Image
        self.Image = Image
        self.path = Path(path)
        self.frames = deque(maxlen=60)
        self.next_frame = 0

    def add(self, rgb, now):
        if now < self.next_frame:
            return
        frame = self.Image.fromarray(rgb).resize((320, 240)).convert("P", palette=self.Image.ADAPTIVE, colors=128)
        self.frames.append((now, frame))
        self.next_frame = now + 0.5

    def save(self):
        if not self.frames:
            return False
        samples = list(self.frames)
        durations = [max(20, round((b[0] - a[0]) * 1000)) for a, b in zip(samples, samples[1:])]
        durations.append(durations[-1] if durations else 500)
        temporary = self.path.with_suffix(".tmp")
        samples[0][1].save(str(temporary), format="GIF", save_all=True,
                           append_images=[f for _, f in samples[1:]], duration=durations,
                           loop=0, optimize=False)
        os.replace(temporary, self.path)
        return True
