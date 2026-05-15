"""Main entry point for Uzi."""

import logging
import threading
import time

import colorlog
from dotenv import load_dotenv

import audio
import brain
import display
import gait
import imu
import led
import servos
import stt
import tts

load_dotenv()


def setup_logging():
    """Sets up color logging."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(thin_white)s%(asctime)s%(reset)s %(log_color)s %(levelname)-8s%(reset)s %(blue)s%(name)s%(reset)s  %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


setup_logging()

log = logging.getLogger("uzi")
should_walk = threading.Event()


def walk_test():
    try:
        servos.reset_all()
        input("Press Enter to continue...")
        # gait.initialize()
        # for _ in range(4):
        #     gait.take_step(step_length=1.0, step_velocity=0.5)

        servos.set_angle(servos.RIGHT_HIP, -30)
        servos.set_angle(servos.RIGHT_KNEE, -30)
        servos.set_angle(servos.RIGHT_ANKLE, 0)
        input("Press Enter to continue...")
        servos.set_angle(servos.RIGHT_HIP, 0)
        servos.set_angle(servos.RIGHT_KNEE, 0)
        servos.set_angle(servos.RIGHT_ANKLE, 0)
        input("Press Enter to continue...")
        servos.set_angle(servos.LEFT_HIP, -20)
        servos.set_angle(servos.LEFT_KNEE, -20)
        servos.set_angle(servos.LEFT_ANKLE, 0)
        input("Press Enter to continue...")
        servos.set_angle(servos.LEFT_HIP, 0)
        servos.set_angle(servos.LEFT_KNEE, 0)
        servos.set_angle(servos.LEFT_ANKLE, 0)
        input("Press Enter to continue...")

        servos.reset_all()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt detected, resetting servos")
        servos.reset_all()


def robot_move_forward():
    log.info("Moving forward")
    should_walk.set()
    for i in range(8):
        led.set(False)
        time.sleep(0.1)
        led.set(True)
        time.sleep(0.1)
    return "ok"


def robot_stop():
    log.info("Stopping")
    should_walk.clear()
    for i in range(3):
        led.set(False)
        time.sleep(0.5)
        led.set(True)
        time.sleep(0.5)
    return "ok"


def walk():
    servos.set_angle(servos.RIGHT_HIP, -35)
    servos.set_angle(servos.RIGHT_KNEE, -35)
    servos.set_angle(servos.RIGHT_ANKLE, 0)
    time.sleep(0.25)
    servos.set_angle(servos.RIGHT_HIP, 0)
    servos.set_angle(servos.RIGHT_KNEE, 0)
    servos.set_angle(servos.RIGHT_ANKLE, 0)
    time.sleep(0.25)
    servos.set_angle(servos.LEFT_HIP, -35)
    servos.set_angle(servos.LEFT_KNEE, -35)
    servos.set_angle(servos.LEFT_ANKLE, 0)
    time.sleep(0.25)
    servos.set_angle(servos.LEFT_HIP, 0)
    servos.set_angle(servos.LEFT_KNEE, 0)
    servos.set_angle(servos.LEFT_ANKLE, 0)
    time.sleep(0.25)


def _walk_loop():
    """Background thread: walks while should_walk is set, idles otherwise."""
    was_walking = False
    while True:
        if should_walk.is_set():
            was_walking = True
            try:
                walk()
            except Exception:
                log.error("walk() failed", exc_info=True)
                should_walk.clear()
        else:
            if was_walking:
                servos.reset_all()
                was_walking = False
            should_walk.wait(timeout=0.1)


def main():
    log.info("Starting Uzi...")

    # walk_test()
    # return

    # Start modules
    audio.setup()
    stt.start(on_utterance=brain.on_utterance)
    brain.set_tool_handler("move_forward", robot_move_forward)
    brain.set_tool_handler("stop", robot_stop)
    brain.set_tool_handler("stay_silent", lambda: "ok")
    tts.start(on_amplitude=display.draw_face)
    brain.prewarm()
    brain.start(on_speak=tts.speak, on_speak_cancel=tts.interrupt)

    servos.reset_all()
    display.clear()

    threading.Thread(target=_walk_loop, daemon=True, name="walk").start()

    # Draw an image with RGB rectangles.
    time.sleep(1)
    display.draw_uzi()

    led.set(True)

    # imu._run_imu_thread()
    # for i in range(100):
    #     if stt.is_voice() is not None:
    #         log.info(f"Voice detected: {stt.is_voice()}")
    #     if stt.direction() is not None:
    #         log.info(f"Direction: {stt.direction()}")
    #     time.sleep(0.1)

    try:
        threading.Event().wait()  # block forever; Ctrl+C to exit
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
