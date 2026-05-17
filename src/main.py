"""Main entry point for Uzi."""

import signal
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
_stop_event = threading.Event()


def _handle_signal(signum, _frame):
    """Trigger clean shutdown on SIGTERM (systemd stop) or SIGINT (Ctrl+C)."""
    log.info(f"Received signal {signal.Signals(signum).name}, shutting down...")
    _stop_event.set()


def _robot_move_forward():
    log.info("Moving forward")
    gait.start_walking()
    for _ in range(8):
        led.set(False)
        time.sleep(0.1)
        led.set(True)
        time.sleep(0.1)
    return "ok"


def _robot_stop():
    log.info("Stopping")
    gait.stop_walking()
    for _ in range(3):
        led.set(False)
        time.sleep(0.5)
        led.set(True)
        time.sleep(0.5)
    return "ok"


def _robot_stay_silent():
    display.set_loading_status(False)
    log.info("Staying silent")
    for _ in range(3):
        led.set(False)
        time.sleep(0.2)
        led.set(True)
        time.sleep(0.2)
    return "ok"


def _on_utterance(text: str, is_final: bool) -> None:
    # Show the loading overlay as soon as we've handed a finalized utterance off
    # to the brain; it will be cleared again when Uzi starts speaking.
    if is_final:
        display.set_loading_status(True)
    brain.on_utterance(text, is_final)


def _speak(text: str) -> None:
    display.set_loading_status(False)
    tts.speak(text)


def main():
    log.info("Starting Uzi...")

    # Start modules
    audio.start()
    display.start()
    imu.start()
    stt.start(on_utterance=_on_utterance)
    brain.set_tool_handler("move_forward", _robot_move_forward)
    brain.set_tool_handler("stop", _robot_stop)
    brain.set_tool_handler("stay_silent", _robot_stay_silent)
    brain.start(on_speak=_speak, on_speak_cancel=tts.interrupt)

    # Reset servos and display
    servos.reset_all()
    servos.start_dither()
    gait.fix_straight_legs_pose()
    gait.start()
    display.clear()
    time.sleep(1)
    display.draw_uzi()

    # Start TTS after drawing Uzi
    tts.start(on_amplitude=display.draw_face)

    # for i in range(100):
    #     if audio.get_respeaker_vad() is not None:
    #         log.info(f"Voice detected: {audio.get_respeaker_vad()}")
    #     if audio.get_respeaker_doa() is not None:
    #         log.info(f"Direction: {audio.get_respeaker_doa()}")
    #     log.info(f"Heading: {imu.get_heading()}")
    #     log.info(f"Acceleration: {imu.get_acceleration()}")
    #     time.sleep(0.1)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    led.set(True)
    try:
        _stop_event.wait()
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
    led.set(False)
    display.draw_3am()
    log.info("Stopping background threads...")
    for name, fn in [
        ("stt", stt.stop),
        ("tts", tts.stop),
        ("audio", audio.stop),
        ("imu", imu.stop),
        ("gait", gait.stop),
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
