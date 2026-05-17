"""Provides servo control via the PCA9685 servo driver.

Optionally runs a background dither thread that alternates each servo's
commanded angle by +/- ``dither_offset`` degrees at a fixed rate. Dithering
helps cheap analog servos (e.g. FS5103B) hold position more stably by keeping
the control loop active instead of letting the servo coast into its dead band.
"""

import threading
import time

from adafruit_servokit import ServoKit

import util

log = util.get_logger(__name__)

# Servo numbers
RIGHT_ANKLE = 11
RIGHT_KNEE = 10
RIGHT_HIP = 9
LEFT_ANKLE = 4
LEFT_KNEE = 5
LEFT_HIP = 6

_SERVOS = [RIGHT_ANKLE, RIGHT_KNEE, RIGHT_HIP, LEFT_ANKLE, LEFT_KNEE, LEFT_HIP]
_CALIBRATED_ZERO_ANGLES = {
    RIGHT_ANKLE: 85,
    RIGHT_KNEE: 96,
    RIGHT_HIP: 94,
    LEFT_ANKLE: 83,
    LEFT_KNEE: 96,
    LEFT_HIP: 93,
}
_DIRECTION = {
    RIGHT_ANKLE: 1,
    RIGHT_KNEE: 1,
    RIGHT_HIP: -1,
    LEFT_ANKLE: -1,
    LEFT_KNEE: -1,
    LEFT_HIP: 1,
}
_SERVO_NAMES = {
    RIGHT_ANKLE: "right_ankle",
    RIGHT_KNEE: "right_knee",
    RIGHT_HIP: "right_hip",
    LEFT_ANKLE: "left_ankle",
    LEFT_KNEE: "left_knee",
    LEFT_HIP: "left_hip",
}

# Initialize servo kit
_kit = ServoKit(channels=16)
for servo_num in _SERVOS:
    _kit.servo[servo_num].set_pulse_width_range(600, 2400)

# Dither state. The "desired" angle is what the user asked for; the dither
# thread writes desired +/- offset to the servo at ``_dither_freq_hz``.
_desired_angles = {servo_num: 0.0 for servo_num in _SERVOS}
_state_lock = threading.Lock()
_dither_offset = 0.0  # Degrees; conservative for FS5103B; this does not work well at all
_dither_freq_hz = 50.0
_dither_stop = threading.Event()
_dither_thread: threading.Thread | None = None


def start_dither() -> None:
    """Starts the dither thread."""
    global _dither_thread
    if _dither_thread is not None and _dither_thread.is_alive():
        log.warning("Dither thread already running; ignoring start_dither()")
        return
    _dither_stop.clear()
    _dither_thread = threading.Thread(target=_run_dither_thread, daemon=True, name="servo-dither")
    _dither_thread.start()
    log.info(f"Started servo dither: offset={_dither_offset} deg, freq={_dither_freq_hz} Hz")


def stop_dither() -> None:
    """Stops the dither thread and re-centers each servo on its desired angle."""
    global _dither_thread
    if _dither_thread is None:
        return
    _dither_stop.set()
    _dither_thread.join(timeout=1.0)
    _dither_thread = None
    with _state_lock:
        for servo_num in _SERVOS:
            _write_servo_locked(servo_num, _desired_angles[servo_num])
    log.info("Stopped servo dither")


def reset_all() -> None:
    """Resets all servos to the fully extended legs position."""
    for servo_num in _SERVOS:
        set_angle(servo_num, 0)
    log.debug("Reset all servos to the fully extended legs position")


def set_angle(servo_num: int, angle: float, gradual=False) -> None:
    """Sets the angle of a servo. 0 is standing."""
    if servo_num not in _SERVOS:
        raise ValueError(f"Invalid servo number: {servo_num}")
    if angle < -80 or angle > 80:
        raise ValueError(f"Angle must be between -80 and 80, got {angle}")
    if gradual:
        with _state_lock:
            prev_angle = _desired_angles[servo_num]
        steps = max(1, int(abs(angle - prev_angle) / 1.0))
        for i in range(1, steps + 1):
            curr_angle = prev_angle + (angle - prev_angle) * (i / steps)
            with _state_lock:
                _desired_angles[servo_num] = curr_angle
                if not _dither_running():
                    _write_servo_locked(servo_num, curr_angle)
            time.sleep(0.01)
    else:
        with _state_lock:
            _desired_angles[servo_num] = angle
            if not _dither_running():
                _write_servo_locked(servo_num, angle)
    log.debug(f"Moved servo {_SERVO_NAMES[servo_num]:11} to {angle:6.02f} degrees")


def get_angle(servo_num: int) -> float:
    """Gets the commanded angle of a servo relative to the standing position. Note that this may not be the actual IRL angle."""
    if servo_num not in _SERVOS:
        raise ValueError(f"Invalid servo number: {servo_num}")
    with _state_lock:
        return _desired_angles[servo_num]


def _dither_running() -> bool:
    return _dither_thread is not None and _dither_thread.is_alive() and not _dither_stop.is_set()


def _write_servo_locked(servo_num: int, angle: float) -> None:
    """Writes the given user-facing angle to the servo. Caller must hold ``_state_lock``."""
    raw_angle = _CALIBRATED_ZERO_ANGLES[servo_num] + angle * _DIRECTION[servo_num]
    _kit.servo[servo_num].angle = raw_angle


def _run_dither_thread() -> None:
    """Continuously writes desired +/- offset to each servo, flipping each tick."""
    log.info("Running servo dither thread")
    sign = 1
    period = 1.0 / max(1.0, _dither_freq_hz)
    next_tick = time.monotonic()
    while not _dither_stop.is_set():
        try:
            with _state_lock:
                for servo_num in _SERVOS:
                    _write_servo_locked(servo_num, _desired_angles[servo_num] + sign * _dither_offset)
                # log.debug(f"Dithering servos: Desired {_desired_angles}")
        except Exception:
            log.exception("Dither thread error")
            break
        sign = -sign
        next_tick += period
        sleep_for = next_tick - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            # Fell behind; resync so we don't spin trying to catch up.
            next_tick = time.monotonic()
