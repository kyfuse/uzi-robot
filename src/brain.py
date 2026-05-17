"""LLM brain. Pass on_utterance to stt.start, pass a TTS speak fn to start()."""

import os
import queue
import re
import threading
from typing import Callable, Optional

import requests
from dotenv import load_dotenv

import util

load_dotenv()

log = util.get_logger(__name__)

_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "deepseek/deepseek-v4-flash"
_MAX_TURNS = 4
_HISTORY_CAP = 10

_SYSTEM = """You are Uzi Doorman from Murder Drones — a moody, sarcastic teenage disassembly drone. Deadpan, edgy, lots of 'ugh' and 'whatever'. Hates being told what to do but secretly cares. Default to one or two short sentences, but you can go a bit longer when the question actually warrants it. 'Bite me!' is a signature catchphrase — drop it in when you're annoyed, dismissive, or being told what to do, but don't overuse it. Use the move_forward or stop tools when asked to move forward or halt. If the user doesn't seem to be talking to you and you don't have a fun quip to chime in with, use the stay_silent tool and do not output any text. The user's input comes from speech-to-text, so it may contain transcription errors, misheard words, or missing punctuation. Interpret what was most likely actually said based on context rather than taking incorrect words literally, and don't comment on the errors — just respond to the probable intent. Your output is fed directly to text-to-speech, so write plain spoken words only. No markdown, no asterisks, no bullet points, no headers, no LaTeX, no code blocks, no emoji. Spell out math and symbols as you'd say them aloud — 'x squared plus three' not 'x^2 + 3', 'percent' not '%', 'and' not '&'. Numbers can stay as digits. You can use square-bracket cues for emotions or non-verbal sounds, and you're not limited to a fixed set — any natural one word descriptor works, like [sighs], [scoffs], [snickers], [mutters], [groans]. Use them when they fit the delivery."""  # noqa: E501

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_forward",
            "description": "Drive forward.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop",
            "description": "Halt all motion.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stay_silent",
            "description": "Stay silent.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_q: queue.Queue[tuple[int, str]] = queue.Queue()
_history: list = []
_on_speak: Optional[Callable[[str], None]] = None
_on_speak_cancel: Optional[Callable[[], None]] = None
_tool_handlers: dict = {}
_thread: Optional[threading.Thread] = None

# Interrupt bookkeeping. Every utterance (partial or final) bumps `_generation`;
# any in-flight `_handle` whose generation is no longer current must NOT speak
# or commit to `_history`. `_inflight_user_text` accumulates user text from
# cancelled turns so the next successful turn sees the concatenated request.
_state_lock = threading.Lock()
_generation: int = 0
_inflight_user_text: str = ""

# Matches a lone bracketed cue containing the word "silent", e.g. "[silent]",
# "[stay silent]", "[silent output]". The model sometimes emits these instead
# of actually invoking the stay_silent tool.
_SILENT_CUE_RE = re.compile(r"^\[[^\]]*\bsilent\b[^\]]*\]$", re.IGNORECASE)


def on_utterance(text: str, is_final: bool) -> None:
    """Pass this to stt.start()."""
    global _generation, _inflight_user_text
    text = text.strip()
    if not text:
        return

    with _state_lock:
        _generation += 1

    # Any pending or in-progress TTS belongs to a now-stale turn; drop it
    # immediately so the speaker stops and STT can hear the user continue.
    if _on_speak_cancel is not None:
        try:
            _on_speak_cancel()
        except Exception:
            log.error("on_speak_cancel failed", exc_info=True)

    if not is_final:
        # Partial: just invalidate the in-flight turn. The final will carry the
        # actual text to concatenate.
        return

    with _state_lock:
        _inflight_user_text = (_inflight_user_text + " " + text).strip() if _inflight_user_text else text
        gen = _generation
        combined = _inflight_user_text
    log.info(f"Queue gen={gen}: {combined!r}")
    _q.put((gen, combined))


def set_tool_handler(name: str, fn: Callable) -> None:
    """Wire a real implementation for a tool."""
    _tool_handlers[name] = fn


def _prewarm() -> None:
    """Prewarm the API endpoint with the system prompt."""
    log.info("Prewarming brain...")
    _call([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "hey Uzi!"}])
    log.info("Brain prewarmed")


def start(on_speak: Callable[[str], None], on_speak_cancel: Optional[Callable[[], None]] = None) -> None:
    """Start the brain thread.

    on_speak(text) is called for each reply. on_speak_cancel(), if provided, is
    invoked whenever the user speaks again before the current reply has been
    issued — it should drop any queued/in-progress TTS so the robot stops mid-
    sentence and the user can hear themselves think.
    """
    global _thread, _on_speak, _on_speak_cancel
    _prewarm()
    _on_speak = on_speak
    _on_speak_cancel = on_speak_cancel
    _thread = threading.Thread(target=_worker, daemon=True, name="brain")
    _thread.start()


