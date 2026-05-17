"""Main entry point for Uzi."""

import threading
import time

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
import util

load_dotenv()


log = util.get_logger("uzi")
should_walk = threading.Event()


def walk_test():
    try:
        servos.reset_all()
        input("Press Enter to continue...")
        gait.initialize()
        input("Press Enter to continue...")
        for _ in range(1):
            gait.take_step()
        input("Press Enter to continue...")

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
    audio.start()
    display.start()
    imu.start()
    stt.start(on_utterance=brain.on_utterance)
    tts.start(on_amplitude=display.draw_face)
    brain.set_tool_handler("move_forward", robot_move_forward)
    brain.set_tool_handler("stop", robot_stop)
    brain.set_tool_handler("stay_silent", lambda: "ok")
    brain.start(on_speak=tts.speak, on_speak_cancel=tts.interrupt)

    # Reset servos and display
    servos.reset_all()
    servos.start_dither()
    display.clear()
    time.sleep(1)
    display.draw_uzi()

    threading.Thread(target=_walk_loop, daemon=True, name="walk").start()

    # for i in range(100):
    #     if audio.get_respeaker_vad() is not None:
    #         log.info(f"Voice detected: {audio.get_respeaker_vad()}")
    #     if audio.get_respeaker_doa() is not None:
    #         log.info(f"Direction: {audio.get_respeaker_doa()}")
    #     log.info(f"Heading: {imu.get_heading()}")
    #     log.info(f"Acceleration: {imu.get_acceleration()}")
    #     time.sleep(0.1)

    led.set(True)
    try:
        threading.Event().wait()  # Block forever; Ctrl+C to exit
    except KeyboardInterrupt:
        log.info("Ctrl+C received, shutting down...")
    finally:
        _shutdown()


def _shutdown() -> None:
    """Stop background threads and release hardware before atexit cleanup runs.

    Order matters: stop the input/output stages first, then the hardware
    pollers, and finally the SPI display. Jetson.GPIO's atexit handler will
    deconfigure all pins after main() returns, so anything still touching
    SPI/GPIO/USB at that point will crash and can leave the ReSpeaker DSP
    wedged until the next power cycle.
    """
    log.info("Stopping background threads...")
    for name, fn in [
        ("stt", stt.stop),
        ("tts", tts.stop),
        ("audio", audio.stop),
        ("imu", imu.stop),
        ("servo-dither", servos.stop_dither),
        ("display", display.stop),
    ]:
        try:
            fn()
        except Exception:
            log.error(f"Error while stopping {name}", exc_info=True)
    log.info("Shutdown complete")


if __name__ == "__main__":
    main()
