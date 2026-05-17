"""
LLM brain. Pass on_utterance to stt.start, pass a TTS speak fn to start().

Note: The buggy version of this has speculative LLM execution, implemented
in a not-so-clean way by Claude Opus 4.7. It decreases end-to-end latency by
a substantial amount, but I didn't fully review the implementation as I'm sure
there is a cleaner way to implement it. However, the current code appears to
work in the average case, and it only runs into bugs semi-rarely. The non-buggy
version is more thoroughly tested.
"""

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

# Queue items are (gen, user_text, is_final). is_final=False entries are
# speculative LLM calls whose reply may be cached and reused if the eventual
# final's text matches.
_q: queue.Queue[tuple[int, str, bool]] = queue.Queue()
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

# Cached reply from the most recent *completed* speculative LLM call, as
# (input_text, reply_msg). Used to short-circuit the next final whose text
# matches the speculation's input. Cleared on every partial (a new partial
# means the speculation no longer reflects the latest transcription) and
# whenever a final consumes or rejects it.
_cached_speculation: Optional[tuple[str, dict]] = None

# (gen, input_text) of the most recent speculation that is either queued or
# currently being processed by the worker. Set by `on_utterance(partial,
# speculate=True)` at queue time so a final arriving while the spec sits
# behind a slower one in the queue can still promote it (not just one that
# happens to be mid-LLM-call). Overwritten on every partial. The worker only
# clears it after processing if its gen is still current (a newer partial
# would've already pointed it at a newer spec it doesn't own).
_active_speculation: Optional[tuple[int, str]] = None

# Set by `on_utterance` when a final's text matches `_active_speculation`.
# The worker reads this under the lock once its LLM call returns and, if
# True, speaks/commits the result as if it had been a final — or, if the
# result isn't directly speakable (tool calls, silent cue), tells the worker
# to re-run via the proper `_handle` flow.
_speculation_promoted: bool = False

# Matches a lone bracketed cue containing the word "silent", e.g. "[silent]",
# "[stay silent]", "[stay_silent]", "[silent output]". The model sometimes
# emits these instead of actually invoking the stay_silent tool. Underscores
# (and other non-letters) count as boundaries so "stay_silent" matches.
_SILENT_CUE_RE = re.compile(r"^\[[^\]]*(?<![a-z])silent(?![a-z])[^\]]*\]$", re.IGNORECASE)

# Used to compare a partial's input text to the eventual final's text. STT
# can tack on trailing punctuation (e.g. "hey" → "hey.") between the last
# partial and the final, so we strip non-word chars and lowercase before
# comparing.
_NORMALIZE_RE = re.compile(r"[\W_]+", re.UNICODE)


def _normalize_for_match(s: str) -> str:
    return _NORMALIZE_RE.sub(" ", s).strip().lower()


