import random
import time
from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory

# Use PiGPIO for hardware PWM (smoother servo control)
factory = PiGPIOFactory()

# Servo configurations
# travel: full physical servo range in degrees (e.g., 190 degrees)
# range: the artificial limits you want to use within that travel (e.g., -34 to 34)
servo_configs = {
    'Base':  {'pin': 23, 'travel': 190, 'range': (-36, 36), 'rest': 0},
    'Pitch': {'pin': 24, 'travel': 190, 'range': (-24, 19), 'rest': -0.13},
    'Tilt':  {'pin': 25, 'travel': 190, 'range': (-19, 19), 'rest': 0},
}

# Create Servo objects
servos = {}
for name, config in servo_configs.items():
    servos[name] = Servo(config['pin'], min_pulse_width=0.5/1000, max_pulse_width=2.5/1000, pin_factory=factory)

def set_servo_angle(servo_name, angle):
    config = servo_configs[servo_name]
    travel = config['travel']
    min_angle, max_angle = config['range']
    
    # Calculate the physical range
    max_physical = travel / 2
    
    # Clamp the angle to the defined limits
    clamped_angle = max(min_angle, min(angle, max_angle))
    
    # Convert angle to servo value: map directly to physical position
    value = clamped_angle / max_physical
    
    servos[servo_name].value = value

def get_current_angle(servo_name):
    servo = servos[servo_name]
    if servo.value is None:
        return None
    
    config = servo_configs[servo_name]
    travel = config['travel']
    
    # Calculate the physical range (same as in set_servo_angle)
    max_physical = travel / 2
    
    # Convert servo value back to angle (inverse of set_servo_angle)
    # servo_val -> angle: value = angle / max_physical, so angle = value * max_physical
    angle = servo.value * max_physical
    
    return angle

def reset_servo(servo_name):
    rest_position = servo_configs[servo_name]['rest']
    set_servo_angle(servo_name, rest_position)
    time.sleep(0.5)

def reset_all_servos():
    for servo_name in servos:
        reset_servo(servo_name)

def deactivate_all_servos():
    for servo in servos.values():
        servo.value = None

def activate_all_servos():
    for name in servos.keys():
        set_servo_angle(name, servo_configs[name]['rest'])

def move_to_angle(servo_name, target_angle, duration):
    start_angle = get_current_angle(servo_name)
    if start_angle is None:
        start_angle = servo_configs[servo_name]['rest']
    
    start_time = time.time()
    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        progress = elapsed / duration
        current_angle = start_angle + (target_angle - start_angle) * progress
        set_servo_angle(servo_name, current_angle)
        time.sleep(0.02)  # 50Hz update rate

def random_head_movement(duration):
    config = servo_configs
    base_angle = random.uniform(config['Base']['range'][0], config['Base']['range'][1])
    pitch_angle = random.uniform(config['Pitch']['range'][0], config['Pitch']['range'][1])
    tilt_angle = random.uniform(config['Tilt']['range'][0], config['Tilt']['range'][1])
    
    print(f"Moving to - Base: {base_angle:.1f}°, Pitch: {pitch_angle:.1f}°, Tilt: {tilt_angle:.1f}°")
    
    move_to_angle('Base', base_angle, duration)
    move_to_angle('Pitch', pitch_angle, duration)
    move_to_angle('Tilt', tilt_angle, duration)

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

if __name__ == "__main__":
    try:
        activate_all_servos()  # Ensure all servos are activated and at rest position at start
        demo_animation()
    except KeyboardInterrupt:
        print("Program stopped by user")
    finally:
        activate_all_servos()  # Ensure servos are active before final reset
        reset_all_servos()  # Ensure all servos return to rest position
        deactivate_all_servos()  # Deactivate all servos before exiting
        for servo in servos.values():
            servo.close()
