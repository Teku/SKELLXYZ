"""One hardware runner per Pi; old scripts must be stopped separately."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def hardware_lock(dry_run=False):
    if dry_run:
        yield
        return
    import fcntl
    path = Path(__file__).resolve().parent / ".skeleton.lock"
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another unified runner owns the servos") from None
        # The old launcher's processes predate the lock protocol.
        for proc in Path("/proc").glob("[0-9]*/cmdline"):
            if proc.parent.name == str(os.getpid()):
                continue
            try:
                args = proc.read_bytes().decode(errors="replace").split("\0")
            except (OSError, PermissionError):
                continue
            if args and "python" in Path(args[0]).name.lower():
                scripts = {Path(a).name for a in args[1:] if a.endswith(".py")}
                if scripts & {"servo_run.py", "servo_test.py", "servo_server.py", "servo_hold.py", "main.py"}:
                    raise RuntimeError("An older servo/ChatterPi process is still running; stop it before starting the dashboard controller")
        yield
