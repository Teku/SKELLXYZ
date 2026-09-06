"""Load and save per-machine servo limits from servo_limits.cfg."""

from pathlib import Path

RASPBERRYPI_DIR = Path(__file__).parent
LIMITS_PATH = RASPBERRYPI_DIR / "servo_limits.cfg"
EXAMPLE_PATH = RASPBERRYPI_DIR / "servo_limits.cfg.example"

# GPIO wiring and physical travel — same for every machine with this build.
SERVO_HARDWARE = {
    "Base": {"pin": 23, "travel": 190},
    "Pitch": {"pin": 24, "travel": 190},
    "Tilt": {"pin": 25, "travel": 190},
    "Mouth": {"pin": 18, "travel": 180},
}

# Fallback when no cfg file exists yet (matches servo_limits.cfg.example).
DEFAULT_LIMITS = {
    "Base": {"min": -36, "max": 36, "rest": 0},
    "Pitch": {"min": -24, "max": 19, "rest": -0.13},
    "Tilt": {"min": -19, "max": 19, "rest": 0},
    "Mouth": {"min": -9, "max": 72, "rest": 0},
}


def _parse_cfg(path):
    values = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def load_limits(path=None):
    """Return {servo_name: {min, max, rest}} from cfg, example, or defaults."""
    path = Path(path) if path else LIMITS_PATH
    raw = {}

    if path.exists():
        raw = _parse_cfg(path)
    elif EXAMPLE_PATH.exists():
        raw = _parse_cfg(EXAMPLE_PATH)

    limits = {}
    for name, defaults in DEFAULT_LIMITS.items():
        entry = dict(defaults)
        prefix = f"{name}_"
        for suffix in ("min", "max", "rest"):
            key = f"{prefix}{suffix}"
            if key in raw:
                entry[suffix] = float(raw[key])
        limits[name] = entry
    return limits


def save_servo_limits(servo_name, min_limit, max_limit, path=None):
    """Update min/max for one servo and write servo_limits.cfg."""
    path = Path(path) if path else LIMITS_PATH
    limits = load_limits(path if path.exists() else None)

    limits[servo_name]["min"] = min_limit
    limits[servo_name]["max"] = max_limit

    _write_limits(limits, path)
    print(f"\nConfig saved to {path}")


def _write_limits(limits, path):
    with open(path, "w") as f:
        f.write("# Per-machine servo limits. Copy from servo_limits.cfg.example to start.\n")
        f.write("# Created/updated by servo_test.py or edit manually.\n\n")
        for name in SERVO_HARDWARE:
            if name not in limits:
                continue
            entry = limits[name]
            f.write(f"{name}_min:{_format_value(entry['min'])}\n")
            f.write(f"{name}_max:{_format_value(entry['max'])}\n")
            f.write(f"{name}_rest:{_format_value(entry['rest'])}\n")


def _format_value(value):
    return int(value) if value == int(value) else value


def get_mouth_config():
    """Mouth/jaw settings for ChatterPi (same source as head servos)."""
    limits = load_limits()
    hw = SERVO_HARDWARE["Mouth"]
    mouth = limits["Mouth"]
    return {
        "pin": hw["pin"],
        "travel": hw["travel"],
        "min_angle": mouth["min"],
        "max_angle": mouth["max"],
        "rest": mouth["rest"],
    }


def get_servo_configs(names=None):
    """Build {name: {pin, travel, range, rest}} for servo scripts."""
    limits = load_limits()
    if names is None:
        names = SERVO_HARDWARE.keys()

    configs = {}
    for name in names:
        if name not in SERVO_HARDWARE:
            raise KeyError(f"Unknown servo: {name}")
        hw = SERVO_HARDWARE[name]
        lim = limits[name]
        configs[name] = {
            "pin": hw["pin"],
            "travel": hw["travel"],
            "range": (lim["min"], lim["max"]),
            "rest": lim["rest"],
        }
    return configs
