#!/usr/bin/env python3
"""Standalone USB camera/person-tracking experiment. No GPIO or audio imports."""
import argparse
import math
import os
from pathlib import Path
import signal
import time


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
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--preview", action="store_true", help="Open a window on the Pi desktop (not plain SSH)")
    parser.add_argument("--detector", choices=("person", "face"), default="person", help="Full-body person detector or close-up frontal faces")
    parser.add_argument("--face-cascade", type=Path, help="Optional face cascade XML path")
    parser.add_argument("--capture-only", action="store_true", help="Check camera/light without person detection")
    parser.add_argument("--snapshot", type=Path, help="Overwrite this annotated JPEG once per second")
    parser.add_argument("--detect-hz", type=float, default=2, help="Requested detection rate; actual speed is measured")
    parser.add_argument("--dark-threshold", type=float, default=25, help="Experimental mean grayscale cutoff (0..255, not lux)")
    args = parser.parse_args()
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
    device = int(args.device) if args.device.isdigit() else args.device
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
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
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        hog = face = None
        if not args.capture_only:
            if args.detector == "face":
                face = load_face_detector(cv2, args.face_cascade)
            else:
                hog = cv2.HOGDescriptor()
                hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        print("Detector: " + ("disabled" if args.capture_only else args.detector), flush=True)
        if args.snapshot:
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        tracker = Target()
        started = last_report = time.monotonic()
        next_detect = started
        boxes, point = [], None
        frames, detections, detector_ms = 0, 0, 0.0
        first = True
        while not stopping and time.monotonic() - started < args.seconds:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Camera stopped returning frames; check USB connection/device ownership.")
            if first:
                print("Camera frame: %dx%d; requested 640x480 MJPEG/15fps" % (frame.shape[1], frame.shape[0]), flush=True)
                first = False
            # Continuous reads discard intervening frames; do not sleep between
            # detections and accumulate a backlog of camera frames.
            frame = cv2.resize(frame, (480, 360))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            now = time.monotonic()
            frames += 1
            dark = brightness < args.dark_threshold
            if now >= next_detect:
                boxes, point = [], None
                if dark:
                    tracker = Target()
                elif not args.capture_only:
                    begin = time.monotonic()
                    if face is not None:
                        found = face.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    else:
                        found, _ = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
                    detector_ms = (time.monotonic() - begin) * 1000
                    boxes = deduplicate([tuple(int(v) for v in b) for b in found])
                    point = tracker.update(boxes, time.monotonic())
                    detections += 1
                next_detect = time.monotonic() + 1 / args.detect_hz
            if dark:
                boxes, point = [], None
            state = "LOW LIGHT" if dark else "CAPTURE ONLY" if args.capture_only else "TRACKING" if point else "CROWD/NO LOCK" if len(boxes) > 1 else "NO TARGET"
            for x, y, w, h in boxes:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 0), 2)
            if point:
                cv2.circle(frame, tuple(int(v) for v in point), 6, (0, 0, 255), -1)
            cv2.putText(frame, "%s %s light=%.0f" % (args.detector, state, brightness), (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            if now - last_report >= 1:
                target = "none" if point is None else "x=%.2f y=%.2f" % (point[0] / 240 - 1, point[1] / 180 - 1)
                print("%s %s=%d target=%s light=%.1f detector=%.0fms" % (state, "faces" if args.detector == "face" else "people", len(boxes), target, brightness, detector_ms), flush=True)
                if args.snapshot and not cv2.imwrite(str(args.snapshot), frame):
                    raise RuntimeError("Cannot write snapshot: " + str(args.snapshot))
                last_report = now
            if args.preview:
                cv2.imshow("Skeleton camera test - q to quit", frame)
                if cv2.waitKey(1) & 0xff == ord("q"):
                    break
        elapsed = max(0.001, time.monotonic() - started)
        print("Finished: %.1f capture fps, %.2f detections/sec; no servos controlled." % (frames / elapsed, detections / elapsed))
    finally:
        cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
