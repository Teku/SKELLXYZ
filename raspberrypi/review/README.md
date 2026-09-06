# Review / archive

Snapshots of files that lived **outside the repo** on the FPP Pi (`/home/fpp/`), collected during a 2026 cleanup.

These are kept for reference only. **Do not run scripts from this folder.**

## Contents

| File | Origin | Notes |
|------|--------|-------|
| `external-files/start_skeleton.sh` | `/home/fpp/start_skeleton.sh` | Superseded by `/start_skeleton.sh` at repo root |
| `external-files/run_skelly.sh` | `/home/fpp/run_skelly.sh` | Old manual launcher for home-copy `servo_test.py` |
| `external-files/servo_*.py` | `/home/fpp/servo_*.py` | Duplicates; boot never used these |
| `external-files/servo_limits.cfg` | `/home/fpp/servo_limits.cfg` | Tuned limits; values already copied into live scripts |
| `external-files/gpio_notes.txt` | `/home/fpp/gpio_notes.txt` | Pin notes only; repo `raspberrypi/gpio_notes.txt` is more complete |

## Canonical locations now

See the root [README.md](../../README.md) for the current layout and config sources of truth.
