"""Configures the Jetson and ReSpeaker audio system."""

import struct
import subprocess
import threading
import time
from typing import Optional

import usb.core
import usb.util

import util

log = util.get_logger(__name__)

# How often to poll the ReSpeaker for VAD/DOA, in seconds.
_POLL_INTERVAL_S = 0.1

# _SPEAKER_VOLUME_PERCENT = 95
_SPEAKER_VOLUME_PERCENT = 90

# ReSpeaker parameters (param_id, offset, is_int)
_PARAM_VOICEACTIVITY = (19, 32, True)
_PARAM_DOAANGLE = (21, 0, True)
_PARAM_GAMMAVAD_SR = (19, 39, False)
_PARAM_ECHOONOFF = (19, 14, True)

# ReSpeaker USB 4-mic Array (XMOS XVF-3000) USB IDs and tuning protocol bits
_RESPEAKER_VID = 0x2886
_RESPEAKER_PID = 0x0018
_TUNING_TIMEOUT_MS = 100000

# Device names
_RESPEAKER_PRO_INPUT = "alsa_input.usb-SEEED_ReSpeaker_4_Mic_Array__UAC1.0_-00.pro-input-0"
_USB_SPEAKER_STEREO_OUTPUT = "alsa_output.usb-Jieli_Technology_UACDemoV1.0_4150344C3631390E-00.analog-stereo"

_tuning_dev = usb.core.find(idVendor=_RESPEAKER_VID, idProduct=_RESPEAKER_PID)
if _tuning_dev is None:
    raise RuntimeError("ReSpeaker mic array not found")
_tuning_lock = threading.Lock()
_stop = threading.Event()
_thread: Optional[threading.Thread] = None

# Saved values from the last read of the ReSpeaker VAD/DOA.
_last_vad: Optional[bool] = None
_last_doa: Optional[int] = None


def _init():
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
        ["pactl", "set-sink-volume", _USB_SPEAKER_STEREO_OUTPUT, f"{_SPEAKER_VOLUME_PERCENT}%"],
        check=True,
    )
    _set_respeaker_vad_threshold(3)
    _set_respeaker_echo_onoff(False)
    log.info("Audio setup complete")


def start() -> None:
    """Starts the ReSpeaker thread."""
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_run_respeaker_thread, daemon=True, name="respeaker-poll")
    _thread.start()


def stop() -> None:
    """Stop the ReSpeaker poll thread and release the USB handle.

    Must be called before process exit so no USB control transfer is in flight
    when the device handle is torn down — otherwise the ReSpeaker DSP can be
    left in a wedged state that survives until it's power-cycled.
    """
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2.0)
    # Take the lock so we can't race a transfer that slipped through between
    # the stop signal and the thread actually noticing it.
    with _tuning_lock:
        try:
            usb.util.dispose_resources(_tuning_dev)
        except Exception:
            log.error("Failed to dispose ReSpeaker USB resources", exc_info=True)


def _run_respeaker_thread() -> None:
    """Continuously polls the ReSpeaker for VAD/DOA."""
    log.info("Running ReSpeaker poll thread")
    while not _stop.is_set():
        try:
            _read_respeaker_state()
        except Exception:
            log.exception("ReSpeaker poll thread error")
            break
        if _stop.wait(_POLL_INTERVAL_S):
            break


def get_respeaker_vad() -> Optional[bool]:
    """ReSpeaker's onboard VAD. Returns True if it currently hears voice, False, or None if the device isn't reachable.

    Polled every 0.2s, so the value can be up to 0.2s old.
    """
    log.debug(f"VAD: {_last_vad}")
    return _last_vad


def get_respeaker_doa() -> Optional[int]:
    """ReSpeaker's direction-of-arrival in degrees [0, 360). Returns None if the device isn't reachable.

    Polled every 0.2s, so the value can be up to 0.2s old.
    """
    log.debug(f"DOA: {_last_doa}")
    return _last_doa


def _read_respeaker_state() -> None:
    """Reads the VAD and DOA from the ReSpeaker and caches them."""
    global _last_vad, _last_doa
    vad_val = _read_respeaker_param(_PARAM_VOICEACTIVITY)
    _last_vad = None if vad_val is None else bool(vad_val)
    _last_doa = _read_respeaker_param(_PARAM_DOAANGLE)


def _set_respeaker_vad_threshold(value: float) -> bool:
    """Set ReSpeaker GAMMAVAD_SR (default 15, lower = more sensitive). Returns False if the device isn't reachable."""
    return _write_respeaker_param(_PARAM_GAMMAVAD_SR, value)


def _set_respeaker_echo_onoff(value: bool) -> bool:
    """Set ReSpeaker ECHOONOFF (default 0, 1 = echo on, 0 = echo off). Returns False if the device isn't reachable."""
    return _write_respeaker_param(_PARAM_ECHOONOFF, value)


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


_init()


if __name__ == "__main__":
    while True:
        print(f"vad: {get_respeaker_vad()}, doa: {get_respeaker_doa()}")
        time.sleep(0.1)
