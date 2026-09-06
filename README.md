# SkellXYZ

Control software for a 3-axis Home Depot skeleton: head servos (Base, Pitch, Tilt) plus jaw animation via [ChatterPi](raspberrypi/vendor/ChatterPi/). Designed to run on a Raspberry Pi with [Falcon Player (FPP)](https://github.com/FalconChristmas/fpp).

## Repository layout

```
SKELLXYZ/
├── start_skeleton.sh          # Boot launcher (ChatterPi + head animation)
├── skeleton.service.example   # systemd unit template for the Pi
├── README.md
└── raspberrypi/
    ├── servo_run.py           # Head movement animation (live at boot)
    ├── servo_test.py          # Interactive limit tuning / debugging
    ├── servo_server.py        # UDP control (port 8888) — not used at boot
    ├── servo_hold.py          # Utility: hold servos at mid position
    ├── servo_reset.py         # Utility: move to mid, then detach
    ├── servo_stop.py          # Utility: detach all servos
    ├── gpio_notes.txt         # Pin wiring + tuning notes
    ├── review/                # Archived copies from outside the repo
    └── vendor/ChatterPi/      # Jaw animation (audio-driven)
        └── src/
            ├── main.py
            └── config.ini     # Jaw servo limits and audio/prop settings
```

## Boot setup

On the Pi, `skeleton.service` starts `start_skeleton.sh`, which:

1. Ensures `pigpiod` is running
2. Launches **ChatterPi** in a `screen` session named `chatter`
3. Waits 30 seconds, then launches **`servo_run.py`** in a `screen` session named `servo_run`

### First-time install (or after moving the script into the repo)

```bash
# On the Pi, from the repo root
chmod +x start_skeleton.sh install_skeleton_service.sh
./install_skeleton_service.sh
sudo systemctl start skeleton.service
```

The install script writes `/etc/systemd/system/skeleton.service` with the correct `ExecStart` path for this repo clone.

Manual install is still possible — see `skeleton.service.example`.

### Verify what is running

```bash
systemctl status skeleton.service
screen -ls
screen -r chatter    # Ctrl+A, D to detach
screen -r servo_run
```

### Migrate from `/home/fpp/start_skeleton.sh`

```bash
./install_skeleton_service.sh
sudo systemctl restart skeleton.service
mv /home/fpp/start_skeleton.sh /home/fpp/start_skeleton.sh.bak
```

## Configuration

All four servos (Base, Pitch, Tilt, Mouth) share one per-machine limits file:

**`raspberrypi/servo_limits.cfg`** — gitignored, like a `.env` file.

```bash
cd raspberrypi
cp servo_limits.cfg.example servo_limits.cfg   # first-time setup on the Pi
```

| File | Tracked? | Purpose |
|------|----------|---------|
| `servo_limits.cfg.example` | Yes | Template with default tuned values |
| `servo_limits.cfg` | **No** | Your skeleton's min/max/rest for all servos |
| `servo_config.py` | Yes | Shared loader |

**Who reads/writes it:**

| Script | Servos | Reads | Writes |
|--------|--------|-------|--------|
| `servo_run.py` | Base, Pitch, Tilt (head) | Yes | No |
| `servo_test.py` | All four | Yes | Yes — via "Debug Servo Limits" |
| `servo_server.py` | All four | Yes | No |
| ChatterPi `config.py` | Mouth (jaw) | Yes | No |

ChatterPi `config.ini` is now **only** for audio, triggers, and controller settings. Jaw angles come from `Mouth_*` in `servo_limits.cfg` — tune the mouth once with `servo_test.py` or edit that file directly. Restart the `chatter` screen session after changing mouth limits.

```bash
screen -r chatter   # Ctrl+C to stop, then:
cd ~/SKELLXYZ/raspberrypi/vendor/ChatterPi/src && python3 main.py
# Or: sudo systemctl restart skeleton.service
```

If `servo_limits.cfg` is missing, scripts fall back to `servo_limits.cfg.example`, then built-in defaults.

**Migrate from an old home-directory copy:**

```bash
cp ~/servo_limits.cfg ~/SKELLXYZ/raspberrypi/servo_limits.cfg
# Add rest lines if missing — see servo_limits.cfg.example
```

GPIO pins and physical travel are defined in `servo_config.py` (same for every machine with this wiring).

Reference archive: `raspberrypi/review/external-files/servo_limits.cfg`

## Manual usage

From `raspberrypi/` on the Pi:

```bash
# Tune or debug servo limits interactively
python3 servo_test.py

# Run head animation manually (same as boot)
python3 servo_run.py

# UDP server for external control (not started at boot)
python3 servo_server.py
```

Requirements:

```bash
sudo apt-get update
sudo apt-get install python3-gpiozero python3-pigpio screen
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

## Cleanup history

This repo accumulated duplicate scripts and untracked config over time. Below is what was going on and what was done about it.

### The problem

- Scripts were copied to `/home/fpp/` (`servo_test.py`, `servo_server.py`, etc.) **and** maintained under `~/SKELLXYZ/raspberrypi/`
- `servo_limits.cfg` was written to `$HOME` by `servo_test.py` but **never read back** by running services
- The same limits were manually copied into `servo_run.py` and ChatterPi `config.ini`
- `start_skeleton.sh` lived outside the repo while systemd pointed at it
- Old and new versions of scripts diverged (different angle math, menus, mouth handling)

### What actually runs at boot

Only paths under this repo, launched by `start_skeleton.sh` via `skeleton.service`:

- `raspberrypi/vendor/ChatterPi/src/main.py`
- `raspberrypi/servo_run.py`

Home-directory `servo_*.py` copies and `~/servo_limits.cfg` were **not** in the boot chain.

### Cleanup steps

**Done**

- [x] Archive external files → `raspberrypi/review/external-files/`
- [x] Move canonical boot script → `start_skeleton.sh` (repo root)
- [x] Document layout, config sources, and boot setup (this README)
- [x] Add `skeleton.service.example` for reproducible systemd setup

**On the Pi (when ready)**

- [ ] Point `skeleton.service` at repo-root `start_skeleton.sh` (see [Migrate](#migrate-from-homefppstart_skeletonsh))
- [ ] Confirm boot: `systemctl restart skeleton.service && screen -ls`
- [ ] Archive or remove orphaned home copies:
  ```bash
  mkdir -p ~/servo_archive
  mv ~/servo_*.py ~/run_skelly.sh ~/servo_limits.cfg ~/servo_archive/ 2>/dev/null
  ```
- [ ] Copy limits to repo: `cp ~/servo_limits.cfg ~/SKELLXYZ/raspberrypi/servo_limits.cfg`
- [ ] Or from template: `cp raspberrypi/servo_limits.cfg.example raspberrypi/servo_limits.cfg`

**Future (optional)**

- [ ] Remove stale duplicate configs inside `vendor/ChatterPi/src/` (`oldconfig.ini`, `difconfig.ini`, `backup/`)
- [ ] Consolidate or delete unused scripts (`servo_server.py` if UDP control is not needed)

### Finding other startup hooks (FPP / Linux)

If something else starts skeleton-related code:

```bash
systemctl list-unit-files | grep -i skeleton
sudo crontab -u fpp -l
cat /home/fpp/media/scripts/UserCallbackHook.sh 2>/dev/null
grep -r skeleton /etc/systemd/system/ 2>/dev/null
```

## Safety

- Stay within tuned `range` limits in `servo_run.py` to avoid mechanical damage
- GPIO 18 is shared: mouth is handled by ChatterPi; head scripts do not drive it at boot
- Ensure the power supply can handle all servos under load

## Attribution

Inspired by the [3-Axis Skull Mod for 12ft Skeleton](https://hackaday.io/project/181103-3-axis-skull-mod-for-12ft-skeleton) by Steven Long.

ChatterPi jaw animation: see `raspberrypi/vendor/ChatterPi/README.md`.
