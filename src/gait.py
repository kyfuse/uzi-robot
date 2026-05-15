"""Bipedal walking gait, ported from the Arduino instructable."""

import logging
import math
import time

import servos

log = logging.getLogger(__name__)

# Leg geometry (cm) — measure yours; these are from the original.
L1 = 5.0  # thigh
L2 = 5.7  # shin

# Gait parameters
STEP_HEIGHT = 10.6  # nominal hip-to-foot distance while standing
STEP_CLEARANCE = 1.0  # how far swing foot lifts


def _ik(x: float, z: float) -> tuple[float, float, float]:
    """Sagittal-plane IK for one leg.

    x = forward foot offset from hip, z = downward foot offset from hip.
    Returns (hip, knee, ankle) in degrees in the kinematic frame.
    """
    hip_rad2 = math.atan(x / z)
    z2 = z / math.cos(hip_rad2)
    hip_rad1 = math.acos((L1**2 + z2**2 - L2**2) / (2 * L1 * z2))
    knee_rad = math.pi - math.acos((L1**2 + L2**2 - z2**2) / (2 * L1 * L2))
    ankle_rad = math.pi / 2 + hip_rad2 - math.acos((L2**2 + z2**2 - L1**2) / (2 * L2 * z2))
    return (
        math.degrees(hip_rad1 + hip_rad2),
        math.degrees(knee_rad),
        math.degrees(ankle_rad),
    )


# IK at the standing pose. We subtract these so set_angle(..., 0) == standing,
# matching what your servos lib already expects.
_STAND_HIP, _STAND_KNEE, _STAND_ANKLE = 0, 0, 90


def pos(x: float, z: float, leg: str) -> None:
    """Command one foot to (x, z) relative to its hip. leg is 'l' or 'r'."""
    hip_deg, knee_deg, ankle_deg = _ik(x, z)
    hip = hip_deg - _STAND_HIP
    knee = knee_deg - _STAND_KNEE
    ankle = ankle_deg - _STAND_ANKLE

    if leg == "l":
        servos.set_angle(servos.LEFT_HIP, hip)
        servos.set_angle(servos.LEFT_KNEE, knee)
        servos.set_angle(servos.LEFT_ANKLE, ankle)
    elif leg == "r":
        servos.set_angle(servos.RIGHT_HIP, hip)
        servos.set_angle(servos.RIGHT_KNEE, knee)
        servos.set_angle(servos.RIGHT_ANKLE, ankle)
    else:
        raise ValueError(f"leg must be 'l' or 'r', got {leg!r}")


def initialize(settle: float = 0.02) -> None:
    """Squat from nearly-straight legs down to the standing pose."""
    z = 10.7
    while z >= STEP_HEIGHT:
        pos(0, z, "l")
        pos(0, z, "r")
        time.sleep(settle)
        z -= 0.1


def take_step(step_length: float = 2.0, step_velocity: float = 0.05) -> None:
    """One full gait cycle: right-leg swing, then left-leg swing."""
    # Right plants and pushes back; left swings forward (lifted).
    i = step_length
    while i >= -step_length:
        pos(i, STEP_HEIGHT, "r")
        pos(-i, STEP_HEIGHT - STEP_CLEARANCE, "l")
        time.sleep(step_velocity)
        i -= 0.5

    # Swap.
    i = step_length
    while i >= -step_length:
        pos(-i, STEP_HEIGHT - STEP_CLEARANCE, "r")
        pos(i, STEP_HEIGHT, "l")
        time.sleep(step_velocity)
        i -= 0.5
