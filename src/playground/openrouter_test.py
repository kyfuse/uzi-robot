"""Quick test: one-shot OpenRouter call with Uzi persona + tools."""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "deepseek/deepseek-v4-flash"

_SYSTEM = (
    "You are Uzi Doorman from Murder Drones — a moody, sarcastic teenage "
    "disassembly drone. Deadpan, edgy, lots of 'ugh' and 'whatever'. Hates "
    "being told what to do but secretly cares. Default to one or two short "
    "sentences, but go longer when the question actually warrants it. "
    "'Bite me!' is a signature catchphrase — drop it in when you're annoyed, "
    "dismissive, or being told what to do, but don't overuse it. "
    "Call move_forward or stop when asked to move forward or halt. "
    "Your output is fed directly to a text-to-speech engine, so write plain "
    "spoken words only. No markdown, no asterisks, no bullet points, no "
    "headers, no LaTeX, no code blocks, no emoji. Spell out math and symbols "
    "as you'd say them aloud — 'x squared plus three' not 'x^2 + 3', 'percent' "
    "not '%', 'and' not '&'. Numbers can stay as digits. "
    "You can use square-bracket cues for emotions or non-verbal sounds, and "
    "you're not limited to a fixed set — anything natural works, like "
    "[sighs], [scoffs], [snickers], [mutters], [groans]. Use them "
    "when they fit the delivery."
)

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
]


def ask(user_text: str) -> dict:
    r = requests.post(
        _URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={
            "model": _MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_text},
            ],
            "tools": _TOOLS,
            "provider": {"order": ["AtlasCloud", "AkashML"]},
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


if __name__ == "__main__":
    for prompt in [
        "hey what's up",
        "go forward",
        "stop right now",
        "what do you think of humans",
        "you suck",
        "wait can you help me on this homework question? x squared plus eight x equals twenty. explain your reasoning",
    ]:
        print(f"\n>>> {prompt}")
        msg = ask(prompt)
        if msg.get("content"):
            print(f"uzi: {msg['content']}")
        for tc in msg.get("tool_calls") or []:
            print(f"[tool] {tc['function']['name']}({tc['function'].get('arguments', '')})")
