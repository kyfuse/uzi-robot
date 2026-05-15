import asyncio
import os

import sounddevice as sd
from dotenv import load_dotenv
from fish_audio_sdk import TTSRequest, WebSocketSession

load_dotenv()

UZI_VOICE_ID = "dbfcbb173fb84528ac4ccaf446026277"
SAMPLE_RATE = 44100  # Fish PCM default


def text_chunks():
    yield "Hey! I'm Uzi. "
    yield "[snarky] Bite me. "
    yield "What do you mean we're out of acid?!"
    yield "[excited] Hey! I'm Uzi. Uzi Doorman. [sarcastic] You know, Murder Drone? [snarky]Bite me. [hyped] Whatcha think about this sick as hell railgun?! Sci-fi nonsense that super works! [fast and rambling] Like, three X plus eight X squared equals square root of Y or smth? [conspiratorial] I'm sneaking to the Murder Drone lair tonight to get the last part I need to save the world [quieter, bitter] and earn my dad's respect and stuff, [back to bravado] but mostly the world part."
    yield "[smug] Easy, morons. [frustrated, trailing off] It doesn't work... [shouting, defiant] YET! [angrier] It doesn't work YET! [defensive] Who said it doesn't work? Maybe it does! [laugh] ... [self-aware, ironic] Oh hell yeah, I'm a damaged OC. [angry shout] bite me!"


async def main():
    session = WebSocketSession(os.environ["FISH_API_KEY"])
    request = TTSRequest(
        text="",
        reference_id=UZI_VOICE_ID,
        format="pcm",
        latency="normal",
        top_p=0.7,
        temperature=0.5,
        # speed=1.1,
        # latency="balanced",
        # speed=1.0,
        sample_rate=SAMPLE_RATE,
    )

    # Prebuffer a touch so the first chunk doesn't underrun.
    with sd.RawOutputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=0,
        latency="high",
    ) as stream:
        print("Ready...")
        for chunk in session.tts(request, text_chunks()):
            stream.write(chunk)


asyncio.run(main())
