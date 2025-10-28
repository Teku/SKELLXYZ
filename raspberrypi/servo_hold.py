from gpiozero import Servo
from time import sleep

servo1 = Servo(23)  # Base
servo2 = Servo(24)  # Pitch
servo3 = Servo(25)  # Tilt
servo4 = Servo(18)  # Mouth

try:
    # Move all servos to middle position
    servo1.mid()
    servo2.mid()
    servo3.mid()
    servo4.mid()

    print("Servos holding position. Press CTRL+C to stop.")
    while True:
        # Just sleep in a loop so they keep holding
        sleep(1)

except KeyboardInterrupt:
    print("\nServo stopped")
    # detach when exiting to release motors
    servo1.detach()
    servo2.detach()
    servo3.detach()
    servo4.detach()

