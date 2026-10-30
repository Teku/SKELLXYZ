#!/usr/bin/env python3
"""Standalone USB/RTSP camera tracking experiment. No GPIO or audio imports."""
import argparse
import getpass
from camera_source import open_source, read_source, validate_rtsp, quiet_native, LatestFrameSource
import math
import json
import os
from pathlib import Path
import signal
import time
from motion_tracking import MotionDetector, StableTarget
from tracking_settings import read as read_tracking, DEFAULTS


def load_face_detector(cv2, explicit=None):
    filename = "haarcascade_frontalface_default.xml"
    roots = [Path("/usr/share/opencv4/haarcascades"), Path("/usr/share/opencv/haarcascades")]
    bundled = getattr(getattr(cv2, "data", None), "haarcascades", None)
    if bundled:
        roots.insert(0, Path(bundled))
    candidates = [Path(explicit)] if explicit else [root / filename for root in roots]
    for path in candidates:
        if path.is_file():
            detector = cv2.CascadeClassifier(str(path))
            if detector.empty():
                raise RuntimeError("Invalid face cascade: " + str(path))
            return detector
    raise RuntimeError("Face cascade missing. Install opencv-data or supply --face-cascade /path/to/" + filename)


def overlap(a, b):
    x = max(a[0], b[0])
    y = max(a[1], b[1])
    w = max(0, min(a[0] + a[2], b[0] + b[2]) - x)
    h = max(0, min(a[1] + a[3], b[1] + b[3]) - y)
    intersection = w * h
    return intersection / max(1, a[2] * a[3] + b[2] * b[3] - intersection)


def deduplicate(boxes):
    result = []
    for box in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        if all(overlap(box, kept) < 0.4 for kept in result):
            result.append(box)
    return result


