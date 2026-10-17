#!/bin/bash
# Run from the Pi checkout: sudo bash install_dashboard_service.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$EUID" -ne 0 ]]; then
    exec sudo bash "$0" "$@"
fi
RUN_USER="${SUDO_USER:-fpp}"
if [[ "$RUN_USER" == root ]]; then RUN_USER=fpp; fi
id "$RUN_USER" >/dev/null
# These characters need additional escaping in systemd unit paths.
if [[ "$REPO_ROOT" =~ [[:space:]%\\\"] ]]; then
    echo "Install from a repository path without whitespace, percent signs, backslashes or quotes." >&2
    exit 1
fi
test -f "$REPO_ROOT/raspberrypi/skeleton_dashboard.py"
systemctl cat pigpiod.service >/dev/null

ENV_FILE=/etc/skeleton-dashboard.env
if [[ ! -f "$ENV_FILE" ]]; then
    # getpass reads the terminal; the secret never appears in arguments or logs.
    python3 - "$ENV_FILE" <<'PY'
import getpass
import json
import os
import sys

password = getpass.getpass("Dashboard password (8+ ASCII characters): ")
if len(password) < 8 or not password.isascii() or not password.isprintable():
    sys.exit("Use at least 8 printable ASCII characters")
if password != getpass.getpass("Confirm dashboard password: "):
    sys.exit("Passwords do not match")
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("SKELL_DASHBOARD_PASSWORD=" + json.dumps(password) + "\n")
PY
fi
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

python3 - "$REPO_ROOT" "$RUN_USER" <<'PY'
from pathlib import Path
import sys
root, user = sys.argv[1:]
template = (Path(root) / "skeleton-dashboard.service.example").read_text()
Path("/etc/systemd/system/skeleton-dashboard.service").write_text(
    template.replace("@USER@", user).replace("@REPO@", root))
PY
systemctl daemon-reload
# On this Pi, stopping the old service also stops its screen sessions.
if systemctl cat skeleton.service >/dev/null 2>&1; then
    systemctl disable --now skeleton.service
fi
systemctl start pigpiod.service
systemctl enable skeleton-dashboard.service
systemctl restart skeleton-dashboard.service
echo "Dashboard installed: http://$(hostname):8080"
echo "Starts idle. Use Start show in the dashboard to begin."
systemctl --no-pager --full status skeleton-dashboard.service
