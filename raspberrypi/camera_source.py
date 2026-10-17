"""Camera source setup; RTSP credentials stay out of application diagnostics."""
from contextlib import contextmanager
import os
import re
import tempfile
import base64
from urllib.parse import urlsplit, unquote


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


def redact_diagnostic(text, url):
    parsed = urlsplit(url)
    secrets = [url, unquote(url), parsed.username, parsed.password,
               unquote(parsed.username or ""), unquote(parsed.password or "")]
    if parsed.username is not None:
        pair = unquote(parsed.username) + ":" + unquote(parsed.password or "")
        secrets.append(base64.b64encode(pair.encode()).decode())
    text = re.sub(r"(?im)^.*(?:authorization|authenticate).*$", "[authentication details redacted]", text)
    text = re.sub(r"rtsps?://[^\s\"<>]+", "[RTSP source]", text, flags=re.I)
    for secret in sorted(set(v for v in secrets if v), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    return text.strip()[-3000:]


@contextmanager
def capture_native(lines, url, debug=False):
    saved = os.dup(2)
    try:
        with tempfile.TemporaryFile() as sink:
            os.dup2(sink.fileno(), 2)
            try:
                yield
            finally:
                os.dup2(saved, 2)
                sink.seek(0)
                output = sink.read(65536).decode("utf-8", "replace")
                lines.append(output if debug else redact_diagnostic(output, url))
    finally:
        os.dup2(saved, 2)
        os.close(saved)


def open_source(cv2, device, rtsp_url=None, debug=False):
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
    diagnostic = []
    try:
        with capture_native(diagnostic, rtsp_url, debug):
            if modern:
                ok = cap.open(rtsp_url, cv2.CAP_FFMPEG,
                              [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
                               cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            else:
                ok = cap.open(rtsp_url, cv2.CAP_FFMPEG)
        if not ok:
            raise RuntimeError("RTSP connection failed")
        return cap
    except Exception as exc:
        with quiet_native():
            cap.release()
        detail = "\n".join(line for line in diagnostic if line)
        detail = detail or (str(exc) if debug else redact_diagnostic(str(exc), rtsp_url))
        raise RuntimeError("Cannot open RTSP stream. OpenCV/FFmpeg detail: " + (detail or "No backend diagnostic returned")) from None
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
