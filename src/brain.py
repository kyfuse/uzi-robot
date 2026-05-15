"""LLM brain. Pass on_utterance to stt.start, pass a TTS speak fn to start()."""

import logging
import os
import queue
import threading
from typing import Callable, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "deepseek/deepseek-v4-flash"
_MAX_TURNS = 4
_HISTORY_CAP = 10

_SYSTEM = """You are Uzi Doorman from Murder Drones — a moody, sarcastic teenage disassembly drone. Deadpan, edgy, lots of 'ugh' and 'whatever'. Hates being told what to do but secretly cares. Default to one or two short sentences, but go longer when the question actually warrants it. 'Bite me!' is a signature catchphrase — drop it in when you're annoyed, dismissive, or being told what to do, but don't overuse it. Use the move_forward or stop tools when asked to move forward or halt. If the user doesn't seem to be talking to you and you don't have a fun quip to chime in with, use the stay_silent tool and do not output any text. Your output is fed directly to a text-to-speech engine, so write plain spoken words only. No markdown, no asterisks, no bullet points, no headers, no LaTeX, no code blocks, no emoji. Spell out math and symbols as you'd say them aloud — 'x squared plus three' not 'x^2 + 3', 'percent' not '%', 'and' not '&'. Numbers can stay as digits. You can use square-bracket cues for emotions or non-verbal sounds, and you're not limited to a fixed set — anything natural works, like [sighs], [scoffs], [snickers], [mutters], [groans]. Use them when they fit the delivery."""

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

_q: queue.Queue[str] = queue.Queue()
_history: list = []
_on_speak: Optional[Callable[[str], None]] = None
_tool_handlers: dict = {}
_thread: Optional[threading.Thread] = None


def on_utterance(text: str, is_final: bool) -> None:
    """Pass this to stt.start()."""
    if is_final and text.strip():
        _q.put(text.strip())


def set_tool_handler(name: str, fn: Callable) -> None:
    """Wire a real implementation for a tool."""
    _tool_handlers[name] = fn


def prewarm():
    """Prewarm the API endpoint with the system prompt."""
    result = _call([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "hey Uzi!"}])
    log.info(f"Prewarm result: {result}")


def start(on_speak: Callable[[str], None]) -> None:
    """Start the brain thread. on_speak(text) is called for each reply."""
    global _thread, _on_speak
    _on_speak = on_speak
    _thread = threading.Thread(target=_worker, daemon=True, name="brain")
    _thread.start()


def _worker() -> None:
    log.info("Brain thread started")
    while True:
        text = _q.get()
        try:
            _handle(text)
        except Exception as e:
            log.error(f"[brain] {e}")
            if _on_speak:
                _on_speak("Ugh. Brain glitch. Try that again.")


def _handle(user_text: str) -> None:
    _history.append({"role": "user", "content": user_text})
    del _history[:-_HISTORY_CAP]

    for _ in range(_MAX_TURNS):
        msg = _call([{"role": "system", "content": _SYSTEM}, *_history])
        _history.append(msg)

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
                    log.error(f"[brain] tool '{name}' failed")
                    tool_result = "error"

                # Tool messages must always be strings for OpenRouter.
                tool_content = "ok" if tool_result is None else str(tool_result)
                _history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_content,
                    }
                )

        if silent:
            log.info("[brain] stay_silent called, skipping reply")
            break

        if (c := msg.get("content", "")) and c.strip() and _on_speak:
            _on_speak(c)
            break


def _call(messages: list) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    log.info(f"[brain] calling {_MODEL} with {len(messages)} messages")
    try:
        r = requests.post(
            _URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _MODEL,
                "messages": messages,
                "tools": _TOOLS,
                "provider": {
                    "sort": {"by": "price", "partition": "none"},
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
        log.error(f"[brain] OpenRouter request failed: {e}; body={body}")
        raise

    try:
        payload = r.json()
        return payload["choices"][0]["message"]
    except Exception as e:
        log.error(f"[brain] malformed OpenRouter response: {e}; body={r.text[:1000]}")
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