class Target:
    """Simple overlap association, not identity recognition or a crowd tracker."""
    def __init__(self):
        self.box = None
        self.point = None
        self.seen = 0

    def update(self, boxes, now):
        if self.box is not None and now - self.seen > 1.5:
            self.box = self.point = None
        selected = None
        if self.box is not None:
            matches = [b for b in boxes if overlap(self.box, b) >= 0.15]
            if matches:
                selected = max(matches, key=lambda b: overlap(self.box, b))
        elif len(boxes) == 1:
            selected = boxes[0]
        if selected is None:
            # Never emit a stale position as a currently observed target.
            return None
        x, y, w, h = selected
        point = (x + w / 2, y + h / 2)
        self.point = point if self.point is None else tuple(0.65 * old + 0.35 * new for old, new in zip(self.point, point))
        self.box, self.seen = selected, now
        return self.point


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/video0", help="V4L2 device path or camera index")
    parser.add_argument("--rtsp", action="store_true", help="Use SKELL_RTSP_URL or securely prompt for an RTSP URL")
    parser.add_argument("--rtsp-debug", action="store_true", help="Show raw connection errors, including any credentials in backend output")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--preview", action="store_true", help="Open a window on the Pi desktop (not plain SSH)")
    parser.add_argument("--detector", choices=("person", "face", "motion"), default="person", help="Moving objects, full-body people, or close-up frontal faces")
    parser.add_argument("--face-cascade", type=Path, help="Optional face cascade XML path")
    parser.add_argument("--capture-only", action="store_true", help="Check camera/light without person detection")
    parser.add_argument("--snapshot", type=Path, help="Write an annotated JPEG at --snapshot-hz")
    parser.add_argument("--detect-hz", type=float, default=2, help="Requested detection rate; actual speed is measured")
    parser.add_argument("--dark-threshold", type=float, default=25, help="Experimental mean grayscale cutoff (0..255, not lux)")
    parser.add_argument("--snapshot-hz", type=float, default=1, help="Maximum JPEG preview rate (1-10 Hz)")
    parser.add_argument("--gif", type=Path, help="Save an animated annotated preview (requires python3-pil)")
    parser.add_argument("--target-file", type=Path, help="Publish fresh single-target coordinates for head following")
    parser.add_argument("--tracking-config", type=Path)
    args = parser.parse_args()
    tracking = read_tracking(args.tracking_config) if args.tracking_config else dict(DEFAULTS)
    if args.tracking_config:
        args.dark_threshold = tracking["dark_threshold"]
    if args.detector == "motion":
        args.detect_hz = 5
    if not math.isfinite(args.snapshot_hz) or not 1 <= args.snapshot_hz <= 10:
        parser.error("snapshot-hz must be in [1, 10]")
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("seconds must be positive and finite")
    if not math.isfinite(args.detect_hz) or not 0 < args.detect_hz <= 15:
        parser.error("detect-hz must be in (0, 15]")
    if not math.isfinite(args.dark_threshold) or not 0 <= args.dark_threshold <= 255:
        parser.error("dark-threshold must be in [0, 255]")
    if args.preview and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        parser.error("No desktop display. Omit --preview; use --snapshot over SSH.")
    try:
        import cv2
    except ImportError:
        parser.exit(1, "OpenCV missing: install python3-opencv on the Pi.\n")
    cv2.setNumThreads(1)
    rtsp_url = None
    if args.rtsp:
        rtsp_url = os.environ.get("SKELL_RTSP_URL") or getpass.getpass("RTSP URL (hidden): ")
        try:
            validate_rtsp(rtsp_url)
        except ValueError as exc:
            parser.error(str(exc))
    gif = None
    if args.gif:
        try:
            from camera_gif import GifPreview
            gif = GifPreview(args.gif)
            args.gif.parent.mkdir(parents=True, exist_ok=True)
        except ImportError:
            print("GIF unavailable: install python3-pil on the Pi", flush=True)
    cap = open_source(cv2, args.device, rtsp_url, debug=args.rtsp_debug)
    reader = None
    stopping = False
    previous = {}
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, stop)
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera. Check v4l2-ctl --list-devices and --device.")
        if args.rtsp:
            reader = LatestFrameSource(cap)
        hog = face = motion_detector = None
        if not args.capture_only:
            if args.detector == "motion":
                motion_detector = MotionDetector(cv2, tracking)
            elif args.detector == "face":
                face = load_face_detector(cv2, args.face_cascade)
            else:
                hog = cv2.HOGDescriptor()
                hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        print("Detector: " + ("disabled" if args.capture_only else args.detector), flush=True)
        if args.snapshot:
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        tracker = StableTarget(hold_seconds=.8 if args.detector == "motion" else 2)
        started = last_report = time.monotonic()
        next_snapshot = started
        next_detect = started
        boxes, point = [], None
        frames, detections, detector_ms = 0, 0, 0.0
        first = True
        while not stopping and time.monotonic() - started < args.seconds:
            if reader is not None:
                ok, frame, captured_at = reader.read()
            else:
                ok, frame = read_source(cap)
                captured_at = time.time()
            if not ok or frame is None:
                raise RuntimeError("Camera stopped returning frames; check source connection and device ownership.")
            if first:
                print("Camera frame: %dx%d; source=%s" % (frame.shape[1], frame.shape[0], "RTSP/TCP" if args.rtsp else "USB (requested 640x480 MJPEG/15fps)"), flush=True)
                first = False
            # RTSP capture drains independently; detection consumes the newest
            # frame instead of queuing video behind preview/detector work.
            source_aspect = frame.shape[1] / frame.shape[0]
            frame = cv2.resize(frame, (480, 360))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            now = time.monotonic()
            frames += 1
            dark = brightness < args.dark_threshold
            if now >= next_detect:
                boxes, point = [], None
                if dark:
                    tracker = StableTarget(hold_seconds=.8 if args.detector == "motion" else 2)
                elif not args.capture_only:
                    begin = time.monotonic()
                    if motion_detector is not None:
                        found = motion_detector.detect(frame, time.monotonic())
                    elif face is not None:
                        found = face.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    else:
                        found, _ = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
                    detector_ms = (time.monotonic() - begin) * 1000
                    boxes = deduplicate([tuple(int(v) for v in b) for b in found])
                    if motion_detector is not None and motion_detector.state != "READY":
                        tracker.reset()
                        point = None
                    else:
                        point = tracker.update(boxes, time.monotonic())
                    detections += 1
                if args.target_file:
                    target = {"time": time.time(), "x": None, "y": None, "aspect": source_aspect, "state": tracker.state}
                    if point is not None and not dark:
                        target.update(x=point[0] / 240 - 1, y=point[1] / 180 - 1,
                                      time=min(captured_at, time.time() - (time.monotonic()-tracker.seen)))
                    temporary = args.target_file.with_suffix(".tmp")
                    temporary.write_text(json.dumps(target))
                    os.replace(temporary, args.target_file)
                next_detect = time.monotonic() + 1 / args.detect_hz
            if dark:
                boxes, point = [], None
            state = "LOW LIGHT" if dark else "CAPTURE ONLY" if args.capture_only else motion_detector.state if motion_detector is not None and motion_detector.state != "READY" else tracker.state
            if motion_detector is not None and motion_detector.region:
                rx, ry, rw, rh = motion_detector.region
                cv2.rectangle(frame, (rx, ry), (rx+rw, ry+rh), (255, 160, 0), 1)
            for x, y, w, h in boxes:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 0), 2)
            if point:
                cv2.circle(frame, tuple(int(v) for v in point), 6, (0, 0, 255), -1)
            cv2.putText(frame, "%s %s light=%.0f" % (args.detector, state, brightness), (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            if gif is not None:
                gif.add(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), time.monotonic())
            if now - last_report >= 1:
                target = "none" if point is None else "x=%.2f y=%.2f" % (point[0] / 240 - 1, point[1] / 180 - 1)
                print("%s %s=%d target=%s light=%.1f detector=%.0fms" % (state, "faces" if args.detector == "face" else "people", len(boxes), target, brightness, detector_ms), flush=True)
                last_report = now
            if args.snapshot and now >= next_snapshot:
                temporary = args.snapshot.with_name(args.snapshot.stem + ".tmp" + args.snapshot.suffix)
                if not cv2.imwrite(str(temporary), frame):
                    raise RuntimeError("Cannot write camera snapshot")
                os.replace(temporary, args.snapshot)
                next_snapshot = time.monotonic() + 1 / args.snapshot_hz
            if args.preview:
                cv2.imshow("Skeleton camera test - q to quit", frame)
                if cv2.waitKey(1) & 0xff == ord("q"):
                    break
        if gif is not None and gif.save():
            print("Animated GIF preview ready", flush=True)
        elapsed = max(0.001, time.monotonic() - started)
        if reader is not None:
            print("RTSP skipped %d superseded frames" % reader.dropped, flush=True)
        print("Finished: %.1f capture fps, %.2f detections/sec; no servos controlled." % (frames / elapsed, detections / elapsed))
    finally:
        if reader is not None:
            reader.close()
        elif args.rtsp:
            with quiet_native():
                cap.release()
        else:
            cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
