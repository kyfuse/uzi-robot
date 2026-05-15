"""Controls the TFT display."""

import logging

import digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw

from pins import TFT_CS, TFT_DC, TFT_RESET

log = logging.getLogger(__name__)

import board  # noqa: E402

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
_UZI_IMAGE = Image.open("img/uzi.png")


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
    _disp.image(img, x=y, y=WIDTH - x - img.width)


def draw_image(img: Image) -> None:
    """Draws an image covering the entire display."""
    if img.width != WIDTH or img.height != HEIGHT:
        raise ValueError(
            f"Image width {img.width} and height {img.height} must match display width {WIDTH} and height {HEIGHT}"
        )
    draw_image_rect(0, 0, img)


def draw_uzi() -> None:
    """Draws Uzi on the display."""
    draw_image(_UZI_IMAGE)


def draw_face(openness: float) -> None:
    """Draws Uzi's mouth open by the given amount. openness is clamped to [0, 1]."""
    openness = max(0.0, min(1.0, float(openness**0.3)))
    x = 149
    y = 196
    face_width = 42
    face_height = 21
    face = _UZI_IMAGE.crop((x, y, x + face_width, y + face_height))
    if openness > 0.02:
        draw = ImageDraw.Draw(face)
        max_inset = face_height // 2
        inset = int(round((1.0 - openness) * max_inset))
        draw.ellipse(
            (0, inset * 0.5, face.width, face.height - inset * 1.4),
            fill=(0, 0, 0),
            outline=(33, 75, 86),
            width=2,
        )
    draw_image_rect(x, y, face)
