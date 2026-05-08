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
    rotation=90,  # 2.2", 2.4", 2.8", 3.2" ILI9341
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
image = Image.new("RGB", (width, height))

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))
disp.image(image)
time.sleep(1)

# Random pixel image
image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)
for i in range(width):
    for j in range(height):
        draw.point((i, j), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
disp.image(image)
time.sleep(1)

image = Image.open("blinka.png")

# Scale the image to the smaller screen dimension
image_ratio = image.width / image.height
screen_ratio = width / height
if screen_ratio < image_ratio:
    scaled_width = image.width * height // image.height
    scaled_height = height
else:
    scaled_width = width
    scaled_height = image.height * width // image.width
image = image.resize((scaled_width, scaled_height), Image.BICUBIC)

# Crop and center the image
x = scaled_width // 2 - width // 2
y = scaled_height // 2 - height // 2
image = image.crop((x, y, x + width, y + height))

# Display image.
disp.image(image)
time.sleep(1)

# Draw a bouncing ball
ball_x = width // 8
ball_y = height // 8
ball_size = width // 8
ball_color = (255, 0, 0)
ball_speed_x = 3
ball_speed_y = 3

while True:
    # Only draw the part with the ball\
    image = Image.new("RGB", (ball_size, ball_size))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, ball_size, ball_size), fill=ball_color)
    disp.image(image, x=ball_y, y=ball_x)
    time.sleep(0.01)
    ball_x += 2 * ball_speed_x
    ball_y += ball_speed_y
    if ball_x + ball_size >= width or ball_x < 0:
        ball_x -= 2 * ball_speed_x
        ball_speed_x = -ball_speed_x
    if ball_y + ball_size >= height or ball_y < 0:
        ball_y -= ball_speed_y
        ball_speed_y = -ball_speed_y


# while True:
#     # Draw a red background
#     image = Image.new("RGB", (width, height))
#     draw = ImageDraw.Draw(image)
#     draw.rectangle((0, 0, width, height), fill=(255, 0, 0))
#     disp.image(image)
