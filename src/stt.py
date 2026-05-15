"""Streaming STT (microphone and ASR). Calls back with finalized utterances."""

import logging
import queue
import struct
import threading
from typing import Callable, Optional

import sherpa_onnx
import sounddevice as sd
import usb.core
import usb.util

log = logging.getLogger(__name__)


def start(on_utterance: Callable[[str, bool], None]) -> None:
    """Starts STT. on_utterance is called from the STT thread for each utterance. The boolean represents whether the utterance is finalized."""
    global _thread, _stream_in
    _stop.clear()
    _thread = threading.Thread(target=_worker, args=(on_utterance,), daemon=True, name="stt")
    _thread.start()
    _stream_in = sd.InputStream(
        channels=_RESPEAKER_CHANNELS,
        samplerate=_SR,
        dtype="float32",
        blocksize=320,
        callback=_audio_cb,
    )
    _stream_in.start()


def mute() -> None:
    """Drop incoming audio frames until unmute(). Used to suppress STT during TTS playback."""
    _muted.set()


def unmute() -> None:
    _muted.clear()


def is_voice() -> Optional[bool]:
    """ReSpeaker's onboard VAD. True if it currently hears voice. None if the device isn't reachable."""
    val = _read_tuning_param(*_PARAM_VOICEACTIVITY)
    return None if val is None else bool(val)


def direction() -> Optional[int]:
    """ReSpeaker's direction-of-arrival in degrees [0, 360). None if the device isn't reachable."""
    return _read_tuning_param(*_PARAM_DOAANGLE)


def set_vad_threshold(value: float) -> bool:
    """Set ReSpeaker GAMMAVAD_SR (default 15, lower = more sensitive). Caution: aggressive values can mute the processed channel; reset with 15 if STT goes silent."""
    return _write_tuning_param(*_PARAM_GAMMAVAD_SR, value)


def stop() -> None:
    global _stream_in
    _stop.set()
    if _stream_in is not None:
        try:
            _stream_in.stop()
            _stream_in.close()
        except Exception:
            log.error("Error while stopping audio stream")
        finally:
            _stream_in = None
    if _thread:
        _thread.join(timeout=2.0)


_MODEL = "models/sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06"
_SR = 16000
_RESPEAKER_CHANNELS = 6
_PROCESSED_CH = 0

# ReSpeaker USB 4-mic Array (XMOS XVF-3000) USB IDs and tuning protocol bits.
_RESPEAKER_VID = 0x2886
_RESPEAKER_PID = 0x0018
_TUNING_TIMEOUT_MS = 100000
# (param_id, offset, is_int) for the params we touch.
_PARAM_VOICEACTIVITY = (19, 32, True)
_PARAM_DOAANGLE = (21, 0, True)
_PARAM_GAMMAVAD_SR = (19, 39, False)

_rec: sherpa_onnx.OnlineRecognizer | None = None
_audio_q: queue.Queue = queue.Queue(maxsize=1000)
_stop = threading.Event()
_muted = threading.Event()
_thread: threading.Thread | None = None
_stream_in: sd.InputStream | None = None
_tuning_dev: Optional[usb.core.Device] = None
_tuning_lock = threading.Lock()


def _get_tuning_dev() -> Optional[usb.core.Device]:
    """Find the ReSpeaker tuning USB endpoint. Cached, returns None if absent."""
    global _tuning_dev
    if _tuning_dev is not None:
        return _tuning_dev
    try:
        _tuning_dev = usb.core.find(idVendor=_RESPEAKER_VID, idProduct=_RESPEAKER_PID)
    except Exception:
        log.error("ReSpeaker tuning USB lookup failed", exc_info=True)
        _tuning_dev = None
    if _tuning_dev is None:
        log.warning("ReSpeaker tuning device not found; VAD/DOA unavailable")
    return _tuning_dev


def _read_tuning_param(param_id: int, offset: int, is_int: bool) -> Optional[int]:
    """Read one ReSpeaker DSP parameter via vendor USB control transfer."""
    dev = _get_tuning_dev()
    if dev is None:
        return None
    cmd = 0x80 | offset | (0x40 if is_int else 0)
    try:
        with _tuning_lock:
            response = dev.ctrl_transfer(
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


def _write_tuning_param(param_id: int, offset: int, is_int: bool, value) -> bool:
    """Write one ReSpeaker DSP parameter via vendor USB control transfer."""
    dev = _get_tuning_dev()
    if dev is None:
        return False
    if is_int:
        payload = struct.pack(b"iii", offset, int(value), 1)
    else:
        payload = struct.pack(b"ifi", offset, float(value), 0)
    try:
        with _tuning_lock:
            dev.ctrl_transfer(
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


def _build_recognizer() -> sherpa_onnx.OnlineRecognizer:
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        encoder=f"{_MODEL}/encoder.onnx",
        decoder=f"{_MODEL}/decoder.onnx",
        joiner=f"{_MODEL}/joiner.onnx",
        tokens=f"{_MODEL}/tokens.txt",
        decoding_method="modified_beam_search",
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.0,
        rule2_min_trailing_silence=1.0,
        rule3_min_utterance_length=30.0,
    )


def _audio_cb(indata, frames, t, status):
    if status:
        log.warning(f"Audio status: {status}")
    if _muted.is_set():
        return
    try:
        _audio_q.put_nowait(indata[:, _PROCESSED_CH].copy())
    except queue.Full:
        log.warning("ASR queue full, dropping audio chunk")


def _worker(on_utterance: Callable[[str, bool], None]) -> None:
    log.info("Starting STT worker...")
    global _rec
    _rec = _build_recognizer()
    stream = _rec.create_stream()
    log.info("STT worker ready")

    last = ""
    was_muted = False
    while not _stop.is_set():
        if _muted.is_set():
            if not was_muted:
                was_muted = True
                while True:
                    try:
                        _audio_q.get_nowait()
                    except queue.Empty:
                        break
                try:
                    _rec.reset(stream)
                except Exception:
                    log.error("STT reset failed on mute")
                last = ""
            try:
                _audio_q.get(timeout=0.1)
            except queue.Empty:
                pass
            continue
        was_muted = False
        try:
            chunk = _audio_q.get(timeout=0.1)
        except queue.Empty:
            continue
        try:
            stream.accept_waveform(_SR, chunk)
            while _rec.is_ready(stream):
                _rec.decode_stream(stream)
            text = _rec.get_result(stream).strip()
        except Exception:
            log.error("STT decode pipeline failed")
            continue
        if not text:
            continue
        if text != last:
            log.info(f"Partial: {text!r}")
            try:
                on_utterance(text, False)
            except Exception:
                log.error("on_utterance callback failed for partial")
            last = text
        try:
            is_endpoint = _rec.is_endpoint(stream)
        except Exception:
            log.error("STT endpoint detection failed")
            is_endpoint = False
        if is_endpoint and text.strip() != "Okay." and text.strip() != "Okay?":  # Weird case when there's silence
            log.info(f"Final: {text!r}")
            try:
                on_utterance(text, True)
            except Exception:
                log.error("on_utterance callback failed for final")
            try:
                _rec.reset(stream)
            except Exception:
                log.error("STT reset failed after endpoint")
            last = ""
