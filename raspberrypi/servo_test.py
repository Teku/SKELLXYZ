import random
import time
from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory

# Use PiGPIO for hardware PWM (smoother servo control)
factory = PiGPIOFactory()

# Servo configurations with angle limits
servo_configs = {
    'Base':  {'pin': 23, 'range': (-34, 34), 'rest': 0},
    'Pitch': {'pin': 24, 'range': (-20, 15), 'rest': 0},
    'Tilt':  {'pin': 25, 'range': (-11, 11), 'rest': 0},
    'Mouth': {'pin': 18, 'range': (45, 80), 'rest': 80}  # Rest position is closed (80 degrees)
}

# Add this near the top of the file, after the servo_configs dictionary
use_mouth_servo = False  # Set this to False to disable the Mouth servo

# Create Servo objects
servos = {}
for name, config in servo_configs.items():
    servos[name] = Servo(config['pin'], min_pulse_width=0.5/1000, max_pulse_width=2.5/1000, pin_factory=factory)

def set_servo_angle(servo_name, angle, check_safety=True):
    if servo_name == 'Mouth' and not use_mouth_servo:
        print(f"Mouth servo is disabled. Skipping movement.")
        return

    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    # Clamp the angle to the defined limits
    clamped_angle = max(min_angle, min(angle, max_angle))
    
    # Safety check for Pitch servo
    if check_safety and servo_name == 'Pitch':
        clamped_angle = check_pitch_safety(clamped_angle)
    
    # Convert the clamped angle to gpiozero's -1 to 1 range
    if servo_name == 'Mouth':
        value = (clamped_angle - 45) / (80 - 45) * 0.78  # Maps 45 to 0 and 80 to 0.78
    elif servo_name == 'Pitch':
        value = (clamped_angle - (-20)) / (15 - (-20)) * (0.3 - (-0.44)) + (-0.44)
    elif servo_name == 'Tilt':
        value = clamped_angle / 11 * 0.24  # Maps -11 to -0.24 and 11 to 0.24
    elif servo_name == 'Base':
        value = clamped_angle / 34 * 0.38  # Maps -34 to -0.38 and 34 to 0.38
    else:
        value = (clamped_angle - min_angle) / (max_angle - min_angle) * 2 - 1
    
    servos[servo_name].value = value
    
    print(f"{servo_name}: Angle: {clamped_angle}, Servo value: {value:.2f}")

def check_pitch_safety(pitch_angle):
    if not use_mouth_servo:
        return pitch_angle  # No safety check needed if mouth is disabled
    
    mouth_angle = get_current_angle('Mouth')
    if mouth_angle is None:  # Mouth servo is deactivated
        return pitch_angle  # No safety check needed if mouth is deactivated
    
    mouth_midpoint = (servo_configs['Mouth']['range'][0] + servo_configs['Mouth']['range'][1]) / 2
    
    if mouth_angle < mouth_midpoint:
        # Mouth is more than halfway open
        safe_pitch = max(pitch_angle, 0)  # Prevent forward tilt
        if safe_pitch != pitch_angle:
            print("Safety constraint: Limiting forward tilt due to open mouth.")
        return safe_pitch
    return pitch_angle

def get_current_angle(servo_name):
    if servo_name == 'Mouth' and not use_mouth_servo:
        return None  # Mouth servo is disabled
    
    servo = servos[servo_name]
    if servo.value is None:
        return None  # Servo is deactivated
    
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    if servo_name == 'Mouth':
        return servo.value / 0.78 * (80 - 45) + 45
    elif servo_name == 'Pitch':
        return (servo.value - (-0.44)) / (0.3 - (-0.44)) * (15 - (-20)) + (-20)
    elif servo_name == 'Tilt':
        return servo.value / 0.24 * 11
    elif servo_name == 'Base':
        return servo.value / 0.38 * 34
    else:
        return (servo.value + 1) / 2 * (max_angle - min_angle) + min_angle

