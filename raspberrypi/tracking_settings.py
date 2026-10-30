"""Validated camera tracking and sidewalk geometry settings."""
import json
import math
import os
from pathlib import Path

DEFAULTS = dict(geometry=True, head_height=12., sidewalk_distance=14., aim_height=5.,
                hfov=60., camera_pitch=0., camera_yaw=0., rest_yaw=0., rest_pitch=0.,
                range_fraction=1., speed=10., acceleration=20.,
                roi_left=0., roi_top=0., roi_right=100., roi_bottom=100.,
                min_area=.3, dark_threshold=25.)
LIMITS = dict(head_height=(1,30), sidewalk_distance=(2,100), aim_height=(0,10),
              hfov=(10,150), camera_pitch=(-60,60), camera_yaw=(-60,60),
              rest_yaw=(-90,90), rest_pitch=(-90,90), range_fraction=(.1,1),
              speed=(1,30), acceleration=(1,60), roi_left=(0,99), roi_top=(0,99),
              roi_right=(1,100), roi_bottom=(1,100), min_area=(.05,10), dark_threshold=(0,255))


def validate(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError("Unknown tracking settings")
    result = dict(DEFAULTS, **values)
    if type(result["geometry"]) is not bool:
        raise ValueError("Geometry must be true or false")
    for key, (low, high) in LIMITS.items():
        value = result[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("Invalid tracking setting: " + key)
    if result["roi_right"] - result["roi_left"] < 5 or result["roi_bottom"] - result["roi_top"] < 5:
        raise ValueError("Detection region must span at least 5 percent in each direction")
    return result


def read(path):
    try:
        return validate(json.loads(Path(path).read_text()))
    except FileNotFoundError:
        return dict(DEFAULTS)


def save(path, values):
    path = Path(path)
    result = validate(values)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    os.replace(temporary, path)
    return result
