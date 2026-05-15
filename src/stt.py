"""Streaming STT (microphone and ASR). Calls back with finalized utterances."""

import logging
import queue
import threading
from typing import Callable

import numpy as np
import sherpa_onnx
import sounddevice as sd

log = logging.getLogger(__name__)


def start(on_utterance: Callable[[str, bool], None]) -> None:
    """Starts STT. on_utterance is called from the STT thread for each utterance. The boolean represents whether the utterance is finalized."""
    global _thread, _stream_in
    _stop.clear()
    _thread = threading.Thread(target=_worker, args=(on_utterance,), daemon=True, name="stt")
    _thread.start()
    _stream_in = sd.InputStream(
        channels=_RESPEAKER_CHANNELS,
        # channels=1,
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


_rec: sherpa_onnx.OnlineRecognizer | None = None
_audio_q: queue.Queue = queue.Queue(maxsize=1000)
_stop = threading.Event()
_muted = threading.Event()
_thread: threading.Thread | None = None
_stream_in: sd.InputStream | None = None


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
        # _audio_q.put_nowait(indata[:, 0].copy())
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    start(on_utterance=lambda text, is_final: print(f"UTT: {text!r} {'FINAL' if is_final else 'PARTIAL'}"))
    threading.Event().wait()