def on_utterance(text: str, is_final: bool, speculate: bool = False) -> None:
    """Pass this to stt.start().

    `speculate=True` on a partial kicks off a speculative LLM call whose
    reply will be reused if the eventual final's text matches. Should only
    be set when external evidence (e.g. VAD) suggests the user has paused.
    """
    global _generation, _inflight_user_text, _cached_speculation, _active_speculation, _speculation_promoted
    text = text.strip()
    if not text:
        return

    # Any pending or in-progress TTS belongs to a now-stale turn; drop it
    # immediately so the speaker stops and STT can hear the user continue.
    if _on_speak_cancel is not None:
        try:
            _on_speak_cancel()
        except Exception:
            log.error("on_speak_cancel failed", exc_info=True)

    if is_final:
        # Atomically: figure out whether this final can ride the coattails
        # of a speculative call. The lock spans the gen bump and history
        # commit so a racing follow-up utterance can't slip in between.
        speak_content: Optional[str] = None
        kind = "miss"
        with _state_lock:
            full_text = (_inflight_user_text + " " + text).strip() if _inflight_user_text else text
            cached = _cached_speculation
            active = _active_speculation
            normalized_full = _normalize_for_match(full_text)

            if cached is not None and _normalize_for_match(cached[0]) == normalized_full:
                # The speculation already came back; commit and speak now.
                _cached_speculation = None
                _generation += 1
                gen = _generation
                cached_input, cached_msg = cached
                _history.append({"role": "user", "content": cached_input})
                _history.append(cached_msg)
                del _history[:-_HISTORY_CAP]
                _inflight_user_text = ""
                speak_content = (cached_msg.get("content") or "").strip()
                kind = "cache_hit"
            elif active is not None and active[0] == _generation and _normalize_for_match(active[1]) == normalized_full:
                # The latest speculation (queued or mid-LLM-call) matches.
                # Promote it — leave generation alone so the worker keeps
                # treating it as current and reads `_speculation_promoted`
                # when its reply lands.
                _speculation_promoted = True
                gen = active[0]
                kind = "promoted"
            else:
                # No matching speculation. Bump gen (which makes any in-flight
                # or queued spec stale), drop the cache and active markers,
                # accumulate inflight text, queue a regular final.
                _cached_speculation = None
                _active_speculation = None
                _speculation_promoted = False
                _generation += 1
                gen = _generation
                _inflight_user_text = full_text

        if kind == "cache_hit":
            log.info(f"Speculation cache hit gen={gen}: {full_text!r} -> {speak_content!r}")
            if speak_content and _on_speak:
                _on_speak(speak_content)
        elif kind == "promoted":
            log.info(f"Speculation promoted gen={gen}: {full_text!r}")
        else:
            log.info(f"Queue final gen={gen}: {full_text!r}")
            _q.put((gen, full_text, True))
        return

    # Partial. If its normalized text matches the speculation already in
    # flight or already cached, this is just STT re-emitting (typically
    # adding/removing trailing punctuation as it firms up its endpoint
    # guess). Skipping invalidation lets the in-flight LLM call stay alive
    # and serves the eventual final from it.
    with _state_lock:
        full_text = (_inflight_user_text + " " + text).strip() if _inflight_user_text else text
        if speculate:
            normalized = _normalize_for_match(full_text)
            active = _active_speculation
            if active is not None and active[0] == _generation and _normalize_for_match(active[1]) == normalized:
                log.info(f"Partial matches active speculation; reusing gen={active[0]}: {full_text!r}")
                return
            cached = _cached_speculation
            if cached is not None and _normalize_for_match(cached[0]) == normalized:
                log.info(f"Partial matches cached speculation; reusing: {full_text!r}")
                return

        # Truly new partial: invalidate any in-flight turn (gen bump makes
        # any running or queued speculation stale and voids any pending
        # promotion). Then, if requested, register and queue a fresh spec.
        _generation += 1
        _cached_speculation = None
        _active_speculation = None
        _speculation_promoted = False
        if not speculate:
            return
        gen = _generation
        # Publish the active marker before we leave the lock so a final
        # racing in immediately after sees us — even if the worker hasn't
        # picked the queued item up yet.
        _active_speculation = (gen, full_text)

    log.info(f"Queue speculation gen={gen}: {full_text!r}")
    _q.put((gen, full_text, False))


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
        gen, text, is_final = _q.get()
        if _is_stale(gen):
            log.info(f"Skipping stale gen={gen}: {text!r}")
            continue
        # The exception handler should surface the "brain glitch" fallback
        # for both real finals and any speculation that got promoted to one.
        treat_as_final = is_final
        try:
            if is_final:
                _handle(gen, text)
            else:
                spec_msg = _handle_speculation(gen, text)
                if spec_msg is not None:
                    # Spec was promoted but its reply wasn't directly
                    # speakable (tool calls / silent cue). Continue the
                    # multi-turn flow from the spec's reply itself — re-asking
                    # the LLM with the same input wastes a call and can land
                    # on a different decision (tool_calls vs no tool_calls).
                    treat_as_final = True
                    _handle(gen, text, initial_msg=spec_msg)
        except Exception as e:
            log.error(f"{e}")
            if treat_as_final and not _is_stale(gen) and _on_speak:
                _on_speak("Ugh. Brain glitch. Try that again.")


def _handle_speculation(gen: int, user_text: str) -> Optional[dict]:
    """Run a single speculative LLM turn.

    Returns the spec's reply `msg` if the caller should continue running it
    via `_handle(gen, user_text, initial_msg=msg)`: the speculation was
    promoted but its reply involved tool calls or a silent cue, so we hand
    the same `msg` off to `_handle` (which executes the tools and continues
    the multi-turn loop) instead of issuing a second redundant LLM call.
    Returns None otherwise (cached, dropped, or already spoken).

    Speculative calls execute zero side effects: tool calls and silent cues
    are never run from this path. They're either ignored (not promoted) or
    handed off to `_handle` for execution (promoted).
    """
    global _cached_speculation, _active_speculation, _speculation_promoted, _inflight_user_text

    # `_active_speculation` and `_speculation_promoted` were set by
    # `on_utterance` (partial set active, an early final may have already set
    # promoted). Don't touch them here — the worker isn't their owner until
    # the final lock below confirms we're still the current spec.
    if _is_stale(gen):
        return None

    error: Optional[BaseException] = None
    msg: dict = {}
    try:
        msg = _call(
            [
                {"role": "system", "content": _SYSTEM},
                *_history,
                {"role": "user", "content": user_text},
            ]
        )
    except Exception as e:
        error = e

    speak_content: Optional[str] = None
    rerun_msg: Optional[dict] = None

    with _state_lock:
        if gen != _generation:
            # A partial slipped in while we were waiting on the LLM. Active
            # and promoted now belong to the newer spec; don't touch them.
            log.info(f"Dropping speculation reply for stale gen={gen}")
            return None

        # We're still current → we own active/promoted and clear them.
        promoted = _speculation_promoted
        _active_speculation = None
        _speculation_promoted = False

        if error is not None:
            log.error(f"Speculation gen={gen} _call failed: {error}")
            if promoted and _on_speak is not None:
                # The user is waiting on this; don't go silent on them.
                speak_content = "Ugh. Brain glitch. Try that again."
        else:
            tool_calls = bool(msg.get("tool_calls"))
            content = (msg.get("content") or "").strip()
            silent = bool(content) and bool(_SILENT_CUE_RE.match(content))
            speakable = (not tool_calls) and bool(content) and (not silent)

            if promoted:
                if speakable:
                    _history.append({"role": "user", "content": user_text})
                    _history.append(msg)
                    del _history[:-_HISTORY_CAP]
                    _inflight_user_text = ""
                    speak_content = content
                else:
                    # Hand the spec's msg off to `_handle` so its tool calls
                    # / silent cue can be executed (and any text content
                    # spoken alongside) without a second LLM call.
                    rerun_msg = msg
            else:
                if speakable:
                    _cached_speculation = (user_text, msg)
                    log.info(f"Cached speculation gen={gen}: {content!r}")
                elif tool_calls:
                    log.info(f"Speculation gen={gen} returned tool calls; not caching")
                elif silent:
                    log.info(f"Speculation gen={gen} returned silent cue; not caching")
                # else: empty content, drop silently

    if speak_content is not None and _on_speak is not None:
        if error is None:
            log.info(f"Speaking promoted speculation gen={gen}: {user_text!r} -> {speak_content!r}")
        _on_speak(speak_content)

    if rerun_msg is not None:
        log.info(f"Speculation gen={gen} promoted; handing spec msg to _handle (no rerun)")
    return rerun_msg


