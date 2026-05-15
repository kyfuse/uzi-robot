# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Be sure to check the learn guides for more usage information.

This example is for use on (Linux) computers that are using CPython with
Adafruit Blinka to support CircuitPython libraries. CircuitPython does
not support PIL/pillow (python imaging library)!

Author(s): Melissa LeBlanc-Williams for Adafruit Industries
"""

import random
import time

import board
import digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw

from pins import TFT_CS, TFT_DC, TFT_RESET

# Configuration for CS and DC pins (these are PiTFT defaults):
cs_pin = digitalio.DigitalInOut(TFT_CS)
dc_pin = digitalio.DigitalInOut(TFT_DC)
reset_pin = digitalio.DigitalInOut(TFT_RESET)

# Config for display baudrate (default max is 24mhz, works: 6 MHz, 7 MHz):
# BAUDRATE = 6000000  # Bits of corruption sometimes
BAUDRATE = 4000000  # Works consistently

# Setup SPI bus using hardware SPI:
spi = board.SPI()

# Create the display:
disp = ili9341.ILI9341(
    spi,
    rotation=90,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
)
time.sleep(1)

# Create blank image for drawing.
# Make sure to create image with mode 'RGB' for full color.
if disp.rotation % 180 == 90:
    height = disp.width  # we swap height/width to rotate it to landscape!
    width = disp.height
else:
    width = disp.width  # we swap height/width to rotate it to landscape!
    height = disp.height
print(f"width: {width}, height: {height}")

image = Image.open("img/uzi.png")
disp.image(image)




def update_face(face_type: str) -> None:
    """Draws a face on Uzi."""
    # TODO height float instead of face type
    face = base_crop.copy()
    draw = ImageDraw.Draw(face)
    if face_type == "big":
        draw.ellipse((0, 0, face.width, face.height), fill=(0, 0, 0), outline=(33, 75, 86), width=2)
    elif face_type == "medium":
        draw.ellipse((0, 2, face.width, face.height - 5), fill=(0, 0, 0), outline=(33, 75, 86), width=2)
    elif face_type == "small":
        draw.ellipse((0, 4, face.width, face.height - 10), fill=(0, 0, 0), outline=(33, 75, 86), width=2)
    elif face_type == "none":
        pass
    else:
        raise ValueError(f"Invalid face type: {face_type}")
    disp.image(face, x=y, y=width - x - face_width)


for i in range(10):
    update_face("big")
    time.sleep(0.1)
    update_face("medium")
    time.sleep(0.1)
    update_face("small")
    time.sleep(0.1)
    update_face("none")
    time.sleep(0.1)
