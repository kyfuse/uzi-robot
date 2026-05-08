import logging

import serial
from adafruit_bno08x_rvc import BNO08x_RVC, RVCReadTimeoutError

log = logging.getLogger(__name__)

_uart = serial.Serial("/dev/ttyTHS1", 115200)
_rvc = BNO08x_RVC(_uart)

# Saved values from the last read
_last_imu_data = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def get_heading() -> tuple[float, float, float]:
    """Gets the latest heading of the IMU as (yaw, pitch, roll) in degrees. This is polled at 100 Hz, so can be up to 0.01s old."""
    log.debug(f"Yaw: {_last_imu_data[0]:.2f} Pitch: {_last_imu_data[1]:.2f} Roll: {_last_imu_data[2]:.2f}")
    return _last_imu_data[0], _last_imu_data[1], _last_imu_data[2]


def get_acceleration() -> tuple[float, float, float]:
    """Gets the latest acceleration of the IMU as (x, y, z) in m/s^2. This is polled at 100 Hz, so can be up to 0.01s old."""
    log.debug(f"Accel X: {_last_imu_data[3]:.2f} Y: {_last_imu_data[4]:.2f} Z: {_last_imu_data[5]:.2f}")
    return _last_imu_data[3], _last_imu_data[4], _last_imu_data[5]


def _read_imu_data() -> None:
    """Reads the IMU data from the serial port."""
    global _last_imu_data
    yaw, pitch, roll, x_accel, y_accel, z_accel = _rvc.heading
    _last_imu_data = (yaw, pitch, roll, x_accel, y_accel, z_accel)


def _run_imu_thread() -> None:
    """Continuously polls the IMU for data."""
    log.debug("Running IMU thread")
    while True:
        try:
            _read_imu_data()
        except RVCReadTimeoutError:
            log.warning("IMU read timeout, retrying...")
        except Exception:
            log.exception("IMU thread error")
            break