def _handle(gen: int, user_text: str, initial_msg: Optional[dict] = None) -> None:
    """Run one turn for `user_text`. Only commits history / speaks if still current.

    If `initial_msg` is given, the first iteration uses it instead of issuing
    its own LLM call — used by the speculation path to reuse a reply that
    came back with tool calls / a silent cue rather than re-rolling the LLM.
    """
    global _inflight_user_text

    # Build the turn's messages locally; commit to _history only on success so a
    # cancelled turn leaves no trace and the next attempt sees a clean slate.
    turn_msgs: list = [{"role": "user", "content": user_text}]
    pending: Optional[dict] = initial_msg

    for _ in range(_MAX_TURNS):
        if _is_stale(gen):
            log.info(f"Aborting stale turn gen={gen}")
            return

        if pending is not None:
            msg = pending
            pending = None
        else:
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
    set_tool_handler("stay_silent", lambda: (print("stay_silent()"), "ok")[1])

    print("\n=== Plain finals (no speculation) ===")
    for prompt in ["hey what's up", "go forward", "stop", "you suck"]:
        print(f"\n>>> final: {prompt!r}")
        on_utterance(prompt, True)
        time.sleep(6)

    # Mocks the STT pipeline: stt.py emits partials as the user speaks, then
    # ~1s of trailing silence triggers an endpoint and a final. Real-world,
    # the last partial typically lands ~1s before the final, so spec usually
    # finishes in time → cache hit. We exercise both that path and the
    # in-flight promotion path (final arrives before spec finishes), plus a
    # mismatch case where the user's final differs from the partial.
    print("\n=== Speculative partial → final flow (chitchat) ===")
    cases = [
        # (partial text, gap before final in seconds, final text, expected path)
        ("tell me a joke", 6.0, "tell me a joke", "cache hit"),
        ("what's your favourite colour", 0.05, "what's your favourite colour", "in-flight promotion"),
        ("how are you doing today", 0.05, "actually never mind", "mismatch (full re-run)"),
    ]
    for partial, gap, final, expected in cases:
        print(f"\n>>> partial: {partial!r} speculate=True  ({expected})")
        on_utterance(partial, False, speculate=True)
        time.sleep(gap)
        print(f">>> final:   {final!r}")
        on_utterance(final, True)
        time.sleep(10)

    # Tool calls and silent cues are deliberately never executed from the
    # speculative path (they have hardware/display side effects), so these
    # cases exercise the "spec dropped or rerun" branches:
    #   - long gap + same text:  spec returns tool_calls → not cached → final
    #     falls through to a normal _handle that fires the tool.
    #   - short gap + same text: spec promoted mid-flight → rerun=True →
    #     worker re-runs _handle which fires the tool.
    #   - short gap + diff text: spec is stale by the time it returns and
    #     gets dropped; the final runs normally and fires its own tool.
    print("\n=== Speculative partial → final flow (tool calls) ===")
    tool_cases = [
        ("walk forward please", 6.0, "walk forward please", "spec dropped (no cache); final runs tool"),
        ("go forward now", 0.05, "go forward now", "in-flight promotion → rerun fires tool"),
        ("move forward", 0.05, "stop now", "mismatch; final runs different tool"),
    ]
    for partial, gap, final, expected in tool_cases:
        print(f"\n>>> partial: {partial!r} speculate=True  ({expected})")
        on_utterance(partial, False, speculate=True)
        time.sleep(gap)
        print(f">>> final:   {final!r}")
        on_utterance(final, True)
        time.sleep(10)
