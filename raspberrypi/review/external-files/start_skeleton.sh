#!/bin/bash
#set -e

# Ensure 'screen' is installed
if ! command -v screen &> /dev/null; then
    echo "Screen is not installed. Please install it first."
    exit 1
fi

# Start pigpiod if not already running
if ! pgrep pigpiod > /dev/null; then
    echo "Starting pigpiod daemon..."
    sudo pigpiod
    sleep 2
fi

# DEBUG
# exit 0

# Start the 'chatter' program in a detached screen session
screen -dmS chatter bash -c 'cd /home/fpp/SKELLXYZ/raspberrypi/vendor/ChatterPi/src/ && python3 main.py; exec bash'

# Log the waiting period
echo "Waiting for 30 seconds before starting the servo_test program..."
sleep 30

# Start the 'servo_test' program with initial inputs in another screen session
screen -dmS servo_test bash -c 'echo -e "1\n1" | python3 /home/fpp/SKELLXYZ/raspberrypi/servo_run.py; exec bash'

# Display running screen sessions
echo "Programs are running in the following screen sessions:"
screen -ls

