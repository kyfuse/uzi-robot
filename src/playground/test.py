import time

import Jetson.GPIO as GPIO

pin_num = 35
GPIO.setmode(GPIO.BOARD)
GPIO.setup(pin_num, GPIO.OUT)
print(f"Driving pin {pin_num} HIGH for 5 seconds...")
GPIO.output(pin_num, GPIO.HIGH)
time.sleep(5)
print(f"Driving pin {pin_num} LOW for 5 seconds...")
GPIO.output(pin_num, GPIO.LOW)
time.sleep(5)
GPIO.cleanup()
