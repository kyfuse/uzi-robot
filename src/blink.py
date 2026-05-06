import time

import digitalio

from pins import STATUS_LED

print(f"Using pin {STATUS_LED} as status LED")
led = digitalio.DigitalInOut(STATUS_LED)
led.direction = digitalio.Direction.OUTPUT

try:
    while True:
        print("LED on")
        led.value = True
        time.sleep(1)
        led.value = False
        print("LED off")
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    print("Exiting...")
    led.value = False
    led.direction = digitalio.Direction.INPUT
    led.deinit()
