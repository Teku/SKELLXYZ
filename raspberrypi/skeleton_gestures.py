"""Small silent expressions expressed as calibrated head poses."""
from skeleton_motion import HEAD

NAMES = ("look", "yes", "no", "happy")


def sequence(name, configs, direction=1):
    """Return (pose, seconds) steps; all expressions end at calibrated rest."""
    if name not in NAMES:
        raise ValueError("Unknown gesture: " + name)

    def pose(**fractions):
        result = {}
        for axis in HEAD:
            cfg = configs[axis]
            amount = fractions.get(axis, 0) * direction
            endpoint = cfg["range"][1 if amount >= 0 else 0]
            result[axis] = cfg["rest"] + abs(amount) * (endpoint - cfg["rest"])
        return result

    if name == "look":
        steps = [(pose(Base=0.35, Pitch=0.1), 2.0),
                 (pose(Base=0.35, Pitch=0.1), 0.8),
                 (pose(Base=-0.3, Pitch=-0.1), 2.5),
                 (pose(Base=-0.3, Pitch=-0.1), 0.8)]
    else:
        axis = {"yes": "Pitch", "no": "Base", "happy": "Tilt"}[name]
        amount = 0.25 if name == "yes" else 0.3
        steps = [(pose(**{axis: amount * sign}), 1.0) for sign in (1, -1, 1, -1)]
    return steps + [(pose(), 1.5)]