def reset_servo(servo_name):
    if servo_name == 'Mouth' and not use_mouth_servo:
        print(f"Mouth servo is disabled. Skipping reset.")
        return
    
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
        if name == 'Mouth' and not use_mouth_servo:
            continue
        set_servo_angle(name, servo_configs[name]['rest'])
    print("All active servos activated and reset to rest positions.")

def move_to_angle(servo_name, target_angle, duration):
    start_angle = get_current_angle(servo_name)
    start_time = time.time()
    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        progress = elapsed / duration
        current_angle = start_angle + (target_angle - start_angle) * progress
        set_servo_angle(servo_name, current_angle)
        time.sleep(0.02)  # 50Hz update rate

def random_head_movement(duration):
    base_angle = random.uniform(-34, 34)
    pitch_angle = random.uniform(-20, 15)
    tilt_angle = random.uniform(-11, 11)
    
    move_to_angle('Base', base_angle, duration)
    move_to_angle('Pitch', pitch_angle, duration)
    move_to_angle('Tilt', tilt_angle, duration)

def random_mouth_movement(duration):
    if not use_mouth_servo:
        return  # Skip mouth movement if disabled
    
    open_angle = random.uniform(45, 70)  # Open mouth to a random position
    move_to_angle('Mouth', open_angle, duration / 2)  # Open mouth
    time.sleep(0.1)  # Short pause
    move_to_angle('Mouth', 80, duration / 2)  # Close mouth

def demo_animation():
    print("Starting demo animation. Press Ctrl+C to stop.")
    try:
        while True:
            # Activate servos and ensure they're at rest positions
            activate_all_servos()
            
            # Run animation for about a minute
            start_time = time.time()
            while time.time() - start_time < 60:
                movement_duration = random.uniform(0.5, 2.0)
                random_head_movement(movement_duration)
                
                # 30% chance to move mouth
                if random.random() < 0.3:
                    random_mouth_movement(movement_duration)
                
                time.sleep(0.1)  # Small pause between movements
            
            # Reset to rest positions
            reset_all_servos()
            
            # Deactivate servos to power them down
            deactivate_all_servos()
            
            # Pause for a minute
            print("Pausing animation for 60 seconds...")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("Demo animation stopped.")
    finally:
        activate_all_servos()  # Ensure servos are active before resetting
        reset_all_servos()
        deactivate_all_servos()

def debug_servo_limits(servo_name):
    if servo_name == 'Mouth' and not use_mouth_servo:
        print("Mouth servo is currently disabled.")
        return
    
    print(f"\nTesting {servo_name} limits:")
    config = servo_configs[servo_name]
    min_angle, max_angle = config['range']
    
    current_angle = config['rest']  # Start at rest position
    set_servo_angle(servo_name, current_angle)
    print(f"Starting at rest position: {current_angle} degrees")
    
    while True:
        action = input("Enter '+' to increase by 1 degree, '-' to decrease by 1 degree, 'r' to reset, or 'q' to quit: ").strip().lower()
        
        if action == '+':
            current_angle = min(current_angle + 1, max_angle)
        elif action == '-':
            current_angle = max(current_angle - 1, min_angle)
        elif action == 'r':
            current_angle = config['rest']
        elif action == 'q':
            break
        else:
            print("Invalid input. Please try again.")
            continue
        
        set_servo_angle(servo_name, current_angle)
        time.sleep(0.5)
    
    # Return to rest position before exiting
    reset_servo(servo_name)

def main_menu():
    global use_mouth_servo  # Add this line to allow modification of the global variable

    while True:
        print("\nMain Menu:")
        print("1. Run Demo Animation")
        print("2. Debug Servo Limits")
        print("3. Toggle Mouth Servo")  # Add this option
        print("4. Exit")
        choice = input("Enter your choice (1-4): ").strip()

        if choice == '1':
            demo_animation()
        elif choice == '2':
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
        elif choice == '3':
            use_mouth_servo = not use_mouth_servo
            print(f"Mouth servo is now {'enabled' if use_mouth_servo else 'disabled'}.")
        elif choice == '4':
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
