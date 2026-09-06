import random
import time
from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory

# Use PiGPIO for hardware PWM (smoother servo control)
factory = PiGPIOFactory()

# Servo configurations
# travel: full physical servo range in degrees (e.g., 190 degrees = ±95 degrees)
servo_configs = {
    'Base':  {'pin': 23, 'travel': 190, 'rest': 0},
    'Pitch': {'pin': 24, 'travel': 190, 'rest': 0},
    'Tilt':  {'pin': 25, 'travel': 190, 'rest': 0},
    'Mouth': {'pin': 18, 'travel': 180, 'rest': 0},
}

# Create Servo objects
servos = {}
for name, config in servo_configs.items():
    servos[name] = Servo(config['pin'], min_pulse_width=0.5/1000, max_pulse_width=2.5/1000, pin_factory=factory)

def set_servo_angle(servo_name, angle):
    config = servo_configs[servo_name]
    travel = config['travel']
    
    # Calculate the physical range from travel
    max_physical = travel / 2  # e.g., 190/2 = 95
    min_physical = -max_physical  # e.g., -95
    
    # Use the full physical range for testing
    min_angle = min_physical
    max_angle = max_physical
    
    # Clamp the angle to the physical limits
    clamped_angle = max(min_angle, min(angle, max_angle))
    
    # Convert angle to servo value: map directly from physical range to servo -1 to 1
    value = clamped_angle / max_physical
    
    servos[servo_name].value = value
    
    print(f"{servo_name}: Angle: {clamped_angle}, Servo value: {value:.2f}")

def get_current_angle(servo_name):
    servo = servos[servo_name]
    if servo.value is None:
        return None
    
    config = servo_configs[servo_name]
    travel = config['travel']
    
    # Calculate the physical range from travel
    max_physical = travel / 2
    min_physical = -max_physical
    
    # Convert servo value back to angle
    # servo_val (-1 to 1) -> physical_angle
    physical_angle = servo.value * max_physical
    
    return physical_angle

def reset_servo(servo_name):
    rest_position = servo_configs[servo_name]['rest']
    set_servo_angle(servo_name, rest_position)
    time.sleep(0.5)
    print(f"{servo_name} reset to rest position: {rest_position} degrees")

def reset_all_servos():
    for servo_name in servos:
        reset_servo(servo_name)

def deactivate_all_servos():
    for servo in servos.values():
        servo.value = None
    print("All servos deactivated.")

def activate_all_servos():
    for name, servo in servos.items():
        set_servo_angle(name, servo_configs[name]['rest'])
    print("All servos activated and reset to rest positions.")

def debug_servo_limits(servo_name):
    print(f"\nTesting {servo_name} limits:")
    config = servo_configs[servo_name]
    travel = config['travel']
    
    # Calculate the physical range
    max_angle = travel / 2
    min_angle = -max_angle
    
    current_angle = config['rest']
    set_servo_angle(servo_name, current_angle)
    
    # Find min limit
    print(f"\nFind MIN limit for {servo_name} (physical range: {min_angle} to {max_angle})")
    print("Note: MIN limit should be the most NEGATIVE (left/down) position you want to allow")
    print("Use '+' to increase angle, '-' to decrease angle, 'c' to confirm, 'q' to quit")
    
    while True:
        action = input(f"Current angle: {current_angle} degrees > ").strip().lower()
        
        if action == '+':
            current_angle += 1
        elif action == '-':
            current_angle -= 1
        elif action == 'c':
            min_limit = current_angle
            print(f"MIN limit set to {min_limit} degrees")
            break
        elif action == 'q':
            reset_servo(servo_name)
            return
        else:
            print("Invalid input. Use '+', '-', 'c' (confirm), or 'q' (quit)")
            continue
        
        # Clamp to physical limits
        current_angle = max(min_angle, min(current_angle, max_angle))
        set_servo_angle(servo_name, current_angle)
        time.sleep(0.2)
    
    # Find max limit
    print(f"\nFind MAX limit for {servo_name} (must be >= MIN which is {min_limit})")
    print("Note: MAX limit should be the most POSITIVE (right/up) position you want to allow")
    print("Use '+' to increase angle, '-' to decrease angle, 'c' to confirm, 'q' to quit")
    
    current_angle = min_limit  # Start from min
    set_servo_angle(servo_name, current_angle)
    
    while True:
        action = input(f"Current angle: {current_angle} degrees > ").strip().lower()
        
        if action == '+':
            current_angle += 1
        elif action == '-':
            current_angle -= 1
        elif action == 'c':
            if current_angle < min_limit:
                print(f"MAX must be >= MIN ({min_limit}). Please try again.")
                continue
            max_limit = current_angle
            print(f"MAX limit set to {max_limit} degrees")
            break
        elif action == 'q':
            reset_servo(servo_name)
            return
        else:
            print("Invalid input. Use '+', '-', 'c' (confirm), or 'q' (quit)")
            continue
        
        # Clamp to physical limits and ensure >= min_limit
        current_angle = max(min_limit, min(current_angle, max_angle))
        set_servo_angle(servo_name, current_angle)
        time.sleep(0.2)
    
    # Save to config file
    save_servo_config(servo_name, min_limit, max_limit)
    
    # Return to rest position
    reset_servo(servo_name)

def save_servo_config(servo_name, min_limit, max_limit):
    """Save servo limits to a config file in key:value format"""
    config_file = "servo_limits.cfg"
    
    # Read existing config if it exists
    config_dict = {}
    try:
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split(':')
                    config_dict[key] = value
    except FileNotFoundError:
        pass
    
    # Update with new values
    config_dict[f"{servo_name}_min"] = min_limit
    config_dict[f"{servo_name}_max"] = max_limit
    
    # Write back to file
    with open(config_file, 'w') as f:
        # Write in the specified order from servo_configs
        for servo_name in servo_configs.keys():
            if f"{servo_name}_min" in config_dict:
                f.write(f"{servo_name}_min:{config_dict[f'{servo_name}_min']}\n")
            if f"{servo_name}_max" in config_dict:
                f.write(f"{servo_name}_max:{config_dict[f'{servo_name}_max']}\n")
    
    print(f"\nConfig saved to {config_file}")

def main_menu():
    while True:
        print("\nServo Debug Menu:")
        print("1. Debug Servo Limits")
        print("2. Exit")
        choice = input("Enter your choice (1-2): ").strip()

        if choice == '1':
            print("\nAvailable servos:")
            for i, name in enumerate(servo_configs.keys(), 1):
                print(f"{i}. {name}")
            servo_choice = input("Enter the number of the servo to debug: ").strip()
            try:
                index = int(servo_choice) - 1
                servo_name = list(servo_configs.keys())[index]
                activate_all_servos()  # Ensure servos are attached before debugging
                debug_servo_limits(servo_name)
                deactivate_all_servos()  # Detach after debugging
            except (ValueError, IndexError):
                print("Invalid choice. Returning to main menu.")
        elif choice == '2':
            print("Exiting program.")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    try:
        activate_all_servos()  # Ensure all servos are activated and at rest position at start
        main_menu()
    except KeyboardInterrupt:
        print("Program stopped by user")
    finally:
        activate_all_servos()  # Ensure servos are active before final reset
        reset_all_servos()  # Ensure all servos return to rest position
        deactivate_all_servos()  # Deactivate all servos before exiting
        for servo in servos.values():
            servo.close()
