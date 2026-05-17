"""Controls the LED."""

import digitalio

import util
from pins import LED

log = util.get_logger(__name__)

_led = digitalio.DigitalInOut(LED)
_led.direction = digitalio.Direction.OUTPUT
_led.value = False


def set(value: bool) -> None:
    """Sets the LED to the given value."""
    _led.value = value
    log.debug(f"LED set to {value}")
