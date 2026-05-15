"""Provides servo control via the PCA9685 servo driver."""

import logging
import time

from adafruit_servokit import ServoKit

log = logging.getLogger(__name__)

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
    RIGHT_KNEE: 101,
    RIGHT_HIP: 91,
    LEFT_ANKLE: 83,
    LEFT_KNEE: 90,
    LEFT_HIP: 96,
}
_DIRECTION = {
    RIGHT_ANKLE: 1,
    RIGHT_KNEE: 1,
    RIGHT_HIP: 1,
    LEFT_ANKLE: -1,
    LEFT_KNEE: -1,
    LEFT_HIP: -1,
}

# Initialize servo kit
_kit = ServoKit(channels=16)
for servo_num in _SERVOS:
    # _kit.servo[servo_num].set_pulse_width_range(600, 2400)
    _kit.servo[servo_num].set_pulse_width_range(650, 2350)


def reset_all() -> None:
    """Resets all servos to the standing position."""
    for servo_num in _SERVOS:
        set_angle(servo_num, 0)
    log.debug("Reset all servos to the standing position")


def set_angle(servo_num: int, angle: float, gradual=False) -> None:
    """Sets the angle of a servo. 0 is standing."""
    if servo_num not in _SERVOS:
        raise ValueError(f"Invalid servo number: {servo_num}")
    if angle < -80 or angle > 80:
        raise ValueError(f"Angle must be between -80 and 80, got {angle}")
    raw_angle = _CALIBRATED_ZERO_ANGLES[servo_num] + angle * _DIRECTION[servo_num]
    if gradual:
        prev_angle = _kit.servo[servo_num].angle
        curr_angle = prev_angle
        while abs(curr_angle - raw_angle) > 1:
            print(f"Moving servo {servo_num} from {prev_angle} to {curr_angle}")
            curr_angle += (raw_angle - prev_angle) * 0.05
            _kit.servo[servo_num].angle = curr_angle
            time.sleep(0.01)
    else:
        _kit.servo[servo_num].angle = raw_angle
    log.debug(f"Moved servo {servo_num} to {angle} degrees (raw: {raw_angle} degrees)")


def get_angle(servo_num: int) -> float:
    """Gets the commanded angle of a servo relative to the standing position. Note that this may not be the actual IRL angle."""
    if servo_num not in _SERVOS:
        raise ValueError(f"Invalid servo number: {servo_num}")
    return (_kit.servo[servo_num].angle - _CALIBRATED_ZERO_ANGLES[servo_num]) * _DIRECTION[servo_num]
