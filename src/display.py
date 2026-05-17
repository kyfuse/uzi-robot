"""Controls the TFT display.

Public draw functions validate their arguments synchronously and then dispatch
the actual SPI write to a background worker thread, so callers never block on
the display.
"""

import threading
from collections import deque
from typing import Callable

import digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw

import util
from pins import TFT_CS, TFT_DC, TFT_RESET

log = util.get_logger(__name__)

import board  # noqa: E402

_BAUDRATE = 4000000  # Works consistently
_UZI_IMAGE = Image.open("img/uzi.png")

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

# Pending draw jobs: (kind, callable). The kind lets us coalesce duplicate
# high-frequency requests (e.g. face frames) so a slow SPI write can't grow
# the queue unboundedly.
_jobs: "deque[tuple[str, Callable[[], None]]]" = deque()
_jobs_lock = threading.Lock()
_jobs_wake = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None


def start() -> None:
    """Starts the display thread."""
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_run_display_thread, daemon=True, name="display")
    _thread.start()


def stop() -> None:
    """Stop the display thread before process exit.

    Required so the SPI worker isn't mid-transfer when Jetson.GPIO's atexit
    cleanup tears down the chip-select pin — otherwise the next SPI write
    raises 'GPIO channel has not been set up as an OUTPUT'.
    """
    _stop.set()
    _jobs_wake.set()
    if _thread is not None:
        _thread.join(timeout=2.0)


def _run_display_thread() -> None:
    """Drains and executes queued draw jobs on the SPI bus."""
    log.info("Running display thread")
    while not _stop.is_set():
        _jobs_wake.wait()
        while not _stop.is_set():
            with _jobs_lock:
                if not _jobs:
                    _jobs_wake.clear()
                    break
                kind, fn = _jobs.popleft()
            try:
                fn()
            except Exception:
                log.error(f"Display job {kind!r} failed", exc_info=True)


def clear() -> None:
    """Queues a display clear. Returns immediately."""
    _enqueue("clear", _do_clear)


def draw_image(img: Image.Image) -> None:
    """Queues a draw of `img` covering the entire display. Returns immediately."""
    if img.width != WIDTH or img.height != HEIGHT:
        raise ValueError(
            f"Image width {img.width} and height {img.height} must match display width {WIDTH} and height {HEIGHT}"
        )
    draw_image_rect(0, 0, img)


def draw_image_rect(x: int, y: int, img: Image.Image) -> None:
    """Queues a draw of `img` with the top-left corner at (x, y). Returns immediately.

    Raises ValueError if the image would extend outside the display bounds.
    The image is referenced (not copied), so don't mutate it after calling.
    """
    if x < 0 or x + img.width > WIDTH or y < 0 or y + img.height > HEIGHT:
        raise ValueError(
            f"Image at ({x}, {y}) with width {img.width} and height {img.height} goes out of display width {WIDTH} and height {HEIGHT}"
        )
    _enqueue("image_rect", lambda: _do_draw_image_rect(x, y, img))


def draw_uzi() -> None:
    """Queues a draw of Uzi covering the entire display. Returns immediately."""
    _enqueue("uzi", lambda: _do_draw_image_rect(0, 0, _UZI_IMAGE))


def draw_face(openness: float) -> None:
    """Queues a draw of Uzi's mouth open by the given amount (clamped to [0, 1]).

    Coalesces with any already-pending face frame, so high-frequency callers
    (e.g. the TTS amplitude callback) only ever render the latest frame.
    """
    openness = max(0.0, min(1.0, float(openness**0.3)))
    _enqueue("face", lambda: _do_draw_face(openness), coalesce=True)


def _enqueue(kind: str, fn: Callable[[], None], coalesce: bool = False) -> None:
    with _jobs_lock:
        if coalesce and _jobs:
            # Drop any pending job of the same kind so only the latest runs.
            remaining = [item for item in _jobs if item[0] != kind]
            _jobs.clear()
            _jobs.extend(remaining)
        _jobs.append((kind, fn))
        _jobs_wake.set()


def _do_clear() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    log.debug("Clearing display")
    _disp.image(image)


def _do_draw_image_rect(x: int, y: int, img: Image.Image) -> None:
    log.debug(f"Drawing image at ({x}, {y}) with width {img.width}, height {img.height}")
    _disp.image(img, x=y, y=WIDTH - x - img.width)


def _do_draw_face(openness: float) -> None:
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
    _do_draw_image_rect(x, y, face)
