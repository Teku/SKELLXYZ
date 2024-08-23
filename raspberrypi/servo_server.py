from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory
import socket
from time import sleep

# Use PiGPIO for hardware PWM (smoother servo control)
factory = PiGPIOFactory()

# Servo configurations with angle limits
servo_configs = {
    'Base':  {'pin': 23, 'range': (-90, 90)},
    'Pitch': {'pin': 24, 'range': (-45, 45)},
    'Tilt':  {'pin': 25, 'range': (-45, 45)},
    'Mouth': {'pin': 18, 'range': (0, 90)}
}

# Create Servo objects
servos = {}
for name, config in servo_configs.items():
    servos[name] = Servo(config['pin'], min_pulse_width=0.5/1000, max_pulse_width=2.5/1000, pin_factory=factory)

# Set up UDP socket
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(('0.0.0.0', 8888))

def set_servo_angle(servo_name, angle):
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    # Clamp the angle to the defined limits
    clamped_angle = max(min_angle, min(angle, max_angle))
    
    # Convert the clamped angle to gpiozero's -1 to 1 range
    if servo_name == 'Mouth':
        # Mouth uses 0 to 90 range
        value = (clamped_angle / 90) * 2 - 1
    else:
        # Other servos use -45 to 45 (or -90 to 90) range
        value = clamped_angle / max_angle
    
    servos[servo_name].value = value
    
    if clamped_angle != angle:
        print(f"Warning: {servo_name} angle clamped from {angle} to {clamped_angle}")

try:
    print("Servo control ready. Waiting for commands...")
    while True:
        data, addr = udp_socket.recvfrom(1024)
        command = data.decode('utf-8')
        print(f"Received: {command}")
        
        # Parse command
        parts = command.split()
        for part in parts:
            if part.startswith('B'):
                set_servo_angle('Base', int(part[1:]))
            elif part.startswith('P'):
                set_servo_angle('Pitch', int(part[1:]))
            elif part.startswith('T'):
                set_servo_angle('Tilt', int(part[1:]))
            elif part.startswith('M'):
                set_servo_angle('Mouth', int(part[1:]))
        
        # Small delay to allow servos to move
        sleep(0.01)

except KeyboardInterrupt:
    print("Stopping...")
finally:
    # Clean up
    for servo in servos.values():
        servo.close()
    udp_socket.close()
