"""Configures the Jetson and ReSpeaker audio system."""

import logging
import struct
import subprocess
import threading
from typing import Optional

import usb.core
import usb.util

log = logging.getLogger(__name__)

# ReSpeaker parameters (param_id, offset, is_int)
PARAM_VOICEACTIVITY = (19, 32, True)
PARAM_DOAANGLE = (21, 0, True)
PARAM_GAMMAVAD_SR = (19, 39, False)
PARAM_ECHOONOFF = (19, 14, True)

# ReSpeaker USB 4-mic Array (XMOS XVF-3000) USB IDs and tuning protocol bits
_RESPEAKER_VID = 0x2886
_RESPEAKER_PID = 0x0018
_TUNING_TIMEOUT_MS = 100000

# Device names
_RESPEAKER_PRO_INPUT = "alsa_input.usb-SEEED_ReSpeaker_4_Mic_Array__UAC1.0_-00.pro-input-0"
_USB_SPEAKER_STEREO_OUTPUT = "alsa_output.usb-Jieli_Technology_UACDemoV1.0_4150344C3631390E-00.analog-stereo"

# Find the ReSpeaker device
try:
    _tuning_dev = usb.core.find(idVendor=_RESPEAKER_VID, idProduct=_RESPEAKER_PID)
except Exception:
    log.error("ReSpeaker tuning USB lookup failed", exc_info=True)
    _tuning_dev = None
if _tuning_dev is None:
    log.warning("ReSpeaker tuning device not found; VAD/DOA unavailable")

_tuning_lock = threading.Lock()


def setup():
    """Sets up the Jetson and ReSpeaker audio system."""
    subprocess.run(
        ["pactl", "set-default-source", _RESPEAKER_PRO_INPUT],
        check=True,
    )
    subprocess.run(
        ["pactl", "set-default-sink", _USB_SPEAKER_STEREO_OUTPUT],
        check=True,
    )
    subprocess.run(
        ["pactl", "set-sink-volume", _USB_SPEAKER_STEREO_OUTPUT, "95%"],
        check=True,
    )
    _set_respeaker_vad_threshold(3)
    _set_respeaker_echo_onoff(False)
    log.info("Jetson and ReSpeaker audio setup complete")


def get_respeaker_vad() -> Optional[bool]:
    """ReSpeaker's onboard VAD. Returns True if it currently hears voice, False, or None if the device isn't reachable."""
    val = _read_respeaker_param(PARAM_VOICEACTIVITY)
    return None if val is None else bool(val)


def get_respeaker_doa() -> Optional[int]:
    """ReSpeaker's direction-of-arrival in degrees [0, 360). Returns None if the device isn't reachable."""
    return _read_respeaker_param(PARAM_DOAANGLE)


def _set_respeaker_vad_threshold(value: float) -> bool:
    """Set ReSpeaker GAMMAVAD_SR (default 15, lower = more sensitive). Returns False if the device isn't reachable."""
    return _write_respeaker_param(PARAM_GAMMAVAD_SR, value)


def _set_respeaker_echo_onoff(value: bool) -> bool:
    """Set ReSpeaker ECHOONOFF (default 0, 1 = echo on, 0 = echo off). Returns False if the device isn't reachable."""
    return _write_respeaker_param(PARAM_ECHOONOFF, value)


def _read_respeaker_param(param: tuple[int, int, bool]) -> Optional[int]:
    """Read a ReSpeaker DSP parameter via vendor USB control transfer. Returns None if the device isn't reachable."""
    param_id, offset, is_int = param
    cmd = 0x80 | offset | (0x40 if is_int else 0)
    try:
        with _tuning_lock:
            response = _tuning_dev.ctrl_transfer(
                usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
                0,
                cmd,
                param_id,
                8,
                _TUNING_TIMEOUT_MS,
            )
        value, exp = struct.unpack(b"ii", response.tobytes())
    except Exception:
        log.error("ReSpeaker tuning read failed", exc_info=True)
        return None
    return value if is_int else int(value * (2.0**exp))


def _write_respeaker_param(param: tuple[int, int, bool], value) -> bool:
    """Write a ReSpeaker DSP parameter via vendor USB control transfer. Returns False if the device isn't reachable."""
    param_id, offset, is_int = param
    if is_int:
        payload = struct.pack(b"iii", offset, int(value), 1)
    else:
        payload = struct.pack(b"ifi", offset, float(value), 0)
    try:
        with _tuning_lock:
            _tuning_dev.ctrl_transfer(
                usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
                0,
                0,
                param_id,
                payload,
                _TUNING_TIMEOUT_MS,
            )
    except Exception:
        log.error("ReSpeaker tuning write failed", exc_info=True)
        return False
    return True
