from gpiozero import Servo
from time import sleep

servo1 = Servo(23) # Base
servo2 = Servo(24) # Pitch
servo3 = Servo(25) # Tilt
servo4 = Servo(18) # Mouth

try:
    servo1.mid()
    servo2.mid()
    servo3.mid()
    servo4.mid()
    # disconnect
    sleep(1)
    servo1.detach()
    servo2.detach()
    servo3.detach()
    servo4.detach()
except KeyboardInterrupt:
    print("servo stopped")
    servo1.detach()
    servo2.detach()
    servo3.detach()
    servo4.detach()
