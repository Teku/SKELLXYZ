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

Pull `main`. Stop the old service with `sudo systemctl stop skeleton.service`
(this also stops its screen sessions on this Pi), and stop any manually launched controller. Keep pigpiod
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
`http://RP3:8080` from a browser on the same network and sign in as `admin` with that password.
If RP3 does not resolve, use the Pi's address, not the RTSP camera's address.
The web server uses Python's standard library; the runner uses its existing
GPIO/audio dependencies. The server starts stopped: click Start show explicitly.

HTTP is for a trusted LAN only; do not forward this port to the Internet. For
an encrypted connection, bind the default localhost address and use a KiTTY/SSH
local tunnel from port 8080 to localhost:8080, then browse http://localhost:8080.
Interactive passwords are held only in memory in the server and browser tab. API endpoints
require HTTP Basic authentication with username `admin`; the unauthenticated page contains no status data.
For unattended startup supply `SKELL_DASHBOARD_PASSWORD` through a protected
service environment file. No password is stored in this repository.

## Run at boot with systemd

Stop any manually running dashboard with Ctrl+C, then run on the Pi:

```bash
cd ~/SKELLXYZ
git pull
sudo bash install_dashboard_service.sh
```

The installer prompts for a password on first installation and saves it in
`/etc/skeleton-dashboard.env`, readable only by root. Reinstalling preserves it.
It uses the sudo caller as the service user (normally `fpp`; direct root execution
also defaults to `fpp`) and the current checkout path. It requires the existing
`pigpiod.service` and starts that daemon before the dashboard.

The installer disables and stops the old `skeleton.service`, then enables and
starts `skeleton-dashboard.service`. No separate screen cleanup is needed on
this Pi. The units conflict so systemd will not run both at once.
Open `http://RP3:8080` and sign in as `admin` with your password. The login form
includes username/password autocomplete fields for password managers such as LastPass. After boot or restart, the dashboard
starts idle: click **Start show** to begin. Saved settings persist across restarts.

```bash
systemctl status skeleton-dashboard.service
journalctl -u skeleton-dashboard.service -n 50 --no-pager
sudo systemctl restart skeleton-dashboard.service
sudo systemctl stop skeleton-dashboard.service
```

Stopping the service asks the dashboard to stop its runner and release the servos.
Systemd allows 60 seconds for cleanup before forcibly terminating remaining
processes. An unexpected dashboard failure restarts the dashboard in the idle state.
For future code updates, run `git pull` and restart the dashboard service. Rerun
the installer if the service template changes. To change the password, use
`sudoedit /etc/skeleton-dashboard.env` and restart the service.

To return to the old boot launcher:

```bash
sudo systemctl disable --now skeleton-dashboard.service
sudo systemctl enable --now skeleton.service
```

## Simulation

```bash
python3 raspberrypi/skeleton_dashboard.py --dry-run
```

Open http://localhost:8080 on the same computer. The page displays Simulation.
All gestures and audio are simulated; no GPIO or audio devices open. Stop is
graceful on Linux. Windows simulation terminates the child process directly.

Ctrl+C on the dashboard stops its runner and waits for cleanup. Do not force-kill
the runner: that skips servo release. Timing is cooperative; shutdown can take
several seconds. The service installer above replaces the old boot startup when
you run it. RTSP monitoring and automatic
vision-driven behavior remain separate from this dashboard.
