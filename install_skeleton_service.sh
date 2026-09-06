#!/bin/bash
# Install or update skeleton.service to use start_skeleton.sh from this repo.
#
# Usage:
#   ./install_skeleton_service.sh
#   sudo ./install_skeleton_service.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DEST="/etc/systemd/system/skeleton.service"
START_SCRIPT="${REPO_ROOT}/start_skeleton.sh"

if [[ ! -x "${START_SCRIPT}" ]]; then
    chmod +x "${START_SCRIPT}"
fi

if [[ "${EUID}" -ne 0 ]]; then
    echo "Re-running with sudo..."
    exec sudo "$0" "$@"
fi

cat > "${SERVICE_DEST}" <<EOF
[Unit]
Description=Run Skeleton on Boot
After=network.target pigpiod.service
Wants=pigpiod.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=fpp
ExecStart=${START_SCRIPT}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable skeleton.service

echo "Installed ${SERVICE_DEST}"
echo "  ExecStart=${START_SCRIPT}"
echo ""
echo "Start now:  systemctl start skeleton.service"
echo "Check:      systemctl status skeleton.service"
echo "            screen -ls"
