# Local skeleton dashboard

The dashboard controls one unified runner on the Pi. It shows process status,
commanded activity, recent logs and exit codes. It provides show/head-only start,
graceful stop, individual expressions, single-recording playback, saying playlist,
software voice/music volume, event pause, head speed, silent-event probability,
and hold/release at rest. It does not measure physical servo position or heat.

Settings save to gitignored `raspberrypi/dashboard-settings.json`. The managed
runner reloads them once per second. Volume applies to subsequent audio buffers;
playlist changes affect upcoming recordings; speed applies to new trajectories;
an already scheduled pause completes with its previous deadline. The software
volume does not change FPP's system mixer. Jaw animation follows the original
audio level so reducing volume does not reduce mouth motion.

Music is selected from `vendor/ChatterPi/src/ambient/*.wav` and plays between
sayings and during silent gestures, restarting when necessary. It stops during
speech and never drives the jaw. This first version does not mix music under
speech, crossfade, or resume the music at its previous position. Head-only and
single-action modes never initialize audio. Both voice and music require
mono/stereo 16-bit PCM WAV files. Add recordings to `vocals/` and music to
`ambient/`, then reload the dashboard to refresh the catalog. No file upload
endpoint is exposed. Empty playlist uses the existing default v01–v10 sequence.

## First run on the Pi

Pull the branch. Stop the old service and its detached screen sessions as in
`unified-trial.md`, and stop any manually launched controller. Keep pigpiod
running. The new runner uses a Linux file lock to reject a second unified
runner, and checks for older Python servo/ChatterPi processes at startup.
Old scripts cannot honor this new lock: do not launch them while the dashboard
is controlling hardware. The dashboard cannot monitor/control an independently
started runner or the legacy service. It reports only its own child process.

From the repo root:

```bash
python3 raspberrypi/skeleton_dashboard.py --host 0.0.0.0 --port 8080
```

Enter a dashboard password (at least 8 ASCII characters). Open
`http://RP3:8080` from a browser on the same network and enter that password.
If RP3 does not resolve, use the Pi's address, not the RTSP camera's address.
The web server uses Python's standard library; the runner uses its existing
GPIO/audio dependencies. The server starts stopped: click Start show explicitly.

HTTP is for a trusted LAN only; do not forward this port to the Internet. For
an encrypted connection, bind the default localhost address and use a KiTTY/SSH
local tunnel from port 8080 to localhost:8080, then browse http://localhost:8080.
Passwords are held only in memory in the server and browser tab. API endpoints
require bearer authentication; the unauthenticated page contains no status data.
For unattended startup supply `SKELL_DASHBOARD_PASSWORD` through a protected
service environment file. No password is stored in this repository.

## Simulation

```bash
python3 raspberrypi/skeleton_dashboard.py --dry-run
```

Open http://localhost:8080 on the same computer. The page displays Simulation.
All gestures and audio are simulated; no GPIO or audio devices open. Stop is
graceful on Linux. Windows simulation terminates the child process directly.

Ctrl+C on the dashboard stops its runner and waits for cleanup. Do not force-kill
the runner: that skips servo release. Timing is cooperative; shutdown can take
several seconds. The existing boot launcher is unchanged; test the dashboard
manually before choosing a systemd migration. RTSP monitoring and automatic
vision-driven behavior remain separate from this dashboard.
