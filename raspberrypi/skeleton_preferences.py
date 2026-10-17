"""Validated dashboard settings, shared with the runner."""
import json
import math
import os
from pathlib import Path
from skeleton_speech import CHATTER, check_clip

PATH = Path(__file__).resolve().parent / "dashboard-settings.json"
DEFAULTS = dict(volume=75, music_volume=25, pause=15, speed=10,
                silent_chance=0.35, clips=[], music="", hold_idle=False)


def catalog():
    return {kind: sorted(p.name for p in (CHATTER / folder).glob("*.wav")
                         if not p.name.endswith(".original.wav"))
            for kind, folder in (("clips", "vocals"), ("music", "ambient"))}


def validate(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unknown settings")
    result = dict(DEFAULTS, **value)
    for name, low, high in (("volume", 0, 100), ("music_volume", 0, 100),
                            ("pause", 0.5, 300), ("speed", 1, 30), ("silent_chance", 0, 1)):
        number = result[name]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError("Invalid " + name)
    if not isinstance(result["hold_idle"], bool):
        raise ValueError("hold_idle must be true or false")
    available = catalog()
    if not isinstance(result["clips"], list) or any(not isinstance(c, str) or c not in available["clips"] for c in result["clips"]):
        raise ValueError("Choose recordings from the catalog")
    if len(result["clips"]) != len(set(result["clips"])):
        raise ValueError("Duplicate recordings")
    if not isinstance(result["music"], str) or result["music"] and result["music"] not in available["music"]:
        raise ValueError("Choose music from the catalog")
    return result


def read(path=PATH):
    return validate(json.loads(Path(path).read_text()) if Path(path).exists() else {})


def save(value, path=PATH):
    result = validate(value)
    for clip in result["clips"]:
        check_clip(CHATTER / "vocals" / clip)
    if result["music"]:
        check_clip(CHATTER / "ambient" / result["music"])
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(temporary, path)
    return result
