# SkellXYZ

This project provides a Python script for controlling and testing servo motors, specifically designed for the home depot skeleton with Base, Pitch, Tilt, and Mouth servos.

## Features

- Godot Animation Tool (WIP)
- Individual servo testing
- Debugging servo limits
- Customizable movement sequences (WIP)
- Special handling for mouth servo

## Requirements

- Raspberry Pi
- Python 3.x
- GPIO Zero library
- pigpio library

## Setup

1. Install the required libraries:

```bash
sudo apt-get update
sudo apt-get install python3-gpiozero python3-pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

2. Clone this repository or download the script to your Raspberry Pi.

3. Make sure your servos are connected to the correct GPIO pins as defined in the script:
   - Base: GPIO 23
   - Pitch: GPIO 24
   - Tilt: GPIO 25
   - Mouth: GPIO 18

## Usage

Run the script using Python 3:

```bash
python3 servo_control.py
```

Follow the on-screen prompts to:

1. Select a servo to test
2. Choose between running a movement sequence or debugging servo limits

### Movement Sequence

This will run a predefined movement sequence for the selected servo.

### Debug Servo Limits

This mode allows you to incrementally adjust the servo position and find its safe operating range.

- Use '+' to increase angle by 5 degrees
- Use '-' to decrease angle by 5 degrees
- Use 'r' to reset to center position
- Use 'q' to quit debugging mode

## Customization

You can adjust the servo configurations in the `servo_configs` dictionary at the top of the script. This includes:

- GPIO pin assignments
- Angle ranges for each servo

## Safety Notes

- Always ensure your servo movements are within safe limits to prevent damage to your robot or servos.
- Start with small movements and gradually increase the range as you verify safe operation.

## Troubleshooting

- If you encounter issues with servo control, ensure the pigpio daemon is running:
  ```bash
  sudo systemctl status pigpiod
  ```
- Double-check your wiring and GPIO pin assignments.
- Verify that your power supply can handle the current draw of all connected servos.

## Attribution

This project was inspired by and adapted from the "3-Axis Skull Mod for 12ft Skeleton" project by Steven Long, available at:

[https://hackaday.io/project/181103-3-axis-skull-mod-for-12ft-skeleton](https://hackaday.io/project/181103-3-axis-skull-mod-for-12ft-skeleton)
