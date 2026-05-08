"""Main entry point for Uzi."""

import logging
import time

import colorlog
from dotenv import load_dotenv
from PIL import Image, ImageDraw

import display
import gait
import imu
import led
import servos

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
    root.setLevel(logging.DEBUG)


setup_logging()

log = logging.getLogger("uzi")


def walk_test():
    try:
        servos.reset_all()
        input("Press Enter to continue...")
        gait.initialize()
        for _ in range(4):
            gait.take_step(step_length=2.0, step_velocity=0.02)
        # Standing calibration
        # servos.set_angle(servos.RIGHT_HIP, -4)
        # servos.set_angle(servos.LEFT_HIP, -4)
        # servos.set_angle(servos.RIGHT_KNEE, 3)
        # servos.set_angle(servos.LEFT_KNEE, 3)
        # input("Press Enter to continue...")
        # servos.set_angle(servos.RIGHT_HIP, -40)
        # servos.set_angle(servos.RIGHT_KNEE, -40)
        # servos.set_angle(servos.RIGHT_ANKLE, 0)
        # time.sleep(3)
        # servos.set_angle(servos.RIGHT_HIP, 0)
        # servos.set_angle(servos.RIGHT_KNEE, 0)
        # servos.set_angle(servos.RIGHT_ANKLE, 0)
        # servos.set_angle(servos.LEFT_HIP, -40)
        # servos.set_angle(servos.LEFT_KNEE, -40)
        # servos.set_angle(servos.LEFT_ANKLE, 0)
        input("Press Enter to continue...")
        servos.reset_all()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt detected, resetting servos")
        servos.reset_all()


def main():
    log.info("Hello Uzi!")
    led.set(False)
    walk_test()
    return

    servos.reset_all()
    display.clear()

    # Draw an image with RGB rectangles.
    led.set(True)
    image = Image.new("RGB", (display.WIDTH, display.HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, display.WIDTH // 3, display.HEIGHT), fill=(255, 0, 0))
    draw.rectangle((display.WIDTH // 3, 0, display.WIDTH // 3 * 2, display.HEIGHT), fill=(0, 255, 0))
    draw.rectangle((display.WIDTH // 3 * 2, 0, display.WIDTH, display.HEIGHT), fill=(0, 0, 255))
    display.draw_image(image)
    display.draw_image_rect(0, 0, image)
    display.clear()

    for i in range(5):
        led.set(True)
        time.sleep(0.1)
        led.set(False)
        time.sleep(0.1)
    led.set(False)

    imu._run_imu_thread()


if __name__ == "__main__":
    main()
