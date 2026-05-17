"""Streaming TTS via Fish Audio. Call speak(text) to enqueue an utterance.

The audio output uses sounddevice's pull-based callback so that loudness can
be measured at the moment samples actually leave for the speaker, keeping any
amplitude-animation callback (`on_amplitude`) tightly synced to what's heard.
"""

import os
import queue
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from fish_audio_sdk import TTSRequest, WebSocketSession

import stt
import util

log = util.get_logger(__name__)

_UZI_VOICE_ID = "dbfcbb173fb84528ac4ccaf446026277"
_SAMPLE_RATE = 44100  # Fish PCM default
_TAIL_SECONDS = 0.2  # Extra grace after buffer drains before re-arming STT
_AMP_NORMALIZATION = 6000.0  # ~Typical speech RMS for int16; tune to taste
_AMP_SMOOTHING = 0.3  # 0 = no smoothing, closer to 1 = more sluggish
_amplitude_FPS = 60

_q: "queue.Queue[str]" = queue.Queue()
_stop = threading.Event()
_interrupt = threading.Event()
_thread: threading.Thread | None = None
_amplitude_thread: threading.Thread | None = None
_stream_out: sd.OutputStream | None = None
_on_amplitude: Optional[Callable[[float], None]] = None

_pcm_buf = bytearray()
_pcm_lock = threading.Lock()
_latest_amp: float = 0.0  # Written by audio callback, read by amplitude thread


def start(on_amplitude: Optional[Callable[[float], None]] = None) -> None:
    """Start the TTS thread and open the audio output stream.

    on_amplitude(level) is dispatched at ~60 Hz from a dedicated thread with
    a smoothed [0, 1] loudness value of audio currently leaving the speaker.
    Drops to ~0 between utterances. Useful for driving a mouth animation.
    """
    global _thread, _amplitude_thread, _stream_out, _on_amplitude
    _on_amplitude = on_amplitude
    _stop.clear()
    _stream_out = sd.OutputStream(
        samplerate=_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=0,
        latency="low",
        callback=_audio_cb,
    )
    _stream_out.start()
    _thread = threading.Thread(target=_worker, daemon=True, name="tts")
    _thread.start()
    _amplitude_thread = threading.Thread(target=_amplitude_worker, daemon=True, name="tts-amplitude")
    _amplitude_thread.start()


def stop() -> None:
    global _stream_out
    _stop.set()
    _q.put("")  # unblock the worker
    if _stream_out is not None:
        try:
            _stream_out.stop()
            _stream_out.close()
        except Exception:
            log.error("Error while stopping TTS audio stream")
        finally:
            _stream_out = None
    if _thread:
        _thread.join(timeout=2.0)
    if _amplitude_thread:
        _amplitude_thread.join(timeout=2.0)


def speak(text: str) -> None:
    """Enqueue text for speech synthesis. Safe to call from any thread."""
    text = text.strip()
    if text:
        _q.put(text)


def interrupt() -> None:
    """Drop everything queued and currently playing. Safe to call from any thread.

    Sets `_interrupt` so the worker bails out of any in-progress synthesis loop
    and play-out wait, drains the text queue, and clears the audio buffer so
    the speaker falls silent within ~one audio callback.
    """
    _interrupt.set()
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
    with _pcm_lock:
        _pcm_buf.clear()


def _audio_cb(outdata, frames: int, time_info, status) -> None:
    """Real-time audio callback. Pulls PCM from `_pcm_buf` and measures loudness."""
    global _latest_amp
    needed = frames * 2  # int16 mono
    with _pcm_lock:
        take = min(len(_pcm_buf), needed)
        chunk = bytes(_pcm_buf[:take])
        del _pcm_buf[:take]
    if take < needed:
        chunk += b"\x00" * (needed - take)
    # Underflow is expected when we're padding silence between utterances; only
    # warn if we actually had audio to deliver this callback.
    if status and not (status.output_underflow and take < needed):
        log.warning(f"TTS output status: {status}")
    samples = np.frombuffer(chunk, dtype=np.int16)
    outdata[:, 0] = samples
    if take > 0:
        real = samples[: take // 2].astype(np.float32)
        rms = float(np.sqrt(np.mean(real * real)))
        _latest_amp = min(1.0, rms / _AMP_NORMALIZATION)
    else:
        _latest_amp = 0.0


def _amplitude_worker() -> None:
    """Reads `_latest_amp` and dispatches `on_amplitude` outside the audio thread."""
    period = 1.0 / _amplitude_FPS
    smoothed = 0.0
    last_emitted = -1.0
    while not _stop.is_set():
        time.sleep(period)
        if _on_amplitude is None:
            continue
        smoothed = _AMP_SMOOTHING * smoothed + (1.0 - _AMP_SMOOTHING) * _latest_amp
        if abs(smoothed - last_emitted) < 0.01 and smoothed < 0.01:
            continue
        last_emitted = smoothed
        try:
            _on_amplitude(smoothed)
        except Exception:
            log.error("on_amplitude callback failed", exc_info=True)


def _build_request() -> TTSRequest:
    return TTSRequest(
        text="",
        reference_id=_UZI_VOICE_ID,
        format="pcm",
        latency="balanced",
        top_p=0.7,
        temperature=0.7,
        sample_rate=_SAMPLE_RATE,
    )


def _pcm_buf_len() -> int:
    with _pcm_lock:
        return len(_pcm_buf)


def _prewarm(api_key: str) -> None:
    log.info("Pre-warming TTS...")
    session = WebSocketSession(api_key)
    session.tts(_build_request(), iter(["Bite", "me!"]))
    session.close()
    log.info("TTS pre-warmed")


def _worker() -> None:
    log.info("Starting TTS worker...")
    api_key = os.environ.get("FISH_API_KEY")
    if not api_key:
        log.error("FISH_API_KEY is not set; TTS worker exiting")
        return
    _prewarm(api_key)
    session = WebSocketSession(api_key)
    log.info("TTS worker ready")

    while not _stop.is_set():
        try:
            text = _q.get(timeout=0.1)
        except queue.Empty:
            continue
        if not text or _stop.is_set():
            continue
        # Reset the interrupt flag for this fresh utterance. Any interrupt()
        # call that lands later will set it again and bail us out.
        _interrupt.clear()
        log.info(f"TTS: {text!r}")
        stt.mute()
        try:
            for chunk in session.tts(_build_request(), iter([text])):
                if _stop.is_set() or _interrupt.is_set():
                    break
                with _pcm_lock:
                    _pcm_buf.extend(chunk)
            while not _stop.is_set() and not _interrupt.is_set() and _pcm_buf_len() > 0:
                time.sleep(0.02)
        except Exception:
            log.error("TTS synthesis failed", exc_info=True)
        finally:
            if _interrupt.is_set():
                # Make sure no late-arriving chunk lingers, and skip the tail
                # grace so STT can capture the user's continued speech ASAP.
                with _pcm_lock:
                    _pcm_buf.clear()
            else:
                time.sleep(_TAIL_SECONDS)
            stt.unmute()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    start(on_amplitude=lambda a: print(f"amp={a:.2f}"))
    speak("Hey! I'm Uzi.")
    speak("[snarky] Bite me.")
    speak("What do you mean we're out of acid?!")
    time.sleep(15)
    stop()
