#!/bin/bash
# Boot launcher for ChatterPi (jaw) and head servo animation.
# Invoked by skeleton.service on the Raspberry Pi / FPP image.
#
# Install: see README.md → Boot setup

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATTERPI_DIR="${REPO_ROOT}/raspberrypi/vendor/ChatterPi/src"
SERVO_RUN="${REPO_ROOT}/raspberrypi/servo_run.py"

if ! command -v screen &> /dev/null; then
    echo "screen is not installed. Install with: sudo apt-get install screen"
    exit 1
fi

if ! pgrep pigpiod > /dev/null; then
    echo "Starting pigpiod daemon..."
    sudo pigpiod
    sleep 2
fi

screen -dmS chatter bash -c "cd '${CHATTERPI_DIR}' && python3 main.py; exec bash"

echo "Waiting 30 seconds before starting head servo animation..."
sleep 30

screen -dmS servo_run bash -c "python3 '${SERVO_RUN}'; exec bash"

echo "Programs are running in the following screen sessions:"
screen -ls
