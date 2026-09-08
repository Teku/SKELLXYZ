# Standalone Aluratek AWC4KF camera trial

`raspberrypi/camera_test.py` never imports servo/audio code or drives GPIO.
Start with the skeleton controller stopped so the camera is stationary and
we can measure the Pi 3 B+'s available performance independently.

## Install and identify the capture device

On the Pi, after pulling this branch:

```bash
sudo apt-get update
sudo apt-get install python3-opencv v4l-utils
v4l2-ctl --list-devices
v4l2-ctl --device=/dev/video0 --list-formats-ext
```

Use the Aluratek's video capture node in the commands below; it may not be
`/dev/video0`. Some cameras expose multiple nodes, including metadata nodes.
Check supported formats before changing capture settings. The script requests
640x480 MJPEG at 15fps and prints the actual first-frame dimensions. Drivers
may ignore requests. A stable `/dev/v4l/by-id/...` capture path also works.

## First confirm the picture over SSH

```bash
python3 raspberrypi/camera_test.py --device /dev/video0 --capture-only --seconds 15 --snapshot /tmp/skell-camera.jpg
```

The JPEG is overwritten once per second, not saved as a recording. Copy it
to your workstation with scp/SFTP to inspect orientation, framing, and lighting.
No web server or camera stream is exposed.

## Test detection and basic tracking

Full-body detection remains the default (`--detector person`). For seated,
close-up indoor testing, use the frontal-face detector:

```bash
sudo apt-get install opencv-data
python3 raspberrypi/camera_test.py --device /dev/video0 --detector face --seconds 60 --snapshot /tmp/skell-camera.jpg
```

Face mode uses OpenCV's frontal-face Haar cascade and the same target association
and smoothing as person mode. Status reports `faces=` and snapshot labels show
the detector mode. Look toward the camera and move slowly left/right; profiles,
occlusion, and uneven lighting can cause misses. This detects faces, not identity.
Measure `detector=...ms` on the Pi rather than assuming a particular speed.
The cascade is found in OpenCV's Python data directory or the Debian OpenCV
data directories. If installed elsewhere, pass `--face-cascade /path/to/model.xml`.
Capture-only mode needs no cascade. No GPIO/audio behavior changes occur.

For full-body testing:

```bash
python3 raspberrypi/camera_test.py --device /dev/video0 --seconds 60 --snapshot /tmp/skell-camera.jpg
```

With a monitor and desktop session on the Pi, add `--preview` for a live window.
Press q in the window or Ctrl+C in the terminal to stop. Plain SSH defaults to
text status with no GUI requirement.

Stand far enough back that your whole body is visible, initially with good
lighting, and move slowly left/right. Green boxes show detections; a red point
shows the selected target's smoothed center. Reported x/y span roughly -1..1:
left/top are negative, right/bottom positive. They are image coordinates, not
servo angles or physical distance. The image is not mirrored.

The prototype uses OpenCV's bundled HOG person detector, requiring no downloaded
model. It is a baseline full-body detector, not face recognition. Expect missed
detections with cropped bodies, occlusion, darkness, and unusual poses. A single
person can acquire the target; overlapping detections keep that lock. When a
target disappears, no current position is reported. After 1.5 seconds without
a match the old lock expires. Multiple people without a lock report ambiguity.
Crossing people can confuse this simple overlap association.

Detection runs on 480x360 images, with one OpenCV worker thread. `--detect-hz 2`
is a requested rate, not a guarantee; detector time is additional. The script
keeps reading between detections, but capture can still block at the driver.
The duration limit is cooperative, not a hard timeout on driver calls.

Brightness is a whole-image grayscale mean, not lux. Below `--dark-threshold 25`
the prototype skips detection and rechecks the image continuously. This is only
a diagnostic threshold; bright background lights and auto exposure can fool it.
The planned visitor-zone visibility checks and delayed recovery are not yet
implemented. No attract mode or servo behavior changes occur here.

Send back the camera-device listing, actual frame dimensions, status lines,
and a sample annotated image to guide the next detector/tracker iteration.

References: [OpenCV HOG detector](https://docs.opencv.org/4.11.0/d5/d33/structcv_1_1HOGDescriptor.html)
and [V4L2 capture backend](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html).
