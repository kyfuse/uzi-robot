import asyncio
from threading import Lock

import pyaudio
from dotenv import load_dotenv
from fishaudio import AsyncFishAudio

load_dotenv()

UZI_VOICE_ID = "dbfcbb173fb84528ac4ccaf446026277"
client = AsyncFishAudio()


async def simulate_llm_stream(user_message: str):
    """Simulate an LLM stream by yielding tokens as they arrive."""
    for token in user_message.split():
        await asyncio.sleep(0.1)
        print(f"{token} ", end="", flush=True)
        yield f"{token} "


async def llm_token_stream(user_message: str):
    """Replace with your actual LLM call (Ollama, OpenAI, Anthropic, whatever)."""
    async for token in simulate_llm_stream(user_message):
        yield token


async def chunk_for_tts(token_stream, min_chars=40, max_chars=120):
    buffer = ""
    boundaries = ".!?,;"
    async for token in token_stream:
        buffer += token
        hit_boundary = len(buffer) >= min_chars and buffer.rstrip().endswith(tuple(boundaries))
        too_long = len(buffer) >= max_chars
        if hit_boundary or too_long:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


SAMPLE_RATE = 44100  # Fish PCM default — verify in their docs/response if it sounds pitched wrong
BYTES_PER_SAMPLE = 2
PREBUFFER_BYTES = int(SAMPLE_RATE * 0.3) * BYTES_PER_SAMPLE  # 300ms


class AudioPlayer:
    def __init__(self):
        self.buf = bytearray()
        self.lock = Lock()
        self.finished = False
        self.started = False
        self.p = pyaudio.PyAudio()
        self.stream = None

    def _callback(self, in_data, frame_count, time_info, status):
        need = frame_count * BYTES_PER_SAMPLE
        with self.lock:
            if len(self.buf) >= need:
                out = bytes(self.buf[:need])
                del self.buf[:need]
            else:
                out = bytes(self.buf) + b"\x00" * (need - len(self.buf))
                self.buf.clear()
        flag = pyaudio.paComplete if self.finished and not any(out) else pyaudio.paContinue
        return (out, flag)

    def write(self, data: bytes):
        with self.lock:
            self.buf.extend(data)
            ready = len(self.buf) >= PREBUFFER_BYTES
        if ready and not self.started:
            self._start()

    def _start(self):
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=1024,
            stream_callback=self._callback,
        )
        self.stream.start_stream()
        self.started = True

    async def close(self):
        self.finished = True
        if not self.started:  # very short utterance, never hit prebuffer threshold
            self._start()
        while True:
            with self.lock:
                empty = len(self.buf) == 0
            if empty:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)  # let device drain
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()


async def speak(user_message: str):
    tokens = llm_token_stream(user_message)
    chunks = chunk_for_tts(tokens)

    audio_stream = client.tts.stream_websocket(
        chunks,
        reference_id=UZI_VOICE_ID,
        latency="normal",
        format="pcm",
    )

    player = AudioPlayer()
    try:
        async for chunk in audio_stream:
            player.write(chunk)
    finally:
        await player.close()


asyncio.run(
    speak(
        "[excited] Hey! I'm Uzi. Uzi Doorman. [sarcastic] You know, Murder Drone? [snarky]Bite me. [hyped] Whatcha think about this sick as hell railgun?! Sci-fi nonsense that super works! [fast and rambling] Like, three X plus eight X squared equals square root of Y or smth? [conspiratorial] I'm sneaking to the Murder Drone lair tonight to get the last part I need to save the world [quieter, bitter] and earn my dad's respect and stuff, [back to bravado] but mostly the world part."
    )
)
