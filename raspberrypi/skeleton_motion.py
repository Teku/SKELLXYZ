"""Hardware-independent, synchronized head trajectories."""
import math

HEAD = ("Base", "Pitch", "Tilt")


def validate_configs(configs):
    for name, config in configs.items():
        low, high = config["range"]
        rest, travel = config["rest"], config["travel"]
        if not all(math.isfinite(v) for v in (low, high, rest, travel)):
            raise ValueError("Non-finite servo configuration: " + name)
        if not (travel > 0 and -travel / 2 <= low <= rest <= high <= travel / 2):
            raise ValueError("Invalid limits/rest/travel: " + name)


class Motion:
    def __init__(self, configs, speed=18.0):
        validate_configs(configs)
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("Speed must be positive and finite")
        self.configs = configs
        self.speed = speed
        self.pose = {name: configs[name]["rest"] for name in HEAD}
        self.start = dict(self.pose)
        self.target = dict(self.pose)
        self.started = 0.0
        self.duration = 0.0

    def sample(self, now):
        u = min(1.0, max(0.0, (now - self.started) / self.duration)) if self.duration else 1.0
        # Quintic easing: zero velocity and acceleration at either endpoint.
        blend = u ** 3 * (10 + u * (-15 + 6 * u))
        self.pose = {n: self.start[n] + (self.target[n] - self.start[n]) * blend for n in HEAD}
        return dict(self.pose)

    def finished(self, now):
        return now >= self.started + self.duration

    def move(self, target, now, duration=1.5):
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Duration must be positive and finite")
        self.sample(now)
        self.start = dict(self.pose)
        for name in HEAD:
            value = target[name]
            if not math.isfinite(value):
                raise ValueError("Non-finite target")
            low, high = self.configs[name]["range"]
            self.target[name] = max(low, min(high, value))
        # Peak derivative of the quintic curve is 1.875.
        self.duration = max(duration, max(1.875 * abs(self.target[n] - self.start[n]) / self.speed for n in HEAD))
        self.started = now
