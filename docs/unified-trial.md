# Unified speech and head movement trial

This manual runner implements the first two development steps: coordinated
recorded speech/jaw animation and simultaneous eased head gestures. It does not
implement camera tracking or attract scheduling. Boot behavior is unchanged.

## Behavior

- One process owns Base, Pitch, Tilt, and (when enabled) Mouth.
- Head axes share a quintic trajectory with zero endpoint velocity and
  acceleration. Peak speed defaults to 18 degrees/second; gestures use the inner
  35% of the calibrated range around rest.
- Head gestures run during recordings. At the end of speech, the current gesture
  finishes and the head eases to rest before the next clip.
- Existing `v01.wav` through `v10.wav` files are cycled, excluding `.original.wav`
  copies. `--once` plays just one recording. The default inter-clip pause is five
  seconds, in addition to the return-to-rest motion.
- Jaw thresholds, enabled setting, and left-channel duplication come from the
  existing ChatterPi `config.ini`; all angle limits come from `servo_config.py`.
  ChatterPi's existing direction is preserved: quiet=max, loud=min. Between
  clips, the jaw uses configured rest.
- This runner supports recorded mono/stereo 16-bit PCM WAVs and ChatterPi styles
  0 and 1. Unsupported source/style settings fail before GPIO initialization.
  Ambient tracks and the old trigger loop are not used by this trial.
- Ctrl+C/SIGTERM stops audio, finishes the current head trajectory, eases home,
  and releases outputs. Shutdown therefore takes a few seconds. Device failures
  still close resources, but cannot guarantee a physical return to rest.

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
