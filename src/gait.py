"""Bipedal walking gait, ported from the Arduino instructable."""

import math
import time

import numpy as np

import servos
import util

log = util.get_logger(__name__)

# Gait parameters
STAND_OFFSET_X = -0.75  # Foot position offset from center (cm)
STAND_HEIGHT = 10.2  # Hip-to-foot distance while standing (cm)
STEP_CLEARANCE = 0.5  # Highest distance that the swing foot lifts (cm)
STEP_LENGTH = 0.75  # Forward foot travel from either side of center (cm)
STEP_VELOCITY = 0.04  # Time between IK substeps (s)
SUBSTEPS = 8  # IK samples per swing phase; one cycle has 2*substeps frames

# Leg geometry
L1 = 5.0  # Thigh (cm)
L2 = 5.7  # Shin (cm)

# Foot names
LEFT_FOOT = "left"
RIGHT_FOOT = "right"


def set_standing_pose() -> None:
    """Squat from straight legs down to the standing pose."""
    change_symmetric_pose(0, L1 + L2, STAND_OFFSET_X, STAND_HEIGHT)


def set_straight_legs_pose() -> None:
    """Go from standing pose to fully extended legs."""
    change_symmetric_pose(STAND_OFFSET_X, STAND_HEIGHT, 0, L1 + L2)


def fix_straight_legs_pose() -> None:
    """Fix the straight legs pose."""
    servos.set_angle(servos.LEFT_HIP, 5)
    servos.set_angle(servos.RIGHT_HIP, 5)


def change_symmetric_pose(xi: float, zi: float, xf: float, zf: float) -> None:
    """Gradually change the symmetric pose from (xi, zi) to (xf, zf)."""
    for i in range(SUBSTEPS + 1):
        x = xi + (xf - xi) * i / SUBSTEPS
        z = zi + (zf - zi) * i / SUBSTEPS
        set_foot_pos(LEFT_FOOT, x, z)
        set_foot_pos(RIGHT_FOOT, x, z)
        time.sleep(STEP_VELOCITY)


def take_step() -> None:
    """One full gait cycle: right foot swing, then left foot swing."""
    # Phase 1: Right plants and pushes back, left swings forward (lifted)
    for k in range(SUBSTEPS + 1):
        i = STEP_LENGTH - 2 * STEP_LENGTH * k / SUBSTEPS  # Sweeps from +L to -L inclusive
        set_foot_pos(RIGHT_FOOT, i + STAND_OFFSET_X, STAND_HEIGHT)
        set_foot_pos(LEFT_FOOT, -i + STAND_OFFSET_X, STAND_HEIGHT - STEP_CLEARANCE)
        time.sleep(STEP_VELOCITY)

    # Phase 2: Swap
    for k in range(SUBSTEPS + 1):
        i = STEP_LENGTH - 2 * STEP_LENGTH * k / SUBSTEPS
        set_foot_pos(LEFT_FOOT, i + STAND_OFFSET_X, STAND_HEIGHT)
        set_foot_pos(RIGHT_FOOT, -i + STAND_OFFSET_X, STAND_HEIGHT - STEP_CLEARANCE)
        time.sleep(STEP_VELOCITY)


def set_foot_pos(foot: str, x: float, z: float) -> None:
    """
    Sets the position of the given foot to (x, z) relative to its hip.
    foot is LEFT_FOOT or RIGHT_FOOT.

    x and z are the forward and downward foot offsets from the hip joint.
    """
    log.debug(f"Commanding {foot} foot to ({x:6.02f}, {z:6.02f})")
    hip, knee, ankle = _ik(x, z)
    if foot == LEFT_FOOT:
        servos.set_angle(servos.LEFT_HIP, hip)
        servos.set_angle(servos.LEFT_KNEE, knee)
        servos.set_angle(servos.LEFT_ANKLE, ankle)
    elif foot == RIGHT_FOOT:
        servos.set_angle(servos.RIGHT_HIP, hip)
        servos.set_angle(servos.RIGHT_KNEE, knee)
        servos.set_angle(servos.RIGHT_ANKLE, ankle)
    else:
        raise ValueError(f"Invalid foot: {foot!r}")


def _ik(x: float, z: float) -> tuple[float, float, float]:
    """
    Given a desired foot position in a 2D frame, computes the (hip, knee, ankle) joint angles to achieve it, such that
    the hip angle is positive (hip goes forward). x and z are the forward and downward foot offsets from the hip joint.

    Joint angles are traced from the top down, with CCW angles as positive. The straight, standing pose is (0, 0, 0).
    """
    d = math.sqrt(x**2 + z**2)
    WARNING_THRESHOLD = 0.1
    if d < abs(L1 - L2) or d > L1 + L2:
        raise ValueError(f"Foot position is unreachable: d = {d}, L1 = {L1}, L2 = {L2}")
    elif d < WARNING_THRESHOLD or d > L1 + L2 - WARNING_THRESHOLD:
        log.warning(f"Foot position is close to the limit: d = {d}, L1 = {L1}, L2 = {L2}")
    theta_1 = math.acos((L2**2 + d**2 - L1**2) / (2 * L2 * d))
    theta_2 = math.acos((L1**2 + d**2 - L2**2) / (2 * L1 * d))
    theta_d = math.pi - theta_1 - theta_2
    theta_x = math.atan(x / z)
    theta_hip = theta_2 + theta_x
    theta_knee = theta_d - math.pi
    theta_ankle = -(theta_hip + theta_knee)
    return (
        math.degrees(theta_hip),
        math.degrees(theta_knee),
        math.degrees(theta_ankle),
    )


# Unit tests for IK
assert np.isclose(_ik(0.4, 10.0), (24.47711873649828, -41.53105254134537, 17.053933804847087), atol=1e-3).all()
assert np.isclose(_ik(-0.4, 10.0), (19.89589865122122, -41.53105254134537, 21.635153890124148), atol=1e-3).all()
assert np.isclose(_ik(0, 10.7), (0, 0, 0), atol=1e-3).all()


if __name__ == "__main__":
    import logging

    logging.getLogger().setLevel(logging.DEBUG)
    print("Walking test")

    # Old:
    # (24.47711873649828, 41.53105254134534, 72.94606619515294)
    # (19.89589865122122, 41.53105254134534, 68.36484610987587)
    # New:
    # (24.47711873649828, -41.53105254134537, 17.053933804847087)
    # (19.89589865122122, -41.53105254134537, 21.635153890124148)
    print("IK test 1:", _ik(0.4, 10.0))
    print("IK test 2:", _ik(-0.4, 10.0))
    print("IK test 3:", _ik(0, 10.7))

    servos.start_dither()
    servos.reset_all()
    fix_straight_legs_pose()
    input("Press Enter to continue...")
    set_standing_pose()
    input("Press Enter to continue...")
    take_step()
    input("Press Enter to continue...")
    for _ in range(4):
        take_step()
    input("Press Enter to continue...")
    set_straight_legs_pose()
    fix_straight_legs_pose()
    input("Press Enter to continue...")
    servos.reset_all()
    fix_straight_legs_pose()
    servos.stop_dither()
