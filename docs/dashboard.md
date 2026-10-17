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
GPIO/audio dependencies. The show starts automatically using saved settings. Use `--start-stopped` to open
the dashboard without starting the show.

HTTP is for a trusted LAN only; do not forward this port to the Internet. For
an encrypted connection, bind the default localhost address and use a KiTTY/SSH
local tunnel from port 8080 to localhost:8080, then browse http://localhost:8080.
Interactive passwords are held only in memory in the server and browser tab. API endpoints
accept a remembered session or HTTP Basic authentication with username `admin`; the unauthenticated page contains no status data.
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
starts the show automatically using saved settings. Saved settings persist across restarts.

```bash
systemctl status skeleton-dashboard.service
journalctl -u skeleton-dashboard.service -n 50 --no-pager
sudo systemctl restart skeleton-dashboard.service
sudo systemctl stop skeleton-dashboard.service
```

Stopping the service asks the dashboard to stop its runner and release the servos.
Systemd allows 60 seconds for cleanup before forcibly terminating remaining
processes. An unexpected dashboard failure restarts the dashboard and starts the show again.
For future code updates, run `bash deploy.sh` from the repo root as your normal
Pi user (no sudo prefix). It runs `git pull`, refreshes the service unit, and
restarts the dashboard. The show starts automatically; a running camera test
stops. Existing password and settings are preserved. If pulling fails, the
script stops before restarting the service. To change the password, use
`sudoedit /etc/skeleton-dashboard.env` and restart the service.

To return to the old boot launcher:

```bash
sudo systemctl disable --now skeleton-dashboard.service
sudo systemctl enable --now skeleton.service
```

## Simulation

```bash
python3 raspberrypi/skeleton_dashboard.py --dry-run --start-stopped
```

Open http://localhost:8080 on the same computer. The page displays Simulation.
All gestures and audio are simulated; no GPIO or audio devices open. Stop is
graceful on Linux. Windows simulation terminates the child process directly.

Ctrl+C on the dashboard stops its runner and waits for cleanup. Do not force-kill
the runner: that skips servo release. Timing is cooperative; shutdown can take
several seconds. The service installer above replaces the old boot startup when
you run it. RTSP diagnostics are available below; automatic vision-driven behavior is not yet connected.

## RTSP camera test

Open **Camera debug** in the navigation, or visit `/camera`, and sign in. Enter the RTSP URL, select Capture only,
Full body, or Face, and a duration (5-3600 seconds). The camera page shows a continuously updating annotated image feed and
tracking/light/timing logs. It requests JPEG frames up to five times per second;
actual rate depends on camera capture and detector speed on the Pi. This is a
JPEG image feed, not full-rate video or audio. Hidden browser tabs pause image
requests; the camera test continues until stopped or its duration expires. The last frame remains after the test
ends; check Running/Stopped for its state. Camera tests start manually and do
not drive servos. They can run alongside the show, but detection adds Pi load.
Start with capture only. Install python3-opencv on the Pi if needed.

The URL is saved server-side in gitignored `raspberrypi/camera-source.json`,
readable only by its owner on the Pi. It is passed through the worker environment,
not command arguments or the status API. Leave the field blank to reuse it, or
enter a new URL to replace it. The saved URL survives service restarts and deployments
and takes priority over SKELL_RTSP_URL. For repeated use add SKELL_RTSP_URL to the protected
/etc/skeleton-dashboard.env file using sudoedit, and restart the service.
Stop camera test stops only the camera; stopping the dashboard stops both workers.

## Remembered login

Sign in once on either page. A signed HttpOnly cookie keeps this browser signed
in for 30 days across page navigation, browser restarts, and dashboard/Pi restarts.
Use the same hostname or IP each time; browser cookies belong to that address.
The password is not stored in browser storage. Changing the dashboard password
invalidates existing cookies. Sign out clears the cookie in this browser.

Older OpenCV builds use the legacy FFmpeg RTSP open call. The dashboard also
watches the camera worker: 30 seconds without a new preview ends a stalled test.
Stop allows 10 seconds for the camera to exit before terminating it. These
limits apply only to the camera process, never the servo controller.

## Animated preview

Install Pillow once on the Pi: `sudo apt-get install python3-pil`.
Camera tests then create an annotated GIF automatically when they finish or are
stopped normally. The Camera debug page shows it with a Download GIF link.
The preview samples up to 2 frames/sec at 320x240 and keeps at most 60 frames
(the latest 30 seconds at that rate). Frame timing follows actual capture timing.
The last GIF lasts until the next test or service restart; download it to keep it.
Missing Pillow leaves the live camera test working and reports installation instructions.

## Delayed camera tests

Start delay defaults to 90 seconds, separate from the 10-second recording duration.
Press Start camera test before walking to the skeleton. The Pi owns the countdown
and recording, so closing the page or losing Wi-Fi does not cancel it. Return to
Camera debug afterward to view/download the GIF. Cancel countdown stops a pending
test; set delay to 0 for an immediate test. Restarting the service cancels pending tests.

Camera tests now signal with the existing silent head gestures: after the
countdown, the show pauses and releases its servos, the head nods yes, and camera
capture begins. After a successful test/GIF export, the head shakes no and the
previous show or head-only mode resumes. A previously stopped show stays stopped.
Cancel/Stop ends the sequence without the ending gesture or automatic resume.
The home Stop button also cancels camera tests. Existing servo calibration and
movement restrictions apply to both signals. Camera tracking itself does not
steer the head. No extra servo controller runs alongside the show.
