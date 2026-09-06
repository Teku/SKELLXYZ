from gpiozero import Servo
from time import sleep

servo1 = Servo(23) # Base
servo2 = Servo(24) # Pitch
servo3 = Servo(25) # Tilt
servo4 = Servo(18) # Mouth

try:
    servo1.detach()
    servo2.detach()
    servo3.detach()
    servo4.detach()
except KeyboardInterrupt:
    print("servo stopped")
