from dotenv import load_dotenv
from fishaudio import FishAudio
from fishaudio.utils import play

load_dotenv()

UZI_VOICE_ID = "dbfcbb173fb84528ac4ccaf446026277"  # from the voice's URL on fish.audio

client = FishAudio()


def text_chunks():
    yield "Hey! I'm Uzi. "
    yield "[snarky] Bite me. "
    yield "What do you mean we're out of acid?!"
    yield "[excited] Hey! I'm Uzi. Uzi Doorman. [sarcastic] You know, Murder Drone? [snarky]Bite me. [hyped] Whatcha think about this sick as hell railgun?! Sci-fi nonsense that super works! [fast and rambling] Like, three X plus eight X squared equals square root of Y or smth? [conspiratorial] I'm sneaking to the Murder Drone lair tonight to get the last part I need to save the world [quieter, bitter] and earn my dad's respect and stuff, [back to bravado] but mostly the world part."
    yield "[smug] Easy, morons. [frustrated, trailing off] It doesn't work... [shouting, defiant] YET! [angrier] It doesn't work YET! [defensive] Who said it doesn't work? Maybe it does! [laugh] ... [self-aware, ironic] Oh hell yeah, I'm a damaged OC. [angry shout] Fuck you! [taunting, lower] Pussy... [aggressive] bite me!"


audio_stream = client.tts.stream_websocket(
    text_chunks(),
    reference_id=UZI_VOICE_ID,
    latency="balanced",
    speed=1.1,
)
print("Ready...")
play(audio_stream)
