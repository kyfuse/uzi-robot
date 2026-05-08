# NOTE: This script did not work when I tried it
import adafruit_bno08x
import serial
from adafruit_bno08x.uart import BNO08X_UART

uart = serial.Serial("/dev/ttyTHS1", 3000000)

bno = BNO08X_UART(uart, debug=True)
print("next")

bno.enable_feature(adafruit_bno08x.BNO_REPORT_ROTATION_VECTOR)

print("Rotation Vector Quaternion:")
quat_i, quat_j, quat_k, quat_real = bno.quaternion
print("I: %0.6f  J: %0.6f K: %0.6f  Real: %0.6f" % (quat_i, quat_j, quat_k, quat_real))
