"""Controls the LED."""

import logging

import digitalio

from pins import LED

log = logging.getLogger(__name__)

_led = digitalio.DigitalInOut(LED)
_led.direction = digitalio.Direction.OUTPUT


def set(value: bool) -> None:
    """Sets the LED to the given value."""
    _led.value = value
    log.debug(f"LED set to {value}")
