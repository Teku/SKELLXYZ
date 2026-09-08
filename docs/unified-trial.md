# Unified speech and head movement trial

This manual runner implements coordinated recorded speech/jaw animation,
simultaneous eased head gestures, and occasional silent expressions. It does not
implement camera tracking or attract scheduling. Boot behavior is unchanged.

## Behavior

- One process owns Base, Pitch, Tilt, and (when enabled) Mouth.
- Head axes share a quintic trajectory with zero endpoint velocity and
  acceleration. Peak speed defaults to 18 degrees/second; gestures use the inner
  35% of the calibrated range around rest.
- Head gestures run during recordings. At the end of speech, the current gesture
  finishes and the head eases to rest before the next clip.
- At each new event, there is a 35% chance of a silent expression: looking
  around, nodding yes (Pitch), shaking no (Base), or playful alternating tilts
  (Tilt). There are never two silent events in a row. Each expression ends at
  rest and gets the normal pause before the next event. The jaw stays released.
  All expression poses use at most 35% of calibrated travel on either side of
  rest and the same speed-limited easing as speech gestures.
  Set `--silent-chance 0` for the previous speech-only behavior, or
  `--silent-chance 1` to alternate silent expressions and recordings.
  `--once` always plays one recording, regardless of this setting.
- Existing `v01.wav` through `v10.wav` files are cycled, excluding `.original.wav`
  copies. `--once` plays just one recording. The default inter-clip pause is five
  seconds, in addition to the return-to-rest motion. The pause also applies
  after silent expressions.
- Jaw thresholds, enabled setting, and left-channel duplication come from the
  existing ChatterPi `config.ini`; all angle limits come from `servo_config.py`.
  ChatterPi's existing direction is preserved: quiet=max, loud=min. Between
  clips, the jaw PWM signal is released, matching the original player.
  `Mouth_rest` is not assumed to be the physically closed position.
- After the head reaches rest, it settles for 0.5 seconds, then releases PWM
  during the remaining pause. Use `--hold-idle` if the mechanism needs holding
  torque to prevent drooping. This flag applies to the head, not the jaw.
  Releasing PWM does not switch off servo supply power; some digital servos
  continue holding without a signal. Position is not sensed after release,
  so a mechanism that drifts may move abruptly when reactivated.
- This runner supports recorded mono/stereo 16-bit PCM WAVs and ChatterPi styles
  0 and 1. Unsupported source/style settings fail before GPIO initialization.
  Ambient tracks and the old trigger loop are not used by this trial.
- Ctrl+C/SIGTERM stops audio, finishes the current head trajectory, eases home,
  and explicitly detaches all owned servos before closing the GPIO connection.
  Shutdown therefore takes a few seconds; holding noise may continue during
  the return-to-rest movement. Wait for `Stopped; servo outputs released`.
  Device failures
  still close resources, but cannot guarantee a physical return to rest.

Stopping the old `skeleton.service` does not necessarily stop a manually launched
unified runner. Send Ctrl+C in that runner's terminal or SIGTERM to its process.
Force-killing it (SIGKILL) bypasses Python cleanup and cannot perform detachment.

Servo position is not sensed. Initial activation commands configured rest;
smoothness guarantees apply to subsequent commanded head trajectories, not
the unknown physical position at startup. The jaw keeps its existing stepped
audio response. Verify travel and speed on the actual mechanism.

## Local simulation

From the repository root (no GPIO/PyAudio packages or hardware required):

```bash
python3 -B -m unittest discover -s tests -v
python3 -B raspberrypi/skeleton_run.py --dry-run --seconds 10 --seed 1
```

Dry-run prints gestures and exercises WAV envelope processing in real time;
it does not play sound or move servos. `--seconds` excludes shutdown easing time.

## Manual Pi trial

Use this branch on the Pi with your existing calibrated
`raspberrypi/servo_limits.cfg`. The same fallback to example limits applies if
that file is absent; verify the actual machine's calibration before movement.
Hardware dependencies are `gpiozero`, `pigpio`, and `pyaudio`, normally provided
by `python3-gpiozero`, `python3-pigpio`, and `python3-pyaudio` on the Pi image.

The current oneshot service does not explicitly stop its detached screen
sessions. Stop the service and both existing sessions before the unified runner
owns the same GPIO pins. Run these commands on the Pi from the repo root:

```bash
sudo systemctl stop skeleton.service
screen -S chatter -X quit
screen -S servo_run -X quit
screen -ls
pgrep -af 'python3.*(main.py|servo_run.py|skeleton_run.py)'
```

Proceed once the old skeleton processes have exited. Keep `pigpiod` running.
If either old session is still present, inspect and stop it before continuing.

```bash
python3 raspberrypi/skeleton_run.py --once --speed 10 --seed 1
```

Check that the jaw follows the recording, all three head axes move together,
motion remains comfortably inside physical limits, and playback stays clear.
The lower trial speed gives a first look at the mechanism. Then try multiple
clips and Ctrl+C:

```bash
python3 raspberrypi/skeleton_run.py --speed 10 --pause 5
```

After the unified runner has exited, restore the existing boot-managed behavior:

```bash
sudo systemctl start skeleton.service
screen -ls
```

No Pi hardware validation or service migration to the new runner has been
performed from the development workstation.
