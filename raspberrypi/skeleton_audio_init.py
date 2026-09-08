"""Condense ALSA diagnostics only during synchronous PortAudio startup."""
import os
import sys
import tempfile


def initialize(factory, debug=False):
    if debug or not sys.platform.startswith("linux"):
        return factory()
    # Native ALSA writes to fd 2, not Python's sys.stderr. No playback thread
    # exists yet. Restore the descriptor before reporting or propagating errors.
    with tempfile.TemporaryFile() as captured:
        sys.stderr.flush()
        saved = os.dup(2)
        success = False
        try:
            os.dup2(captured.fileno(), 2)
            result = factory()
            success = True
        finally:
            os.dup2(saved, 2)
            os.close(saved)
            captured.seek(0)
            report(captured.read(), success)
    return result


def report(data, success):
    lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
    hidden = 0
    for line in lines:
        if success and line.startswith("ALSA lib "):
            hidden += 1
        else:
            sys.stderr.write(line)
    if hidden:
        print("Audio initialized (%d ALSA startup diagnostic lines hidden; use --audio-debug to show them)." % hidden,
              file=sys.stderr)
