"""Camera source setup; RTSP credentials stay out of application diagnostics."""
from contextlib import contextmanager
import os
from urllib.parse import urlsplit


def validate_rtsp(url):
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in ("rtsp", "rtsps") and bool(parsed.hostname)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Expected an RTSP URL with a valid host")
    return url


@contextmanager
def quiet_native():
    # OpenCV/FFmpeg can print the credential-bearing URL directly to fd 2.
    # This standalone diagnostic has no other application worker threads.
    saved = os.dup(2)
    try:
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


def open_source(cv2, device, rtsp_url=None):
    if rtsp_url is None:
        cap = cv2.VideoCapture(int(device) if device.isdigit() else device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap
    validate_rtsp(rtsp_url)
    required = ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC")
    modern = all(hasattr(cv2, name) for name in required)
    cap = cv2.VideoCapture()
    key = "OPENCV_FFMPEG_CAPTURE_OPTIONS"
    previous = os.environ.get(key)
    os.environ[key] = "rtsp_transport;tcp" if modern else "rtsp_transport;tcp|stimeout;5000000"
    try:
        with quiet_native():
            if modern:
                ok = cap.open(rtsp_url, cv2.CAP_FFMPEG,
                              [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
                               cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            else:
                ok = cap.open(rtsp_url, cv2.CAP_FFMPEG)
        if not ok:
            raise RuntimeError("RTSP connection failed")
        return cap
    except Exception:
        with quiet_native():
            cap.release()
        raise RuntimeError("Cannot open RTSP stream. Check address, credentials, network reachability, and OpenCV FFmpeg support.") from None
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def read_source(cap, rtsp=False):
    if not rtsp:
        return cap.read()
    try:
        with quiet_native():
            return cap.read()
    except Exception:
        raise RuntimeError("RTSP read failed; check the camera and network connection") from None
