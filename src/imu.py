import threading
import time

import serial
from adafruit_bno08x_rvc import BNO08x_RVC, RVCReadTimeoutError

import util

log = util.get_logger(__name__)

# Pitch when the robot is (nearly) upright.
ZERO_PITCH = -87.0

# Low-pass time constant (s) for the head-tilt derivative. Larger = smoother but more lag
# ~0.02s gives a ~8 Hz cutoff, which is comfortably above balance dynamics while rejecting IMU noise
_DTHETA_TAU = 0.02
# Reject pathological dt values (e.g. first sample, big stalls) so a single bad timestamp can't spike the D-term
_DTHETA_MIN_DT = 1e-4
_DTHETA_MAX_DT = 0.1

_uart = serial.Serial("/dev/ttyTHS1", 115200)
_rvc = BNO08x_RVC(_uart)
_stop = threading.Event()
_thread: threading.Thread | None = None

# Saved values from the last read
_last_imu_data = (0.0, ZERO_PITCH, 0.0, 0.0, 0.0, 0.0)
_last_head_theta = 0.0
_last_head_dtheta = 0.0
_last_theta_time: float | None = None


def start() -> None:
    """Starts the IMU thread."""
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_run_imu_thread, daemon=True, name="imu")
    _thread.start()


def stop() -> None:
    """Stop the IMU poll thread and close the UART."""
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2.0)
    try:
        _uart.close()
    except Exception:
        log.error("Failed to close IMU UART", exc_info=True)


def get_head_tilt() -> float:
    """
    0 means the robot is upright. Positive means the robot is tilting forward.
    This is polled at 100 Hz, so can be up to 0.01s old.
    """
    return _last_head_theta


def get_head_tilt_rate() -> float:
    """
    Low-pass filtered derivative of the head tilt, in degrees per second.
    Positive means tilting forward faster (or backward slower). Intended for
    the D-term of a balance PID controller.
    """
    return _last_head_dtheta


def get_heading() -> tuple[float, float, float]:
    """Gets the latest heading of the IMU as (yaw, pitch, roll) in degrees. This is polled at 100 Hz, so can be up to 0.01s old."""
    log.debug(f"Yaw: {_last_imu_data[0]:.2f} Pitch: {_last_imu_data[1]:.2f} Roll: {_last_imu_data[2]:.2f}")
    return _last_imu_data[0], _last_imu_data[1], _last_imu_data[2]


def get_acceleration() -> tuple[float, float, float]:
    """Gets the latest acceleration of the IMU as (x, y, z) in m/s^2. This is polled at 100 Hz, so can be up to 0.01s old."""
    log.debug(f"Accel X: {_last_imu_data[3]:.2f} Y: {_last_imu_data[4]:.2f} Z: {_last_imu_data[5]:.2f}")
    return _last_imu_data[3], _last_imu_data[4], _last_imu_data[5]


def _run_imu_thread() -> None:
    """Continuously polls the IMU for data."""
    log.info("Running IMU thread")
    while not _stop.is_set():
        try:
            _read_imu_data()
        except RVCReadTimeoutError:
            log.warning("IMU read timeout, retrying...")
        except Exception:
            log.exception("IMU thread error")
            break


def _read_imu_data() -> None:
    """Reads the IMU data from the serial port."""
    global _last_imu_data, _last_head_theta, _last_head_dtheta, _last_theta_time
    yaw, pitch, roll, x_accel, y_accel, z_accel = _rvc.heading
    _last_imu_data = (yaw, pitch, roll, x_accel, y_accel, z_accel)
    prev_theta = _last_head_theta
    if pitch < ZERO_PITCH:
        new_theta = 0.0
    else:
        tilt_angle = abs(pitch - ZERO_PITCH)
        if z_accel > 0.0:
            new_theta = tilt_angle
        else:
            new_theta = -tilt_angle
    _last_head_theta = new_theta

    # Compute head tilt derivative
    now = time.monotonic()
    if _last_theta_time is None:
        _last_head_dtheta = 0.0
    else:
        dt = now - _last_theta_time
        if _DTHETA_MIN_DT <= dt <= _DTHETA_MAX_DT:
            raw = (new_theta - prev_theta) / dt
            # First-order IIR low-pass: alpha derived from actual dt so the
            # cutoff stays consistent under loop-rate jitter
            alpha = dt / (_DTHETA_TAU + dt)
            _last_head_dtheta += alpha * (raw - _last_head_dtheta)
        # Else, skip this sample to avoid blowing up the filter
    _last_theta_time = now


if __name__ == "__main__":
    start()
    while True:
        print(
            f"Head tilt: {get_head_tilt():+6.2f} deg | rate: {get_head_tilt_rate():+7.2f} deg/s | raw pitch: {_last_imu_data[1]:+6.2f} deg"
        )
        time.sleep(0.1)
