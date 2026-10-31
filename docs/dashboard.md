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

Music is selected from `vendor/ChatterPi/src/ambient/*.wav` and loops continuously,
including during speech and silent gestures. Speech ducks music to 20% of the
selected music volume, with approximately 50 ms fade-down and 400 ms recovery.
The music cursor keeps advancing during speech; it rewinds only at the end of
the track, or when selecting a different track. Music never drives the jaw.
Turning music Off stops that track; stopping the show closes the audio output.
Head-only and single-expression modes never initialize audio. Both voice and
music in the show require 44100 Hz mono/stereo 16-bit PCM WAV files; MP3 playback
and soundtrack extraction are separate follow-up work. Add recordings to
`vocals/` and music to
`ambient/`, then reload the dashboard to refresh the catalog. No file upload
endpoint is exposed. Empty playlist uses all default v01–v10 recordings. Each run
shuffles the selected sayings; every clip plays once per cycle before reshuffling,
with no adjacent repeat across cycle boundaries when at least two clips are selected.
A single selected clip necessarily repeats. Live playlist changes start a fresh
shuffle and avoid the previous clip when another is available.

Continuous mixing requires NumPy (`sudo apt-get install python3-numpy`), already
installed with OpenCV on the deployed Pi. Mixing uses compiled array operations
to keep audio callback work below its 20 ms buffer deadline.

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
ends; check Running/Stopped for its state. Camera tests start manually and pause the show for the head signals. Optional
head following drives the servos during capture; detection adds Pi load.
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
movement restrictions apply to both signals. Camera tracking steers the head only when following is enabled. No extra servo
controller runs alongside the show.

## Head-following trial

Choose Full body or Face and enable **Follow detected person with head**.
Following is off by default. The existing countdown and yes/no signals still
apply. A separate servo worker runs at 50 Hz while camera detection runs at its
own speed; the show remains paused until tracking has returned to rest and
released the servos. The jaw is not driven during tracking.

The legacy image-relative mapping is available by disabling sidewalk geometry.
Sidewalk geometry is described below. Both use continuous damped movement with
a 10 degrees/sec default speed limit. Tilt stays at rest.
Both trajectory generation and output enforce servo_limits.cfg; no limits change.
It follows only one detected target. Low light, multiple detections, invalid
coordinates, or coordinates older than two seconds cause a smooth return to
rest and PWM release. Stop also returns home and releases PWM.

This mapping assumes a fixed camera aimed in the same direction as the resting
head. Reverse left/right or up/down if either axis moves the wrong way. A camera
mounted on the moving head needs a different feedback mapping. Test direction
in adequate light before relying on following; false face detections remain
possible. This is a timed diagnostic trial, not automatic vision-triggered speech
or the final attract-mode behavior.

## Motion tracking and the sidewalk layout

Camera debug now offers **Motion (any moving object)**. Start with following
unchecked to inspect the rectangles and GIF. It uses OpenCV MOG2 background
subtraction, rejects shadow-labelled pixels, filters small blobs, and suppresses
large whole-region changes such as exposure jumps. It learns the background for
at least three seconds/ten frames; keep the view clear initially. Motion is not
person recognition: pets, decorations, headlights and shadows can still trigger
it, and a stationary person eventually stops being a motion target.

Under **Tracking setup**, narrow the detection region to the sidewalk and exclude
lights, moving decorations and the skeleton. The blue rectangle shows the region.
Three matching observations confirm a target. A time-based filter smooths its
position, and a brief gap holds position for at most 0.8 seconds in motion mode (up to two
seconds for slower face/person detection). A distant object
cannot immediately steal the target; ambiguous new crowds do not acquire one.
Dark or major scene changes immediately clear tracking. The follower independently
rejects stale packets and continues running smoothly even while detection is slow.

The confirmed layout is a fixed ground camera directly below a skull about
12 feet up, looking toward a sidewalk about 14 feet out. **Aim using sidewalk
geometry** projects the target horizontally onto that assumed sidewalk plane.
The default aim height is 5 feet; vertical blob motion does not make the skull
bob up/down. As people move sideways, both yaw and downward elevation change.
This estimates position for a known walkway; it does not measure a person's depth
or actual height. People well in front of/behind the sidewalk will be mis-aimed.

**Calibrate before judging accuracy:**

- Horizontal field of view defaults to 60 degrees as a placeholder, not a known
  camera specification. Enter the camera's actual horizontal FOV at its current zoom.
- Enter camera upward tilt and yaw relative to the sidewalk center. The source
  aspect ratio is used when correcting for camera tilt.
- Enter the direction the skull actually looks at its calibrated servo rest:
  rest yaw, and rest elevation (negative for downward). These change the aiming
  transform, not servo_limits.cfg. Use the reverse-axis controls for linkage direction.
- At the sidewalk center, a 5-foot aim height calls for 26.6 degrees below horizontal.
  If rest is level, the default Pitch lower limit of -24 degrees cannot reach this;
  the initial 35% travel envelope is narrower still. Adjust the physical resting aim
  or its measured calibration, never extend a mechanical limit to compensate.
- The travel fraction may be increased after direction/clearance checks, up to
  the existing calibrated range. All outputs remain clamped by servo_limits.cfg.

Tracking uses continuous damped motion instead of waiting for each gesture to end.
The default maximum speed is 10 degrees/sec and acceleration is 20 degrees/sec
squared, adjustable within bounded settings. Lost targets and Stop ease back to
rest and release PWM. Settings save on Start camera test in gitignored
`raspberrypi/tracking-settings.json` and survive deployment.

Detector reference: https://docs.opencv.org/4.0.0/d1/dc5/tutorial_background_subtraction.html
