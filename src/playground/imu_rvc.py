import time

import serial
from adafruit_bno08x_rvc import BNO08x_RVC

uart = serial.Serial("/dev/ttyTHS1", 115200)
rvc = BNO08x_RVC(uart)

ZERO_PITCH = -87.5


def get_head_tilt(pitch: float, z_accel: float) -> float:
    """
    Positive means the robot is tilting forward.
    Need to do these calculations due to being near gimbal lock.
    """
    tilt_angle = abs(pitch - ZERO_PITCH)
    if z_accel > 0.0:
        return tilt_angle
    else:
        return -tilt_angle


while True:
    yaw, pitch, roll, x_accel, y_accel, z_accel = rvc.heading
    print("Yaw: %2.2f Pitch: %2.2f Roll: %2.2f Degrees" % (yaw, pitch, roll))
    print("Acceleration X: %2.2f Y: %2.2f Z: %2.2f m/s^2" % (x_accel, y_accel, z_accel))
    print(f"Head tilt: {get_head_tilt(pitch, z_accel):.2f} degrees")
    time.sleep(0.1)