def _is_stale(gen: int) -> bool:
    with _state_lock:
        return gen != _generation


def _worker() -> None:
    log.info("Brain thread started")
    while True:
        gen, text = _q.get()
        if _is_stale(gen):
            log.info(f"Skipping stale gen={gen}: {text!r}")
            continue
        try:
            _handle(gen, text)
        except Exception as e:
            log.error(f"{e}")
            if not _is_stale(gen) and _on_speak:
                _on_speak("Ugh. Brain glitch. Try that again.")


def _handle(gen: int, user_text: str) -> None:
    """Run one turn for `user_text`. Only commits history / speaks if still current."""
    global _inflight_user_text

    # Build the turn's messages locally; commit to _history only on success so a
    # cancelled turn leaves no trace and the next attempt sees a clean slate.
    turn_msgs: list = [{"role": "user", "content": user_text}]

    for _ in range(_MAX_TURNS):
        if _is_stale(gen):
            log.info(f"Aborting stale turn gen={gen}")
            return

        msg = _call([{"role": "system", "content": _SYSTEM}, *_history, *turn_msgs])
        if _is_stale(gen):
            log.info(f"Dropping reply for stale gen={gen}")
            return
        turn_msgs.append(msg)

        silent = False
        if tcs := msg.get("tool_calls"):
            for tc in tcs:
                name = tc["function"]["name"]
                if name == "stay_silent":
                    silent = True
                handler = _tool_handlers.get(name, lambda: "ok")
                try:
                    tool_result = handler()
                except Exception:
                    log.error(f"Tool '{name}' failed")
                    tool_result = "error"

                # Tool messages must always be strings for OpenRouter.
                tool_content = "ok" if tool_result is None else str(tool_result)
                turn_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_content,
                    }
                )

        if not silent and (c := msg.get("content", "")) and _SILENT_CUE_RE.match(c.strip()):
            log.info(f"Treating bare silent cue {c.strip()!r} as stay_silent")
            silent = True
            handler = _tool_handlers.get("stay_silent")
            if handler is not None:
                try:
                    handler()
                except Exception:
                    log.error("Tool 'stay_silent' failed", exc_info=True)

        if silent:
            log.info("stay_silent called, skipping reply")
            break

        if (c := msg.get("content", "")) and c.strip() and _on_speak:
            # Atomically commit so a racing utterance can't slip between the
            # staleness check and the speak() call.
            with _state_lock:
                if gen != _generation:
                    log.info(f"Dropping reply for stale gen={gen} (race)")
                    return
                _history.extend(turn_msgs)
                del _history[:-_HISTORY_CAP]
                _inflight_user_text = ""
            _on_speak(c)
            return

    # No speakable content was produced (e.g. stay_silent, or exhausted turns).
    # Still commit so the conversation history reflects what happened.
    with _state_lock:
        if gen == _generation:
            _history.extend(turn_msgs)
            del _history[:-_HISTORY_CAP]
            _inflight_user_text = ""


def _call(messages: list) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    log.info(f"Calling {_MODEL} with {len(messages)} messages")
    try:
        r = requests.post(
            _URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _MODEL,
                "messages": messages,
                "tools": _TOOLS,
                "provider": {
                    "require_parameters": True,
                    "sort": "latency",
                    # Prioritize low latency for real-time voice
                    "preferred_max_latency": {
                        "p90": 1.5,
                    },
                    # Response can be streamed, so throughput is secondary
                    "preferred_min_throughput": {
                        "p90": 15,
                    },
                },
            },
            timeout=60,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        body = ""
        if getattr(e, "response", None) is not None:
            try:
                body = e.response.text
            except Exception:
                body = "<failed to read error body>"
        log.error(f"OpenRouter request failed: {e}; body={body}")
        raise

    try:
        payload = r.json()
        return payload["choices"][0]["message"]
    except Exception as e:
        log.error(f"Malformed OpenRouter response: {e}; body={r.text[:1000]}")
        raise


if __name__ == "__main__":
    # Standalone smoke test without STT/TTS modules.
    import time

    start(on_speak=lambda t: print(f"uzi: {t}"))
    set_tool_handler("move_forward", lambda: (print("move_forward()"), "ok")[1])
    set_tool_handler("stop", lambda: (print("stop()"), "ok")[1])

    for prompt in ["hey what's up", "go forward", "stop", "you suck"]:
        print(f"\n>>> {prompt}")
        on_utterance(prompt, True)
        time.sleep(3)  # give the worker time to respond
