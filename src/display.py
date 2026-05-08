"""Controls the TFT display."""

import logging

import board
import digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw

from pins import TFT_CS, TFT_DC, TFT_RESET

log = logging.getLogger(__name__)

_BAUDRATE = 4000000  # Works consistently

# Create display
_disp = ili9341.ILI9341(
    board.SPI(),
    rotation=90,
    cs=digitalio.DigitalInOut(TFT_CS),
    dc=digitalio.DigitalInOut(TFT_DC),
    rst=digitalio.DigitalInOut(TFT_RESET),
    baudrate=_BAUDRATE,
)

# Swap height/width to rotate display to landscape
WIDTH = _disp.height
HEIGHT = _disp.width


def clear() -> None:
    """Clears the display."""
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    log.debug("Clearing display")
    _disp.image(image)


def draw_image_rect(x: int, y: int, img: Image) -> None:
    """Draws an image with the top-left corner at (x, y). The offset must be within the image's bounds."""
    if x < 0 or x + img.width > WIDTH or y < 0 or y + img.height > HEIGHT:
        raise ValueError(
            f"Image at ({x}, {y}) with width {img.width} and height {img.height} goes out of display width {WIDTH} and height {HEIGHT}"
        )
    log.debug(f"Drawing image at ({x}, {y}) with width {img.width}, height {img.height}")
    _disp.image(img, x=x, y=y)


def draw_image(img: Image) -> None:
    """Draws an image covering the entire display."""
    if img.width != WIDTH or img.height != HEIGHT:
        raise ValueError(
            f"Image width {img.width} and height {img.height} must match display width {WIDTH} and height {HEIGHT}"
        )
    draw_image_rect(0, 0, img)
