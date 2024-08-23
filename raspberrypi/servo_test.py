from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory
from time import sleep

# Use PiGPIO for hardware PWM (smoother servo control)
factory = PiGPIOFactory()

# Servo configurations with angle limits
servo_configs = {
    'Base':  {'pin': 23, 'range': (-90, 90), 'rest': 0},
    'Pitch': {'pin': 24, 'range': (-45, 45), 'rest': 0},
    'Tilt':  {'pin': 25, 'range': (-45, 45), 'rest': 0},
    'Mouth': {'pin': 18, 'range': (45, 80), 'rest': 80}  # Rest position is closed (80 degrees)
}

# Create Servo objects
servos = {}
for name, config in servo_configs.items():
    servos[name] = Servo(config['pin'], min_pulse_width=0.5/1000, max_pulse_width=2.5/1000, pin_factory=factory)

def set_servo_angle(servo_name, angle):
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    # Clamp the angle to the defined limits
    clamped_angle = max(min_angle, min(angle, max_angle))
    
    # Convert the clamped angle to gpiozero's 0 to 1 range for mouth, -1 to 1 for others
    if servo_name == 'Mouth':
        # Special handling for mouth servo
        value = (clamped_angle - 45) / (80 - 45) * 0.78  # Maps 45 to 0 and 80 to 0.78
    else:
        value = (clamped_angle - min_angle) / (max_angle - min_angle) * 2 - 1
    
    servos[servo_name].value = value
    
    print(f"{servo_name}: Angle: {clamped_angle}, Servo value: {value:.2f}")

def move_servo_range(servo_name, angle_range=15, repetitions=5):
    print(f"Testing {servo_name} movement")
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    center = (min_angle + max_angle) / 2
    
    for _ in range(repetitions):
        # Move from center to +angle_range degrees
        for pos in range(int(center), int(min(center + angle_range, max_angle)) + 1):
            set_servo_angle(servo_name, pos)
            sleep(0.02)
        
        # Move from +angle_range to -angle_range degrees
        for pos in range(int(min(center + angle_range, max_angle)), int(max(center - angle_range, min_angle)) - 1, -1):
            set_servo_angle(servo_name, pos)
            sleep(0.02)
        
        # Move back to center
        for pos in range(int(max(center - angle_range, min_angle)), int(center) + 1):
            set_servo_angle(servo_name, pos)
            sleep(0.02)
    
    # Return to rest position
    reset_servo(servo_name)

def move_mouth(repetitions=2):
    print("Testing MOUTH movement")
    for _ in range(repetitions):
        # Open mouth (move from 80 to 45 degrees)
        for pos in range(80, 44, -1):
            set_servo_angle('Mouth', pos)
            sleep(0.02)
        
        # Close mouth (move from 45 to 80 degrees)
        for pos in range(45, 81):
            set_servo_angle('Mouth', pos)
            sleep(0.02)

def reset_servo(servo_name):
    rest_position = servo_configs[servo_name]['rest']
    set_servo_angle(servo_name, rest_position)
    sleep(0.5)
    print(f"{servo_name} reset to rest position: {rest_position} degrees")

def reset_all_servos():
    for servo_name in servos:
        reset_servo(servo_name)

def debug_servo_limits(servo_name):
    print(f"\nTesting {servo_name} limits:")
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    current_angle = config['rest']  # Start at rest position
    set_servo_angle(servo_name, current_angle)
    print(f"Starting at rest position: {current_angle} degrees")
    
    while True:
        action = input("Enter '+' to increase by 5 degrees, '-' to decrease by 5 degrees, 'r' to reset, or 'q' to quit: ").strip().lower()
        
        if action == '+':
            current_angle = min(current_angle + 5, max_angle)
        elif action == '-':
            current_angle = max(current_angle - 5, min_angle)
        elif action == 'r':
            current_angle = config['rest']
        elif action == 'q':
            break
        else:
            print("Invalid input. Please try again.")
            continue
        
        set_servo_angle(servo_name, current_angle)
        sleep(0.5)
    
    # Return to rest position before exiting
    reset_servo(servo_name)

def test_single_servo():
    print("Available servos:")
    for i, name in enumerate(servo_configs.keys(), 1):
        print(f"{i}. {name}")
    
    choice = input("Enter the number of the servo you want to test: ").strip()
    try:
        index = int(choice) - 1
        servo_name = list(servo_configs.keys())[index]
    except (ValueError, IndexError):
        print("Invalid choice. Exiting.")
        return

    print(f"\nTesting {servo_name}")
    print("1. Run movement sequence")
    print("2. Debug servo limits")
    test_choice = input("Enter your choice (1 or 2): ").strip()

    if test_choice == '1':
        if servo_name == 'Mouth':
            move_mouth()
        else:
            move_servo_range(servo_name)
    elif test_choice == '2':
        debug_servo_limits(servo_name)
    else:
        print("Invalid choice. Exiting.")

    # Ensure servo returns to rest position after testing
    reset_servo(servo_name)

if __name__ == "__main__":
    try:
        reset_all_servos()  # Ensure all servos are in rest position at start
        test_single_servo()
    except KeyboardInterrupt:
        print("Program stopped by user")
    finally:
        reset_all_servos()  # Ensure all servos return to rest position
        for servo in servos.values():
            servo.close()