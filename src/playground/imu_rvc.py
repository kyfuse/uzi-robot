import serial
from adafruit_bno08x_rvc import BNO08x_RVC

uart = serial.Serial("/dev/ttyTHS1", 115200)
rvc = BNO08x_RVC(uart)

yaw, pitch, roll, x_accel, y_accel, z_accel = rvc.heading
print("Yaw: %2.2f Pitch: %2.2f Roll: %2.2f Degrees" % (yaw, pitch, roll))
print("Acceleration X: %2.2f Y: %2.2f Z: %2.2f m/s^2" % (x_accel, y_accel, z_accel))
