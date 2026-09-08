# Unified skeleton controller

Current scope: implement smooth head motion and recorded speech coordination
first. `skeleton_run.py` now provides a manual trial of those two features;
see [trial instructions](unified-trial.md). Camera and attract behavior below
remain future requirements. The existing vendor runtime remains available for
rollback; the new playback component reuses its recordings and style 0/1
threshold semantics without importing its hardware-initializing trigger loop.

## Objectives

- Coordinate speech, jaw animation, and head motion through one controller.
- Move all head axes together with eased motion and configurable speed limits.
- Optionally track a person and trigger speech when they enter a configured range.
- Use attract behavior when nobody is nearby or a crowd prevents reliable focus.
- While operational, allow no more than 300 seconds without skeleton activity.
- Keep camera-free operation available.

## Current implementation

`skeleton.service` starts `start_skeleton.sh`, the only confirmed startup path.
The launcher runs ChatterPi and `servo_run.py` in separate screen sessions.
Head motion moves Base, Pitch, and Tilt sequentially with linear interpolation,
then alternates roughly a minute of motion with a minute at rest.
ChatterPi currently uses recorded files, ambient playback, and a five-second
trigger delay. Its audio, track selection, and trigger modules depend on each
other, and initialize hardware during import. These need separating before a
new controller can own scheduling cleanly.

## Hardware

Confirmed controller: Raspberry Pi 3 Model B Plus Rev 1.3.
Available cameras: Xbox Kinect v2 and an Aluratek AWC4KF 4K USB camera.
The installation operates at night. Camera operation has not yet been tested
on the Pi at the installation location.

The Pi 3 B+ has USB 2.0 ports ([Pi specifications](https://datasheets.raspberrypi.org/rpi3/raspberry-pi-3-b-plus-product-brief.pdf)).
Kinect v2 requires USB 3.0 with libfreenect2; USB 2 is explicitly unsupported
([driver requirements](https://github.com/OpenKinect/libfreenect2#requirements)).
It is therefore not a direct camera option for this Pi. A separate compatible
USB 3 computer could process Kinect depth and send target observations to the Pi.

Proposed first camera trial: the existing Aluratek AWC4KF. The manufacturer's
[specifications](https://aluratek.com/products/live-pro-4k-hd-webcam-with-5x-digital-zoom-and-dual-stereo-noise-cancelling-mics)
list Linux compatibility, USB 2.0, 640x480 at 30fps, MJPEG/YUV, fixed focus,
and automatic low-light correction. Verify available capture modes on the Pi,
start at 640x480, and benchmark detection alongside audio playback.
Keep vision in a separate worker with bounded observation queues so delayed
frames do not delay motion. Detection rate is a measured performance target,
not a promised frame rate. Smooth motion should interpolate between observations.

A normal RGB webcam does not supply measured depth. Initial range triggering
would use a calibrated image zone or approximate apparent person size; it must
not be presented as accurate distance in feet/meters. Mounting and lighting
need testing at the installation location.

## Proposed structure

One controller owns behavior and lifecycle. An independent motion tick updates
all three head axes; audio playback must not block this tick. The jaw follows
the playing audio, with only one owner for each GPIO output. Reuse the existing
per-machine servo limits and validate them before enabling movement.

Separate components:

- Motion: simultaneous eased trajectories, bounded speed, continuous retargeting
  from the current pose, and controlled return to rest.
- Speech: recorded clip selection, playback start/completion events, audio-driven
  jaw movement, cancellation, and cleanup.
- Presence: optional observations of targets, confidence, and range eligibility.
  Camera/model choice and distance estimation depend on available hardware.
- Behavior: target selection, speech cooldowns, crowd fallback, and activity timer.
- Runtime: configuration, dry-run output, clean shutdown, and error handling.

## Proposed behavior

| Situation | Behavior |
| --- | --- |
| Nobody eligible nearby | Rest between short attract sequences; start one before 300 seconds of inactivity. |
| One stable target enters range | Ease toward them and play a greeting, subject to cooldown. |
| Target remains | Follow gently; avoid replaying a greeting every detection frame. |
| Several people, stable target available | Keep the current target to avoid rapid switching. |
| Crowd prevents stable focus | Use a general attract sequence instead of individual tracking. |
| Camera disabled, unavailable, or observations stale | Continue camera-free attract behavior. |
| Too dark or image quality inadequate | Use attract-only behavior; periodically check for usable visibility. |

### Nighttime visibility fallback

Confirmed requirement: poor visibility must not stop the skeleton. Suspend
person tracking and person-triggered greetings, discard the old target, and
continue attract activity with the same 300-second inactivity ceiling.
An already playing clip may finish while the head eases out of tracking.

Assess image usability within the visitor zone using brightness, dark/clipped
pixel coverage, and usable contrast over multiple fresh frames. Bright lamps
outside that zone must not make a dark visitor area appear usable. No person
detections alone do not mean the camera is too dark; the scene may be empty.
Automatic exposure also means image brightness is not a calibrated lux reading.

Proposed configurable starting timings, to tune on-site:

- Enter low-visibility mode after 3 seconds of consistently unusable images.
- While in that mode, run a short visibility probe every 30 seconds, allowing
  exposure to settle if capture is restarted. Keep expensive person detection
  paused between probes.
- Restore vision after 3 seconds of consistently usable fresh images, with a
  stricter recovery threshold than the fallback threshold to avoid mode flicker.
- After recovery, acquire a new stable target before greeting or following.
- Retry disconnected/failed cameras at the same bounded interval; an explicitly
  disabled camera stays disabled.

Probes and mode transitions do not reset the activity timer. Verify darkness,
brief flashes, bright background lights, an empty lit scene, sustained recovery,
and camera disconnect/reconnect in tests and on-site trials.

Track actual activity with a monotonic clock. Passive camera detections must not
reset the inactivity timer. While speech or a motion sequence is active, avoid
overlapping attract sequences. Schedule the next attract deadline from the end
of activity, with configurable intervals capped at 300 seconds. Tests should
cover target loss, camera failure, crowd ambiguity, and timer boundaries.

## Implementation sequence

1. Extract hardware-independent motion and behavior logic; add simulation and
   focused tests for limits, trajectory continuity, and the inactivity deadline.
2. Separate ChatterPi playback from its trigger loop; connect speech events to
   the motion controller and verify recorded speech plus coordinated movement.
3. Add optional presence observations and target selection. Select a camera
   backend after confirming the Pi model, camera, and intended trigger distance.
4. Validate on the Pi, then change the existing launcher to start the unified
   runtime. Give systemd direct supervision of the runtime and clean shutdown.

## Decisions to confirm

- Camera mounting position, actual nighttime lighting, and trigger range.
- Recorded clips versus microphone input or interactive generated speech.
- Attract sequence length and preferred frequency within the five-minute maximum.
- Greeting cooldown and how long to retain a target before falling back.

No camera backend or boot behavior has been changed yet.
